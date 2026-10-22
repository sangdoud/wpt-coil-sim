# -*- coding: utf-8 -*-
"""GPU 能不能提速：实测（参考点，区域 A_prod，生产 OPT 配置）。

原理上的上限（实测 profile）：
  初始网格（TAU 网格器）1m03s~4m52s   <- 纯 CPU，AEDT 无 GPU 通路
  每趟自适应：迭代求解 31~39s + 加密 8~44s + 网格重建   <- 只有迭代求解可能吃 GPU
  最终矩阵求解 14~19s（占 0.2%）
所以即便矩阵求解快 10 倍也只省十几秒；真正能动的是每趟那 30~40 秒的迭代求解。

本脚本跑两次同配置求解：
  G0: analyze(cores=8)              基线
  G1: analyze(cores=8, gpus=1)      指定 1 张 GPU（本机 8 张 RTX 2080 Ti）
并比对 .profile 的 HPC 段里有没有 GPU 条目、耗时差多少。
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
LOGF = os.path.join(WORK, "queueGPU.log")
OUT = os.path.join(WORK, "queueGPU.json")
LC, KR, KX = 167.2829, 0.3587, -0.3
W, G, MU, THK = 10.0, 20.0, 1000.0, 10.0
REG = {"x": (-330.0, 330.0), "y": (-134.94, 161.0), "z": (-45.0, 75.0)}
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
    return dict(L11=v[8], L22=v[9], L33=v[10], M12=v[11], M13=v[12], M23=v[13])


def profile_full():
    fs = [f for f in os.listdir(RESDIR) if f.endswith(".profile")]
    if not fs:
        return {}
    f = max((os.path.join(RESDIR, x) for x in fs), key=os.path.getmtime)
    txt = open(f, encoding="utf-8", errors="replace").read()
    out = {"file": os.path.basename(f)}
    m = re.search(r"Name='HPC'.*?\$end 'ProfileGroup'", txt, re.S)
    out["hpc_block"] = m.group(0)[:900] if m else None
    out["has_gpu_word"] = bool(re.search(r"gpu", txt, re.I))
    out["gpu_lines"] = [l.strip() for l in txt.splitlines() if re.search(r"gpu", l, re.I)][:6]
    m = re.search(r"I\(1, 'Elapsed Time', '([^']+)'\)", txt)
    out["total_elapsed"] = m.group(1) if m else None
    out["n_passes"] = len(re.findall(r"Name='Pass \d+'", txt))
    out["iter_solver_s"] = [int(x) for x in re.findall(r"'Iterative solver', \d+, 0, (\d+)", txt)]
    out["matrix_solve_s"] = [int(x) for x in re.findall(r"'Matrix Solve', \d+, 0, (\d+)", txt)]
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
    try:
        m.modeler.delete("Region")
    except Exception:
        pass
    time.sleep(1)
    m.modeler.create_region(pad_value=["%.4fmm" % max(0.0, v) for v in pad],
                            pad_type="Absolute Offset")
    log("  Region X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]"
        % tuple(m.modeler["Region"].bounding_box[i] for i in (0, 3, 1, 4, 2, 5)))


def solve(tag, gpus=0):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, 8, 5.0
    csvp = os.path.join(WORK, "solve_gpu_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    # 注入 gpus 参数（pyaedt 的 analyze 支持 gpus=）
    orig_analyze = m.analyze

    def analyze_with_gpu(*a, **kw):
        if gpus:
            kw.setdefault("gpus", gpus)
        kw.setdefault("cores", B.CORES)
        kw.setdefault("run_in_thread", True)
        return orig_analyze(*a, **kw)

    m.analyze = analyze_with_gpu
    B.set_rx_dx(m, 0.05)
    B.set_rx_dx(m, 0.0)
    log(">>> [%s] cores=8 gpus=%d ..." % (tag, gpus))
    t0 = time.time()
    try:
        st, r = B.run_stage("求解[%s]" % tag,
                            lambda: B.solve_and_extract(d, m, LC, KR, KX, W, G, 0.0, MU, THK),
                            5400)
    finally:
        try:
            m.analyze = orig_analyze
        except Exception:
            pass
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    row = rows[-1] if len(rows) > 1 else ""
    prof = profile_full()
    log("    [%s] %s %.2f 分钟  趟数=%s  迭代求解=%s  矩阵求解=%s  GPU字样=%s"
        % (tag, st, dt, prof.get("n_passes"), prof.get("iter_solver_s"),
           prof.get("matrix_solve_s"), prof.get("has_gpu_word")))
    if prof.get("gpu_lines"):
        log("    [%s] GPU 相关行: %s" % (tag, prof["gpu_lines"]))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, gpus=gpus, stage=st, ok=bool(r), minutes=round(dt, 2),
                row=row, stats=stats_of(row), profile=prof)


def main():
    global d, m
    log("#" * 78)
    log("GPU 实测：同配置 gpus=0 vs gpus=1（本机 8 张 RTX 2080 Ti）")
    kill_aedt_ps()
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "queueGPU_solve.log")
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
    # 生产 OPT 配置（用模块级常量，避免被脚本内设置覆盖）
    B.FLEX_MESH, B.PCT_REFINEMENT = True, 10
    B.RELATIVE_RESIDUAL, B.REGION_MAX_LEN_DIV = "1e-05", 5.0
    B.OPT_MIN_GAP = -1.0
    for mo in list(m.mesh.meshoperations):
        try:
            mo.delete()
        except Exception:
            pass
    log("  配置 OPT: FLEX=True PREF=10 RRES=1e-05 DIV=5.0")

    RES["G0_cpu"] = solve("G0_cpu", gpus=0)
    dump()
    RES["G1_gpu"] = solve("G1_gpu", gpus=1)
    dump()

    g0, g1 = RES["G0_cpu"], RES["G1_gpu"]
    log("")
    log("=== GPU 实测结果 ===")
    log("  gpus=0: %.2f 分钟   迭代求解 %s   矩阵求解 %s"
        % (g0["minutes"], g0["profile"].get("iter_solver_s"), g0["profile"].get("matrix_solve_s")))
    log("  gpus=1: %.2f 分钟   迭代求解 %s   矩阵求解 %s"
        % (g1["minutes"], g1["profile"].get("iter_solver_s"), g1["profile"].get("matrix_solve_s")))
    log("  耗时差: %+.1f%%   profile 里出现 GPU 字样: %s / %s"
        % (100.0 * (g1["minutes"] - g0["minutes"]) / g0["minutes"],
           g0["profile"].get("has_gpu_word"), g1["profile"].get("has_gpu_word")))
    if g0["stats"] and g1["stats"]:
        dev = {k: round(100.0 * (g1["stats"][k] - g0["stats"][k]) / abs(g0["stats"][k]), 4)
               for k in ("L11", "L22", "L33", "M12", "M13", "M23")}
        RES["dev"] = dev
        log("  电感偏差: %s" % dev)
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
