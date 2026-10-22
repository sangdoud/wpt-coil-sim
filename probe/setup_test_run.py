"""Build an isolated test rig under C:\\wpt\\_test_run so that:
  * the real batch_sweep_unit30.py is NOT modified
  * the 1705-point sweep_all_unit30.csv is NOT touched
  * backup_upload (missing from the repo) is satisfied by a documented no-op

Layout produced:
  _test_run/combos_unit30.csv      3 known points (header + 3 rows)
  _test_run/batch_sweep_test.py    copy of the real script, BASE_DIR redirected
  _test_run/backup_upload.py       no-op stub (git/gh do not exist on this host)
"""

import os
import shutil

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")

SRC_SCRIPT = os.path.join(WPT, "batch_sweep_unit30.py")
DST_SCRIPT = os.path.join(TEST, "batch_sweep_test.py")

# the three already-computed points we will re-run
POINTS = [
    (10.0, 20.0, -150.0, 0.0, 1000.0),
    (15.0, 15.0, -150.0, 30.0, 1000.0),
    (20.0, 10.0, -150.0, 60.0, 1000.0),
]

os.makedirs(TEST, exist_ok=True)

# ---- 1. plan CSV -----------------------------------------------------------
plan = os.path.join(TEST, "combos_unit30.csv")
with open(plan, "w", newline="", encoding="utf-8") as f:
    f.write("W_mm,G_mm,dx_mm,tx_gap_mm,mu\n")
    for p in POINTS:
        f.write("%s,%s,%s,%s,%s\n" % p)
print("wrote plan:", plan)

# ---- 2. copy of the script, BASE_DIR redirected ----------------------------
with open(SRC_SCRIPT, "r", encoding="utf-8") as f:
    src = f.read()

old = 'BASE_DIR = r"C:/wpt"'
new = 'BASE_DIR = r"C:/wpt/_test_run"'
if old not in src:
    raise SystemExit("!! could not find the BASE_DIR line to redirect")
src2 = src.replace(old, new, 1)

# make it obvious this is a test copy
src2 = src2.replace(
    "# 批量扫描（UNIT=30 版）",
    "# [TEST COPY] 批量扫描（UNIT=30 版）—— 由 setup_test_run.py 生成，BASE_DIR 指向 _test_run",
    1,
)

with open(DST_SCRIPT, "w", encoding="utf-8", newline="") as f:
    f.write(src2)
print("wrote script:", DST_SCRIPT)

# verify only that one line differs
a = src.splitlines()
b = src2.splitlines()
diffs = [(i + 1, x, y) for i, (x, y) in enumerate(zip(a, b)) if x != y]
print("differing lines: %d" % len(diffs))
for ln, x, y in diffs:
    print("  L%d" % ln)
    print("    - %s" % x)
    print("    + %s" % y)

# ---- 3. no-op backup_upload stub ------------------------------------------
stub = os.path.join(TEST, "backup_upload.py")
with open(stub, "w", encoding="utf-8") as f:
    f.write('''# -*- coding: utf-8 -*-
"""No-op stand-in for the missing backup_upload module.

The real batch_sweep_unit30.py does `import backup_upload as _bu` and calls
_bu.run_backup() once per hour. That module is NOT in the GitHub repo, and this
host has neither git nor gh installed, so the real hourly "git commit + gh push"
backup could not work here anyway.

This stub keeps the import working and logs that the backup was skipped.
It performs NO network, NO git, and NO file writes.
"""

import time


def run_backup(*args, **kwargs):
    print("[backup_upload stub] %s  hourly backup skipped (no git/gh on this host)"
          % time.strftime("%Y-%m-%d %H:%M:%S"))
    return False
''')
print("wrote stub:", stub)

print()
print("=== _test_run contents ===")
for n in sorted(os.listdir(TEST)):
    p = os.path.join(TEST, n)
    print("  %10d  %s" % (os.path.getsize(p), n))
