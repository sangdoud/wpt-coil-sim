# -*- coding: utf-8 -*-
"""核实「除以 144」到底能不能替代重算，以及精度/范围问题。"""

import csv
import os

WPT = r"C:\wpt"
PRISTINE = os.path.join(WPT, "backup", "pristine_data", "sweep_all_unit30.csv")
CN1 = os.path.join(WPT, "_test_run", "sweep_all_unit30.csv")
POINT = [10.0, 20.0, -150.0, 0.0, 1000.0]

# 8 核三点测试那次的结果（同一次运行里的 cn=12 基线）
TEST_CN12 = {
    "L11_uH": 3359.179, "L22_uH": 2794.752, "L33_uH": 3452.955,
    "M12_uH": -154.884, "M13_uH": 478.406, "M23_uH": -21.972,
    "k13": 0.14047, "k23": -0.00707,
}


def find_point(path):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        hdr = next(r)
        for row in r:
            if len(row) >= 13 and [float(v) for v in row[:5]] == POINT:
                return hdr, row
    return None, None


h1, pris = find_point(PRISTINE)
h2, cn1 = find_point(CN1)

print("=" * 78)
print("1. 同一次运行内的精确比值（8核三点测试 cn=12  vs  cn=1 实验）")
print("=" * 78)
print("  %-10s %16s %16s %12s" % ("量", "cn=12", "cn=1", "比值"))
worst = 0
for i, name in enumerate(h1[5:13], 5):
    if name not in TEST_CN12:
        continue
    a = TEST_CN12[name]
    b = float(cn1[i])
    ratio = a / b if b else float("nan")
    if name.startswith(("L", "M")):
        worst = max(worst, abs(ratio - 144))
    print("  %-10s %16.4f %16.4f %12.4f" % (name, a, b, ratio))
print()
print("  磁学量比值与 144 的最大偏离: %.4f  (即 %.3f%%)" % (worst, worst / 144 * 100))

print()
print("=" * 78)
print("2. 但 1705 点数据集本身有运行间波动")
print("=" * 78)
print("  %-10s %16s %16s %10s" % ("量", "数据集(pristine)", "三点测试(cn=12)", "差异"))
for i, name in enumerate(h1[5:13], 5):
    if name not in TEST_CN12:
        continue
    a = float(pris[i])
    b = TEST_CN12[name]
    d = abs(a - b) / abs(b) * 100 if b else 0
    print("  %-10s %16.4f %16.4f %9.2f%%" % (name, a, b, d))
print()
print("  -> 同一个点、同一套 cn=12 设置，两次独立运行的差异可达 ~0.3%")
print("     （自适应网格带随机性，之前核数实验也观察到过）")

print()
print("=" * 78)
print("3. 用数据集原值 /144  vs  实测 cn=1，差多少")
print("=" * 78)
print("  %-10s %16s %16s %10s" % ("量", "数据集/144", "实测 cn=1", "相对差"))
for i, name in enumerate(h1[5:13], 5):
    a = float(pris[i]) / 144.0
    b = float(cn1[i])
    d = abs(a - b) / abs(b) * 100 if b else 0
    print("  %-10s %16.6f %16.6f %9.3f%%" % (name, a, b, d))
print()
print("  -> 除法与实测的差 = 数据集自身的运行间波动，不是 144 这个系数不准")

print()
print("=" * 78)
print("4. 舍入精度：小数值除以 144 后再保留几位")
print("=" * 78)
print("  数据集里 M 的最小绝对值（这些是最容易丢精度的）")
vals = []
with open(PRISTINE, newline="", encoding="utf-8") as f:
    r = csv.reader(f)
    next(r)
    for row in r:
        if len(row) >= 13:
            for idx, nm in ((8, "M12"), (9, "M13"), (10, "M23")):
                v = abs(float(row[idx]))
                if v > 0:
                    vals.append((v, nm, row[:5], row[idx]))
vals.sort()
print("  %-6s %14s %14s %10s   %s" % ("量", "原值", "/144", "3位小数误差", "工况"))
for v, nm, cond, raw in vals[:8]:
    q = v / 144
    err = abs(round(q, 3) - q) / q * 100 if q else 0
    print("  %-6s %14s %14.6f %9.3f%%   %s" % (nm, raw, q, err, tuple(cond)))

print()
print("=" * 78)
print("5. 各数据文件的列结构（哪些列要除、哪些不能动）")
print("=" * 78)
for name in sorted(os.listdir(WPT)):
    if not name.endswith(".csv"):
        continue
    p = os.path.join(WPT, name)
    if not os.path.isfile(p):
        continue
    with open(p, newline="", encoding="utf-8") as f:
        hdr = next(csv.reader(f), [])
    mag = [c for c in hdr if c.endswith("_uH") or c in ("L11_uH",)]
    cou = [c for c in hdr if c in ("k13", "k23")]
    print("  %-26s 磁学量列 %-2d 个 | 耦合列 %d 个 | %s" % (name, len(mag), len(cou), hdr))
