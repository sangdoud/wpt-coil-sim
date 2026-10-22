"""为 24 核验证搭一个单点测试环境。

跑的点与 8 核基线完全相同：W=10 G=20 dx=-150 tg=0
（8 核实测：求解 7m23s，墙钟 8m04s）

从**当前**的 batch_sweep_unit30.py（已是 CORES=24）生成副本，
BASE_DIR 指向 _test_run，并注入 modeler 调用追踪。
真实脚本不改动。
"""

import os

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")
SRC = os.path.join(WPT, "batch_sweep_unit30.py")
DST = os.path.join(TEST, "batch_sweep_test.py")

POINT = (10.0, 20.0, -150.0, 0.0, 1000.0)

os.makedirs(TEST, exist_ok=True)

# 单点计划表
plan = os.path.join(TEST, "combos_unit30.csv")
with open(plan, "w", newline="", encoding="utf-8") as f:
    f.write("W_mm,G_mm,dx_mm,tx_gap_mm,mu\n")
    f.write("%s,%s,%s,%s,%s\n" % POINT)
print("plan:", plan, "->", POINT)

# 清掉旧输出
for name in ("sweep_all_unit30.csv", "batch_sweep_unit30.log", "batch.log"):
    p = os.path.join(TEST, name)
    if os.path.exists(p):
        os.remove(p)
        print("cleared:", name)

with open(SRC, "r", encoding="utf-8") as f:
    src = f.read()
orig = src

old = 'BASE_DIR = r"C:/wpt"'
new = 'BASE_DIR = r"C:/wpt/_test_run"'
if old not in src:
    raise SystemExit("!! BASE_DIR 行没找到")
src = src.replace(old, new, 1)

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
                  "# [24核验证] 批量扫描（UNIT=30 版）", 1)

with open(DST, "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("script:", DST)

with open(SRC, "r", encoding="utf-8") as f:
    print("真实脚本未被改动:", f.read() == orig)

# 确认副本里的核数
for i, line in enumerate(src.splitlines(), 1):
    if "CORES = " in line or "analyze(cores" in line:
        print("  L%-5d %s" % (i, line.strip()))
