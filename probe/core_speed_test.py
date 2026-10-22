# -*- coding: utf-8 -*-
"""核数测速（受控）：同一个几何、同一个点，8/12/16 核各跑 2 次。

几何只建一次，之后只换 analyze(cores=...) 重算 —— 消除几何差异，只剩核数与
自适应网格随机性的影响。结果写 core_speed_test.json / .log。
"""
import json
import os
import sys
import time
import traceback

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")
import batch_sweep_lc as B                       # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

PROJ = os.path.join(WORK, "Projecttonight.aedt")
LOGF = os.path.join(WORK, "core_speed_test.log")
OUT = os.path.join(WORK, "core_speed_test.json")
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
CORES = [8, 12, 16]
REPS = 1
TIMEOUT = 3600


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def main():
    log("=" * 70)
    log("核数测速：点 LC=%.2f KR=%.4f KX=%+.1f  cores=%s x %d 次/档"
        % (PT["LC"], PT["KR"], PT["KX"], CORES, REPS))
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "core_speed_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN)
    log("已打开 %s" % m.design_name)

    # ---- 几何只建一次 ----
    tg = PT["KX"] * PT["LC"]
    B.set_rx_dx(m, 0.0)
    B.CG.rebuild_all(m, PT["LC"], PT["KR"], log=log)
    rx_leads = B.CG.current_leads(m, "Rx")
    B.set_tx_gap(m, tg, B.CG.coil_outer(PT["LC"]))
    nf = B.rebuild_ferrite(m, PT["W"], PT["G"], tg, PT["thk"],
                           B.CG.coil_outer(PT["LC"]), rx_leads)
    B.ensure_region(m, tg)
    B.set_rx_dx(m, tg and 0.0 or 0.0)
    log("几何就绪：铁氧体 %d 条，接收引线 %s" % (nf, rx_leads))

    res = []
    for cores in CORES:
        B.CORES = cores
        for rep in range(1, REPS + 1):
            csvp = os.path.join(WORK, "core_speed_%d_%d.csv" % (cores, rep))
            if os.path.exists(csvp):
                os.remove(csvp)
            B.OUT_CSV = csvp
            # 强制失效：几何微动 0.05mm 再回来。否则 AEDT 认为上一次的解仍然有效，
            # analyze() 直接返回、0.7 分钟"跑完"，拿到的还是旧解（踩过一次）。
            B.set_rx_dx(m, 0.05)
            B.set_rx_dx(m, 0.0)
            log(">>> %d 核  第 %d 次 ..." % (cores, rep))
            t0 = time.time()
            st, r = B.run_stage("核数%d-%d" % (cores, rep),
                                lambda: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                            PT["W"], PT["G"], 0.0,
                                                            PT["mu"], PT["thk"]),
                                TIMEOUT)
            dt = (time.time() - t0) / 60.0
            row = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
            log("    %d 核 第%d次：%s  用时 %.2f 分钟  %s"
                % (cores, rep, st, dt, row[-1] if len(row) > 1 else ""))
            res.append(dict(cores=cores, rep=rep, stage=st, minutes=round(dt, 2),
                            ok=bool(r), csv=row[-1] if len(row) > 1 else ""))
            json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("")
    log("=== 汇总（分钟）===")
    for cores in CORES:
        t = [x["minutes"] for x in res if x["cores"] == cores]
        log("  %2d 核: %s   中位 %.2f  最小 %.2f" % (cores, t,
                                                   sorted(t)[len(t) // 2] if t else 0,
                                                   min(t) if t else 0))
    log("全部完成")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!! 失败\n" + traceback.format_exc())
        sys.exit(1)
