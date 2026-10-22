# -*- coding: utf-8 -*-
"""线圈数据自检：物理约束 / 一致性 / 完整性 / 异常值。"""

import csv
import math
import os
from collections import Counter, defaultdict

WPT = r"C:\wpt"
MAIN = os.path.join(WPT, "sweep_all_unit30.csv")
PLAN = os.path.join(WPT, "combos_unit30.csv")

FIELDS = ["L11_uH", "L22_uH", "L33_uH", "M12_uH", "M13_uH", "M23_uH", "k13", "k23"]
CONSTRAINT = ["W_mm", "G_mm", "dx_mm", "tx_gap_mm", "mu"]


def load(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r)
        for i, row in enumerate(r, 2):
            if not row or all(c.strip() == "" for c in row):
                continue
            rows.append((i, row))
    return header, rows


def num(s):
    try:
        return float(s)
    except Exception:
        return None


def section(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


# ============================================================ 主数据集
hdr, raw = load(MAIN)
print("主数据集:", MAIN)
print("表头:", hdr)
print("数据行数:", len(raw))

problems = []
notes = []

# ---------- 1. 解析 / NaN / 非数值 ----------
bad_num = []
recs = []
for lineno, row in raw:
    if len(row) != len(hdr):
        bad_num.append((lineno, "列数 %d != 表头 %d" % (len(row), len(hdr))))
        continue
    vals = [num(c) for c in row]
    if any(v is None for v in vals):
        bad_num.append((lineno, "非数值: %s" % row))
        continue
    recs.append(dict(zip(hdr, vals), _line=lineno))

section("1. 格式 / NaN / 非数值")
if bad_num:
    for ln, m in bad_num[:20]:
        print("  L%d: %s" % (ln, m))
    problems.append("有 %d 行列数或数值异常" % len(bad_num))
else:
    print("  OK — %d 行全部可解析为数值，无 NaN" % len(recs))

# ---------- 2. 重复 ----------
section("2. 重复工况")
keys = [(r["W_mm"], r["G_mm"], r["dx_mm"], r["tx_gap_mm"], r["mu"]) for r in recs]
dup = [k for k, c in Counter(keys).items() if c > 1]
if dup:
    print("  发现 %d 组重复:" % len(dup))
    for k in dup[:20]:
        lines = [r["_line"] for r in recs
                 if (r["W_mm"], r["G_mm"], r["dx_mm"], r["tx_gap_mm"], r["mu"]) == k]
        print("    %s  出现在行 %s" % (k, lines))
    problems.append("存在 %d 组重复工况" % len(dup))
else:
    print("  OK — 无重复")

# ---------- 3. 与 combos_unit30.csv 对账 ----------
section("3. 与参数表 combos_unit30.csv 对账")
phdr, praw = load(PLAN)
plan = set()
for _ln, row in praw:
    v = [num(c) for c in row]
    if all(x is not None for x in v):
        plan.add((v[0], v[1], v[2], v[3], v[4]))
got = set(keys)
print("  参数表组合数 : %d" % len(plan))
print("  结果表组合数 : %d" % len(got))
missing = plan - got
extra = got - plan
print("  参数表有、结果表缺 : %d" % len(missing))
print("  结果表有、参数表无 : %d" % len(extra))
if missing:
    for k in sorted(missing)[:15]:
        print("    缺 %s" % (k,))
    problems.append("结果表缺少 %d 个参数表里的工况" % len(missing))
if extra:
    for k in sorted(extra)[:15]:
        print("    多 %s" % (k,))
    problems.append("结果表多出 %d 个参数表外的工况" % len(extra))
if not missing and not extra:
    print("  OK — 两表完全一致")

# ---------- 4. 网格完整性 ----------
section("4. 变量取值网格")
for f in CONSTRAINT:
    vals = sorted({r[f] for r in recs})
    print("  %-12s 共 %d 个值: %s%s" % (f, len(vals), vals[:12], " ..." if len(vals) > 12 else ""))

Ws = sorted({r["W_mm"] for r in recs})
Gs = sorted({r["G_mm"] for r in recs})
tgs = sorted({r["tx_gap_mm"] for r in recs})
dxs = sorted({r["dx_mm"] for r in recs})
mus = sorted({r["mu"] for r in recs})
print()
print("  实际网格: %d(W) x %d(tg) x %d(dx) x %d(mu) = %d   (实际行数 %d)"
      % (len(Ws), len(tgs), len(dxs), len(mus),
         len(Ws) * len(tgs) * len(dxs) * len(mus), len(recs)))

# W+G 约束
bad_wg = [(r["_line"], r["W_mm"], r["G_mm"]) for r in recs if abs(r["W_mm"] + r["G_mm"] - 30.0) > 1e-6]
print()
print("  W+G=30 约束: %s" % ("OK" if not bad_wg else "违反 %d 行" % len(bad_wg)))
if bad_wg:
    for ln, w, g in bad_wg[:10]:
        print("    L%d: W=%s G=%s (和=%.3f)" % (ln, w, g, w + g))
    problems.append("有 %d 行不满足 W+G=30" % len(bad_wg))

# dx 步长
if len(dxs) > 1:
    steps = sorted({round(dxs[i + 1] - dxs[i], 6) for i in range(len(dxs) - 1)})
    print("  dx 步长: %s" % steps)

# ---------- 5. 物理约束 ----------
section("5. 物理约束")

# 5a 自感必须为正
neg = [(r["_line"], r) for r in recs if r["L11_uH"] <= 0 or r["L22_uH"] <= 0 or r["L33_uH"] <= 0]
print("  自感 L11/L22/L33 > 0 : %s" % ("OK" if not neg else "违反 %d 行" % len(neg)))
for ln, r in neg[:10]:
    print("    L%d: L11=%.3f L22=%.3f L33=%.3f" % (ln, r["L11_uH"], r["L22_uH"], r["L33_uH"]))
if neg:
    problems.append("有 %d 行自感非正" % len(neg))

# 5b |k| < 1
badk = [(r["_line"], r) for r in recs if abs(r["k13"]) >= 1 or abs(r["k23"]) >= 1]
print("  |k13| < 1 且 |k23| < 1 : %s" % ("OK" if not badk else "违反 %d 行" % len(badk)))
for ln, r in badk[:10]:
    print("    L%d: k13=%.4f k23=%.4f" % (ln, r["k13"], r["k23"]))
if badk:
    problems.append("有 %d 行耦合系数绝对值 >= 1（物理上不可能）" % len(badk))

# 5c |Mij| <= sqrt(Lii*Ljj)
viol = []
for r in recs:
    for (mi, a, b) in (("M12_uH", "L11_uH", "L22_uH"),
                       ("M13_uH", "L11_uH", "L33_uH"),
                       ("M23_uH", "L22_uH", "L33_uH")):
        bound = math.sqrt(r[a] * r[b])
        if abs(r[mi]) > bound * (1 + 1e-9):
            viol.append((r["_line"], mi, r[mi], bound))
print("  |Mij| <= sqrt(Lii*Ljj) : %s" % ("OK" if not viol else "违反 %d 处" % len(viol)))
for ln, mi, m, b in viol[:10]:
    print("    L%d: |%s|=%.3f > %.3f" % (ln, mi, abs(m), b))
if viol:
    problems.append("有 %d 处互感超过 sqrt(Lii*Ljj) 上限" % len(viol))

# 5d k 与 M/L 的自洽
kk = []
for r in recs:
    c13 = r["M13_uH"] / math.sqrt(r["L11_uH"] * r["L33_uH"]) if r["L11_uH"] > 0 and r["L33_uH"] > 0 else 0
    c23 = r["M23_uH"] / math.sqrt(r["L22_uH"] * r["L33_uH"]) if r["L22_uH"] > 0 and r["L33_uH"] > 0 else 0
    d13 = abs(c13 - r["k13"])
    d23 = abs(c23 - r["k23"])
    kk.append((max(d13, d23), r["_line"], r["k13"], c13, r["k23"], c23))
kk.sort(reverse=True)
worst = kk[0]
print()
print("  k 是否等于 M/sqrt(Li*Lj)（表内自洽性）")
print("    最大偏差 %.6f  出现在 L%d" % (worst[0], worst[1]))
if worst[0] > 5e-4:
    print("    !! 偏差偏大，可能有取列/计算错误")
    problems.append("k 与 M/L 不自洽，最大偏差 %.6f (L%d)" % (worst[0], worst[1]))
    for d, ln, k13, c13, k23, c23 in kk[:8]:
        print("      L%-6d 表内 k13=%.5f 算得=%.5f | k23=%.5f 算得=%.5f" % (ln, k13, c13, k23, c23))

# ---------- 6. 镜像对称 ----------
section("6. 镜像对称检查")
print("  几何关于 x=0 镜像对称 => 预期:")
print("    L33(dx) = L33(-dx),  L11(dx) = L22(-dx),  M13(dx) = M23(-dx),  M12(dx) = M12(-dx)")
print()
bymap = {}
for r in recs:
    bymap[(r["W_mm"], r["G_mm"], r["tx_gap_mm"], r["mu"], r["dx_mm"])] = r

pairs = 0
worst_sym = []
for (w, g, tg, mu, dx), r in bymap.items():
    if dx <= 0:
        continue
    other = bymap.get((w, g, tg, mu, -dx))
    if other is None:
        continue
    pairs += 1
    checks = [
        ("L33", r["L33_uH"], other["L33_uH"]),
        ("L11<->L22", r["L11_uH"], other["L22_uH"]),
        ("L22<->L11", r["L22_uH"], other["L11_uH"]),
        ("M13<->M23", r["M13_uH"], other["M23_uH"]),
        ("M23<->M13", r["M23_uH"], other["M13_uH"]),
        ("M12", r["M12_uH"], other["M12_uH"]),
    ]
    for name, a, b in checks:
        denom = max(abs(a), abs(b), 1e-9)
        rel = abs(a - b) / denom * 100.0
        worst_sym.append((rel, name, w, g, tg, dx, a, b))

worst_sym.sort(reverse=True)
print("  可配对 %d 对（±dx）" % pairs)
print("  偏差最大的 10 项:")
for rel, name, w, g, tg, dx, a, b in worst_sym[:10]:
    print("    %-10s W=%-5.1f G=%-5.1f tg=%-5.1f dx=%+6.1f : %+12.3f vs %+12.3f  (%.3f%%)"
          % (name, w, g, tg, dx, a, b, rel))
med = worst_sym[len(worst_sym) // 2][0] if worst_sym else 0
print("  中位偏差: %.3f%%" % med)
if worst_sym and worst_sym[0][0] > 5.0:
    notes.append("镜像对称最大偏差 %.2f%%（可能来自引线/绕组不对称，或数据错误，需人工判断）"
                 % worst_sym[0][0])

# ---------- 7. 异常值 ----------
section("7. 分布 / 异常值")
import statistics as st
for f in FIELDS:
    vals = [r[f] for r in recs]
    m = st.mean(vals)
    sd = st.pstdev(vals)
    lo, hi = min(vals), max(vals)
    outl = [r["_line"] for r in recs if sd > 0 and abs(r[f] - m) > 6 * sd]
    print("  %-9s min=%12.3f  max=%12.3f  mean=%12.3f  sd=%10.3f   >6sd: %d %s"
          % (f, lo, hi, m, sd, len(outl), outl[:5] if outl else ""))

# ---------- 汇总 ----------
section("汇总")
if problems:
    print("发现问题 %d 类:" % len(problems))
    for p in problems:
        print("  ✗ %s" % p)
else:
    print("未发现硬性错误")
if notes:
    print()
    print("需人工判断 %d 项:" % len(notes))
    for n in notes:
        print("  ? %s" % n)
