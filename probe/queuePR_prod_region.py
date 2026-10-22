# -*- coding: utf-8 -*-
"""口径对齐：用**生产实际区域**（修好后的 ensure_region -> 固定盒 X±330 / Y161）重测 BASE vs BEST。

背景：此前所有基准点数字（14.23 / 4.69 分钟）都是在工程里遗留的 X±205 / Y134 区域上测的；
而生产 `ensure_region` 的目标盒是 X±330 / Y[-134.94,161]（文档 4.4 节为消除"区域大小假效应"而固定）。
C 阶段用 ② 规则区域（X±202/Y160）时 L33 比遗留区域高约 1.6% —— 说明区域口径必须统一。

本脚本：
  1) 调用修好后的 B.ensure_region()，打印实际建出的区域盒
  2) 在同一区域下跑 BASE（现行口径）与 BEST（整套优化，柔性闸门会自动放行）
  3) 给出耗时与同会话电感偏差
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
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

aedt_shim.patch_pyaedt_proc()

PROJ = os.path.join(WORK, "Projecttonight_ref.aedt")
RESDIR = os.path.join(WORK, "Projecttonight_ref.aedtresults", "WPT_G.results")
LOGF = os.path.join(WORK, "queuePR.log")
OUT = os.path.join(WORK, "queuePR.json")
LC, KR, KX = 167.2829, 0.3587, -0.3
W, G, MU, THK = 10.0, 20.0, 1000.0, 10.0
RES = {}


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    try:
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass


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


def pct(a, b):
    return {k: round(100.0 * (a[k] - b[k]) / abs(b[k]), 4) for k in
            ("L11", "L22", "L33", "M12", "M13", "M23")}


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
    return out


def solve(tag):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, 8, 5.0
    csvp = os.path.join(WORK, "solve_pr_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, 0.05)
    B.set_rx_dx(m, 0.0)
    log(">>> [%s] 8 核 / 8 趟 / 5%% ..." % tag)
    t0 = time.time()
    st, r = B.run_stage("求解[%s]" % tag,
                        lambda: B.solve_and_extract(d, m, LC, KR, KX, W, G, 0.0, MU, THK), 5400)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    row = rows[-1] if len(rows) > 1 else ""
    prof = profile_now()
    log("    [%s] %s %.2f 分钟  初始网格=%s 趟数=%s" % (tag, st, dt,
                                                   prof.get("initial_mesh_elapsed"),
                                                   prof.get("n_passes")))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, stage=st, ok=bool(r), minutes=round(dt, 2), row=row,
                stats=stats_of(row), profile=prof)


def main():
    global d, m
    log("#" * 78)
    log("口径对齐：生产区域（固定盒）下的 BASE vs BEST")
    kill_aedt_ps()
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "queuePR_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s" % os.path.basename(PROJ))
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
    # 生产区域：调用修好后的 ensure_region（目标盒 = REGION_FIXED）
    rbb = B.ensure_region(m, tg)
    try:
        rbb = m.modeler["Region"].bounding_box
    except Exception:
        pass
    if rbb:
        log("  生产区域: X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]"
            % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5]))
    RES["region"] = [round(v, 3) for v in rbb] if rbb else None
    log("  铁氧体 %d 条" % nf)
    # BASE
    for mo in list(m.mesh.meshoperations):
        mo.delete()
    m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=False)
    s = m.setups[0]
    s.props["PercentRefinement"] = 5
    s.props["RelativeResidual"] = "1e-06"
    s.update()
    B.PCT_REFINEMENT = 5
    RES["base"] = solve("base")
    # BEST
    for mo in list(m.mesh.meshoperations):
        mo.delete()
    m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=True)
    m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                              maximum_length="%.4fmm" % (LC / 5.0),
                              maximum_elements=None, name="region_coarse")
    s.props["PercentRefinement"] = 10
    s.props["RelativeResidual"] = "1e-05"
    s.update()
    B.PCT_REFINEMENT = 10
    RES["best"] = solve("best")
    if RES["base"]["stats"] and RES["best"]["stats"]:
        RES["dev"] = pct(RES["best"]["stats"], RES["base"]["stats"])
        RES["speed_pct"] = round(100.0 * (RES["best"]["minutes"] - RES["base"]["minutes"])
                                 / RES["base"]["minutes"], 2)
        log("")
        log("=== 生产区域下的对照 ===")
        log("  BASE %.2f -> BEST %.2f 分钟 (%+.1f%%)  最坏偏差 %.3f%%"
            % (RES["base"]["minutes"], RES["best"]["minutes"], RES["speed_pct"],
               max(abs(v) for v in RES["dev"].values())))
        log("  逐项 %s" % RES["dev"])
        log("  （对比：遗留小区域下 BASE 14.23 -> BEST 4.69 分钟）")
    json.dump(RES, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
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
            json.dump(RES, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except Exception:
            pass
        sys.exit(1)
