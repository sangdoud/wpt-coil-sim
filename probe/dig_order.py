# -*- coding: utf-8 -*-
"""深挖 2：文件行序结构 + L22 随 W 的曲线形状。"""

import csv
import os
from collections import defaultdict

WPT = r"C:\wpt"
MAIN = os.path.join(WPT, "sweep_all_unit30.csv")
PLAN = os.path.join(WPT, "combos_unit30.csv")


def load(path):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        hdr = next(r)
        for i, row in enumerate(r, 2):
            if len(row) >= 5:
                out.append((i, [float(x) for x in row[:13]]))
    return hdr, out


hdr, main = load(MAIN)
_, plan = load(PLAN)


def sec(t):
    print()
    print("=" * 76)
    print(t)
    print("=" * 76)


# ---------- 1. 行序 vs 参数表行序 ----------
sec("1. 结果表行序 是否与 参数表行序 一致")
mk = [(r[0], r[1], r[2], r[3], r[4]) for _l, r in main]
pk = [(r[0], r[1], r[2], r[3], r[4]) for _l, r in plan]
first_diff = next((i for i, (a, b) in enumerate(zip(mk, pk)) if a != b), None)
print("  参数表行数 %d, 结果表行数 %d" % (len(pk), len(mk)))
if first_diff is None:
    print("  两表行序完全一致")
else:
    print("  第 %d 行开始不同" % (first_diff + 1))
    for i in range(max(0, first_diff - 2), min(len(pk), first_diff + 4)):
        print("    行%-5d 参数表 %-34s 结果表 %s" % (i + 1, pk[i], mk[i]))

# ---------- 2. 结果表里 W 的块结构 ----------
sec("2. 结果表里 (W, tg) 的分块结构（看是否为多批次追加）")
blocks = []
prev = None
for idx, ((w, g, dx, tg, mu), (ln, _r)) in enumerate(zip(mk, main)):
    if prev is None or (w, tg) != prev:
        blocks.append([idx, idx, (w, tg)])
        prev = (w, tg)
    else:
        blocks[-1][1] = idx
print("  共 %d 个连续块（若按 W 分 11 块 × tg 分 5 = 55 块，则说明是逐 (W,tg) 顺序写入）" % len(blocks))
for s, e, k in blocks[:20]:
    print("    块: W=%-5.1f tg=%-6.1f  行 %d..%d  (%d 条)" % (k[0], k[1], s + 2, e + 2, e - s + 1))
if len(blocks) > 20:
    print("    ... 共 %d 块" % len(blocks))

# ---------- 3. L22 随 W 的曲线（分 tg） ----------
sec("3. L22 随 W 的曲线（按 tg 分开）—— 每格是该 (W,tg) 下 dx 全范围的均值")
tgs = sorted({r[3] for _l, r in main})
Ws = sorted({r[0] for _l, r in main})
print("  %-6s" % "W" + "".join("%12s" % ("tg=%.0f" % t) for t in tgs))
grid = defaultdict(list)
for _l, r in main:
    grid[(r[0], r[3])].append(r)
for w in Ws:
    row = "  %-6.1f" % w
    for t in tgs:
        v = grid[(w, t)]
        row += "%12.1f" % (sum(x[6] for x in v) / len(v))
    print(row)

sec("4. L11 随 W 的曲线（同样口径，用于对照）")
print("  %-6s" % "W" + "".join("%12s" % ("tg=%.0f" % t) for t in tgs))
for w in Ws:
    row = "  %-6.1f" % w
    for t in tgs:
        v = grid[(w, t)]
        row += "%12.1f" % (sum(x[5] for x in v) / len(v))
    print(row)

sec("5. 相邻 W 之间的增量（tg=0 切片，看是否有跳变）")
print("  %-8s %12s %12s %12s %12s" % ("W->W+1", "ΔL11", "ΔL22", "ΔL33", "ΔM13"))
for i in range(len(Ws) - 1):
    a = grid[(Ws[i], 0.0)]
    b = grid[(Ws[i + 1], 0.0)]
    f = lambda v, j: sum(x[j] for x in v) / len(v)
    d11 = f(b, 5) - f(a, 5)
    d22 = f(b, 6) - f(a, 6)
    d33 = f(b, 7) - f(a, 7)
    d13 = f(b, 9) - f(a, 9)
    flag = "   <== 跳变?" if abs(d22) > 100 else ""
    print("  %-8s %12.1f %12.1f %12.1f %12.1f%s"
          % ("%.0f->%.0f" % (Ws[i], Ws[i + 1]), d11, d22, d33, d13, flag))

sec("6. 对照：L11/L22/L33 归一化到 W=10 的倍数（tg=0）")
print("  %-6s %12s %12s %12s" % ("W", "L11/L11(10)", "L22/L22(10)", "L33/L33(10)"))
base = grid[(10.0, 0.0)]
bf = lambda j: sum(x[j] for x in base) / len(base)
for w in Ws:
    v = grid[(w, 0.0)]
    f = lambda j: sum(x[j] for x in v) / len(v)
    print("  %-6.1f %12.4f %12.4f %12.4f" % (w, f(5) / bf(5), f(6) / bf(6), f(7) / bf(7)))
