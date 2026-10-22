# -*- coding: utf-8 -*-
"""④ 多实例并行的 worker：每个进程负责自己那份工程副本，解决自己的点。

环境变量：
  WPT_RUN   实例号 0/1/2
  WPT_DX    接收位置（mm）
关键改造（对应文档第 12 节那 5 项里的前 3 项）：
  1) 路径/工程按实例号参数化（各自 .aedt 副本 + 各自输出文件）
  2) kill 改成**只杀自己那个 AEDT 的 PID**（原 kill_aedt 无差别 taskkill 会互杀）
  3) 不再动全局 ansysedt 进程
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
DX = float(os.environ.get("WPT_DX", "0"))
CORES = int(os.environ.get("WPT_CORES", "8"))
PROJ = os.path.join(WORK, "Projecttonight_run%d.aedt" % RUN)
LOGF = os.path.join(WORK, "p4_run%d.log" % RUN)
OUT = os.path.join(WORK, "p4_run%d.json" % RUN)
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
RES = {"run": RUN, "dx": DX}
MY_PID = [None]


def log(m=""):
    s = "%s | [run%d] %s" % (time.strftime("%H:%M:%S"), RUN, m)
    try:
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass


def dump():
    json.dump(RES, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def kill_own():
    """只杀自己这个实例 —— 多实例并行的关键（原来的无差别 taskkill 会互杀）。"""
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
    RES["t0_str"] = time.strftime("%H:%M:%S")
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "p4_solve_run%d.log" % RUN)
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    MY_PID[0] = d.aedt_process_id
    RES["aedt_pid"] = MY_PID[0]
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s (AEDT pid=%s)" % (os.path.basename(PROJ), MY_PID[0]))
    RES["t_open"] = time.time()
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
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = CORES, 8, 5.0
    csvp = os.path.join(WORK, "solve_p4_run%d.csv" % RUN)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, DX + 0.05)
    B.set_rx_dx(m, DX)
    log(">>> 求解 dx=%.4f %d 核/8 趟/5%%" % (DX, CORES))
    t0 = time.time()
    st, r = B.run_stage("求解run%d" % RUN,
                        lambda: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                    PT["W"], PT["G"], DX, PT["mu"], PT["thk"]),
                        3600)
    RES["cores"] = CORES
    RES["solve_minutes"] = round((time.time() - t0) / 60.0, 2)
    RES["stage"] = st
    RES["ok"] = bool(r)
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    RES["row"] = rows[-1] if len(rows) > 1 else ""
    RES["t_end"] = time.time()
    log("求解完成 %s %.2f 分钟  %s" % (st, RES["solve_minutes"], RES["row"]))
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
