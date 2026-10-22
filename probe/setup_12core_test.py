"""为「12 核测速」搭单点测试环境。

跑的点与 8 核 / 24 核基线完全相同：W=10 G=20 dx=-150 tg=0
  - 8  核实测：求解 7m23s
  - 24 核实测：求解 7m46s（profile 7m39s）

**只改测试副本**：真实 batch_sweep_unit30.py 保持 CORES = 8 不动。
"""

import os
import re
import sys

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")
SRC = os.path.join(WPT, "batch_sweep_unit30.py")
DST = os.path.join(TEST, "batch_sweep_test.py")

POINT = (10.0, 20.0, -150.0, 0.0, 1000.0)
TEST_CORES = 12

os.makedirs(TEST, exist_ok=True)

plan = os.path.join(TEST, "combos_unit30.csv")
with open(plan, "w", newline="", encoding="utf-8") as f:
    f.write("W_mm,G_mm,dx_mm,tx_gap_mm,mu\n")
    f.write("%s,%s,%s,%s,%s\n" % POINT)
print("plan:", POINT)

for name in ("sweep_all_unit30.csv", "batch_sweep_unit30.log", "batch.log"):
    p = os.path.join(TEST, name)
    if os.path.exists(p):
        os.remove(p)
        print("cleared:", name)

with open(SRC, "r", encoding="utf-8") as f:
    src = f.read()
orig = src

# 1. 隔离 BASE_DIR
old = 'BASE_DIR = r"C:/wpt"'
new = 'BASE_DIR = r"C:/wpt/_test_run"'
if old not in src:
    raise SystemExit("!! BASE_DIR 行没找到")
src = src.replace(old, new, 1)

# 2. 只把副本里的核数改成 12（真实脚本不动）
src, n = re.subn(r"(\bCORES\s*=\s*)8\b", r"\g<1>%d" % TEST_CORES, src)
if n != 1:
    raise SystemExit("!! 期望改 1 处 CORES，实际 %d 处" % n)
print("副本 CORES 改为 %d（%d 处）" % (TEST_CORES, n))

# 3. 注入追踪
TRACE = '''
# ---- injected: modeler call tracing ----
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
    raise SystemExit("!! 主流程标记没找到")
src = src.replace(marker, TRACE + marker, 1)

anchor = """    d, m3d = open_session()
    if d is None:
        sys.exit(1)
"""
if anchor not in src:
    raise SystemExit("!! open_session 锚点没找到")
src = src.replace(anchor, anchor + "    _trace_modeler(m3d)\n", 1)

src = src.replace("# 批量扫描（UNIT=30 版）",
                  "# [%d核测速] 批量扫描（UNIT=30 版）" % TEST_CORES, 1)

with open(DST, "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("script:", DST)

with open(SRC, "r", encoding="utf-8") as f:
    print("真实脚本未被改动:", f.read() == orig)

print()
print("=== 副本里的核数相关行 ===")
for i, line in enumerate(src.splitlines(), 1):
    if re.search(r"\bCORES\s*=", line) or "analyze(cores" in line:
        print("  L%-5d %s" % (i, line.strip()))
print()
print("=== 真实脚本里的核数（应仍为 8） ===")
for i, line in enumerate(orig.splitlines(), 1):
    if re.search(r"^\s*CORES\s*=", line):
        print("  L%-5d %s" % (i, line.strip()))
