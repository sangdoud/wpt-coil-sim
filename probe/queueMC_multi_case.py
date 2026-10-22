# -*- coding: utf-8 -*-
"""A：多工况抽查 —— 最优网格配置（柔性+⑥+pref10+rres1e-5）在不同 LC/KR 上是否站得住。

每个工况点做**同会话 A/B**（几何相同，只换网格/求解开关）：
  BASE  滑块5 / flex关 / pref5 / rres1e-6      （= 现行生产口径）
  BEST  flex开 / ⑥ / pref10 / rres1e-5        （= 参考点验出的最优组合）

判据（沿用 0.5% 门槛）：
  - 相对偏差（同工况同会话）：自感/互感各自 <0.5%
  - 相对参考点：确认偏差不随 LC/KR 放大（系统性偏移可接受，随工况漂移不可接受）

工况点：LC=120/KR=0.50、LC=200/KR=0.25，均 KX=-0.3（重叠工况，网格最吃力）。
每个点的 Region 按 ② 规则建（X = max(S/2, Lc/2)+60），并在同一工况内两配置共用。
"""
import json
import os
import re
import subprocess
import sys
import time
import traceback

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                               # noqa: E402
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import batch_sweep_lc as B                       # noqa: E402
import coil_gen as CG                            # noqa: E402
import wpt_contract as WC                        # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

aedt_shim.patch_pyaedt_proc()

PROJ = os.path.join(WORK, "Projecttonight_ref.aedt")
RESDIR = os.path.join(WORK, "Projecttonight_ref.aedtresults", "WPT_G.results")
LOGF = os.path.join(WORK, "queueMC.log")
OUT = os.path.join(WORK, "queueMC.json")
W, G, MU, THK = 10.0, 20.0, 1000.0, 10.0
POINTS = [
    dict(tag="P120", LC=120.0, KR=0.50, KX=-0.3),
    dict(tag="P200", LC=200.0, KR=0.25, KX=-0.3),
]
ONLY = os.environ.get("WPT_ONLY", "")
if ONLY:
    POINTS = [p for p in POINTS if p["tag"] in ONLY.split(",")]
# 参考点已实测：BASE 14.23 min / BEST 4.69 min，供跨工况对比
REF = dict(tag="P165", LC=167.2829, KR=0.3587,
           base_min=14.23, best_min=4.69,
           base=dict(L11=20.418, L22=20.443, L33=24.844, M12=-2.250, M13=3.940, M23=4.028),
           best=dict(L11=20.504, L22=20.542, L33=24.681, M12=-2.246, M13=3.947, M23=4.035))
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


def run_ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                          capture_output=True, text=True)


def kill_aedt_ps(wait_s=60):
    t0 = time.time()
    while time.time() - t0 < wait_s:
        run_ps("Get-Process -Name ansysedt,ansyscl -ErrorAction SilentlyContinue |"
               " Stop-Process -Force -ErrorAction SilentlyContinue")
        time.sleep(3)
        r = run_ps("@(Get-Process -Name ansysedt -ErrorAction SilentlyContinue).Count")
        if (r.stdout or "").strip() in ("0", ""):
            break


B.kill_aedt = kill_aedt_ps


def stats_of(row):
    if not row:
        return None
    v = [float(x) for x in row.split(",")]
    return dict(L11=v[8], L22=v[9], L33=v[10], M12=v[11], M13=v[12], M23=v[13],
                k13=v[14], k23=v[15])


def validity(st):
    if not st:
        return False, "无结果行"
    if any(st[k] <= 0 for k in ("L11", "L22", "L33")):
        return False, "自感<=0"
    if st["M13"] == 0 or st["M23"] == 0:
        return False, "互感为 0"
    if abs(st["k13"]) > 1 or abs(st["k23"]) > 1:
        return False, "|k|>1"
    return True, ""


def pct(a, b, keys=("L11", "L22", "L33", "M12", "M13", "M23")):
    if not a or not b:
        return None
    return {k: round(100.0 * (a[k] - b[k]) / abs(b[k]), 4) for k in keys}


