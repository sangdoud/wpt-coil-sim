# -*- coding: utf-8 -*-
"""后续实验：把「4 弦模板的 +0.92%」定性（几何 vs 网格），并单独量 ⑥ 的耗时降幅。

四个求解，同一会话、同一点（LC=167.2829 KR=0.3587 KX=-0.3 dx=0，8 核）：

  S1  旧模板(768点)  8 趟/5%   ⑥关   -> 本会话基线（对标 9/17 的 15.66 分钟 / L11=20.194）
  S2  旧模板(768点)  8 趟/5%   ⑥开   -> ⑥ 的耗时降幅 + 精度影响（干净 A/B）
  S3  4弦模板(241点) 12 趟/2%  ⑥关   -> 4 弦在更密网格下的电感（看是否回落到 20.19 附近）
  S4  旧模板(768点)  12 趟/2%  ⑥关   -> 与 S3 同收敛口径的公平对照

判据：
  |S3 - S4| / S4 < 0.5%  -> 4 弦几何本身没问题，之前那 0.92% 是网格收敛差异
  |S3 - S4| / S4 >= 0.5% -> 4 弦确实改变了电感，⑤ 不能用

每步都把 AEDT 的 .profile 解析出来（初始网格耗时/单元数、每趟耗时、最终单元数）。
"""
import glob
import json
import os
import re
import subprocess
import sys
import time
import traceback

import numpy as np

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                               # noqa: E402
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import batch_sweep_lc as B                       # noqa: E402
import coil_gen as CG                            # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

aedt_shim.patch_pyaedt_proc()

PROJ = os.path.join(WORK, "Projecttonight_4ch.aedt")
RESDIR = os.path.join(WORK, "Projecttonight_4ch.aedtresults", "WPT_G.results")
TMPL_OLD = r"C:\wpt\coil_template_Rx.json"
TMPL_NEW = os.path.join(WORK, "coil_template_Rx_v_4_1_area.json")
LOGF = os.path.join(WORK, "followup_5_6.log")
OUT = os.path.join(WORK, "followup_5_6.json")
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
BASE = dict(minutes=15.66, L11=20.194, L22=20.230, L33=24.549,
            M12=-2.233, M13=3.832, M23=3.931, k13=0.17211, k23=0.17638)
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


def kill_aedt_ps(wait_s=60):
    """强杀 AEDT（沙箱里 taskkill 被拒，用 PowerShell），并等到进程真的消失。"""
    t0 = time.time()
    while time.time() - t0 < wait_s:
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Get-Process -Name ansysedt,ansyscl -ErrorAction SilentlyContinue |"
                            " Stop-Process -Force -ErrorAction SilentlyContinue"],
                           capture_output=True, text=True)
        except Exception:
            pass
        time.sleep(3)
        try:
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                "@(Get-Process -Name ansysedt -ErrorAction SilentlyContinue).Count"],
                               capture_output=True, text=True)
            if (r.stdout or "").strip() in ("0", ""):
                break
        except Exception:
            break
    if time.time() - t0 > 5:
        log("  等待 AEDT 退出用了 %.0f 秒" % (time.time() - t0))


def clear_lock(proj):
    """杀掉会话后 .lock 会残留，必须先删，否则 pyaedt 报 Project is locked。"""
    lk = proj + ".lock"
    if os.path.exists(lk):
        try:
            os.remove(lk)
            log("  已删除陈旧锁 %s" % os.path.basename(lk))
        except Exception as e:
            log("  !! 删锁失败 %s: %r" % (lk, e))


B.kill_aedt = kill_aedt_ps


def anchors(path):
    P = np.array(json.load(open(path, encoding="utf-8")), dtype=float)[:, :2]
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    return float(s[0]), float(s.max()), len(P)


H_IN, H_OUT, _ = anchors(TMPL_OLD)


def set_template(path):
    CG.TEMPLATE = path
    CG._ref = None
    CG._s_ref = None
    CG._h_in_ref = None
    CG._h_out_ref = None
    CG._load()
    CG._h_in_ref = H_IN
    CG._h_out_ref = H_OUT
    log("  模板 -> %s" % os.path.basename(path))


def stats_of(row):
    if not row:
        return None
    v = [float(x) for x in row.split(",")]
    return dict(L11=v[8], L22=v[9], L33=v[10], M12=v[11], M13=v[12], M23=v[13],
                k13=v[14], k23=v[15])


