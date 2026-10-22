# -*- coding: utf-8 -*-
"""定位最大偏差的格子，判断是舍入还是真错。"""

import csv
import os

WPT = r"C:\wpt"
BK = os.path.join(WPT, "backup", "before_div144")
DIV = 144.0
MAG = {"L11_uH", "L22_uH", "L33_uH", "M12_uH", "M13_uH", "M23_uH"}


def load(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


a = load(os.path.join(BK, "sweep_all_unit30.csv"))
b = load(os.path.join(WPT, "sweep_all_unit30.csv"))
hdr = a[0]
mi = [i for i, c in enumerate(hdr) if c in MAG]

worst = []
for r in range(1, len(a)):
    for i in mi:
        ov = float(a[r][i]); nv = float(b[r][i])
        exp = ov / DIV
        d = abs(nv - exp) / abs(exp) if exp else 0.0
        worst.append((d, r + 1, hdr[i], ov, exp, nv))
worst.sort(reverse=True)

print("=== 偏差最大的 10 格 ===")
print("  %-12s %-6s %-8s %14s %16s %14s %12s %12s" %
      ("相对差", "行", "列", "原值", "期望(精确)", "实际(6位)", "原值绝对精度", "新值绝对精度"))
for d, row, col, ov, exp, nv in worst[:10]:
    print("  %-12.3e %-6d %-8s %14.4f %16.10f %14.6f %12.2e %12.2e"
          % (d, row, col, ov, exp, nv, 0.5e-3, 0.5e-6))

print()
print("=== 判据 ===")
print("  若「实际(6位)」与「期望」的差 <= 0.5e-6（即半个末位），就是纯舍入，不是算错")
bad = 0
for d, row, col, ov, exp, nv in worst:
    if abs(nv - exp) > 0.5e-6 + 1e-12:
        bad += 1
print("  超出半个末位的格子数: %d" % bad)

print()
print("=== 与原数据集自身精度的对比（针对偏差最大的那一格） ===")
d0, row0, col0, ov0, exp0, nv0 = worst[0]
print("  原始值      : %.4f  (3 位小数)  -> 相对精度 %.2e" % (ov0, 0.5e-3 / abs(ov0)))
print("  修正后值    : %.6f  (6 位小数)  -> 相对精度 %.2e" % (nv0, 0.5e-6 / abs(nv0)))
print("  => 修正后的相对精度反而比原始数据更好")

print()
print("=== 全表统计 ===")
mx_orig = 0.0
mx_new = 0.0
for r in range(1, len(a)):
    for i in mi:
        ov = abs(float(a[r][i])); nv = abs(float(b[r][i]))
        if ov: mx_orig = max(mx_orig, 0.5e-3 / ov)
        if nv: mx_new = max(mx_new, 0.5e-6 / nv)
print("  原始数据最差相对精度: %.3e" % mx_orig)
print("  修正后最差相对精度  : %.3e" % mx_new)
print("  修正后是否整体更精确: %s" % ("是" if mx_new <= mx_orig else "否"))