def profile_now():
    fs = [f for f in os.listdir(RESDIR) if f.endswith(".profile")]
    if not fs:
        return {}
    f = max((os.path.join(RESDIR, x) for x in fs), key=os.path.getmtime)
    txt = open(f, encoding="utf-8", errors="replace").read().splitlines()
    out, group, npass = {}, None, 0
    for ln in txt:
        m = re.search(r"Name='([^']+)'", ln)
        if m:
            group = m.group(1)
            if re.match(r"Pass \d+", group):
                npass += 1
            continue
        m = re.search(r"I\(1, 'Elapsed Time', '([^']+)'\)", ln)
        if m and group:
            out.setdefault("elapsed", {})[group] = m.group(1)
    out["n_passes"] = npass
    out["initial_mesh_elapsed"] = (out.get("elapsed") or {}).get("Initial Meshing")
    out["adaptive_elapsed"] = (out.get("elapsed") or {}).get("Adaptive Meshing")
    return out


def objs_bbox():
    bb = None
    for o in m.modeler.object_names:
        if o == "Region":
            continue
        try:
            b = m.modeler[o].bounding_box
        except Exception:
            continue
        bb = list(b) if bb is None else [min(bb[0], b[0]), min(bb[1], b[1]), min(bb[2], b[2]),
                                         max(bb[3], b[3]), max(bb[4], b[4]), max(bb[5], b[5])]
    return bb


def create_region_to_box(box):
    bb = objs_bbox()
    pad = [box["x"][1] - bb[3], bb[0] - box["x"][0],
           box["y"][1] - bb[4], bb[1] - box["y"][0],
           box["z"][1] - bb[5], bb[2] - box["z"][0]]
    if any(v < -1e-6 for v in pad):
        log("  !! 物体超出目标盒 pad=%s bbox=%s" % (pad, bb))
        return None
    try:
        m.modeler.delete("Region")
    except Exception:
        pass
    time.sleep(1)
    m.modeler.create_region(pad_value=["%.4fmm" % max(0.0, v) for v in pad],
                            pad_type="Absolute Offset")
    rbb = m.modeler["Region"].bounding_box
    log("  Region X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]"
        % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5]))
    return rbb


def set_config(cfg):
    """cfg in ('base','best')"""
    clear = []
    for mo in list(m.mesh.meshoperations):
        try:
            mo.delete()
            clear.append(mo.name)
        except Exception:
            pass
    s = m.setups[0]
    if cfg == "base":
        m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=False)
        B.PCT_REFINEMENT = 5
        s.props["RelativeResidual"] = "1e-06"
    else:
        m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=True)
        B.PCT_REFINEMENT = 10
        s.props["RelativeResidual"] = "1e-05"
        LC = RES["_cur_LC"]
        m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                  maximum_length="%.4fmm" % (LC / 5.0),
                                  maximum_elements=None, name="region_coarse")
    s.update()
    log("  配置=%s 清网格操作=%s pref=%d rres=%s"
        % (cfg, clear, B.PCT_REFINEMENT, s.props.get("RelativeResidual")))


def solve(tag, LC, KR, KX):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, 8, 5.0
    csvp = os.path.join(WORK, "solve_mc_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, 0.05)
    B.set_rx_dx(m, 0.0)
    log(">>> [%s] 8 核 / 8 趟 / 5%% ..." % tag)
    t0 = time.time()
    st, r = B.run_stage("求解[%s]" % tag,
                        lambda: B.solve_and_extract(d, m, LC, KR, KX, W, G, 0.0, MU, THK),
                        5400)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    row = rows[-1] if len(rows) > 1 else ""
    stt = stats_of(row)
    ok, why = validity(stt)
    prof = profile_now()
    log("    [%s] %s %.2f 分钟  初始网格=%s 自适应=%s 趟数=%s 有效=%s %s"
        % (tag, st, dt, prof.get("initial_mesh_elapsed"), prof.get("adaptive_elapsed"),
           prof.get("n_passes"), ok, why))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, stage=st, ok=bool(r), minutes=round(dt, 2), row=row,
                stats=stt, valid=ok, invalid_reason=why, profile=prof)


