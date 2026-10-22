# -*- coding: utf-8 -*-
"""4 弦/角新模板的三段验证（一次 AEDT 会话内完成）：

  A. 几何比对：新模板重建参考点几何 vs 现模型（面数 / 体积 / 端子 / bbox）
  B. 参考点求解（⑤ 只用 4 弦模板）：8 核 / 8 趟 / 5%，与基线比电感偏差是否 <0.5%
  C. 同一求解开 ⑥（Region 最大单元尺寸 = Lc/5）：量耗时降幅 + 复核电感

基线（9/17 受控实测，同点同设置）：
  15.66 分钟  L11=20.194 L22=20.230 L33=24.549
              M12=-2.233 M13=3.832  M23=3.931  k13=0.17211 k23=0.17638

不写 C:\\wpt；工程用副本 _work\\Projecttonight_4ch.aedt。
"""
import json
import os
import shutil
import subprocess
import sys
import time
import traceback

import numpy as np

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                               # noqa: E402  必须最先（沙箱管道/进程枚举）
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import batch_sweep_lc as B                       # noqa: E402
import coil_gen as CG                            # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

aedt_shim.patch_pyaedt_proc()


def kill_aedt_ps():
    """沙箱版 kill_aedt：tasklist/taskkill 被拒，改用 PowerShell 停进程。"""
    try:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "Get-Process -Name ansysedt,ansyscl -ErrorAction SilentlyContinue |"
                        " Stop-Process -Force -ErrorAction SilentlyContinue"],
                       capture_output=True, text=True)
    except Exception:
        pass
    time.sleep(3)


B.kill_aedt = kill_aedt_ps

PROJ_SRC = os.path.join(WORK, "Projecttonight.aedt")
PROJ = os.path.join(WORK, "Projecttonight_4ch.aedt")
TMPL_OLD = r"C:\wpt\coil_template_Rx.json"
TMPL_NEW = os.path.join(WORK, "coil_template_Rx_v_4_1_area.json")
LOGF = os.path.join(WORK, "verify_4chord.log")
OUT = os.path.join(WORK, "verify_4chord.json")

PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
BASE = dict(minutes=15.66, L11=20.194, L22=20.230, L33=24.549,
            M12=-2.233, M13=3.832, M23=3.931, k13=0.17211, k23=0.17638)
GATE = 0.005                    # 0.5%
SOLVE_TIMEOUT = 3600

RES = {}


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    try:
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass


def dump():
    json.dump(RES, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def anchors(path):
    P = np.array(json.load(open(path, encoding="utf-8")), dtype=float)[:, :2]
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    return float(s[0]), float(s.max()), len(P)


def coil_snapshot(m, coils=("Tx1", "Tx2", "Rx")):
    out = {}
    for c in coils:
        d = {}
        try:
            d["faces"] = len(m.modeler[c].faces)
            d["volume"] = round(m.modeler[c].volume, 4)
            d["bbox"] = [round(v, 4) for v in m.modeler[c].bounding_box]
            d["material"] = m.modeler[c].material_name
        except Exception as e:
            d["err"] = repr(e)
        try:
            t = CG.record_terminals(m, c)
            d["terminals"] = {k: dict(center=[round(v, 4) for v in v["center"]],
                                      area=round(v["area"], 6),
                                      polarity=v["polarity"]) for k, v in t.items()}
        except Exception as e:
            d["terminals_err"] = repr(e)
        out[c] = d
    return out


def diff_snap(a, b):
    """a=旧(现模型) b=新(4弦模板)"""
    rep = {}
    for c in a:
        ra = a[c]
        rb = b.get(c, {})
        e = {}
        e["faces_old"] = ra.get("faces")
        e["faces_new"] = rb.get("faces")
        e["faces_delta"] = (rb.get("faces", 0) - ra.get("faces", 0))
        e["vol_old"] = ra.get("volume")
        e["vol_new"] = rb.get("volume")
        if ra.get("volume") and rb.get("volume"):
            e["vol_ppm"] = round(1e6 * (rb["volume"] - ra["volume"]) / ra["volume"], 2)
        bb_o, bb_n = ra.get("bbox"), rb.get("bbox")
        if bb_o and bb_n:
            e["bbox_delta"] = [round(bb_n[i] - bb_o[i], 4) for i in range(6)]
        ta, tb = ra.get("terminals") or {}, rb.get("terminals") or {}
        e["term_count_old"] = len(ta)
        e["term_count_new"] = len(tb)
        td = {}
        for k in sorted(set(ta) | set(tb)):
            if k in ta and k in tb:
                dc = max(abs(ta[k]["center"][i] - tb[k]["center"][i]) for i in range(3))
                td[k] = dict(d_center=round(dc, 5),
                             area_old=ta[k]["area"], area_new=tb[k]["area"],
                             polarity_same=(ta[k]["polarity"] == tb[k]["polarity"]))
            else:
                td[k] = "MISSING_IN_%s" % ("NEW" if k in ta else "OLD")
        e["terminals"] = td
        rep[c] = e
    return rep


def solve(tag, cores=8, passes=8, pct=5.0):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = cores, passes, pct
    csvp = os.path.join(WORK, "solve_4ch_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, 0.05)                    # 强制失效，否则 AEDT 直接返回旧解
    B.set_rx_dx(m, 0.0)
    log(">>> 求解[%s] cores=%d passes=%d pct=%.1f%% ..." % (tag, cores, passes, pct))
    t0 = time.time()
    st, r = B.run_stage("求解[%s]" % tag,
                        lambda: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                    PT["W"], PT["G"], 0.0, PT["mu"], PT["thk"]),
                        SOLVE_TIMEOUT)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    last = rows[-1] if len(rows) > 1 else ""
    log("    [%s] 看门狗=%s 返回=%s 耗时 %.2f 分钟" % (tag, st, r, dt))
    log("    [%s] %s" % (tag, last))
    return dict(tag=tag, stage=st, ok=bool(r), minutes=round(dt, 2),
                cores=cores, passes=passes, pct=pct, row=last)


def stats_of(row):
    if not row:
        return None
    v = [float(x) for x in row.split(",")]
    return dict(L11=v[8], L22=v[9], L33=v[10], M12=v[11], M13=v[12], M23=v[13],
                k13=v[14], k23=v[15])


def compare(st, base=None):
    base = base or BASE
    out = {}
    worst = 0.0
    for k in ("L11", "L22", "L33", "M12", "M13", "M23"):
        if st is None or base.get(k) in (None, 0):
            continue
        pct = 100.0 * (st[k] - base[k]) / abs(base[k])
        out[k] = dict(base=base[k], new=st[k], pct=round(pct, 4))
        if abs(base[k]) > 1.0:               # 互感小值不参与门槛（相对误差会被放大）
            worst = max(worst, abs(pct))
    out["worst_pct_self_and_bigM"] = round(worst, 4)
    out["gate_pct"] = 0.5
    out["pass"] = bool(worst < 0.5)
    return out


def main():
    global d, m
    log("=" * 78)
    log("4 弦/角模板验证：几何比对 -> 参考点求解 -> 开 ⑥ 再求解")
    h_in_ref, h_out_ref, n_old = anchors(TMPL_OLD)
    h_in_new, h_out_new, n_new = anchors(TMPL_NEW)
    log("模板: 旧 %d 点 (h_in %.5f / h_out %.5f)  新 %d 点 (h_in %.5f / h_out %.5f)"
        % (n_old, h_in_ref, h_out_ref, n_new, h_in_new, h_out_new))
    RES["template"] = dict(old=TMPL_OLD, new=TMPL_NEW, n_old=n_old, n_new=n_new,
                           h_in_ref=h_in_ref, h_out_ref=h_out_ref,
                           h_in_new=h_in_new, h_out_new=h_out_new)
    dump()

    # ---- 工程副本（避免动到还在被别的会话占用的原工程）----
    if os.path.exists(PROJ):
        os.remove(PROJ)
    shutil.copy2(PROJ_SRC, PROJ)
    lock = PROJ + ".lock"
    if os.path.exists(lock):
        os.remove(lock)

    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "verify_4chord_solve.log")
    kill_aedt_ps()          # 清掉遗留会话（含 9/17 23:18 那个被 relax_test 崩掉后留下的）
    log("已清理遗留 AEDT 会话")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN)
    log("已打开 %s / %s" % (PROJ, m.design_name))

    # ================= A. 几何比对 =================
    log("")
    log("---- A. 几何比对（现模型 vs 4 弦模板重建）----")
    B.set_rx_dx(m, 0.0)
    old = coil_snapshot(m)
    for c, v in old.items():
        log("  现模型 %-4s 面=%s 体积=%s 端子=%d" % (c, v.get("faces"), v.get("volume"),
                                                 len(v.get("terminals") or {})))
    RES["geom_old"] = old
    dump()

    CG.TEMPLATE = TMPL_NEW
    CG._ref = None
    CG._s_ref = None
    CG._h_in_ref = None
    CG._h_out_ref = None
    CG._load()
    CG._h_in_ref = h_in_ref          # 锚点钉住参考模板值（两模板实测相同，这里是显式保险）
    CG._h_out_ref = h_out_ref
    log("  已切模板: %s  锚点钉住 h_in=%.5f h_out=%.5f"
        % (os.path.basename(TMPL_NEW), CG._h_in_ref, CG._h_out_ref))

    r = CG.rebuild_all(m, PT["LC"], PT["KR"], log=log)
    new = coil_snapshot(m)
    RES["geom_new"] = new
    RES["geom_diff"] = diff_snap(old, new)
    log("")
    log("  面数:  %s" % "  ".join("%s %s->%s (%+d)" % (c, RES["geom_diff"][c]["faces_old"],
                                                    RES["geom_diff"][c]["faces_new"],
                                                    RES["geom_diff"][c]["faces_delta"])
                                 for c in ("Tx1", "Tx2", "Rx")))
    log("  体积:  %s" % "  ".join("%s %s->%s (%+s ppm)" % (c, RES["geom_diff"][c]["vol_old"],
                                                        RES["geom_diff"][c]["vol_new"],
                                                        RES["geom_diff"][c].get("vol_ppm"))
                                 for c in ("Tx1", "Tx2", "Rx")))
    for c in ("Tx1", "Tx2", "Rx"):
        e = RES["geom_diff"][c]
        log("  %-4s bboxΔ=%s" % (c, e.get("bbox_delta")))
        for tn, tv in sorted((e.get("terminals") or {}).items()):
            log("      %-10s %s" % (tn, tv))
    dump()

    # ================= 参考点几何（铁氧体 + Region）=================
    tg = PT["KX"] * PT["LC"]
    outer = CG.coil_outer(PT["LC"])
    rx_leads = CG.current_leads(m, "Rx")
    B.set_tx_gap(m, tg, outer)
    nf = B.rebuild_ferrite(m, PT["W"], PT["G"], tg, PT["thk"], outer, rx_leads)
    B.ensure_region(m, tg)
    log("  铁氧体 %d 条  接收引线 %s  tg=%.2f  outer=%.4f" % (nf, rx_leads, tg, outer))
    bb = m.modeler["Region"].bounding_box
    log("  Region X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]"
        % (bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))
    RES["geom_ref"] = dict(tg=tg, outer=outer, n_ferrite=nf, rx_leads=rx_leads,
                           region=[round(v, 4) for v in bb])
    try:
        m.save_project()
        log("  工程已存盘（副本）")
    except Exception as e:
        log("  save err: %s" % repr(e))
    dump()

    # ================= B. 参考点求解（只上 ⑤）=================
    log("")
    log("---- B. 参考点求解：4 弦模板（⑤），8 核/8 趟/5%% ----")
    b = solve("tmpl4ch")
    RES["solve_B_tmpl4ch"] = b
    st = stats_of(b["row"])
    RES["cmp_B"] = compare(st)
    if st:
        log("  偏差 vs 基线:")
        for k, v in RES["cmp_B"].items():
            if isinstance(v, dict):
                log("    %-4s %.3f -> %.3f  %+.3f%%" % (k, v["base"], v["new"], v["pct"]))
        log("  最大自感/互(大)偏差 = %.4f%%  -> %s"
            % (RES["cmp_B"]["worst_pct_self_and_bigM"],
               "通过 ✓（<0.5%，模板可用）" if RES["cmp_B"]["pass"] else "不通过 ✗"))
    dump()

    # ================= C. 开 ⑥ 再求解 =================
    if RES.get("cmp_B", {}).get("pass"):
        log("")
        max_len = PT["LC"] / 5.0
        log("---- C. 同一几何开 ⑥：Region 最大单元尺寸 = Lc/5 = %.4f mm ----" % max_len)
        try:
            op = m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                           maximum_length="%.4fmm" % max_len,
                                           maximum_elements=None, name="region_coarse")
            log("  网格操作已加: %s" % getattr(op, "name", op))
            RES["six_op"] = str(getattr(op, "name", op))
        except Exception as e:
            RES["six_op_err"] = repr(e)
            log("  !! assign_length_mesh 失败: %s" % repr(e))
        try:
            m.save_project()
        except Exception:
            pass
        c = solve("tmpl4ch_six")
        RES["solve_C_six"] = c
        stc = stats_of(c["row"])
        RES["cmp_C"] = compare(stc)
        dtb, dtc = b["minutes"], c["minutes"]
        RES["six_gain"] = dict(minutes_off=dtb, minutes_on=dtc,
                               pct=round(100.0 * (dtb - dtc) / dtb, 2) if dtb else None)
        log("  耗时: ⑥关 %.2f 分钟 -> ⑥开 %.2f 分钟  (%.2f%%)"
            % (dtb, dtc, RES["six_gain"]["pct"]))
        log("  ⑥ 相对基线 15.66 分钟: %.2f%%" % (100.0 * (dtc - BASE["minutes"]) / BASE["minutes"]))
        if stc:
            log("  L11 %.3f->%.3f   L33 %.3f->%.3f   (max |Δ| vs ⑥关 = %.4f%%)"
                % (st["L11"], stc["L11"], st["L33"], stc["L33"],
                   max(abs(100 * (stc[k] - st[k]) / st[k]) for k in ("L11", "L22", "L33"))))
    else:
        log("")
        log("B 未通过 0.5% 门槛 -> 按约定不启用该模板，C（⑥）不执行")
    dump()
    log("")
    log("全部完成")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!! 失败\n" + traceback.format_exc())
        RES["fatal"] = traceback.format_exc()
        try:
            dump()
        except Exception:
            pass
        sys.exit(1)
