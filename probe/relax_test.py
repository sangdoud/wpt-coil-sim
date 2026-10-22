# -*- coding: utf-8 -*-
"""③ 放宽自适应的精度核对。

同一几何、同一位置、同样 8 核，只改自适应设置：
    基准 : MaximumPasses=8, PercentError=5%   （已实测 15.66 分钟 / L11=20.194 L33=24.549 k13=0.17211）
    放宽 : MaximumPasses=4, PercentError=10%
判据：耗时下降多少、电感偏差是否 <1%（>1% 则 ③ 不能用）。
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
LOGF = os.path.join(WORK, "relax_test.log")
OUT = os.path.join(WORK, "relax_test.json")
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
BASE = dict(minutes=15.66, L11=20.194, L22=20.230, L33=24.549,
            M12=-2.233, M13=3.832, M23=3.931, k13=0.17211, k23=0.17638)


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def run(tag, passes, pct):
    B.MAX_PASSES, B.PCT_ERROR, B.CORES = passes, pct, 8
    csvp = os.path.join(WORK, "relax_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, 0.05)          # 强制失效，否则直接返回旧解
    B.set_rx_dx(m, 0.0)
    log(">>> %s: passes=%d pct=%.0f%% ..." % (tag, passes, pct))
    t0 = time.time()
    st, r = B.run_stage(tag, lambda: B.solve_and_extract(
        d, m, PT["LC"], PT["KR"], PT["KX"], PT["W"], PT["G"], 0.0, PT["mu"], PT["thk"]), 3600)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    log("    %s: %s  %.2f 分钟  %s" % (tag, st, dt, rows[-1] if len(rows) > 1 else ""))
    return dict(tag=tag, passes=passes, pct=pct, stage=st, minutes=round(dt, 2),
                row=rows[-1] if len(rows) > 1 else "")


def main():
    global d, m
    log("=" * 70)
    log("③ 放宽自适应精度核对（同几何同位置，8 核）")
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "relax_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN)
    tg = PT["KX"] * PT["LC"]
    B.set_rx_dx(m, 0.0)
    B.CG.rebuild_all(m, PT["LC"], PT["KR"], log=log)
    rx_leads = B.CG.current_leads(m, "Rx")
    B.set_tx_gap(m, tg, B.CG.coil_outer(PT["LC"]))
    nf = B.rebuild_ferrite(m, PT["W"], PT["G"], tg, PT["thk"], B.CG.coil_outer(PT["LC"]), rx_leads)
    B.ensure_region(m, tg)
    log("几何就绪：铁氧体 %d 条" % nf)

    res = [run("relax", 4, 10.0)]
    log("")
    log("=== 对比（基准 passes=8 pct=5%%  %.2f 分钟）===" % BASE["minutes"])
    log("  基准: L11=%.3f L33=%.3f k13=%.5f" % (BASE["L11"], BASE["L33"], BASE["k13"]))
    row = res[0]["row"].split(",") if res[0]["row"] else []
    if len(row) >= 14:
        v = [float(x) for x in row[8:14]]
        log("  放宽: L11=%.3f L33=%.3f k13=%.5f   耗时 %.2f 分钟（−%.0f%%）"
            % (v[0], v[2], v[6], res[0]["minutes"],
               100 * (1 - res[0]["minutes"] / BASE["minutes"])))
        for nm, new, old in (("L11", v[0], BASE["L11"]), ("L22", v[1], BASE["L22"]),
                             ("L33", v[2], BASE["L33"]), ("M13", v[4], BASE["M13"])):
            log("    %-4s %.3f vs %.3f  → %+.2f%%" % (nm, new, old, 100 * (new - old) / old))
        dev = max(abs(v[0] - BASE["L11"]) / BASE["L11"], abs(v[2] - BASE["L33"]) / BASE["L33"])
        log("  最大自感偏差 = %.2f%%  → %s" % (100 * dev,
                                              "可用 ✓" if dev < 0.01 else "!! 超 1%，③ 不能用"))
    json.dump(dict(base=BASE, results=res), open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    log("全部完成")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!! 失败\n" + traceback.format_exc())
        sys.exit(1)
