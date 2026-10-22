# -*- coding: utf-8 -*-
"""定位结果表的分块断点与 W=14/15 的跳变位置。"""

import csv
import os
from collections import Counter, defaultdict

WPT = r"C:\wpt"
MAIN = os.path.join(WPT, "sweep_all_unit30.csv")
PLAN = os.path.join(WPT, "combos_unit30.csv")


def load(path):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        hdr = next(r)
        for i, row in enumerate(r, 2):
            if len(row) >= 13:
                out.append((i, [float(x) for x in row[:13]]))
    return hdr, out


_, main = load(MAIN)
_, plan = load(PLAN)


def sec(t):
    print()
    print("=" * 76)
    print(t)
    print("=" * 76)


# ---------- 1. 列出所有 (W,tg) 块 ----------
sec("1. 结果表所有 (W,tg) 连续块")
blocks = []
prev = None
for idx, (ln, r) in enumerate(main):
    key = (r[0], r[3])
    if prev is None or key != prev:
        blocks.append([idx, idx, key])
        prev = key
    else:
        blocks[-1][1] = idx

print("  总块数: %d   (完整应为 11 W x 5 tg = 55)" % len(blocks))
cnt = Counter(k for _s, _e, k in blocks)
dup = {k: c for k, c in cnt.items() if c > 1}
print("  出现多次的 (W,tg): %d 个 -> %s" % (len(dup), sorted(dup.items())))

print()
print("  所有块（行号）:")
for s, e, k in blocks:
    n = e - s + 1
    flag = "   <== 不足 31 条" if n != 31 else ""
    print("    行%5d..%-5d  %-6d 条   W=%-5.1f tg=%-6.1f%s" % (s + 2, e + 2, n, k[0], k[1], flag))

# ---------- 2. 与参数表逐行对齐找错位区间 ----------
sec("2. 结果表 vs 参数表 逐行错位区间")
mis = []
for i, ((l1, r1), (l2, r2)) in enumerate(zip(main, plan)):
    if r1[:5] != r2[:5]:
        mis.append(i)
if not mis:
    print("  完全对齐")
else:
    # 找连续区间
    runs = []
    for i in mis:
        if runs and i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    print("  错位行数 %d，共 %d 段:" % (len(mis), len(runs)))
    for s, e in runs:
        print()
        print("    --- 段: 结果表行 %d..%d （%d 行） ---" % (s + 2, e + 2, e - s + 1))
        for i in range(max(0, s - 1), min(len(main), s + 2)):
            print("      行%-5d 参数表 %-36s 结果表 %s"
                  % (i + 2, tuple(plan[i][1][:5]), tuple(main[i][1][:5])))
        print("      ...")
        for i in range(max(0, e - 1), min(len(main), e + 2)):
            print("      行%-5d 参数表 %-36s 结果表 %s"
                  % (i + 2, tuple(plan[i][1][:5]), tuple(main[i][1][:5])))

# ---------- 3. W 在结果表里是否严格递增 ----------
sec("3. 结果表里 W 是否单调（分段看）")
seq = [r[0] for _l, r in main]
descents = [(i + 2, seq[i], seq[i + 1]) for i in range(len(seq) - 1) if seq[i + 1] < seq[i]]
print("  W 回退次数: %d" % len(descents))
for ln, a, b in descents:
    print("    行%d: W %.1f -> %.1f" % (ln, a, b))

# ---------- 4. W=14->15 跳变：是否所有 tg 一致 ----------
sec("4. L22 / L33 在 W=14 与 W=15 的对比（分 tg，dx 全范围均值）")
g = defaultdict(list)
for _l, r in main:
    g[(r[0], r[3])].append(r)
print("  %-6s %14s %14s %10s   %14s %14s %10s" %
      ("tg", "L22(W=14)", "L22(W=15)", "跳幅", "L33(W=14)", "L33(W=15)", "跳幅"))
for tg in sorted({r[3] for _l, r in main}):
    a, b = g[(14.0, tg)], g[(15.0, tg)]
    f = lambda v, j: sum(x[j] for x in v) / len(v)
    d22 = f(b, 6) - f(a, 6)
    d33 = f(b, 7) - f(a, 7)
    print("  %-6.0f %14.1f %14.1f %10.1f   %14.1f %14.1f %10.1f"
          % (tg, f(a, 6), f(b, 6), d22, f(a, 7), f(b, 7), d33))

# ---------- 5. 跳变是否也出现在 L11 ----------
sec("5. 对照 L11 / M13 在同一边界上的表现")
print("  %-6s %14s %14s %10s" % ("tg", "L11(W=14)", "L11(W=15)", "跳幅"))
for tg in sorted({r[3] for _l, r in main}):
    a, b = g[(14.0, tg)], g[(15.0, tg)]
    f = lambda v, j: sum(x[j] for x in v) / len(v)
    print("  %-6.0f %14.1f %14.1f %10.1f" % (tg, f(a, 5), f(b, 5), f(b, 5) - f(a, 5)))
