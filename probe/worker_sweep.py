# -*- coding: utf-8 -*-
"""B2 的 worker：在自己那份工程副本上，把分配到的接收位置逐个解出来。

环境变量：
  WPT_RUN  实例号
  WPT_XS   本实例负责的位置列表（逗号分隔，mm）
  WPT_NX   扫描总点数（仅用于记录）
关键：只杀自己那个 AEDT 的 PID（多实例下无差别 taskkill 会互杀）。
"""
import json
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
XS = [float(v) for v in os.environ.get("WPT_XS", "0").split(",") if v.strip()]
PROJ = os.path.join(WORK, "Projecttonight_s%d.aedt" % RUN)
LOGF = os.path.join(WORK, "b2_run%d.log" % RUN)
OUT = os.path.join(WORK, "b2_run%d.json" % RUN)
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
MY_PID = [None]
RES = {"run": RUN, "xs": XS, "rows": []}


def log(m=""):
    s = "%s | [s%d] %s" % (time.strftime("%H:%M:%S"), RUN, m)
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
    B.LOG_FILE = os.path.join(WORK, "b2_solve_run%d.log" % RUN)
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    MY_PID[0] = d.aedt_process_id
    RES["aedt_pid"] = MY_PID[0]
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s (pid=%s)，负责 %d 个位置" % (os.path.basename(PROJ), MY_PID[0], len(XS)))
    CG.TEMPLATE = r"C:\wpt\coil_template_Rx.json"
    CG._ref = None
    CG._s_ref = None
    CG._load()
    B.set_rx_dx(m, 0.0)
    CG.rebuild_all(m, PT["LC"], PT["KR"], log=log)
    tg = PT["KX"] * PT["LC"]
    outer = CG.coil_outer(PT["LC"])
    rx_leads = CG.current_leads(m, "Rx")
    B.set_tx_gap(m, tg, outer)
    nf = B.rebuild_ferrite(m, PT["W"], PT["G"], tg, PT["thk"], outer, rx_leads)
    try:
        m.modeler.delete("Region")
        time.sleep(1)
        m.modeler.create_region(pad_value=["50.0mm", "50.0mm", "50.0mm", "0mm", "0mm", "5.0mm"],
                                pad_type="Absolute Offset")
    except Exception as e:
        log("region err %r" % e)
    log("几何就绪：铁氧体 %d 条" % nf)
    RES["t_geom"] = time.time()

    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, 8, 5.0
    for i, x in enumerate(XS):
        csvp = os.path.join(WORK, "solve_b2_s%d_%d.csv" % (RUN, i))
        if os.path.exists(csvp):
            os.remove(csvp)
        B.OUT_CSV = csvp
        B.set_rx_dx(m, x + 0.05)
        B.set_rx_dx(m, x)
        t0 = time.time()
        st, r = B.run_stage("s%d[%d] x=%.3f" % (RUN, i, x),
                            lambda xx=x: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                             PT["W"], PT["G"], xx,
                                                             PT["mu"], PT["thk"]),
                            3600)
        dt = (time.time() - t0) / 60.0
        rows = [z.strip() for z in open(csvp)] if os.path.exists(csvp) else []
        row = rows[-1] if len(rows) > 1 else ""
        RES["rows"].append(dict(x=x, stage=st, ok=bool(r), minutes=round(dt, 2), row=row))
        log("  [%d/%d] x=%+8.3f  %s  %.2f 分钟  %s" % (i + 1, len(XS), x, st, dt, row[:80]))
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
