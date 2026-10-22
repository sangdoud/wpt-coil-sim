# -*- coding: utf-8 -*-
"""在副本上跑一个点：新引线 + 无铁氧体开孔，与基线 23.328 uH 对比。

生成 _test_run/batch_sweep_test.py：
  * BASE_DIR  -> _test_run
  * PROJECT   -> _test_run/Projecttonight_newlead.aedt
  * 【删除】rebuild_ferrite 里的 aux_hole 开孔逻辑（新引线不再穿铁氧体）
  * 注入 modeler 追踪
"""

import os
import re

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")
SRC = os.path.join(WPT, "batch_sweep_unit30.py")
DST = os.path.join(TEST, "batch_sweep_test.py")
POINT = (10.0, 20.0, -150.0, 0.0, 1000.0)

os.makedirs(TEST, exist_ok=True)

plan = os.path.join(TEST, "combos_unit30.csv")
with open(plan, "w", newline="", encoding="utf-8") as f:
    f.write("W_mm,G_mm,dx_mm,tx_gap_mm,mu\n")
    f.write("%s,%s,%s,%s,%s\n" % POINT)
print("plan:", POINT)

for n in ("sweep_all_unit30.csv", "batch_sweep_unit30.log", "batch.log"):
    p = os.path.join(TEST, n)
    if os.path.exists(p):
        os.remove(p)
        print("cleared:", n)

with open(SRC, "r", encoding="utf-8") as f:
    src = f.read()
orig = src

# 1. 隔离
src = src.replace('BASE_DIR = r"C:/wpt"', 'BASE_DIR = r"C:/wpt/_test_run"', 1)
src = src.replace('PROJECT = r"C:/wpt/Projecttonight.aedt"',
                  'PROJECT = r"C:/wpt/_test_run/Projecttonight_newlead.aedt"', 1)

# 2. 删掉 aux_hole 开孔段
start_mark = "    # 开孔：引线穿过铁氧体"
end_mark = "    return len(ferr)"
i0 = src.find(start_mark)
i1 = src.find(end_mark, i0)
if i0 < 0 or i1 < 0:
    raise SystemExit("!! 找不到开孔段 (i0=%s i1=%s)" % (i0, i1))
removed = src[i0:i1]
src = src[:i0] + src[i1:]
print("已删除开孔逻辑 %d 字符 / %d 行" % (len(removed), removed.count(chr(10))))
print("删除片段首行:", removed.splitlines()[0].strip())
print("删除片段末行:", removed.splitlines()[-1].strip())

# 3. 追踪
TRACE = '''
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
        _o = getattr(mdl, _n, None)
        if _o is None or not callable(_o):
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
            setattr(mdl, _n, _mk(_n, _o))
            hooked.append(_n)
        except Exception:
            pass
    _trace_log("modeler hooked: %s" % ",".join(hooked))


'''
mk = "# ============ 主流程 ============"
src = src.replace(mk, TRACE + mk, 1)
anchor = """    d, m3d = open_session()
    if d is None:
        sys.exit(1)
"""
src = src.replace(anchor, anchor + "    _trace_modeler(m3d)\n", 1)
src = src.replace("# 批量扫描（UNIT=30 版）", "# [新引线测试] 批量扫描", 1)

with open(DST, "w", encoding="utf-8", newline="") as f:
    f.write(src)
print("script:", DST)

with open(SRC, "r", encoding="utf-8") as f:
    print("真实脚本未被改动:", f.read() == orig)

print()
print("=== 副本关键行 ===")
for i, line in enumerate(src.splitlines(), 1):
    if re.match(r"\s*(PROJECT|BASE_DIR|CORES)\s*=", line) or "aux_hole" in line:
        print("  L%-5d %s" % (i, line.strip()))
