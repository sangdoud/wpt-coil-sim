# -*- coding: utf-8 -*-
"""在【副本】上改引线：布尔切短 + 接水平段。

思路（避免重建螺旋）：
  1. 用一个大盒子把 z < -3（Tx）/ z > 33（Rx）的引线段【减掉】
     —— 螺旋在 z=-0.25~0.25（Tx）/ 29.75~30.25（Rx），不受影响
  2. 在 z=-3（Tx）/ z=33（Rx）平面内，从原引线位置沿 -Y 接水平段到 y=-120
  3. unite 回线圈
  4. 把 6 个线圈端子的 Faces 改到水平段远端面（b.update() 已证实会保留 Winding）
"""

import os
import shutil

from ansys.aedt.core import Desktop, Maxwell3d

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")
SRC = os.path.join(WPT, "Projecttonight.aedt")
DST = os.path.join(TEST, "Projecttonight_newlead.aedt")

Y_OUT = -120.0
STUB = 3.0
RAD = 0.3
# 线圈 z, 引线方向(+1 向上 / -1 向下), 切割盒 z 范围
COIL = {
    "Tx1": dict(z=0.0, up=False),
    "Tx2": dict(z=0.0, up=False),
    "Rx":  dict(z=30.0, up=True),
}


def log(m):
    print(m, flush=True)


os.makedirs(TEST, exist_ok=True)
shutil.copyfile(SRC, DST)
log("复制 -> %s" % DST)

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=DST, design="WPT_G")
log("design=%s" % m.design_name)

terms = {}
for b in m.boundaries:
    if b.name.startswith("CT_"):
        terms[b.name] = dict(b.props)
log("端子 %d 个: %s" % (len(terms), sorted(terms)))

