# -*- coding: utf-8 -*-
"""收尾核对：行序对齐（修正版）+ 末尾追加行 + Lmatrix 系列文件。"""

import csv
import os

WPT = r"C:\wpt"


def sec(t):
    print()
    print("=" * 76)
    print(t)
    print("=" * 76)


def rows(path):
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        hdr = next(r)
        for i, row in enumerate(r, 2):
            out.append((i, row))
    return hdr, out


# ---------- 1. 行序对齐（修正：参数表只有 5 列） ----------
sec("1. 结果表 vs 参数表 行序对齐（修正版）")
mh, main = rows(os.path.join(WPT, "sweep_all_unit30.csv"))
ph, plan = rows(os.path.join(WPT, "combos_unit30.csv"))
print("  结果表 %d 行 x %d 列 | 参数表 %d 行 x %d 列" % (len(main), len(mh), len(plan), len(ph)))

mis = []
for i in range(min(len(main), len(plan))):
    a = [main[i][1][j] for j in range(5)]
    b = [plan[i][1][j] for j in range(5)]
    # 数值比较，容忍 "150" vs "150.0"
    if [float(x) for x in a] != [float(x) for x in b]:
        mis.append(i)

if not mis:
    print("  OK — 两表行序完全一致")
else:
    runs = []
    for i in mis:
        if runs and i == runs[-1][1] + 1:
            runs[-1][1] = i
        else:
            runs.append([i, i])
    print("  错位行数: %d   连续段数: %d" % (len(mis), len(runs)))
    for s, e in runs:
        print()
        print("  --- 错位段: 结果表第 %d..%d 行 ---" % (s + 2, e + 2))
        for i in range(max(0, s - 1), min(len(main), s + 3)):
            print("     行%-5d 参数表 %-36s 结果表 %s"
                  % (i + 2, tuple(plan[i][1][:5]), tuple(main[i][1][:5])))
        print("     ...")
        for i in range(max(0, e - 1), min(len(main), e + 3)):
            print("     行%-5d 参数表 %-36s 结果表 %s"
                  % (i + 2, tuple(plan[i][1][:5]), tuple(main[i][1][:5])))

# ---------- 2. 文件末尾两行 ----------
sec("2. 结果表最后 8 行（末尾是否有多出来的追加行）")
print("  %-6s %-34s %s" % ("行", "工况(W,G,dx,tg,mu)", "L11 / L22 / L33 / M13"))
for ln, row in main[-8:]:
    print("  %-6d %-34s %s / %s / %s / %s"
          % (ln, tuple(row[:5]), row[5], row[6], row[7], row[9]))
print()
print("  参数表最后 8 行:")
for ln, row in plan[-8:]:
    print("  %-6d %s" % (ln, tuple(row[:5])))

# ---------- 3. 确认末尾两行就是缺的那两条 ----------
sec("3. 校验：末尾追加的两行是否补上了 (19,120) 与 (20,30) 缺的那条")
def keys_of(rs):
    return [tuple(float(x) for x in r[:5]) for _l, r in rs]

mk, pk = keys_of(main), keys_of(plan)
print("  参数表组合数 %d, 结果表组合数 %d" % (len(set(pk)), len(set(mk))))
print("  结果表缺: %s" % (sorted(set(pk) - set(mk))[:5] or "无"))
print("  结果表多: %s" % (sorted(set(mk) - set(pk))[:5] or "无"))

# 块内缺失
bymap = {}
for _l, r in main:
    bymap[tuple(float(x) for x in r[:5])] = r
print()
for (W, tg) in ((19.0, 120.0), (20.0, 30.0)):
    have = [k for k in bymap if k[0] == W and k[3] == tg]
    want = [k for k in (tuple(float(x) for x in r[:5]) for _l, r in plan) if k[0] == W and k[3] == tg]
    missing = sorted(set(want) - set(have))
    print("  (W=%.0f, tg=%.0f): 参数表 %d 条, 结果表 %d 条, 缺 %s"
          % (W, tg, len(want), len(have), missing if missing else "无"))

# ---------- 4. Lmatrix 系列小文件 ----------
sec("4. Lmatrix 系列文件（单位与数值）")
for name in ("Lmatrix.csv", "Lmatrix_EC3.csv", "Lmatrix_WPT_EC8.csv",
             "Lmatrix_WPT_G.csv", "Lmatrix_WPT_G_mag.csv"):
    p = os.path.join(WPT, name)
    if not os.path.isfile(p):
        print("  --- %s : 不存在" % name)
        continue
    print("  --- %s" % name)
    with open(p, encoding="utf-8") as f:
        for line in f:
            print("      " + line.rstrip())
    print()
