# -*- coding: utf-8 -*-
"""④ 二分排查用的 worker（副本名/核数可参数化，带结果有效性校验）。

环境变量：WPT_RUN(实例号) WPT_SUFFIX(副本后缀，默认 run%d) WPT_CORES(默认 8) WPT_DX(默认 0)
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
SUF = os.environ.get("WPT_SUFFIX", "run%d" % RUN)
DX = float(os.environ.get("WPT_DX", "0"))
CORES = int(os.environ.get("WPT_CORES", "8"))
FLEX = os.environ.get("WPT_FLEX", "0") == "1"
SIX = os.environ.get("WPT_SIX", "0") == "1"
LC = float(os.environ.get("WPT_LC", "167.2829"))
PROJ = os.path.join(WORK, "Projecttonight_%s.aedt" % SUF)
LOGF = os.path.join(WORK, "b_run%d.log" % RUN)
OUT = os.path.join(WORK, "b_run%d.json" % RUN)
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
MY_PID = [None]
RES = {"run": RUN, "suffix": SUF, "cores": CORES, "dx": DX}


def log(m=""):
    s = "%s | [b%d] %s" % (time.strftime("%H:%M:%S"), RUN, m)
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
    B.LOG_FILE = os.path.join(WORK, "b_solve_run%d.log" % RUN)
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    MY_PID[0] = d.aedt_process_id
    RES["aedt_pid"] = MY_PID[0]
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s (pid=%s, %d 核)" % (os.path.basename(PROJ), MY_PID[0], CORES))
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
    # 生产配置开关：柔性网格 + ⑥ 区域单元上限
    try:
        if FLEX:
            m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=True)
            log("柔性网格 ON")
        if SIX:
            op = m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                           maximum_length="%.4fmm" % (LC / 5.0),
                                           maximum_elements=None, name="region_coarse")
            log("⑥ ON: %s" % getattr(op, "name", op))
    except Exception as e:
        log("网格开关失败: %r" % e)
    RES["flex"] = FLEX
    RES["six"] = SIX
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = CORES, 8, 5.0
    csvp = os.path.join(WORK, "solve_b_run%d.csv" % RUN)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, DX + 0.05)
    B.set_rx_dx(m, DX)
    log(">>> 求解 dx=%.4f %d 核/8 趟/5%%" % (DX, CORES))
    t0 = time.time()
    st, r = B.run_stage("求解b%d" % RUN,
                        lambda: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                    PT["W"], PT["G"], DX, PT["mu"], PT["thk"]),
                        3600)
    RES["solve_minutes"] = round((time.time() - t0) / 60.0, 2)
    RES["stage"] = st
    RES["ok"] = bool(r)
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    RES["row"] = rows[-1] if len(rows) > 1 else ""
    RES["t_end"] = time.time()
    # 有效性
    v = RES["row"].split(",") if RES["row"] else []
    why = "无结果行" if len(v) < 16 else ""
    if not why:
        try:
            L = [float(v[8]), float(v[9]), float(v[10])]
            M = [float(v[11]), float(v[12]), float(v[13])]
            if any(math.isnan(x) for x in L + M):
                why = "含 NaN"
            elif any(x <= 0 for x in L):
                why = "自感<=0"
            elif M[1] == 0 or M[2] == 0:
                why = "互感为 0"
        except Exception as e:
            why = "解析失败 %r" % e
    RES["valid"] = (why == "")
    RES["invalid_reason"] = why
    log("求解完成 %s %.2f 分钟  有效=%s %s  %s"
        % (st, RES["solve_minutes"], RES["valid"], why, RES["row"][:90]))
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
