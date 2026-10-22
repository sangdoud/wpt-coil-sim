"""Regenerate the isolated test rig from the CURRENT (watchdog-enabled) script,
and inject modeler-call tracing so that if a hang happens we see the exact call.

Produces _test_run/batch_sweep_test.py:
  * BASE_DIR -> C:/wpt/_test_run   (isolated plan/output/log)
  * watchdog config unchanged from the real script
  * modeler calls traced with timestamps
"""

import os

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")
SRC = os.path.join(WPT, "batch_sweep_unit30.py")
DST = os.path.join(TEST, "batch_sweep_test.py")

POINTS = [
    (10.0, 20.0, -150.0, 0.0, 1000.0),
    (15.0, 15.0, -150.0, 30.0, 1000.0),
    (20.0, 10.0, -150.0, 60.0, 1000.0),
]

os.makedirs(TEST, exist_ok=True)

# ---- plan ---------------------------------------------------------------
plan = os.path.join(TEST, "combos_unit30.csv")
with open(plan, "w", newline="", encoding="utf-8") as f:
    f.write("W_mm,G_mm,dx_mm,tx_gap_mm,mu\n")
    for p in POINTS:
        f.write("%s,%s,%s,%s,%s\n" % p)
print("wrote plan:", plan)

# ---- fresh output -------------------------------------------------------
for name in ("sweep_all_unit30.csv", "batch_sweep_unit30.log"):
    p = os.path.join(TEST, name)
    if os.path.exists(p):
        os.remove(p)
        print("cleared old:", name)

# ---- read the real script ----------------------------------------------
with open(SRC, "r", encoding="utf-8") as f:
    src = f.read()

orig = src

# 1. isolate BASE_DIR
old = 'BASE_DIR = r"C:/wpt"'
new = 'BASE_DIR = r"C:/wpt/_test_run"'
if old not in src:
    raise SystemExit("!! BASE_DIR line not found")
src = src.replace(old, new, 1)

# 2. inject the tracing helper right before "# ============ 主流程 ============"
TRACE = '''
# ---- injected by setup_test_run2.py: modeler call tracing ----
_TRACE_T0 = time.time()


def _trace_log(msg):
    print("[trace %7.1fs] %s" % (time.time() - _TRACE_T0, msg), flush=True)
    try:
        with open(LOG_FILE, "a") as _f:
            _f.write("[trace %7.1fs] %s\\n" % (time.time() - _TRACE_T0, msg))
    except Exception:
        pass


def _trace_modeler(mdl):
    hooked = []
    for _n in ("create_box", "delete", "move", "subtract", "create_region", "unite"):
        _orig = getattr(mdl, _n, None)
        if _orig is None or not callable(_orig):
            continue

        def _mk(_name, _fn):
            def _w(*a, **k):
                _t = time.time()
                _trace_log("-> %s" % _name)
                _r = _fn(*a, **k)
                _trace_log("<- %s  %.2fs" % (_name, time.time() - _t))
                return _r
            return _w

        try:
            setattr(mdl, _n, _mk(_n, _orig))
            hooked.append(_n)
        except Exception:
            pass
    _trace_log("modeler hooked: %s" % ",".join(hooked))


'''
marker = "# ============ 主流程 ============"
if marker not in src:
    raise SystemExit("!! main-flow marker not found")
src = src.replace(marker, TRACE + marker, 1)

# 3. call the tracer right after the session is up
anchor = """    d, m3d = open_session()
    if d is None:
        sys.exit(1)
"""
if anchor not in src:
    raise SystemExit("!! open_session anchor not found")
src = src.replace(anchor, anchor + "    _trace_modeler(m3d)\n", 1)

# 4. mark it as a test copy
src = src.replace("# 批量扫描（UNIT=30 版）",
                  "# [TEST COPY] 批量扫描（UNIT=30 版）—— 隔离 + 追踪版", 1)

with open(DST, "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("wrote script:", DST)

# ---- confirm the original is untouched ---------------------------------
with open(SRC, "r", encoding="utf-8") as f:
    after = f.read()
print("real script unchanged:", after == orig)

# ---- report what differs ------------------------------------------------
a = orig.splitlines()
b = src.splitlines()
diffs = [(i + 1, x) for i, (x, y) in enumerate(zip(a, b)) if x != y]
print("lines differing from the real script: %d" % len(diffs))
for ln, x in diffs[:6]:
    print("  L%d: %s" % (ln, x))

print()
print("=== _test_run contents ===")
for n in sorted(os.listdir(TEST)):
    p = os.path.join(TEST, n)
    if os.path.isfile(p):
        print("  %10d  %s" % (os.path.getsize(p), n))
