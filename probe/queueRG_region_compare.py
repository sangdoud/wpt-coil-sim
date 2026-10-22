# -*- coding: utf-8 -*-
"""区域口径对照矩阵：3 个 LC × 2 个区域，全部 BASE 口径（隔离区域这一个变量）。

区域：
  A_prod    生产固定盒 X[-330,330] Y[-134.94,161] Z[-45,75]（文档 4.4 节口径）
  B_legacy  工程遗留小区域 X[-205,205] Y[-134.94,134] Z[-45,75]（此前所有数字的口径）

点位：LC = 120 / 167.2829 / 220，KR 固定 0.3587，KX=-0.3，W=10 G=20 thk=10。

要回答两件事：
  1) 同一 LC 下，两个区域的电感差多少；
  2) L 随 LC 的走势在两个区域下是否一致（文档当年担心"区域跟着物体走会混进假效应"，
     他们举的例子是 LC=180 时 L33 偏低 15%）——若 B 的走势明显失真，就必须用 A。
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
LOGF = os.path.join(WORK, "queueRG.log")
OUT = os.path.join(WORK, "queueRG.json")
KR, KX = 0.3587, -0.3
W, G, MU, THK = 10.0, 20.0, 1000.0, 10.0
LCS = [120.0, 167.2829, 220.0]
_ONLY = os.environ.get("WPT_LCS", "")
if _ONLY:
    LCS = [float(x) for x in _ONLY.split(",")]
REGIONS = {
    "A_prod": {"x": (-330.0, 330.0), "y": (-134.94, 161.0), "z": (-45.0, 75.0)},
    "B_legacy": {"x": (-205.0, 205.0), "y": (-134.94, 134.0), "z": (-45.0, 75.0)},
}
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
    try:
        m.modeler.delete("Region")
    except Exception:
        pass
    time.sleep(1)
    if any(v < -1e-6 for v in pad):
        log("  !! 物体超出目标盒 pad=%s bbox=%s -> 该组合不可用" % (pad, bb))
        return None, pad
    m.modeler.create_region(pad_value=["%.4fmm" % max(0.0, v) for v in pad],
                            pad_type="Absolute Offset")
    rbb = m.modeler["Region"].bounding_box
    log("  Region X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]  pad=%s"
        % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5],
           ["%.1f" % v for v in pad]))
    return rbb, pad


def set_base_config():
    for mo in list(m.mesh.meshoperations):
        try:
            mo.delete()
        except Exception:
            pass
    m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=False)
    s = m.setups[0]
    s.props["PercentRefinement"] = 5
    s.props["RelativeResidual"] = "1e-06"
    s.update()
    B.PCT_REFINEMENT = 5


def solve(tag, LC):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, 8, 5.0
    csvp = os.path.join(WORK, "solve_rg_%s.csv" % tag)
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
    log("    [%s] %s %.2f 分钟  %s" % (tag, st, dt, row))
    return dict(tag=tag, stage=st, ok=bool(r), minutes=round(dt, 2), row=row,
                stats=stats_of(row))


def main():
    global d, m
    log("#" * 78)
    log("区域口径对照矩阵：LC %s × 区域 %s" % (LCS, list(REGIONS)))
    kill_aedt_ps()
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "queueRG_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s" % os.path.basename(PROJ))
    CG.TEMPLATE = r"C:\wpt\coil_template_Rx.json"
    CG._ref = None
    CG._s_ref = None
    CG._load()
    set_base_config()

    for LC in LCS:
        log("")
        log("=" * 70)
        log("LC=%.4f  KR=%.4f KX=%+.2f" % (LC, KR, KX))
        B.set_rx_dx(m, 0.0)
        CG.rebuild_all(m, LC, KR, log=log)
        tg = KX * LC
        outer = CG.coil_outer(LC)
        rx_leads = CG.current_leads(m, "Rx")
        B.set_tx_gap(m, tg, outer)
        nf = B.rebuild_ferrite(m, W, G, tg, THK, outer, rx_leads)
        log("  铁氧体 %d 条 outer=%.2f" % (nf, outer))
        rec = {}
        for rname, box in REGIONS.items():
            log("  -- 区域 %s --" % rname)
            rbb, pad = create_region_to_box(box)
            if rbb is None:
                rec[rname] = dict(error="物体超出目标盒", pad=pad)
                continue
            rec[rname] = solve("LC%.0f_%s" % (LC, rname), LC)
            rec[rname]["region"] = [round(v, 3) for v in rbb]
            dump()
        RES["LC%.0f" % LC] = rec
        if all(rec.get(k, {}).get("stats") for k in REGIONS):
            a, b = rec["A_prod"]["stats"], rec["B_legacy"]["stats"]
            dev = {k: round(100.0 * (b[k] - a[k]) / abs(a[k]), 4) for k in
                   ("L11", "L22", "L33", "M12", "M13", "M23")}
            rec["B_vs_A_pct"] = dev
            log("  B(遗留) 相对 A(生产): %s" % dev)
        dump()

    # 汇总：走势对比
    log("")
    log("=== 区域 × LC 对照汇总 ===")
    log("  LC       区域      耗时      L11      L22      L33      M12      M13      M23")
    for LC in LCS:
        rec = RES.get("LC%.0f" % LC, {})
        for rname in REGIONS:
            r = rec.get(rname, {})
            st = r.get("stats")
            if st:
                log("  %-7.0f  %-9s %6.2f  %7.3f  %7.3f  %7.3f  %7.3f  %7.3f  %7.3f"
                    % (LC, rname, r["minutes"], st["L11"], st["L22"], st["L33"],
                       st["M12"], st["M13"], st["M23"]))
            else:
                log("  %-7.0f  %-9s  %s" % (LC, rname, r.get("error", "无结果")))
        if rec.get("B_vs_A_pct"):
            log("          B_vs_A%%: %s" % rec["B_vs_A_pct"])
    log("")
    log("=== L 随 LC 的走势（判断区域是否扭曲趋势）===")
    for rname in REGIONS:
        vals = []
        for LC in LCS:
            st = RES.get("LC%.0f" % LC, {}).get(rname, {}).get("stats")
            if st:
                vals.append((LC, st["L33"], st["L11"]))
        if len(vals) >= 2:
            log("  %s: " % rname + "  ".join("LC=%.0f L11=%.3f L33=%.3f" % v for v in vals))
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
