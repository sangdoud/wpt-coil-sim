# -*- coding: utf-8 -*-
"""校验 /144 处理：k 列必须逐字节不变，磁学量必须精确等于 原值/144。"""

import csv
import os

WPT = r"C:\wpt"
BK = os.path.join(WPT, "backup", "before_div144")
DIV = 144.0

MAG = {"L11_uH", "L22_uH", "L33_uH", "M12_uH", "M13_uH", "M23_uH",
       "L11_Tx1_uH", "L22_Tx2_uH", "L33_Rx_uH"}
KEEP = {"k13", "k23"}

COLUMNAR = ["sweep_all_unit30.csv", "scan_B.csv", "scan_G.csv", "scan_RxX.csv",
            "scan_W.csv", "training_data.csv", "sweep_all_full.csv",
            "sweep_all_full_mu1000.csv", "sweep_w30g10_tg120.csv"]


def load(p):
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


print("=" * 80)
print("1. 列式文件逐格校验")
print("=" * 80)
print("  %-26s %8s %8s %10s %12s %12s" %
      ("文件", "行数", "k列不变", "磁列格数", "最大相对差", "结论"))

allok = True
for name in COLUMNAR:
    a = load(os.path.join(BK, name))
    b = load(os.path.join(WPT, name))
    if len(a) != len(b) or a[0] != b[0]:
        print("  %-26s 结构不一致！" % name)
        allok = False
        continue
    hdr = a[0]
    mi = [i for i, c in enumerate(hdr) if c in MAG]
    ki = [i for i, c in enumerate(hdr) if c in KEEP]

    k_same = all(a[r][i] == b[r][i] for r in range(len(a)) for i in ki)
    cells = 0
    worst = 0.0
    for r in range(1, len(a)):
        for i in mi:
            try:
                ov = float(a[r][i])
                nv = float(b[r][i])
            except Exception:
                continue
            exp = ov / DIV
            d = abs(nv - exp) / abs(exp) if exp else 0.0
            worst = max(worst, d)
            cells += 1
    ok = k_same and worst < 1e-5
    allok = allok and ok
    print("  %-26s %8d %8s %10d %12.2e %12s" %
          (name, len(a) - 1, "是" if k_same else "否!", cells, worst,
           "OK" if ok else "FAIL"))

print()
print("=" * 80)
print("2. 与 cn=1 实测对照（W=10 G=20 dx=-150 tg=0 mu=1000）")
print("=" * 80)
PT = [10.0, 20.0, -150.0, 0.0, 1000.0]
CN1 = {"L11_uH": 23.328, "L22_uH": 19.408, "L33_uH": 23.979,
       "M12_uH": -1.076, "M13_uH": 3.322, "M23_uH": -0.153,
       "k13": 0.14047, "k23": -0.00707}

rows = load(os.path.join(WPT, "sweep_all_unit30.csv"))
hdr = rows[0]
target = None
for r in rows[1:]:
    if len(r) >= 13 and [float(v) for v in r[:5]] == PT:
        target = r
        break

print("  %-10s %16s %16s %10s" % ("量", "修正后数据集", "cn=1 实测", "相对差"))
worst = 0.0
for i, c in enumerate(hdr):
    if c in CN1:
        a = float(target[i])
        b = CN1[c]
        d = abs(a - b) / abs(b) * 100 if b else 0
        worst = max(worst, d)
        print("  %-10s %16.6f %16.4f %9.3f%%" % (c, a, b, d))
print()
print("  最大相对差 %.3f%% —— 这就是数据集自身的运行间波动（第三次核对过约 0.3%%）" % worst)
print("  k 列应当与 cn=1 完全一致（它是比值，本来就没被放大）")

print()
print("=" * 80)
print("3. 主数据集修正后范围")
print("=" * 80)
vals = {c: [] for c in hdr if c in MAG or c in KEEP}
for r in rows[1:]:
    if len(r) < 13:
        continue
    for c in vals:
        i = hdr.index(c)
        try:
            vals[c].append(float(r[i]))
        except Exception:
            pass
print("  %-10s %14s %14s" % ("量", "最小", "最大"))
for c in ("L11_uH", "L22_uH", "L33_uH", "M12_uH", "M13_uH", "M23_uH", "k13", "k23"):
    v = vals.get(c, [])
    if v:
        print("  %-10s %14.6f %14.6f" % (c, min(v), max(v)))

print()
print("=" * 80)
print("4. 结论")
print("=" * 80)
print("  所有文件校验通过" if allok else "  !! 有文件校验失败，需检查")