log("")
log("=== 改前 ===")
for n in ("Tx1", "Tx2", "Rx"):
    bb = m.modeler[n].bounding_box
    log("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
        % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

# ---------- 1. 找出引线的 (x, y) ----------
# 引线在螺旋的 x 范围内，但 Z 方向伸出很远。用「线圈 bbox 的 z 极值」处的截面判断。
# 更稳的做法：从 .aedt 已知的 6 个引出点（与 z 无关，纯 x,y）
LEAD_XY = {
    "Tx1": [(-56.00, -15.00), (-2.36, -71.87)],
    "Tx2": [(116.00, -15.00), (169.64, -71.87)],
    "Rx":  [(30.00, -15.00), (83.64, -71.87)],
}
# 但线圈被移动过，需要按当前 bbox 中心校正
for coil, pts in LEAD_XY.items():
    bb = m.modeler[coil].bounding_box
    # 螺旋理论 x 中心 = 当前 bbox 的 x 中心（引线在 bbox 内部）
    cx_now = (bb[0] + bb[3]) / 2.0
    # 原始螺旋中心（build 时）: Tx1/Tx2 = ∓86, Rx = 0
    cx_ref = {"Tx1": -86.0, "Tx2": 86.0, "Rx": 0.0}[coil]
    dx = cx_now - cx_ref
    LEAD_XY[coil] = [(x + dx, y) for (x, y) in pts]
    log("  %-5s bbox x 中心 %.2f (参考 %.2f, 位移 %+.2f) -> 引线 %s"
        % (coil, cx_now, cx_ref, dx, [(round(a, 2), round(b, 2)) for a, b in LEAD_XY[coil]]))

# ---------- 2. 布尔切短引线 ----------
log("")
log("=== 2. 布尔切短引线 ===")
for coil, cfg in COIL.items():
    zc = cfg["z"]
    if cfg["up"]:
        z_lo, z_hi = zc + STUB, zc + STUB + 60.0
    else:
        z_lo, z_hi = zc - STUB - 60.0, zc - STUB
    try:
        cut = m.modeler.create_box(origin=[-400, -400, z_lo], sizes=[800, 800, z_hi - z_lo], name="CUT_%s" % coil)
        m.modeler.subtract(blank_list=[coil], tool_list=[cut.name], keep_originals=False)
        if cut.name in m.modeler.object_names:
            m.modeler.delete(cut.name)
        bb = m.modeler[coil].bounding_box
        log("  %-5s 切掉 z 外于 [%.1f, %.1f] 的部分 -> 现在 Z[%.2f, %.2f]"
            % (coil, z_lo, z_hi, bb[2], bb[5]))
    except Exception as e:
        log("  %-5s 切割 FAILED: %r" % (coil, e))

# ---------- 3. 接水平段 ----------
log("")
log("=== 3. 接水平段（沿 -Y 到 y=%.0f）===")
newruns = {}
for coil, cfg in COIL.items():
    zc = cfg["z"]
    zrun = zc + STUB if cfg["up"] else zc - STUB
    made = []
    for i, (x, y) in enumerate(LEAD_XY[coil]):
        tag = "a" if i == 0 else "b"
        nm = "RUN_%s_%s" % (coil, tag)
        try:
            m.modeler.create_cylinder(orientation="Y", origin=[x, Y_OUT, zrun],
                                      radius=RAD, height=(y - Y_OUT), name=nm)
            made.append(nm)
            log("  %-10s x=%.2f  y %.1f -> %.1f  z=%.2f" % (nm, x, Y_OUT, y, zrun))
        except Exception as e:
            log("  %s FAILED %r" % (nm, e))
    newruns[coil] = made

# ---------- 4. unite ----------
log("")
log("=== 4. unite 回线圈 ===")
for coil, runs in newruns.items():
    parts = [coil] + [n for n in runs if n in m.modeler.object_names]
    if len(parts) < 2:
        log("  %-5s 部件不足 %s" % (coil, parts))
        continue
    try:
        res = m.modeler.unite(parts)
        log("  %-5s unite -> %s" % (coil, res))
        if res and res != coil:
            try:
                m.modeler.rename(res, coil)
                log("        rename -> %s" % coil)
            except Exception as e:
                log("        rename FAILED %r" % e)
    except Exception as e:
        log("  %-5s unite FAILED %r" % (coil, e))

log("")
log("=== unite 后 ===")
for n in ("Tx1", "Tx2", "Rx"):
    if n in m.modeler.object_names:
        bb = m.modeler[n].bounding_box
        log("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
            % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

# ---------- 5. 端子改到新端面 ----------
log("")
log("=== 5. 端子改面 ===")
done = 0
for name in sorted(terms):
    coil = name.split("_")[1]
    cfg = COIL[coil]
    zrun = cfg["z"] + STUB if cfg["up"] else cfg["z"] - STUB
    want = None
    for f in m.modeler[coil].faces:
        try:
            c = f.center
            a = f.area
        except Exception:
            continue
        if abs(c[1] - Y_OUT) < 0.05 and abs(c[2] - zrun) < 0.2 and a < 1e-6:
            want = f.id
            break
    if want is None:
        log("  %-12s 未找到 y=%.0f z=%.1f 的端面" % (name, Y_OUT, zrun))
        continue
    b = next((x for x in m.boundaries if x.name == name), None)
    if b is None:
        log("  %-12s 找不到端子对象" % name)
        continue
    b.props["Faces"] = [want]
    try:
        ok = b.update()
        got = b.props.get("Faces")
        good = got and got[0] == want
        if good:
            done += 1
        log("  %-12s face=%s update=%s Winding=%s Conductor=%s %s"
            % (name, got, ok, b.props.get("Winding"), b.props.get("Conductor number"),
               "OK" if good else "<== 未生效"))
    except Exception as e:
        log("  %-12s update FAILED %r" % (name, e))

log("")
log("成功换面的端子: %d / 6" % done)
if done == 6:
    log("=== 存盘 ===")
    log("  save_project -> %s" % m.save_project())
else:
    log("!! 未全部成功，不存盘")
