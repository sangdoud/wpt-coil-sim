"""Instrumented reproduction of the geometry-rebuild hang.

Runs the EXACT batch sequence for W=10 G=20 dx=-150 tg=0 (the point that hung),
with every modeler call timestamped and each phase under a watchdog.

The last line printed before the watchdog fires identifies the blocking call.
Does NOT solve anything. Kills AEDT at the end.
"""

import os
import sys
import threading
import time
import traceback

T0 = time.time()
WPT = r"C:\wpt"
sys.path.insert(0, WPT)
os.chdir(WPT)


def log(msg):
    print("[%7.1fs] %s" % (time.time() - T0, msg), flush=True)


import batch_sweep_unit30 as B  # noqa: E402

from ansys.aedt.core import Desktop, Maxwell3d  # noqa: E402


def run_stage(name, fn, timeout):
    box = {}

    def target():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e
            box["tb"] = traceback.format_exc()

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        log("!! %s 超过 %ds 未返回 —— 判定挂死" % (name, timeout))
        B.kill_aedt()
        return "HANG", None
    if "e" in box:
        log("!! %s 异常: %s" % (name, repr(box["e"])[:200]))
        log("   " + (box.get("tb") or "").strip().replace("\n", " | ")[-400:])
        return "ERR", None
    return "OK", box.get("v")


def trace_modeler(mdl):
    traced = []
    for n in ("create_box", "delete", "move", "subtract", "create_region",
              "unite", "sweep_along_vector", "create_object_from_edge"):
        orig = getattr(mdl, n, None)
        if orig is None or not callable(orig):
            continue

        def mk(name, fn):
            def w(*a, **k):
                t = time.time()
                log("      -> modeler.%s" % name)
                r = fn(*a, **k)
                log("      <- modeler.%s   %.2fs" % (name, time.time() - t))
                return r
            return w

        try:
            setattr(mdl, n, mk(n, orig))
            traced.append(n)
        except Exception as e:
            log("   (无法 hook %s: %s)" % (n, repr(e)[:60]))
    log("  modeler hooked: %s" % ", ".join(traced))


# ---------------- Phase A: session ----------------
def _open():
    dd = Desktop(version=B.AEDT_VERSION, new_desktop=True,
                 non_graphical=False, close_on_exit=False)
    mm = Maxwell3d(project=B.PROJECT, design=B.DESIGN)
    return dd, mm


log("=== Phase A: 启动 AEDT 并打开工程 ===")
st, v = run_stage("open session", _open, 300)
if st != "OK":
    log("会话建立失败，终止")
    sys.exit(1)
d, m = v
log("  solution_type = %s" % m.solution_type)
log("  objects = %d" % len(m.modeler.object_names))

trace_modeler(m.modeler)

W, G, dx, tg = 10.0, 20.0, -150.0, 0.0
log("=== 复现批次序列: W=%.0f G=%.0f dx=%.0f tg=%.0f ===" % (W, G, dx, tg))

log("--- Phase B1: set_rx_dx(0) ---")
st, _ = run_stage("set_rx_dx(0)", lambda: B.set_rx_dx(m, 0.0), 120)
log("  -> %s" % st)

log("--- Phase B2: set_tx_gap(0) ---")
st, _ = run_stage("set_tx_gap(0)", lambda: B.set_tx_gap(m, 0.0), 120)
log("  -> %s" % st)

log("--- Phase C: rebuild_ferrite(10,20,0) ---")
st, nf = run_stage("rebuild_ferrite", lambda: B.rebuild_ferrite(m, W, G, tg), 600)
log("  -> %s  nf=%s" % (st, nf))
if st == "HANG":
    log("### 挂死在 rebuild_ferrite，见上方最后一条 modeler 调用")
    sys.exit(2)

log("--- Phase D: ensure_region (逐对象插桩) ---")


def _region_traced():
    objs = [o for o in m.modeler.object_names if o != "Region"]
    log("    ensure_region: 需遍历 %d 个对象" % len(objs))
    bb = None
    for i, o in enumerate(objs):
        t = time.time()
        try:
            b = m.modeler[o].bounding_box
        except Exception as e:
            log("    bb[%02d] %-22s 异常 %s" % (i, o, repr(e)[:70]))
            continue
        log("    bb[%02d] %-22s %.3fs" % (i, o, time.time() - t))
        if bb is None:
            bb = list(b)
        else:
            bb[0] = min(bb[0], b[0]); bb[1] = min(bb[1], b[1]); bb[2] = min(bb[2], b[2])
            bb[3] = max(bb[3], b[3]); bb[4] = max(bb[4], b[4]); bb[5] = max(bb[5], b[5])
    if bb is None:
        log("    bb 为空")
        return None
    try:
        rbb = m.modeler["Region"].bounding_box
        if rbb[0] <= bb[0] - 20.0 and rbb[3] >= bb[3] + 20.0:
            log("    Region 余量充足，跳过重建")
            return rbb
        log("    Region 余量不足，需重建")
    except Exception as e:
        log("    Region bb 异常: %s" % repr(e)[:80])
    log("    删除 Region ...")
    m.modeler.delete("Region")
    time.sleep(1)
    log("    create_region ...")
    m.modeler.create_region(pad_value=["50mm", "50mm", "50mm", "50mm", "0mm", "0mm"])
    rbb = m.modeler["Region"].bounding_box
    log("    Region 重建: X[%.1f, %.1f]" % (rbb[0], rbb[3]))
    return rbb


st, rbb = run_stage("ensure_region", _region_traced, 300)
log("  -> %s" % st)
if st == "HANG":
    log("### 挂死在 ensure_region，见上方最后一步")

log("--- Phase E: set_rx_dx(-150) ---")
st, _ = run_stage("set_rx_dx(-150)", lambda: B.set_rx_dx(m, dx), 120)
log("  -> %s" % st)

log("DIAG COMPLETE")
B.kill_aedt()
log("AEDT killed")
