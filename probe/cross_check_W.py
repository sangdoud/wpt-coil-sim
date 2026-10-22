# -*- coding: utf-8 -*-
"""独立交叉验证：其他含 W 扫描的文件里，L22 在 W=14->15 是否也跳变。"""

import csv
import os
import re

WPT = r"C:\wpt"


def sec(t):
    print()
    print("=" * 76)
    print(t)
    print("=" * 76)


def load(path):
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        hdr = next(r)
        return hdr, [row for row in r if row]


sec("A. scan_W.csv / scan_B.csv / training_data.csv 的表头与全部内容")

for name in ("scan_W.csv", "scan_B.csv", "training_data.csv"):
    p = os.path.join(WPT, name)
    hdr, rs = load(p)
    print()
    print("--- %s  (%d 行)" % (name, len(rs)))
    print("    表头: %s" % hdr)
    wi = hdr.index("W_mm") if "W_mm" in hdr else None
    li = [hdr.index(c) for c in ("L11_uH", "L22_uH", "L33_uH") if c in hdr]
    if wi is None or len(li) < 3:
        print("    (列名不匹配，跳过)")
        continue
    print("    %-8s %12s %12s %12s" % ("W", "L11", "L22", "L33"))
    prev = None
    for row in rs:
        w = float(row[wi])
        v = [float(row[i]) for i in li]
        d = ""
        if prev is not None and abs(w - prev[0] - 1.0) < 1e-6:
            d = "   ΔL22=%+.1f" % (v[1] - prev[1][1])
        print("    %-8.1f %12.1f %12.1f %12.1f%s" % (w, v[0], v[1], v[2], d))
        prev = (w, v)

sec("B. scan_W.csv 的 L22 随 W 增量（G=15 固定，与 unit30 的 G=30-W 不同）")
hdr, rs = load(os.path.join(WPT, "scan_W.csv"))
wi, i22, i11 = hdr.index("W_mm"), hdr.index("L22_uH"), hdr.index("L11_uH")
rows = sorted(((float(r[wi]), float(r[i11]), float(r[i22])) for r in rs))
print("  %-10s %12s %12s" % ("W->W+1", "ΔL11", "ΔL22"))
for i in range(len(rows) - 1):
    print("  %-10s %12.1f %12.1f" % ("%.0f->%.0f" % (rows[i][0], rows[i + 1][0]),
                                     rows[i + 1][1] - rows[i][1], rows[i + 1][2] - rows[i][2]))

sec("C. 主数据集 vs 其他文件：同 (W,G) 下的 L11/L22 比值对比")
mh, mrs = load(os.path.join(WPT, "sweep_all_unit30.csv"))
mi_w, mi_g, mi_tg = mh.index("W_mm"), mh.index("G_mm"), mh.index("tx_gap_mm")
mi_l = [mh.index(c) for c in ("L11_uH", "L22_uH")]
# 取 unit30 里 tg=0 的每 W 均值
from collections import defaultdict
agg = defaultdict(list)
for r in mrs:
    if abs(float(r[mi_tg])) < 1e-9:
        agg[float(r[mi_w])].append((float(r[mi_l[0]]), float(r[mi_l[1]])))
print("  unit30 (G=30-W, tg=0):")
print("  %-6s %12s %12s %10s" % ("W", "L11", "L22", "L11/L22"))
for w in sorted(agg):
    v = agg[w]
    a = sum(x[0] for x in v) / len(v)
    b = sum(x[1] for x in v) / len(v)
    print("  %-6.1f %12.1f %12.1f %10.4f" % (w, a, b, a / b))

sec("D. 结论判据")
print("  若其他 W 扫描文件在 W=14->15 也出现 L22 大跳 -> 可能是真实的物理/几何效应")
print("  若其他文件没有该跳变 -> unit30 的该处更可能是数据问题")
