"""回退后的收尾校验：语法 + 核数统计。"""

import ast
import os
import re
import sys

ROOT = r"C:\wpt"
EXCLUDE_DIRS = {"backup", "_incident_20260913", "_incident_20260914", "__pycache__", "_test_run"}

files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
    for fn in filenames:
        if fn.endswith(".py"):
            files.append(os.path.join(dirpath, fn))
files.sort()

print("=== 语法校验 (%d 个 .py) ===" % len(files))
bad = []
for p in files:
    try:
        ast.parse(open(p, encoding="utf-8").read(), filename=p)
    except SyntaxError as e:
        bad.append((p, e.lineno, e.msg))
if bad:
    for p, ln, m in bad:
        print("  FAIL %s line %s: %s" % (p, ln, m))
else:
    print("  all %d files parse cleanly" % len(files))

n8 = n24 = 0
for p in files:
    for line in open(p, encoding="utf-8"):
        if re.search(r"\bcores\s*=\s*8\b", line, re.I):
            n8 += 1
        if re.search(r"\bcores\s*=\s*24\b", line, re.I):
            n24 += 1

print()
print("cores=8  : %d 处" % n8)
print("cores=24 : %d 处   %s" % (n24, "OK" if n24 == 0 else "<== 还有残留！"))

print()
print("=== 5 个 CORES 常量 ===")
for name in ("batch_sweep_unit30.py", "preflight_2025.py", "batch_sweep.py",
             "batch_sweep_full.py", "batch_sweep_txgap.py"):
    for i, line in enumerate(open(os.path.join(ROOT, name), encoding="utf-8"), 1):
        if re.match(r"\s*CORES\s*=", line):
            print("  %-24s L%-4d %s" % (name, i, line.strip()))

sys.exit(1 if (bad or n24) else 0)
