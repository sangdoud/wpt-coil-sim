# -*- coding: utf-8 -*-
"""在【副本】上改引线（第 2 版）——修正端子换面。

上一版几何全对，只是端子换面失败：FacePrimitive.center / area 的单位不是 mm。
这一版：
  * 改动前先从原端子的面中心反推「该端子在哪根引线上」
  * 换面时同时按 mm 与 m 两种尺度匹配，取最近的面（单位无关）
  * 打印候选面用于诊断
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
COIL = {"Tx1": dict(z=0.0, up=False), "Tx2": dict(z=0.0, up=False), "Rx": dict(z=30.0, up=True)}
LEAD_XY0 = {
    "Tx1": [(-56.00, -15.00), (-2.36, -71.87)],
    "Tx2": [(116.00, -15.00), (169.64, -71.87)],
    "Rx":  [(30.00, -15.00), (83.64, -71.87)],
}
CX_REF = {"Tx1": -86.0, "Tx2": 86.0, "Rx": 0.0}


def log(m):
    print(m, flush=True)


d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=DST, design="WPT_G")
log("design=%s" % m.design_name)

# ---------- 0. 记录端子 -> 哪根引线 ----------
log("")
log("=== 0. 反推每个端子在哪个引出点上（改动前）===")
term_lead = {}
for coil in COIL:
    bb = m.modeler[coil].bounding_box
    dx = (bb[0] + bb[3]) / 2.0 - CX_REF[coil]
    pts = [(x + dx, y) for (x, y) in LEAD_XY0[coil]]
    fac = {}
    for f in m.modeler[coil].faces:
        try:
            fac[f.id] = (f.center, f.area)
        except Exception:
            pass
    for b in m.boundaries:
        if not b.name.startswith("CT_" + coil + "_"):
            continue
        fid = b.props.get("Faces", [None])[0]
        c = fac.get(fid, (None, None))[0]
        which = None
        if c is not None:
            for si, sc in ((0, 1.0), (1, 1000.0)):
                cx, cy = c[0] * sc, c[1] * sc
                for i, (px, py) in enumerate(pts):
                    if abs(cx - px) < 0.1 and abs(cy - py) < 0.1:
                        which = i
            log("  %-12s face=%-6s center=%s (x1000=%s)  -> 引出点 #%s"
                % (b.name, fid, tuple(round(v, 4) for v in c) if c else None,
                   tuple(round(v * 1000, 2) for v in c) if c else None, which))
        else:
            log("  %-12s face=%-6s 找不到面中心" % (b.name, fid))
        term_lead[b.name] = (coil, which, pts)
    log("  %-5s 引出点: %s" % (coil, [(round(a, 2), round(b, 2)) for a, b in pts]))

log("")
log("=== 面中心/面积单位抽查（螺旋某个面）===")
for coil in ("Tx1",):
    for f in list(m.modeler[coil].faces)[:4]:
        try:
            log("  %-5s face %-7s center=%s area=%s"
                % (coil, f.id, tuple(round(v, 5) for v in f.center), f.area))
        except Exception as e:
            log("  err %r" % e)

# ---------- 1. 切短 ----------
log("")
log("=== 1. 布尔切短 ===")
for coil, cfg in COIL.items():
    zc = cfg["z"]
    z_lo, z_hi = (zc + STUB, zc + STUB + 60.0) if cfg["up"] else (zc - STUB - 60.0, zc - STUB)
    try:
        cut = m.modeler.create_box(origin=[-400, -400, z_lo], sizes=[800, 800, z_hi - z_lo], name="CUT_%s" % coil)
        m.modeler.subtract(blank_list=[coil], tool_list=[cut.name], keep_originals=False)
        if cut.name in m.modeler.object_names:
            m.modeler.delete(cut.name)
        bb = m.modeler[coil].bounding_box
        log("  %-5s -> Z[%.2f, %.2f]" % (coil, bb[2], bb[5]))
    except Exception as e:
        log("  %-5s FAILED %r" % (coil, e))

# ---------- 2. 接水平段 ----------
log("")
log("=== 2. 接水平段 ===")
runs = {}
for coil, cfg in COIL.items():
    zrun = cfg["z"] + STUB if cfg["up"] else cfg["z"] - STUB
    bb = m.modeler[coil].bounding_box
    dx = (bb[0] + bb[3]) / 2.0 - CX_REF[coil]
    pts = [(x + dx, y) for (x, y) in LEAD_XY0[coil]]
    made = []
    for i, (x, y) in enumerate(pts):
        nm = "RUN_%s_%s" % (coil, "a" if i == 0 else "b")
        try:
            m.modeler.create_cylinder(orientation="Y", origin=[x, Y_OUT, zrun],
                                      radius=RAD, height=(y - Y_OUT), name=nm)
            made.append((i, nm, x, zrun))
            log("  %-10s x=%.2f y %.1f->%.1f z=%.2f" % (nm, x, Y_OUT, y, zrun))
        except Exception as e:
            log("  %s FAILED %r" % (nm, e))
    runs[coil] = made

# ---------- 3. unite ----------
log("")
log("=== 3. unite ===")
for coil, made in runs.items():
    parts = [coil] + [n for (_, n, _, _) in made if n in m.modeler.object_names]
    if len(parts) < 2:
        log("  %-5s 部件不足" % coil)
        continue
    res = m.modeler.unite(parts)
    log("  %-5s unite -> %s" % (coil, res))
    if res and res != coil:
        try:
            m.modeler.rename(res, coil)
        except Exception as e:
            log("    rename FAILED %r" % e)

for n in ("Tx1", "Tx2", "Rx"):
    bb = m.modeler[n].bounding_box
    log("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
        % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

# ---------- 4. 换面（单位无关匹配） ----------
log("")
log("=== 4. 端子换到水平段远端面 ===")
done = 0
for name in sorted(term_lead):
    coil, which, pts = term_lead[name]
    cfg = COIL[coil]
    zrun = cfg["z"] + STUB if cfg["up"] else cfg["z"] - STUB
    if which is None:
        log("  %-12s 无法确定引出点，跳过" % name)
        continue
    x = pts[which][0]
    target = (x, Y_OUT, zrun)
    cands = []
    for f in m.modeler[coil].faces:
        try:
            c = f.center
            a = f.area
        except Exception:
            continue
        for sc in (1.0, 1000.0):
            d2 = sum((c[i] * sc - target[i]) ** 2 for i in range(3)) ** 0.5
            cands.append((d2, f.id, tuple(round(v, 4) for v in c), sc, a))
    cands.sort(key=lambda q: q[0])
    log("  %-12s 目标 %s  最近 3 个面:" % (name, tuple(round(v, 2) for v in target)))
    for d2, fid, c, sc, a in cands[:3]:
        log("       face %-7s center=%-28s scale=%-6.0f area=%-12s 距离=%.3f"
            % (fid, c, sc, a, d2))
    best = cands[0]
    if best[0] > 0.5:
        log("       !! 最近面距离 %.3f 太大，跳过" % best[0])
        continue
    b = next((x2 for x2 in m.boundaries if x2.name == name), None)
    b.props["Faces"] = [best[1]]
    try:
        ok = b.update()
        got = b.props.get("Faces")
        if got and got[0] == best[1]:
            done += 1
        log("       -> face=%s update=%s Winding=%s Conductor=%s %s"
            % (got, ok, b.props.get("Winding"), b.props.get("Conductor number"),
               "OK" if (got and got[0] == best[1]) else "<== 未生效"))
    except Exception as e:
        log("       update FAILED %r" % e)

log("")
log("成功换面: %d / 6" % done)
if done == 6:
    log("=== 存盘 ===")
    log("  save_project -> %s" % m.save_project())
else:
    log("!! 不存盘")
