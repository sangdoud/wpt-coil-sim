# -*- coding: utf-8 -*-
"""修正版：区域 × 配置 的 2×2 对照（在 LC=167.2829 参考点）。

为什么重做：
  生产脚本在 16:20 被打上"提速开关"补丁后，`solve_and_extract` 会在**每次求解时**
  强制套用优化配置（flex+⑥+pref10+rres），覆盖脚本里手工设的 BASE。
  于是此前 queuePR 得到的 "BASE 6.23 -> BEST 5.99" 其实是"优化 vs 优化"的噪声，
  而"区域带来 −56%"也混淆了区域与配置两个变量。

本脚本用**模块级常量覆盖**（solve_and_extract 读的正是这些全局量）来精确控制配置：
    BASE : FLEX_MESH=False, PCT_REFINEMENT=5,  RELATIVE_RESIDUAL="1e-06", REGION_MAX_LEN_DIV=0
    OPT  : FLEX_MESH=True,  PCT_REFINEMENT=10, RELATIVE_RESIDUAL="1e-05", REGION_MAX_LEN_DIV=5.0

只补两格（另两格在补丁前已测、口径干净）：
    A_prod + BASE   <- 本次
    A_prod + OPT    <- 本次（复核 5.90）
已知（补丁前 11:46 / 13:50 测得，口径干净）：
    B_legacy + BASE = 14.23 min
    B_legacy + OPT  = 4.69 min
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
LOGF = os.path.join(WORK, "queueCFG.log")
OUT = os.path.join(WORK, "queueCFG.json")
LC, KR, KX = 167.2829, 0.3587, -0.3
W, G, MU, THK = 10.0, 20.0, 1000.0, 10.0
REG = {"x": (-330.0, 330.0), "y": (-134.94, 161.0), "z": (-45.0, 75.0)}   # A_prod
KNOWN = {
    "B_legacy+BASE": dict(minutes=14.23, L11=20.418, L22=20.443, L33=24.844,
                          M12=-2.250, M13=3.940, M23=4.028),
    "B_legacy+OPT": dict(minutes=4.69, L11=20.504, L22=20.542, L33=24.681,
                         M12=-2.246, M13=3.947, M23=4.035),
}
RES = {"known": KNOWN}


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


def set_cfg(mode):
    """用模块级常量精确设置配置（solve_and_extract 每次求解都会读这些全局量）。"""
    if mode == "BASE":
        B.FLEX_MESH = False
        B.PCT_REFINEMENT = 5
        B.RELATIVE_RESIDUAL = "1e-06"
        B.REGION_MAX_LEN_DIV = 0
        B.OPT_MIN_GAP = -1.0        # 让闸门不参与（BASE 本来就不走优化）
    else:
        B.FLEX_MESH = True
        B.PCT_REFINEMENT = 10
        B.RELATIVE_RESIDUAL = "1e-05"
        B.REGION_MAX_LEN_DIV = 5.0
        B.OPT_MIN_GAP = -1.0        # 强制走优化（参考点 gap=2.56 本来也会放行）
    for mo in list(m.mesh.meshoperations):
        try:
            mo.delete()
        except Exception:
            pass
    log("  配置=%s: FLEX=%s PREF=%s RRES=%s DIV=%s"
        % (mode, B.FLEX_MESH, B.PCT_REFINEMENT, B.RELATIVE_RESIDUAL, B.REGION_MAX_LEN_DIV))


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
    m.modeler.create_region(pad_value=["%.4fmm" % max(0.0, v) for v in pad],
                            pad_type="Absolute Offset")
    rbb = m.modeler["Region"].bounding_box
    log("  Region X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]"
        % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5]))
    return rbb


def solve(tag):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, 8, 5.0
    csvp = os.path.join(WORK, "solve_cfg_%s.csv" % tag)
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
    log("    [%s] %s %.2f 分钟  %s" % (tag, st, dt, row))
    return dict(tag=tag, stage=st, ok=bool(r), minutes=round(dt, 2), row=row,
                stats=stats_of(row))


def main():
    global d, m
    log("#" * 78)
    log("修正版 2x2：区域(A_prod) × 配置(BASE/OPT) @ LC=167.2829")
    kill_aedt_ps()
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "queueCFG_solve.log")
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
    create_region_to_box(REG)
    log("  铁氧体 %d 条" % nf)

    for mode in ("BASE", "OPT"):
        log("")
        log("---- A_prod + %s ----" % mode)
        set_cfg(mode)
        RES["A_prod+%s" % mode] = solve("A_%s" % mode)
        dump()

    # 汇总
    log("")
    log("=== 2×2 汇总（LC=167.2829 参考点）===")
    log("  %-22s %8s %8s %8s %8s %8s %8s %8s" % ("组合", "分钟", "L11", "L22", "L33", "M12", "M13", "M23"))
    grid = {}
    for reg, key in (("A_prod", "A_prod+%s"), ("B_legacy", "B_legacy+%s")):
        for mode in ("BASE", "OPT"):
            k = key % mode
            r = RES.get(k) or KNOWN.get(k)
            if not r or not r.get("stats", r if k in KNOWN else None):
                continue
            st = r.get("stats") or {kk: r[kk] for kk in ("L11", "L22", "L33", "M12", "M13", "M23")}
            grid[k] = (r["minutes"], st)
            log("  %-22s %8.2f %8.3f %8.3f %8.3f %8.3f %8.3f %8.3f"
                % (k, r["minutes"], st["L11"], st["L22"], st["L33"], st["M12"], st["M13"], st["M23"]))
    # 区域效应（同配置）
    for mode in ("BASE", "OPT"):
        a, b = grid.get("A_prod+%s" % mode), grid.get("B_legacy+%s" % mode)
        if a and b:
            dev = {k: round(100.0 * (a[1][k] - b[1][k]) / abs(b[1][k]), 4)
                   for k in ("L11", "L22", "L33", "M12", "M13", "M23")}
            log("  区域效应(%s) A 相对 B: %s   耗时 %.2f -> %.2f" % (mode, dev, b[0], a[0]))
            RES["region_effect_%s" % mode] = dict(dev=dev, minutes_A=a[0], minutes_B=b[0])
    # 配置效应（同区域）
    for reg in ("A_prod", "B_legacy"):
        b_, o_ = grid.get("%s+BASE" % reg), grid.get("%s+OPT" % reg)
        if b_ and o_:
            dev = {k: round(100.0 * (o_[1][k] - b_[1][k]) / abs(b_[1][k]), 4)
                   for k in ("L11", "L22", "L33", "M12", "M13", "M23")}
            log("  配置效应(%s) OPT 相对 BASE: %s   耗时 %.2f -> %.2f (%+.1f%%)"
                % (reg, dev, b_[0], o_[0], 100.0 * (o_[0] - b_[0]) / b_[0]))
            RES["config_effect_%s" % reg] = dict(
                dev=dev, minutes_base=b_[0], minutes_opt=o_[0],
                speed_pct=round(100.0 * (o_[0] - b_[0]) / b_[0], 2))
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
