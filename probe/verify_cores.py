"""Verify the cores=24 change: syntax + residual scan + targeted listing."""

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

print("=== 1. 语法校验 (%d 个 .py) ===" % len(files))
bad = []
for p in files:
    try:
        ast.parse(open(p, encoding="utf-8").read(), filename=p)
    except SyntaxError as e:
        bad.append((p, "line %s: %s" % (e.lineno, e.msg)))
if bad:
    for p, m in bad:
        print("  FAIL %s -> %s" % (p, m))
else:
    print("  all %d files parse cleanly" % len(files))

print()
print("=== 2. 残留 cores=8 扫描 ===")
res = []
for p in files:
    for i, line in enumerate(open(p, encoding="utf-8"), 1):
        if re.search(r"\bcores\s*=\s*8\b", line, re.I):
            res.append((p, i, line.strip()))
if res:
    for p, i, l in res:
        print("  %s L%d: %s" % (p, i, l))
else:
    print("  none")

print()
print("=== 3. cores=24 总数 ===")
n24 = 0
for p in files:
    for line in open(p, encoding="utf-8"):
        if re.search(r"\bcores\s*=\s*24\b", line, re.I):
            n24 += 1
print("  %d 处" % n24)

print()
print("=== 4. 关键文件的 CORES 行 ===")
for name in ("batch_sweep_unit30.py", "preflight_2025.py", "batch_sweep.py",
             "batch_sweep_full.py", "batch_sweep_txgap.py"):
    p = os.path.join(ROOT, name)
    if os.path.isfile(p):
        for i, line in enumerate(open(p, encoding="utf-8"), 1):
            if re.match(r"\s*CORES\s*=", line):
                print("  %-24s L%-5d %s" % (name, i, line.strip()))

print()
print("=== 5. batch_sweep_unit30.py 的 analyze 调用 ===")
p = os.path.join(ROOT, "batch_sweep_unit30.py")
for i, line in enumerate(open(p, encoding="utf-8"), 1):
    if "analyze(" in line:
        print("  L%-5d %s" % (i, line.strip()))

sys.exit(1 if (bad or res) else 0)