def build_geometry(LC, KR, KX):
    CG.TEMPLATE = r"C:\wpt\coil_template_Rx.json"
    CG._ref = None
    CG._s_ref = None
    CG._load()
    B.set_rx_dx(m, 0.0)
    CG.rebuild_all(m, LC, KR, log=log)
    tg = KX * LC
    outer = CG.coil_outer(LC)
    rx_leads = CG.current_leads(m, "Rx")
    B.set_tx_gap(m, tg, outer)
    nf = B.rebuild_ferrite(m, W, G, tg, THK, outer, rx_leads)
    box = WC.region_box(LC, KX)
    create_region_to_box(box)
    log("  铁氧体 %d 条  tg=%.2f  outer=%.2f  LC=%.1f KR=%.2f" % (nf, tg, outer, LC, KR))


def main():
    global d, m
    log("#" * 78)
    log("A：多工况抽查（BASE vs BEST）")
    kill_aedt_ps()
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "queueMC_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s" % os.path.basename(PROJ))
    RES["ref_point"] = REF
    dump()

    for pt in POINTS:
        tag, LC, KR, KX = pt["tag"], pt["LC"], pt["KR"], pt["KX"]
        RES["_cur_LC"] = LC
        log("")
        log("=" * 70)
        log("%s : LC=%.1f KR=%.2f KX=%+.2f" % (tag, LC, KR, KX))
        build_geometry(LC, KR, KX)
        set_config("base")
        r_base = solve("%s_base" % tag, LC, KR, KX)
        set_config("best")
        r_best = solve("%s_best" % tag, LC, KR, KX)
        rec = dict(tag=tag, LC=LC, KR=KR, KX=KX, base=r_base, best=r_best)
        if r_base["stats"] and r_best["stats"]:
            rec["dev"] = pct(r_best["stats"], r_base["stats"])
            rec["speed_pct"] = round(100.0 * (r_best["minutes"] - r_base["minutes"])
                                     / r_base["minutes"], 2)
            rec["worst"] = max(abs(v) for v in rec["dev"].values())
            log("")
            log("  %s 汇总: BASE %.2f -> BEST %.2f 分钟 (%+.1f%%)  最坏偏差 %.3f%%"
                % (tag, r_base["minutes"], r_best["minutes"], rec["speed_pct"], rec["worst"]))
            log("    逐项: %s" % rec["dev"])
        RES[tag] = rec
        dump()

    # 汇总
    log("")
    log("=== 多工况汇总 ===")
    log("  参考点 P165: BASE %.2f -> BEST %.2f 分钟 (-%.1f%%)  最坏偏差 %.3f%%"
        % (REF["base_min"], REF["best_min"],
           100 * (REF["base_min"] - REF["best_min"]) / REF["base_min"],
           max(abs(100 * (REF["best"][k] - REF["base"][k]) / REF["base"][k])
               for k in REF["base"])))
    for pt in POINTS:
        rec = RES.get(pt["tag"])
        if rec and rec.get("dev"):
            log("  %s LC=%.0f KR=%.2f: BASE %.2f -> BEST %.2f 分钟 (%+.1f%%)  最坏偏差 %.3f%%  %s"
                % (rec["tag"], rec["LC"], rec["KR"], rec["base"]["minutes"],
                   rec["best"]["minutes"], rec["speed_pct"], rec["worst"],
                   "✅ 通过" if rec["worst"] <= 0.5 else "⚠️ 超门槛"))
            log("     逐项 %s" % rec["dev"])
        else:
            log("  %s 结果不完整" % pt["tag"])
    dump()
    log("全部完成")
    try:
        kill_aedt_ps(wait_s=40)
        if os.path.exists(PROJ + ".lock"):
            os.remove(PROJ + ".lock")
    except Exception:
        pass


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
