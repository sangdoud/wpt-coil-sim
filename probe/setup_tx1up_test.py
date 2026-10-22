# -*- coding: utf-8 -*-
"""验证 Tx1 引线上移后能否正常求解，并对比 L。

复制正式模型 -> _test_run/Projecttonight_tx1up.aedt
生成测试脚本（PROJECT 指向副本，开孔只跳过 Tx1），跑 W=10 G=20 dx=-150 tg=0
基线：23.328 uH（原引线 + 开孔 + Conductor=1）
"""

import os
import shutil

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")
SRC_AEDT = os.path.join(WPT, "Projecttonight.aedt")
DST_AEDT = os.path.join(TEST, "Projecttonight_tx1up.aedt")
SRC_PY = os.path.join(WPT, "batch_sweep_unit30.py")
DST_PY = os.path.join(TEST, "batch_sweep_test.py")
POINT = (10.0, 20.0, -150.0, 0.0, 1000.0)

shutil.copyfile(SRC_AEDT, DST_AEDT)
print("复制模型 -> %s (%d bytes)" % (DST_AEDT, os.path.getsize(DST_AEDT)))

with open(os.path.join(TEST, "combos_unit30.csv"), "w", newline="", encoding="utf-8") as f:
    f.write("W_mm,G_mm,dx_mm,tx_gap_mm,mu\n")
    f.write("%s,%s,%s,%s,%s\n" % POINT)
print("plan:", POINT)

for n in ("sweep_all_unit30.csv", "batch_sweep_unit30.log", "batch.log"):
    p = os.path.join(TEST, n)
    if os.path.exists(p):
        os.remove(p)
        print("cleared:", n)

with open(SRC_PY, "r", encoding="utf-8") as f:
    src = f.read()
orig = src

src = src.replace('BASE_DIR = r"C:/wpt"', 'BASE_DIR = r"C:/wpt/_test_run"', 1)
src = src.replace('PROJECT = r"C:/wpt/Projecttonight.aedt"',
                  'PROJECT = r"C:/wpt/_test_run/Projecttonight_tx1up.aedt"', 1)

i0 = src.find("    # 开孔：引线穿过铁氧体")
i1 = src.find("    return len(ferr)", i0)
if i0 < 0 or i1 < 0:
    raise SystemExit("!! 找不到开孔段")

# 只跳过 Tx1 的开孔（Tx1 引线已改到上侧，不再穿铁氧体）
# Tx2（向下）与 Rx（向上）的引线仍然穿铁氧体，必须保留开孔
old_loop = """    for coil, pts in ENDS.items():
        if coil == "Tx1":
            base_x = tx1_c"""
new_loop = """    for coil, pts in ENDS.items():
        if coil == "Tx1":
            continue          # Tx1 引线已改到上侧，不再穿越铁氧体
        if coil == "Tx1":
            base_x = tx1_c"""
if old_loop not in src:
    raise SystemExit("!! 找不到开孔 for 循环")
src = src.replace(old_loop, new_loop, 1)
print("已在开孔循环里跳过 Tx1（Tx2 / Rx 的开孔保留）")

with open(DST_PY, "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("script:", DST_PY)
with open(SRC_PY, "r", encoding="utf-8") as f:
    print("真实脚本未被改动:", f.read() == orig)
