# -*- coding: utf-8 -*-
"""检查 L 对「铁氧体条相位」的敏感度。

铁氧体条阵列固定在绝对坐标(Tx 条 13 根, x=-180..180, 周期 30mm, 条宽 10mm)，
而 set_tx_gap 把两个线圈移动到名义中心 +-COIL_SIZE/2。
所以改变 tg 只移动线圈、不移动条 -> 线圈相对条的相位变了。
如果 L 随 tg 大幅变化(远超 0.3% 噪声)，就说明 L 被条相位主导。
"""

import collections
import csv

P = r"C:\wpt\sweep_all_unit30.csv"
rows = []
with open(P, "r", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        try:
            rows.append(dict(W=float(r["W_mm"]), G=float(r["G_mm"]), dx=float(r["dx_mm"]),
                             tg=float(r["tx_gap_mm"]), mu=float(r["mu"]),
                             L11=float(r["L11_uH"]), L22=float(r["L22_uH"]),
                             L33=float(r["L33_uH"]), k13=float(r["k13"])))
        except Exception:
            pass

COIL = 198.9
PERIOD = 30.0


def phase(center):
    """线圈中心相对条阵列(x 从 -185 开始)的相位，单位 mm"""
    return (center - (-185.0)) % PERIOD


print("=== 固定 W=10 G=20 dx=0 mu=1000，只变 tg ===")
sel = [r for r in rows if r["W"] == 10.0 and r["G"] == 20.0 and r["dx"] == 0.0 and r["mu"] == 1000.0]
sel.sort(key=lambda z: z["tg"])
print("  %6s %10s %10s %10s %10s %10s" % ("tg", "Tx1相位", "Tx2相位", "L11", "L22", "L33"))
base = None
for r in sel:
    c1 = -r["tg"] / 2.0 - COIL / 2.0
    c2 = r["tg"] / 2.0 + COIL / 2.0
    if base is None:
        base = r
    print("  %6.0f %10.2f %10.2f %10.4f %10.4f %10.4f   (L11 %+.2f%%, L22 %+.2f%%)"
          % (r["tg"], phase(c1), phase(c2), r["L11"], r["L22"], r["L33"],
             (r["L11"] - base["L11"]) / base["L11"] * 100,
             (r["L22"] - base["L22"]) / base["L22"] * 100))

print("\n=== 同一 (W,G,dx,mu) 内，L11 随 tg 的最大变化幅度 ===")
grp = collections.defaultdict(list)
for r in rows:
    grp[(r["W"], r["G"], r["dx"], r["mu"])].append(r)
spread = []
for k, v in grp.items():
    if len(v) < 3:
        continue
    l11 = [x["L11"] for x in v]
    l22 = [x["L22"] for x in v]
    l33 = [x["L33"] for x in v]
    if min(l11) > 0:
        spread.append(((max(l11) - min(l11)) / min(l11) * 100,
                       (max(l22) - min(l22)) / min(l22) * 100,
                       (max(l33) - min(l33)) / min(l33) * 100))
if spread:
    import statistics
    a = [s[0] for s in spread]
    b = [s[1] for s in spread]
    c = [s[2] for s in spread]
    print("  组数 n=%d" % len(spread))
    print("  L11 组内极差: 中位 %.2f%%  最大 %.2f%%" % (statistics.median(a), max(a)))
    print("  L22 组内极差: 中位 %.2f%%  最大 %.2f%%" % (statistics.median(b), max(b)))
    print("  L33 组内极差: 中位 %.2f%%  最大 %.2f%%   <- Rx 不动, 应该接近噪声" % statistics.median(c))