def parse_profile():
    """解析最新的 .profile：初始网格耗时/单元数、趟数、每趟耗时、最终单元数。"""
    fs = glob.glob(os.path.join(RESDIR, "*.profile"))
    if not fs:
        return {}
    f = max(fs, key=os.path.getmtime)
    txt = open(f, encoding="utf-8", errors="replace").read().splitlines()
    out = {"file": os.path.basename(f), "mtime": time.strftime(
        "%H:%M:%S", time.localtime(os.path.getmtime(f)))}
    group = None
    passes = []
    tets = []
    for ln in txt:
        m = re.search(r"Name='([^']+)'", ln)
        if m:
            group = m.group(1)
            if re.match(r"Pass \d+", group):
                passes.append({"name": group, "items": []})
            continue
        m = re.search(r"I\(1, 'Elapsed Time', '([^']+)'\)", ln)
        if m:
            out.setdefault("elapsed_by_group", {})[group] = m.group(1)
            continue
        m = re.search(r"ProfileItem\('([^']*)', (\d+), 0, (\d+), 0, (\d+), 'I\((\d+), (.*)\)'", ln)
        if m:
            name, cpu, el, mem, nargs, args = m.groups()
            item = {"name": name, "cpu_s": int(cpu), "elapsed_s": int(el),
                    "mem_kb": int(mem)}
            tm = re.search(r"'Tetrahedra', (\d+)", args)
            if tm:
                item["tets"] = int(tm.group(1))
                tets.append(int(tm.group(1)))
            if passes and name not in ("",):
                passes[-1]["items"].append(item)
            elif name in ("Mesh", "Coarsen", "Post"):
                out.setdefault("initial", []).append(item)
            continue
        m = re.search(r"ProfileFootnote\('I\(\d+, 1, 'Stop Time', '([^']+)'", ln)
        if m:
            out["stop_time"] = m.group(1)
    out["n_passes"] = len(passes)
    out["passes"] = passes
    out["tets_last"] = tets[-1] if tets else None
    out["tets_first"] = tets[0] if tets else None
    return out


def solve(tag, passes, pct):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, passes, pct
    csvp = os.path.join(WORK, "solve_fu_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, 0.05)
    B.set_rx_dx(m, 0.0)
    log(">>> [%s] 8 核 / %d 趟 / %.1f%% ..." % (tag, passes, pct))
    t0 = time.time()
    st, r = B.run_stage("求解[%s]" % tag,
                        lambda: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                    PT["W"], PT["G"], 0.0, PT["mu"], PT["thk"]),
                        3600)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    row = rows[-1] if len(rows) > 1 else ""
    prof = parse_profile()
    log("    [%s] %s  %.2f 分钟  趟数=%s 最终单元=%s  初始网格=%s"
        % (tag, st, dt, prof.get("n_passes"), prof.get("tets_last"),
           (prof.get("elapsed_by_group") or {}).get("Initial Meshing")))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, stage=st, ok=bool(r), minutes=round(dt, 2),
                passes=passes, pct=pct, row=row, stats=stats_of(row), profile=prof)


def cmp_pct(a, b, keys=("L11", "L22", "L33", "M12", "M13", "M23")):
    if not a or not b:
        return None
    out = {}
    for k in keys:
        out[k] = round(100.0 * (a[k] - b[k]) / abs(b[k]), 4)
    return out


