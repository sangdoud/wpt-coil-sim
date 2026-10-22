# -*- coding: utf-8 -*-
"""把磁学量除以 144（修正匝数重复计数），k 列保持原样。

规则
----
列式文件（6 个磁学量 + 2 个耦合系数）:
    L11_uH / L22_uH / L33_uH / M12_uH / M13_uH / M23_uH  ->  /144
    k13 / k23                                            ->  不动（比值，公因子已约掉）
    scan_RxX.csv 的列名是 L11_Tx1_uH / L22_Tx2_uH / L33_Rx_uH，一并处理

矩阵文件（3x3，行标签 + 3 个数值列）:
    所有数值 -> /144

输出：原地改写（原文件已先备份到 backup/before_div144/），保留 6 位小数。
"""

import csv
import os
import shutil
import sys

WPT = r"C:\wpt"
BK = os.path.join(WPT, "backup", "before_div144")
DIV = 144.0
NDEC = 6

# 列式文件：要除的列名（覆盖两种命名）
MAG_COLS = {
    "L11_uH", "L22_uH", "L33_uH", "M12_uH", "M13_uH", "M23_uH",
    "L11_Tx1_uH", "L22_Tx2_uH", "L33_Rx_uH",
    "M11_uH", "M22_uH", "M33_uH",
}
KEEP_COLS = {"k13", "k23", "k12"}

COLUMNAR = [
    "sweep_all_unit30.csv",
    "scan_B.csv",
    "scan_G.csv",
    "scan_RxX.csv",
    "scan_W.csv",
    "training_data.csv",
    "sweep_all_full.csv",
    "sweep_all_full_mu1000.csv",
    "sweep_w30g10_tg120.csv",
]

# 矩阵文件：(文件名, 是否跳过表头行, 是否只处理数值列)
MATRIX = [
    "Lmatrix.csv",           # 含 nH 段 + uH 段，各有一个表头
    "Lmatrix_EC3.csv",
    "Lmatrix_WPT_G_mag.csv",
]
NAN_FILES = ["Lmatrix_WPT_G.csv", "Lmatrix_WPT_EC8.csv"]

os.makedirs(BK, exist_ok=True)


def backup(name):
    src = os.path.join(WPT, name)
    if os.path.isfile(src):
        shutil.copyfile(src, os.path.join(BK, name))


def fmt(v):
    s = ("%%.%df" % NDEC) % v
    # 去掉多余的尾零，保持可读（但至少保留 1 位小数）
    if "." in s:
        s = s.rstrip("0")
        if s.endswith("."):
            s += "0"
    return s


def is_num(s):
    try:
        float(s)
        return True
    except Exception:
        return False


def process_columnar(name):
    src = os.path.join(WPT, name)
    with open(src, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    if not rows:
        return None
    hdr = rows[0]
    idx = [i for i, c in enumerate(hdr) if c in MAG_COLS]
    kdx = [i for i, c in enumerate(hdr) if c in KEEP_COLS]
    if not idx:
        return None

    n = 0
    before_sample = None
    after_sample = None
    for r in rows[1:]:
        if len(r) != len(hdr):
            continue
        if before_sample is None and all(is_num(r[i]) for i in idx):
            before_sample = [r[i] for i in idx]
        for i in idx:
            if is_num(r[i]):
                r[i] = fmt(float(r[i]) / DIV)
                n += 1
        if after_sample is None:
            after_sample = [r[i] for i in idx]

    with open(src, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)

    return dict(name=name, cols=len(idx), kcols=len(kdx), cells=n,
                before=before_sample, after=after_sample,
                hdr=[hdr[i] for i in idx])


def process_matrix(name):
    src = os.path.join(WPT, name)
    if not os.path.isfile(src):
        return None
    with open(src, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    n = 0
    out = []
    before = after = None
    for r in rows:
        # 表头行：第一格不是行标签（含 "L (" ）
        if r and r[0].strip().startswith("L ("):
            out.append(r)
            continue
        if len(r) >= 4 and r[0].strip():
            newr = [r[0]]
            for c in r[1:4]:
                if is_num(c):
                    if before is None:
                        before = list(r[1:4])
                    newr.append(fmt(float(c) / DIV))
                    n += 1
                else:
                    newr.append(c)
            if after is None:
                after = newr[1:4]
            out.append(newr)
        else:
            out.append(r)

    with open(src, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(out)
    return dict(name=name, cells=n, before=before, after=after)


def main():
    print("=" * 78)
    print("除以 144：修正匝数重复计数")
    print("=" * 78)
    print("备份目录:", BK)
    print()

    allfiles = COLUMNAR + MATRIX + NAN_FILES
    print("--- 备份 ---")
    for n in allfiles:
        backup(n)
        p = os.path.join(BK, n)
        if os.path.isfile(p):
            print("  %-26s %d bytes" % (n, os.path.getsize(p)))
    print()

    print("--- 列式文件：6 个磁学量 /144，k 列不动 ---")
    results = []
    for n in COLUMNAR:
        r = process_columnar(n)
        if r:
            results.append(r)
            print("  %-26s 除 %d 列 x %d 格 | k 列 %d 个保持不动"
                  % (n, r["cols"], r["cells"], r["kcols"]))
        else:
            print("  %-26s 跳过（无匹配列）" % n)

    print()
    print("--- 矩阵文件：整体 /144 ---")
    for n in MATRIX:
        r = process_matrix(n)
        if r:
            print("  %-26s 除 %d 格" % (n, r["cells"]))
    print()
    print("--- 全 NaN 文件：不动 ---")
    for n in NAN_FILES:
        print("  %-26s 内容全是 nan，保持原样" % n)

    print()
    print("=" * 78)
    print("抽查样例（sweep_all_unit30.csv 第一行）")
    print("=" * 78)
    main_r = next(r for r in results if r["name"] == "sweep_all_unit30.csv")
    print("  %-12s %16s %16s" % ("列", "原值", "÷144 后"))
    for c, a, b in zip(main_r["hdr"], main_r["before"], main_r["after"]):
        print("  %-12s %16s %16s" % (c, a, b))
    return 0


if __name__ == "__main__":
    sys.exit(main())
