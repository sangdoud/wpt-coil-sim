# -*- coding: utf-8 -*-
"""对照实验环境：把线圈端子的 Conductor number 从 12 改成 1，跑同一个点。

做法（不碰原模型）：
  1. 复制 Projecttonight.aedt -> _test_run/Projecttonight_cn1.aedt
  2. 只把 'Conductor number'='12' 改成 '1'（恰好 6 处，逐处校验）
  3. 生成测试脚本，PROJECT 指向这个副本
  4. 跑与基线相同的点 W=10 G=20 dx=-150 tg=0

基线（Conductor number=12）：L11 = 3359.2 uH
  若改后 L -> ~23 uH  (即 1/144)  => 匝数被按 N^2 重复计入
  若改后 L -> ~280 uH (即 1/12)   => 只按 N 计入
  若改后 L 几乎不变                => conductor number 对该结果无影响
"""

import os
import re
import shutil

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")
SRC_AEDT = os.path.join(WPT, "Projecttonight.aedt")
DST_AEDT = os.path.join(TEST, "Projecttonight_cn1.aedt")
SRC_SCRIPT = os.path.join(WPT, "batch_sweep_unit30.py")
DST_SCRIPT = os.path.join(TEST, "batch_sweep_test.py")

POINT = (10.0, 20.0, -150.0, 0.0, 1000.0)
OLD = "'Conductor number'='12'"
NEW = "'Conductor number'='1'"

os.makedirs(TEST, exist_ok=True)

# ---------- 1. 复制 aedt ----------
shutil.copyfile(SRC_AEDT, DST_AEDT)
print("copied aedt -> %s  (%d bytes)" % (DST_AEDT, os.path.getsize(DST_AEDT)))

# ---------- 2. 只改 Conductor number ----------
with open(DST_AEDT, "r", encoding="utf-8", errors="surrogateescape") as f:
    txt = f.read()

n_old = txt.count(OLD)
n_new = txt.count(NEW)
print("原文中 %r 出现 %d 次" % (OLD, n_old))
print("原文中 %r 出现 %d 次" % (NEW, n_new))

# 只替换 Coil Terminal 块里的（就是那 6 处）
txt2 = txt.replace(OLD, NEW)
n_after = txt2.count(NEW)
print("替换后 %r 出现 %d 次" % (NEW, n_after))

if n_old != 12:
    print("!! 预期恰好 12 处（2 个 design x 6 个端子），实际 %d 处 —— 停下，不继续" % n_old)
    raise SystemExit(1)

with open(DST_AEDT, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
    f.write(txt2)
print("已改写 Conductor number 12 -> 1 (%d 处)" % n_old)

# 校验：只有这 6 处不同
a, b = txt.splitlines(), txt2.splitlines()
diffs = [i + 1 for i, (x, y) in enumerate(zip(a, b)) if x != y]
print("差异行号: %s   (共 %d 行)" % (diffs, len(diffs)))
print("行数是否一致: %s" % (len(a) == len(b)))

# ---------- 3. 计划表 ----------
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

# ---------- 4. 生成测试脚本 ----------
with open(SRC_SCRIPT, "r", encoding="utf-8") as f:
    src = f.read()
orig = src

old_bd = 'BASE_DIR = r"C:/wpt"'
new_bd = 'BASE_DIR = r"C:/wpt/_test_run"'
if old_bd not in src:
    raise SystemExit("!! BASE_DIR 行没找到")
src = src.replace(old_bd, new_bd, 1)

old_pj = 'PROJECT = r"C:/wpt/Projecttonight.aedt"'
new_pj = 'PROJECT = r"C:/wpt/_test_run/Projecttonight_cn1.aedt"'
if old_pj not in src:
    raise SystemExit("!! PROJECT 行没找到")
src = src.replace(old_pj, new_pj, 1)

# 注入追踪
TRACE = '''
# ---- injected: tracing ----
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
src = src.replace(marker, TRACE + marker, 1)
anchor = """    d, m3d = open_session()
    if d is None:
        sys.exit(1)
"""
if anchor not in src:
    raise SystemExit("!! open_session 锚点没找到")
src = src.replace(anchor, anchor + "    _trace_modeler(m3d)\n", 1)
src = src.replace("# 批量扫描（UNIT=30 版）", "# [conductor=1 对照实验] 批量扫描", 1)

with open(DST_SCRIPT, "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("script:", DST_SCRIPT)

with open(SRC_SCRIPT, "r", encoding="utf-8") as f:
    print("真实脚本未被改动:", f.read() == orig)

print()
print("=== 副本脚本的 PROJECT 行 ===")
for i, line in enumerate(src.splitlines(), 1):
    if re.match(r"\s*PROJECT\s*=", line):
        print("  L%-5d %s" % (i, line.strip()))
