# -*- coding: utf-8 -*-
"""深挖：W=14 的异常，以及镜像对称到底成不成立。"""

import csv
import math
import os
from collections import defaultdict

MAIN = r"C:\wpt\sweep_all_unit30.csv"

recs = []
with open(MAIN, newline="", encoding="utf-8") as f:
    r = csv.reader(f)
    hdr = next(r)
    for row in r:
        if len(row) < 13:
            continue
        recs.append(dict(zip(hdr, [float(x) for x in row])))


def sec(t):
    print()
    print("=" * 76)
    print(t)
    print("=" * 76)


# ---------- 1. 每个 W 的 L11 / L22 统计 ----------
sec("1. 按 W 分组的 L11 vs L22（Tx1 / Tx2 自感）")
print("  若线圈对称，同 W 下 L11 与 L22 应当基本相等")
print()
print("  %-6s %12s %12s %12s %12s %10s" % ("W", "L11均值", "L22均值", "L11最大", "L22最大", "L11/L22"))
byW = defaultdict(list)
for r in recs:
    byW[r["W_mm"]].append(r)
for w in sorted(byW):
    rs = byW[w]
    m11 = sum(x["L11_uH"] for x in rs) / len(rs)
    m22 = sum(x["L22_uH"] for x in rs) / len(rs)
    x11 = max(x["L11_uH"] for x in rs)
    x22 = max(x["L22_uH"] for x in rs)
    flag = "   <== 异常" if abs(m11 / m22 - 1) > 0.05 else ""
    print("  %-6.1f %12.2f %12.2f %12.2f %12.2f %10.4f%s"
          % (w, m11, m22, x11, x22, m11 / m22, flag))

# ---------- 2. W=14 的原始行 ----------
sec("2. W=14 的部分原始行（G 必为 16）")
sel = [r for r in recs if r["W_mm"] == 14.0 and r["tx_gap_mm"] == 0.0]
sel.sort(key=lambda x: x["dx_mm"])
print("  %8s %10s %10s %10s %10s %10s %10s" % ("dx", "L11", "L22", "L33", "M12", "M13", "M23"))
for r in sel:
    print("  %8.0f %10.1f %10.1f %10.1f %10.2f %10.2f %10.2f"
          % (r["dx_mm"], r["L11_uH"], r["L22_uH"], r["L33_uH"],
             r["M12_uH"], r["M13_uH"], r["M23_uH"]))

# ---------- 3. 对照：W=15 的同样切片 ----------
sec("3. 对照 W=15（G=15, tg=0）")
sel = [r for r in recs if r["W_mm"] == 15.0 and r["tx_gap_mm"] == 0.0]
sel.sort(key=lambda x: x["dx_mm"])
print("  %8s %10s %10s %10s %10s %10s %10s" % ("dx", "L11", "L22", "L33", "M12", "M13", "M23"))
for r in sel:
    print("  %8.0f %10.1f %10.1f %10.1f %10.2f %10.2f %10.2f"
          % (r["dx_mm"], r["L11_uH"], r["L22_uH"], r["L33_uH"],
             r["M12_uH"], r["M13_uH"], r["M23_uH"]))

# ---------- 4. 关键判定：M12 是否与 dx 无关 ----------
sec("4. M12 是否与 dx 无关（M12 是 Tx1-Tx2 互感，Rx 移动不该影响它）")
print("  若模型对称且 Rx 位置不影响 Tx-Tx 耦合，则同一 (W,tg) 下 M12 应恒定")
print()
g = defaultdict(list)
for r in recs:
    g[(r["W_mm"], r["tx_gap_mm"])].append(r["M12_uH"])
worst = []
for k, v in g.items():
    worst.append((max(v) - min(v), k, min(v), max(v)))
worst.sort(reverse=True)
print("  波动最大的 8 组 (W, tg):")
for spread, k, lo, hi in worst[:8]:
    print("    W=%-5.1f tg=%-6.1f  M12 范围 [%.3f, %.3f]  波动 %.3f" % (k[0], k[1], lo, hi, spread))
same = sum(1 for s, _, _, _ in worst if s < 1e-6)
print()
print("  M12 在同一 (W,tg) 内完全恒定的组数: %d / %d" % (same, len(worst)))

# ---------- 5. 镜像对称：逐项拆开看 ----------
sec("5. 镜像对称逐项检验")
bymap = {}
for r in recs:
    bymap[(r["W_mm"], r["tx_gap_mm"], r["dx_mm"])] = r

tests = {
    "L33(dx)=L33(-dx)": ("L33_uH", "L33_uH"),
    "L11(dx)=L11(-dx)": ("L11_uH", "L11_uH"),
    "L22(dx)=L22(-dx)": ("L22_uH", "L22_uH"),
    "L11(dx)=L22(-dx)": ("L11_uH", "L22_uH"),
    "M13(dx)=M23(-dx)": ("M13_uH", "M23_uH"),
    "M12(dx)=M12(-dx)": ("M12_uH", "M12_uH"),
}
for label, (fa, fb) in tests.items():
    devs = []
    for (w, tg, dx), r in bymap.items():
        if dx <= 0:
            continue
        o = bymap.get((w, tg, -dx))
        if o is None:
            continue
        a, b = r[fa], o[fb]
        den = max(abs(a), abs(b), 1e-9)
        devs.append((abs(a - b) / den * 100.0, w, tg, dx, a, b))
    devs.sort(reverse=True)
    med = devs[len(devs) // 2][0]
    print("  %-20s 中位 %.4f%%   最大 %.3f%%  (最差: W=%.0f tg=%.0f dx=%+.0f  %.1f vs %.1f)"
          % (label, med, devs[0][0], devs[0][1], devs[0][2], devs[0][3], devs[0][4], devs[0][5]))

# ---------- 6. W=14 在所有 tg 下都异常吗 ----------
sec("6. W=14 在 5 个 tx_gap 下的 L11/L22 比值")
print("  %-8s %12s %12s %10s" % ("tg", "L11均值", "L22均值", "L11/L22"))
for tg in sorted({r["tx_gap_mm"] for r in recs}):
    rs = [r for r in recs if r["W_mm"] == 14.0 and r["tx_gap_mm"] == tg]
    m11 = sum(x["L11_uH"] for x in rs) / len(rs)
    m22 = sum(x["L22_uH"] for x in rs) / len(rs)
    print("  %-8.0f %12.2f %12.2f %10.4f" % (tg, m11, m22, m11 / m22))
