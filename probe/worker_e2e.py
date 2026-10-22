# -*- coding: utf-8 -*-
"""端到端单工况的 worker：在自己那份工程副本上解分到的接收位置（生产配置）。

环境变量：
  WPT_RUN   实例号
  WPT_XS    本实例负责的位置（逗号分隔，mm）
  WPT_LC/KR/KX  工况参数（默认参考点）
  WPT_FLEX/SIX/PREF/RRES  生产网格开关（默认按"最优组合"）
  WPT_SUFFIX  工程副本后缀
只杀自己那个 AEDT 的 PID。
"""
import json
import math
import os
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

RUN = int(os.environ.get("WPT_RUN", "0"))
SUF = os.environ.get("WPT_SUFFIX", "e%d" % RUN)
XS = [float(v) for v in os.environ.get("WPT_XS", "0").split(",") if v.strip()]
LC = float(os.environ.get("WPT_LC", "167.2829"))
KR = float(os.environ.get("WPT_KR", "0.3587"))
KX = float(os.environ.get("WPT_KX", "-0.3"))
W, G, MU, THK = 10.0, 20.0, 1000.0, 10.0
FLEX = os.environ.get("WPT_FLEX", "1") == "1"
SIX = os.environ.get("WPT_SIX", "1") == "1"
PREF = int(os.environ.get("WPT_PREF", "10"))
RRES = os.environ.get("WPT_RRES", "1e-05")
CORES = int(os.environ.get("WPT_CORES", "8"))
PROJ = os.path.join(WORK, "Projecttonight_%s.aedt" % SUF)
LOGF = os.path.join(WORK, "e_run%d.log" % RUN)
OUT = os.path.join(WORK, "e_run%d.json" % RUN)
MY_PID = [None]
RES = {"run": RUN, "xs": XS, "lc": LC, "kr": KR, "kx": KX, "rows": [],
       "flex": FLEX, "six": SIX, "pref": PREF, "rres": RRES}


def log(m=""):
    s = "%s | [e%d] %s" % (time.strftime("%H:%M:%S"), RUN, m)
    try:
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass


def dump():
    json.dump(RES, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def kill_own():
    pid = MY_PID[0]
    if pid:
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Stop-Process -Id %d -Force -ErrorAction SilentlyContinue" % int(pid)],
                           capture_output=True, text=True)
        except Exception:
            pass
    time.sleep(2)


B.kill_aedt = kill_own


def main():
    RES["t0"] = time.time()
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "e_solve_run%d.log" % RUN)
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    MY_PID[0] = d.aedt_process_id
    RES["aedt_pid"] = MY_PID[0]
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s (pid=%s)" % (os.path.basename(PROJ), MY_PID[0]))
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
    S = LC * (2.0 + KX)
    box = {"x": (-(max(S / 2.0, LC / 2.0) + 60.0), max(S / 2.0, LC / 2.0) + 60.0),
           "y": (-134.94, 1.2 * LC / 2.0 + 60.0), "z": (-45.0, 75.0)}
    pad = [box["x"][1] - bb[3], bb[0] - box["x"][0], box["y"][1] - bb[4], bb[1] - box["y"][0],
           box["z"][1] - bb[5], bb[2] - box["z"][0]]
    try:
        m.modeler.delete("Region")
        time.sleep(1)
        if any(v < -1e-6 for v in pad):
            raise RuntimeError("物体超出目标盒 pad=%s" % pad)
        m.modeler.create_region(pad_value=["%.4fmm" % max(0.0, v) for v in pad],
                                pad_type="Absolute Offset")
    except Exception as e:
        log("region err %r" % e)
    log("几何就绪：铁氧体 %d 条，负责 %d 个位置" % (nf, len(XS)))
    # 生产配置
    try:
        if FLEX:
            m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=True)
        if SIX:
            m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                      maximum_length="%.4fmm" % (LC / 5.0),
                                      maximum_elements=None, name="region_coarse")
        s = m.setups[0]
        s.props["RelativeResidual"] = RRES
        s.update()
        log("配置: flex=%s six=%s pref=%d rres=%s" % (FLEX, SIX, PREF, RRES))
    except Exception as e:
        log("配置失败 %r" % e)
    RES["t_geom"] = time.time()

    B.CORES, B.MAX_PASSES, B.PCT_ERROR, B.PCT_REFINEMENT = CORES, 8, 5.0, PREF
    for i, x in enumerate(XS):
        csvp = os.path.join(WORK, "solve_e_s%d_%d.csv" % (RUN, i))
        if os.path.exists(csvp):
            os.remove(csvp)
        B.OUT_CSV = csvp
        B.set_rx_dx(m, x + 0.05)
        B.set_rx_dx(m, x)
        t0 = time.time()
        st, r = B.run_stage("e%d[%d] x=%.3f" % (RUN, i, x),
                            lambda xx=x: B.solve_and_extract(d, m, LC, KR, KX, W, G, xx, MU, THK),
                            3600)
        dt = (time.time() - t0) / 60.0
        rows = [z.strip() for z in open(csvp)] if os.path.exists(csvp) else []
        row = rows[-1] if len(rows) > 1 else ""
        v = row.split(",") if row else []
        ok = len(v) >= 16 and not any(math.isnan(float(z)) for z in v[8:14]) and float(v[8]) > 0
        RES["rows"].append(dict(x=x, stage=st, ok=bool(r) and ok, minutes=round(dt, 2), row=row))
        log("  [%d/%d] x=%+8.3f %s %.2f 分钟 有效=%s  %s"
            % (i + 1, len(XS), x, st, dt, ok, row[:70]))
        dump()
    RES["t_end"] = time.time()
    dump()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        RES["fatal"] = traceback.format_exc()
        log("!! 失败\n" + RES["fatal"])
    finally:
        try:
            dump()
        except Exception:
            pass
        kill_own()
