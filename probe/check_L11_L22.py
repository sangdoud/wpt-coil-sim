# -*- coding: utf-8 -*-
"""用已有 1705 点数据集检查：L11-L22 的差是不是由 Rx 的位置(dx)造成的。

数据集里的 L/M 已经除过 144（比值不受影响）。
若 dx=0（Rx 在中间，离两个 Tx 一样远）时 L11≈L22，
而 dx 很大（Rx 偏向某一侧）时 |L11-L22| 变大，就说明差值来自 Rx。
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
                             L33=float(r["L33_uH"])))
        except Exception:
            pass

print("读到 %d 行" % len(rows))

# 1) 把所有行的比值按 (tg) 汇总
print("\n=== (L11-L22)/L22  vs  dx  (只用 tg=0 的行) ===")
by_dx = collections.defaultdict(list)
for r in rows:
    if r["tg"] == 0.0 and r["L22"] > 0:
        by_dx[r["dx"]].append((r["L11"] - r["L22"]) / r["L22"] * 100.0)
for dx in sorted(by_dx):
    v = by_dx[dx]
    print("  dx=%7.1f  n=%3d  (L11-L22)/L22 = %+6.2f%%  (min %+6.2f, max %+6.2f)"
          % (dx, len(v), sum(v) / len(v), min(v), max(v)))

# 2) 固定 W/G/mu，只看 dx 的影响
print("\n=== 固定 W=10 G=20 mu=1000 tg=0，扫 dx ===")
sel = [r for r in rows if r["W"] == 10.0 and r["G"] == 20.0 and r["mu"] == 1000.0 and r["tg"] == 0.0]
for r in sorted(sel, key=lambda z: z["dx"]):
    print("  dx=%7.1f  L11=%8.4f L22=%8.4f  (L11-L22)/L22=%+6.2f%%"
          % (r["dx"], r["L11"], r["L22"], (r["L11"] - r["L22"]) / r["L22"] * 100.0))

# 3) 汇总：dx=0 vs |dx|>0
z0 = [r for r in rows if r["dx"] == 0.0 and r["L22"] > 0]
zn = [r for r in rows if r["dx"] != 0.0 and r["L22"] > 0]
for tag, s in (("dx=0   ", z0), ("|dx|>0 ", zn)):
    if s:
        d = [(r["L11"] - r["L22"]) / r["L22"] * 100.0 for r in s]
        print("\n%s n=%4d  (L11-L22)/L22 平均 %+6.2f%%  范围 [%+6.2f, %+6.2f]"
              % (tag, len(s), sum(d) / len(d), min(d), max(d)))