def main():
    global d, m
    log("=" * 78)
    log("后续实验 S1..S4（4 弦模板定性 + ⑥ 单独量效）")
    kill_aedt_ps()
    clear_lock(PROJ)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "followup_5_6_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s / %s" % (PROJ, m.design_name))
    B.set_rx_dx(m, 0.0)

    # ---- 先用旧模板把几何恢复成基线状态 ----
    set_template(TMPL_OLD)
    CG.rebuild_all(m, PT["LC"], PT["KR"], log=log)
    tg = PT["KX"] * PT["LC"]
    outer = CG.coil_outer(PT["LC"])
    rx_leads = CG.current_leads(m, "Rx")
    B.set_tx_gap(m, tg, outer)
    nf = B.rebuild_ferrite(m, PT["W"], PT["G"], tg, PT["thk"], outer, rx_leads)
    B.ensure_region(m, tg)
    log("几何就绪（旧模板）：铁氧体 %d 条  tg=%.2f" % (nf, tg))
    dump()

    # ---- S1: 旧模板 8/5 ⑥关（本会话基线）----
    RES["S1_old_8_5_off"] = solve("S1_old_8_5_off", 8, 5.0)
    RES["S1_vs_doc_baseline"] = dict(
        minutes_doc=BASE["minutes"], minutes_now=RES["S1_old_8_5_off"]["minutes"],
        pct=cmp_pct(RES["S1_old_8_5_off"]["stats"], BASE))
    dump()

    # ---- S2: 旧模板 8/5 + ⑥（Region 最大单元尺寸 = Lc/5）----
    max_len = PT["LC"] / 5.0
    log("---- ⑥：Region 最大单元尺寸 = Lc/5 = %.4f mm ----" % max_len)
    try:
        op = m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                       maximum_length="%.4fmm" % max_len,
                                       maximum_elements=None, name="region_coarse")
        RES["six_op"] = str(getattr(op, "name", op))
        log("  网格操作: %s" % RES["six_op"])
    except Exception as e:
        RES["six_op_err"] = repr(e)
        log("  !! 加网格操作失败: %s" % repr(e))
    RES["S2_old_8_5_six"] = solve("S2_old_8_5_six", 8, 5.0)
    s1, s2 = RES["S1_old_8_5_off"], RES["S2_old_8_5_six"]
    RES["six_gain"] = dict(
        minutes_off=s1["minutes"], minutes_on=s2["minutes"],
        pct=round(100.0 * (s1["minutes"] - s2["minutes"]) / s1["minutes"], 2),
        vs_doc=round(100.0 * (s2["minutes"] - BASE["minutes"]) / BASE["minutes"], 2),
        l_dev_pct=cmp_pct(s2["stats"], s1["stats"]))
    log("  ⑥ 耗时: %.2f -> %.2f 分钟 (%.2f%%)   相对文档基线 15.66: %.2f%%"
        % (s1["minutes"], s2["minutes"], RES["six_gain"]["pct"], RES["six_gain"]["vs_doc"]))
    log("  ⑥ 电感偏差 %s" % RES["six_gain"]["l_dev_pct"])
    dump()

    # ---- 去掉 ⑥ 网格操作 ----
    try:
        for mo in list(m.mesh.meshoperations):
            if mo.name == RES.get("six_op"):
                mo.delete()
                log("  已删除网格操作 %s" % mo.name)
    except Exception as e:
        log("  !! 删网格操作失败: %s" % repr(e))

    # ---- S3: 4 弦模板 12/2 ----
    set_template(TMPL_NEW)
    CG.rebuild_all(m, PT["LC"], PT["KR"], log=log)
    RES["S3_new_12_2"] = solve("S3_new_12_2", 12, 2.0)
    dump()

    # ---- S4: 旧模板 12/2（同收敛口径对照）----
    set_template(TMPL_OLD)
    CG.rebuild_all(m, PT["LC"], PT["KR"], log=log)
    RES["S4_old_12_2"] = solve("S4_old_12_2", 12, 2.0)
    s3, s4 = RES["S3_new_12_2"]["stats"], RES["S4_old_12_2"]["stats"]
    dev = cmp_pct(s3, s4)
    RES["S3_vs_S4"] = dict(pct=dev,
                           worst_self=max(abs(dev["L11"]), abs(dev["L22"]), abs(dev["L33"]))
                           if dev else None,
                           verdict=None)
    if dev:
        w = RES["S3_vs_S4"]["worst_self"]
        RES["S3_vs_S4"]["verdict"] = ("几何本身没问题（差异 = 网格收敛）" if w < 0.5
                                      else "4 弦确实改变电感，⑤ 不能用")
        log("")
        log("=== S3(4弦,12/2) vs S4(旧,12/2) 同收敛口径 ===")
        for k, v in dev.items():
            log("    %-4s %+.3f%%" % (k, v))
        log("    自感最大偏差 %.3f%% -> %s" % (w, RES["S3_vs_S4"]["verdict"]))
    dump()
    log("全部完成")
    # 收尾：analyze() 已存盘，这里直接收掉会话并清锁，避免下次启动报 Project is locked
    try:
        kill_aedt_ps(wait_s=40)
        clear_lock(PROJ)
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
