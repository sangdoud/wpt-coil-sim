"""Verify the watchdog + backup_upload changes."""

import ast
import os
import subprocess
import sys

WPT = r"C:\wpt"

print("=== 1. syntax check ===")
for name in ("batch_sweep_unit30.py", "backup_upload.py"):
    p = os.path.join(WPT, name)
    try:
        ast.parse(open(p, encoding="utf-8").read(), filename=p)
        print("  OK   %s" % name)
    except SyntaxError as e:
        print("  FAIL %s -> line %s: %s" % (name, e.lineno, e.msg))
        sys.exit(1)

print()
print("=== 2. module import (main flow is guarded, must not run) ===")
sys.path.insert(0, WPT)
try:
    import batch_sweep_unit30 as B
    print("  imported batch_sweep_unit30 OK")
    print("  AEDT_VERSION   =", B.AEDT_VERSION)
    print("  BASE_DIR       =", B.BASE_DIR)
    print("  PLAN_CSV       =", B.PLAN_CSV)
    print("  OUT_CSV        =", B.OUT_CSV)
    print("  PROJECT        =", B.PROJECT)
    print("  STAGE_TIMEOUT  =", B.STAGE_TIMEOUT)
    print("  SOLVE_TIMEOUT  =", B.SOLVE_TIMEOUT)
    print("  HANG_RETRIES   =", B.HANG_RETRIES)
    for fn in ("kill_aedt", "run_stage", "read_done", "solve_and_extract", "rebuild_ferrite"):
        print("  has %-18s %s" % (fn, callable(getattr(B, fn, None))))
except Exception as e:
    print("  FAIL importing: %s %s" % (type(e).__name__, e))
    sys.exit(1)

print()
print("=== 3. run_stage smoke test (watchdog must fire) ===")
import time as _t


def _fast():
    return 42


def _hang():
    _t.sleep(600)
    return 1


st, v = B.run_stage("fast-op", _fast, 5)
print("  fast  -> status=%s value=%s" % (st, v))
st2, v2 = B.run_stage("hang-op", _hang, 3)
print("  hang  -> status=%s value=%s" % (st2, v2))
assert st == "OK" and v == 42, "fast path broken"
assert st2 == "HANG", "watchdog did not fire!"

print()
print("=== 4. backup_upload with no token (must degrade gracefully) ===")
sys.path.insert(0, WPT)
import backup_upload as BU
ok = BU.run_backup()
print("  run_backup() returned:", ok)
print("  (False + a clear log line is the expected result with no token)")
print("  TOKEN_FILE =", BU.TOKEN_FILE)
print("  REPO       =", BU.REPO)
print("  patterns   =", BU.BACKUP_PATTERNS)

print()
print("ALL CHECKS PASSED")
