# -*- coding: utf-8 -*-
"""兜底配置验证：LC=120/KR=0.50（柔性网格不可用）下，非柔性 + ⑥ + pref10 + rres 是否可用。

对照：
  P120_base（本会话已测）：9.64 分钟 / L11=19.181 L22=19.212 L33=19.216
                            M12=-1.827 M13=3.194 M23=3.216
  P120_best（柔性）：求解 Status='Error'（TAU Flex 在 0.55mm 匝间间隙上修坏 26 个 body）
本脚本跑的就是生产脚本在 gap_min<1.5mm 时实际会走的那条路。
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
LOGF = os.path.join(WORK, "queueFB.log")
OUT = os.path.join(WORK, "queueFB.json")
LC, KR, KX = 120.0, 0.50, -0.3
W, G, MU, THK = 10.0, 20.0, 1000.0, 10.0
P120_BASE = dict(minutes=9.64, L11=19.181, L22=19.212, L33=19.216,
                 M12=-1.827, M13=3.194, M23=3.216)
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
        run_ps("Get-Process -Name ansedt,ansysedt,ansyscl -ErrorAction SilentlyContinue |"
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


def main():
    global d, m
    log("#" * 78)
    log("兜底配置验证：LC=%.0f KR=%.2f（柔性禁用）" % (LC, KR))
    gap = CG.path_dims(LC, KR)["gap_min"]
    log("  gap_min=%.4f  FLEX_MIN_GAP=%.2f  -> 生产脚本会 %s 柔性网格"
        % (gap, B.FLEX_MIN_GAP, "启用" if gap >= B.FLEX_MIN_GAP else "禁用"))
    kill_aedt_ps()
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "queueFB_solve.log")
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
    box = WC.region_box(LC, KX)
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
    pad = [box["x"][1] - bb[3], bb[0] - box["x"][0], box["y"][1] - bb[4], bb[1] - box["y"][0],
           box["z"][1] - bb[5], bb[2] - box["z"][0]]
    m.modeler.delete("Region")
    time.sleep(1)
    m.modeler.create_region(pad_value=["%.4fmm" % max(0.0, v) for v in pad],
                            pad_type="Absolute Offset")
    log("  几何就绪：铁氧体 %d 条" % nf)
    # 兜底配置：非柔性 + ⑥ + pref10 + rres1e-5
    for mo in list(m.mesh.meshoperations):
        mo.delete()
    m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=False)
    m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                              maximum_length="%.4fmm" % (LC / 5.0),
                              maximum_elements=None, name="region_coarse")
    s = m.setups[0]
    s.props["RelativeResidual"] = "1e-05"
    s.update()
    B.PCT_REFINEMENT = 10
    log("  配置: flex=关 ⑥=开 pref=10 rres=1e-5")
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, 8, 5.0
    csvp = os.path.join(WORK, "solve_fb.csv")
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, 0.05)
    B.set_rx_dx(m, 0.0)
    t0 = time.time()
    st, r = B.run_stage("兜底求解",
                        lambda: B.solve_and_extract(d, m, LC, KR, KX, W, G, 0.0, MU, THK), 3600)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    row = rows[-1] if len(rows) > 1 else ""
    stt = stats_of(row)
    prof = profile_now()
    log("  [兜底] %s %.2f 分钟  初始网格=%s 趟数=%s" % (st, dt, prof.get("initial_mesh_elapsed"),
                                                   prof.get("n_passes")))
    log("  [兜底] %s" % row)
    RES["fallback"] = dict(stage=st, ok=bool(r), minutes=round(dt, 2), row=row,
                           stats=stt, profile=prof)
    RES["p120_base"] = P120_BASE
    RES["gap_min"] = gap
    if stt:
        dev = pct(stt, P120_BASE)
        RES["dev"] = dev
        RES["speed_pct"] = round(100.0 * (dt - P120_BASE["minutes"]) / P120_BASE["minutes"], 2)
        log("")
        log("=== 结果 ===")
        log("  耗时: 基线 %.2f -> 兜底 %.2f 分钟 (%+.1f%%)"
            % (P120_BASE["minutes"], dt, RES["speed_pct"]))
        log("  偏差: %s  最坏 %.3f%%" % (dev, max(abs(v) for v in dev.values())))
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
