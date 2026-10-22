# -*- coding: utf-8 -*-
"""对照实验：用「原始引线」的基线模型跑同一个点，确认 23.328 uH 今天还能复现。

基线模型 = C:\\wpt\\backup\\before_tx1_lead_up\\Projecttonight.aedt
  (原始引线: Tx1/Tx2 都是竖直向下到 z=-45, 穿铁氧体开孔, Conductor=1)

生成脚本时要【恢复】Tx 开孔逻辑（生产脚本现在只给 Rx 开孔），
否则原始引线会直接穿过铁氧体 -> 几何相交报错。
"""

import os
import shutil
import sys

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")
SRC_AEDT = os.path.join(WPT, "backup", "before_tx1_lead_up", "Projecttonight.aedt")
DST_AEDT = os.path.join(TEST, "Projecttonight_base.aedt")
SRC_PY = os.path.join(WPT, "batch_sweep_unit30.py")
DST_PY = os.path.join(TEST, "batch_sweep_base.py")
POINT = tuple(float(v) for v in sys.argv[1:6]) if len(sys.argv) >= 6 \
    else (10.0, 20.0, -150.0, 0.0, 1000.0)

for n in ("Projecttonight_base.aedt", "Projecttonight_base.aedt.lock"):
    p = os.path.join(TEST, n)
    if os.path.exists(p):
        os.chmod(p, 0o666)
        os.remove(p)
        print("removed:", n)
for n in ("Projecttonight_base.aedtresults", "Projecttonight_base.pyaedt"):
    p = os.path.join(TEST, n)
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)
        print("removed dir:", n)

shutil.copyfile(SRC_AEDT, DST_AEDT)
os.chmod(DST_AEDT, 0o666)
print("基线模型 -> %s (%d bytes)" % (DST_AEDT, os.path.getsize(DST_AEDT)))

with open(os.path.join(TEST, "combos_unit30.csv"), "w", newline="", encoding="utf-8") as f:
    f.write("W_mm,G_mm,dx_mm,tx_gap_mm,mu\n")
    f.write("%s,%s,%s,%s,%s\n" % POINT)
print("plan:", POINT)

with open(SRC_PY, "r", encoding="utf-8") as f:
    src = f.read()
orig = src

src = src.replace('BASE_DIR = r"C:/wpt"', 'BASE_DIR = r"C:/wpt/_test_run"', 1)
src = src.replace('PROJECT = r"C:/wpt/Projecttonight.aedt"',
                  'PROJECT = r"C:/wpt/_test_run/Projecttonight_base.aedt"', 1)

# 恢复 Tx 开孔
new_loop = """    for coil, pts in ENDS.items():
        if coil in ("Tx1", "Tx2"):
            continue
        base_x = RX_CENTER
        group_pref = "Rx\""""
old_loop = """    for coil, pts in ENDS.items():
        if coil == "Tx1":
            base_x = tx1_c
        elif coil == "Tx2":
            base_x = tx2_c
        else:
            base_x = RX_CENTER
        group_pref = {"Tx1": "Tx", "Tx2": "Tx", "Rx": "Rx"}[coil]"""
if new_loop not in src:
    raise SystemExit("!! 找不到要替换的开孔段")
src = src.replace(new_loop, old_loop, 1)
print("已恢复 Tx1/Tx2 开孔逻辑（基线模型需要）")

if "_test_run" not in src:
    raise SystemExit("!! 路径替换失败")

with open(DST_PY, "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("script:", DST_PY)
with open(SRC_PY, "r", encoding="utf-8") as f:
    print("真实脚本未被改动:", f.read() == orig)
