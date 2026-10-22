# -*- coding: utf-8 -*-
"""在【副本】上改引线（第 3 版，最终）。

关键修正：
  * FacePrimitive.center 单位 = mm，area 单位 = mm²
  * 引线的真实 (x,y) 直接取【端子面中心】，不再用 bbox 推算（之前差 0.625mm）
  * 每根引线的水平段建在它自己的 x 上，端子换到它自己的远端面

顺序：
  0. 读 6 个端子面中心 -> 得到 6 根引线的 (x,y)
  1. 布尔切短（Tx 切 z<-3，Rx 切 z>33）
  2. 在每个 (x,y) 接水平段到 y=-120
  3. unite 回线圈
  4. 每个端子换到对应水平段的远端面
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


def log(m):
    print(m, flush=True)


shutil.copyfile(SRC, DST)
log("复制 -> %s" % DST)

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=DST, design="WPT_G")
log("design=%s" % m.design_name)

# ---------- 0. 从端子面中心读引线坐标 ----------
log("")
log("=== 0. 读端子面中心（mm）===")
leads = {}          # name -> (coil, lx, ly)
for coil in COIL:
    fac = {}
    for f in m.modeler[coil].faces:
        try:
            fac[f.id] = f.center
        except Exception:
            pass
    for b in m.boundaries:
        if not b.name.startswith("CT_" + coil + "_"):
            continue
        fid = b.props.get("Faces", [None])[0]
        c = fac.get(fid)
        if c is None:
            log("  %-12s face=%s 取不到中心" % (b.name, fid))
            continue
        leads[b.name] = (coil, c[0], c[1])
        log("  %-12s face=%-6s center=(%.4f, %.4f, %.4f)  -> 引线 (%.4f, %.4f)"
            % (b.name, fid, c[0], c[1], c[2], c[0], c[1]))

# ---------- 1. 切短 ----------
log("")
log("=== 1. 布尔切短 ===")
for coil, cfg in COIL.items():
    zc = cfg["z"]
    z_lo, z_hi = (zc + STUB, zc + STUB + 60.0) if cfg["up"] else (zc - STUB - 60.0, zc - STUB)
    cut = m.modeler.create_box(origin=[-400, -400, z_lo], sizes=[800, 800, z_hi - z_lo], name="CUT_%s" % coil)
    m.modeler.subtract(blank_list=[coil], tool_list=[cut.name], keep_originals=False)
    if cut.name in m.modeler.object_names:
        m.modeler.delete(cut.name)
    bb = m.modeler[coil].bounding_box
    log("  %-5s -> Z[%.2f, %.2f]   (x 中心 %.2f)" % (coil, bb[2], bb[5], (bb[0] + bb[3]) / 2))

# ---------- 2. 接水平段 ----------
log("")
log("=== 2. 接水平段到 y=%.0f ===" % Y_OUT)
runs = {}
for name, (coil, lx, ly) in leads.items():
    cfg = COIL[coil]
    zrun = cfg["z"] + STUB if cfg["up"] else cfg["z"] - STUB
    nm = "RUN_" + name
    try:
        m.modeler.create_cylinder(orientation="Y", origin=[lx, Y_OUT, zrun],
                                  radius=RAD, height=(ly - Y_OUT), name=nm)
        runs[name] = nm
        log("  %-14s x=%.4f  y %.1f -> %.4f  z=%.2f  长 %.2f" % (nm, lx, Y_OUT, ly, zrun, ly - Y_OUT))
    except Exception as e:
        log("  %s FAILED %r" % (nm, e))

# ---------- 3. unite ----------
log("")
log("=== 3. unite ===")
for coil in COIL:
    parts = [coil] + [runs[n] for n, (c, _, _) in leads.items()
                      if c == coil and runs.get(n) in m.modeler.object_names]
    if len(parts) < 2:
        log("  %-5s 部件不足 %s" % (coil, parts))
        continue
    res = m.modeler.unite(parts)
    log("  %-5s unite(%d 个) -> %s" % (coil, len(parts), res))
    if res and res != coil:
        try:
            m.modeler.rename(res, coil)
        except Exception as e:
            log("    rename FAILED %r" % e)

for n in ("Tx1", "Tx2", "Rx"):
    bb = m.modeler[n].bounding_box
    log("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
        % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

# ---------- 4. 端子换面 ----------
log("")
log("=== 4. 端子换到自己的远端面 ===")
# unite 之后 pyAEDT 的边界缓存可能过期，重新取一次
bnd = list(m.boundaries)
log("  当前边界: %s" % [getattr(x, "name", "?") for x in bnd])
by_name = {}
for x in bnd:
    try:
        by_name[str(x.name).strip()] = x
    except Exception:
        pass

done = 0
for name, (coil, lx, ly) in sorted(leads.items()):
    cfg = COIL[coil]
    zrun = cfg["z"] + STUB if cfg["up"] else cfg["z"] - STUB
    target = (lx, Y_OUT, zrun)
    best = None
    for f in m.modeler[coil].faces:
        try:
            c = f.center
        except Exception:
            continue
        d2 = sum((c[i] - target[i]) ** 2 for i in range(3)) ** 0.5
        if best is None or d2 < best[0]:
            best = (d2, f.id, c, f.area)
    if best is None:
        log("  %-12s 没找到任何面" % name)
        continue
    log("  %-12s 目标(%.3f,%.1f,%.2f)  最近面 %s 距离 %.4f mm  area=%.6f"
        % (name, target[0], target[1], target[2], best[1], best[0], best[3]))
    if best[0] > 0.3:
        log("       !! 距离过大，跳过")
        continue
    b = by_name.get(name.strip())
    if b is None:
        log("       !! 边界列表里没有 %r；现有: %s" % (name, sorted(by_name)))
        continue
    b.props["Faces"] = [best[1]]
    ok = b.update()
    got = b.props.get("Faces")
    good = bool(got) and got[0] == best[1]
    if good:
        done += 1
    log("       -> face=%s update=%s Winding=%s Conductor=%s %s"
        % (got, ok, b.props.get("Winding"), b.props.get("Conductor number"),
           "OK" if good else "<== 未生效"))

log("")
log("成功换面 %d / 6" % done)
if done == 6:
    log("=== 存盘 ===")
    log("  save_project -> %s" % m.save_project())
else:
    log("!! 不存盘")
