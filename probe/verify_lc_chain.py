# -*- coding: utf-8 -*-
"""验证 LC 参数化链路：
  1) 离线跑 gen_plan_csv，确认组合数与列
  2) 在 AEDT 里跑两个点：
       ref   : (LC,KR) = 参考值 -> 应复现当前 2mm 模型的电感
       lc180 : (LC,KR) = (180, 0.30) -> 新参数点，验证链路能算
     其余维度固定 W=10 G=20 dx=-150 tg=0 mu=1000 thk=10（与已知基线同点）
"""
import json
import os
import sys
import time
import traceback

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import batch_sweep_lc as B          # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

PROJ = os.path.join(WORK, "Projecttonight.aedt")
PT = dict(W=10.0, G=20.0, dx=-150.0, tg=0.0, mu=1000.0, thk=10.0)

# 模式：
#   layered : 分层 + KX 验证（默认）
#   nof     : 去铁氧体对照 —— 铁氧体 μr 设成 1（几何/网格不变，只把铁氧体变空气）
ALL_CASES = {
    "layered": [("ref_layered", 167.2829, 0.3587, 0.0),
                ("ovl30", 167.2829, 0.3587, -0.3)],
    "nof": [("nof_ref", 167.2829, 0.3587, 0.0),
            ("nof_lc120", 120.0, 0.50, 0.0),
            ("nof_lc180", 180.0, 0.30, 0.0)],
    # 重叠点 + 0.15mm 层间隙：验证"接触/薄壳"假设（超时放宽到 90 分钟）
    "ovlgap": [("ovl30_gap015", 167.2829, 0.3587, -0.3)],
    # 铁氧体拆分对照（参考几何）：只留一块，看是谁在异常放大 Rx 自感
    "ferrsplit": [("ferr_RxOnly", 167.2829, 0.3587, 0.0),
                  ("ferr_TxOnly", 167.2829, 0.3587, 0.0)],
}
# 按用例名删除某一组铁氧体（删对象，另一组保持 μr=1000）
DELETE_GROUP = {"ferr_RxOnly": "ferrite_Tx_", "ferr_TxOnly": "ferrite_Rx_"}
MODE = sys.argv[1] if (len(sys.argv) > 1 and sys.argv[1] in ALL_CASES) else "layered"
CASES = ALL_CASES[MODE]
MU = 1.0 if MODE == "nof" else PT["mu"]
LOGF = os.path.join(WORK, "verify_lc_chain_%s.log" % MODE)
OUT = os.path.join(WORK, "verify_lc_chain_%s.json" % MODE)


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def main():
    log("=" * 70)
    # ---- 1) 离线：参数表 ----
    B.PLAN_CSV = os.path.join(WORK, "combos_lc_preview.csv")
    n = B.gen_plan_csv()
    log("参数表组合数 = %d" % n)
    with open(B.PLAN_CSV) as f:
        head = f.readline().strip()
        first = f.readline().strip()
    log("表头: %s" % head)
    log("首行: %s" % first)
    log("几何抽查: " + json.dumps(
        {("%.0f/%.1f" % (lc, kr)): B.CG.path_dims(lc, kr)
         for lc in (120.0, 170.0, 220.0) for kr in (0.2, 0.5)}, ensure_ascii=False))

    # ---- 2) 求解 ----
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "verify_lc_solve.log")
    if MODE == "ovlgap":
        B.SOLVE_TIMEOUT = 5400          # 重叠点可能很慢，放宽到 90 分钟
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN)
    log("已打开 %s" % m.design_name)

    res = {}
    for tag, LC, KR, KX in CASES:
        outer = B.CG.coil_outer(LC)
        tg = KX * LC
        log("")
        log("===== [%s] LC=%.4f KR=%.4f KX=%+.2f (tg=%.2fmm) outer=%.2f ====="
            % (tag, LC, KR, KX, tg, outer))
        B.set_rx_dx(m, 0.0)
        B.CG.rebuild_all(m, LC, KR, log=log)
        rx_leads = B.CG.current_leads(m, "Rx")
        log("  接收引线位置 = %s" % rx_leads)
        B.set_tx_gap(m, tg, outer)
        nf = B.rebuild_ferrite(m, PT["W"], PT["G"], tg, PT["thk"], outer, rx_leads)
        B.ensure_region(m, tg)
        pref = DELETE_GROUP.get(tag)
        if pref:
            dels = [o for o in m.modeler.object_names if o.startswith(pref)]
            for o in dels:
                m.modeler.delete(o)
            log("  铁氧体拆分：删掉 %d 个 %s* 对象，保留 %d 个"
                % (len(dels), pref, len([o for o in m.modeler.object_names
                                         if o.startswith("ferrite_")])))
        log("  铁氧体条数 = %d" % nf)
        for o in ("Tx1", "Tx2", "Rx"):
            bb = m.modeler[o].bounding_box
            log("  %-4s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%7.2f,%6.2f]"
                % (o, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))
        B.set_rx_dx(m, PT["dx"])
        csvp = os.path.join(WORK, "solve_%s_%s.csv" % (MODE, tag))
        if os.path.exists(csvp):
            os.remove(csvp)
        B.OUT_CSV = csvp
        t0 = time.time()
        st, r = B.run_stage("求解[%s]" % tag,
                            lambda: B.solve_and_extract(d, m, LC, KR, KX, PT["W"], PT["G"],
                                                        PT["dx"], MU, PT["thk"]),
                            B.SOLVE_TIMEOUT)
        rows = []
        if os.path.exists(csvp):
            rows = [x.strip() for x in open(csvp) if x.strip()]
        res[tag] = {"stage": st, "ok": bool(r), "csv": rows,
                    "minutes": round((time.time() - t0) / 60.0, 2),
                    "LC": LC, "KR": KR, "rx_leads": rx_leads}
        log("  [%s] 看门狗=%s 返回=%s 耗时 %.1f 分钟" % (tag, st, r, res[tag]["minutes"]))
        log("  [%s] %s" % (tag, rows))
        json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("")
    log("全部完成")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!! 失败\n" + traceback.format_exc())
        sys.exit(1)
