# -*- coding: utf-8 -*-
"""验证「Tx 引线改 L 形（竖直一小段 + 沿 -Y 出线）」后能否正常求解，并对比 L。

复制正式模型 -> _test_run/Projecttonight_leadsL.aedt
生成测试脚本（只改路径，开孔逻辑已是生产版：只给 Rx 开孔）
跑 W=10 G=20 dx=-150 tg=0 mu=1000
基线：23.328 uH（原始竖直引线 + 开孔 + Conductor=1）
"""

import os
import shutil
import sys

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")
SRC_AEDT = os.path.join(WPT, "Projecttonight.aedt")
DST_AEDT = os.path.join(TEST, "Projecttonight_leadsL.aedt")
SRC_PY = os.path.join(WPT, "batch_sweep_unit30.py")
DST_PY = os.path.join(TEST, "batch_sweep_test.py")
POINT = tuple(float(v) for v in sys.argv[1:7]) if len(sys.argv) >= 7 \
    else (10.0, 20.0, -150.0, 0.0, 1000.0, 5.0)

os.makedirs(TEST, exist_ok=True)

# 清掉同名旧产物，避免用到上次的 .lock / .aedtresults
for n in ("Projecttonight_leadsL.aedt", "Projecttonight_leadsL.aedt.lock"):
    p = os.path.join(TEST, n)
    if os.path.exists(p):
        os.remove(p)
        print("removed:", n)
for n in ("Projecttonight_leadsL.aedtresults", "Projecttonight_leadsL.pyaedt"):
    p = os.path.join(TEST, n)
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)
        print("removed dir:", n)

shutil.copyfile(SRC_AEDT, DST_AEDT)
print("复制模型 -> %s (%d bytes)" % (DST_AEDT, os.path.getsize(DST_AEDT)))

with open(os.path.join(TEST, "combos_unit30.csv"), "w", newline="", encoding="utf-8") as f:
    f.write("W_mm,G_mm,dx_mm,tx_gap_mm,mu,thk_mm\n")
    f.write("%s,%s,%s,%s,%s,%s\n" % POINT)
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
                  'PROJECT = r"C:/wpt/_test_run/Projecttonight_leadsL.aedt"', 1)

if "_test_run" not in src:
    raise SystemExit("!! 路径替换失败")

with open(DST_PY, "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("script:", DST_PY)
with open(SRC_PY, "r", encoding="utf-8") as f:
    print("真实脚本未被改动:", f.read() == orig)

# 确认测试脚本里开孔只剩 Rx
import re
m = re.search(r"for coil, pts in ENDS\.items\(\):\n(.*?)\n\s*for i, \(lx, ly\)", src, re.S)
print("开孔段现在长这样:")
print(m.group(0) if m else "  (没匹配到)")
