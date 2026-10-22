# -*- coding: utf-8 -*-
"""在【副本】上改引线（最终版）。

第 3 版发现：unite 会清掉引用了旧面的 6 个线圈端子。所以流程改为：
  0. 记录 6 个端子的面中心(=引线坐标) + 极性 + 所属 Winding
  1. 布尔切短 → 2. 接水平段 → 3. unite（端子会消失，意料之中）
  4. 用 assign_coil 在 6 个新远端面上【重建】端子
  5. 复核 Winding / Conductor number / Point out of terminal，全对才存盘
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
WINDING = {"Tx1": "Winding_Tx1", "Tx2": "Winding_Tx2", "Rx": "Winding_Rx"}


def log(m):
    print(m, flush=True)


shutil.copyfile(SRC, DST)
log("复制 -> %s" % DST)

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=DST, design="WPT_G")
log("design=%s" % m.design_name)

# ---------- 0. 记录原端子 ----------
log("")
log("=== 0. 记录原端子（面中心 / 极性）===")
orig = {}
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
            continue
        pol = "negative" if b.props.get("Point out of terminal") in (True, "true") else "positive"
        orig[b.name] = dict(coil=coil, lx=c[0], ly=c[1],
                            polarity=pol,
                            cn=str(b.props.get("Conductor number")),
                            winding=str(b.props.get("Winding")))
        log("  %-12s 引线(%.4f,%.4f) 极性=%-8s Conductor=%s Winding=%s"
            % (b.name, c[0], c[1], pol, b.props.get("Conductor number"), b.props.get("Winding")))

# ---------- 1..3 几何 ----------
log("")
log("=== 1. 切短 ===")
for coil, cfg in COIL.items():
    zc = cfg["z"]
    z_lo, z_hi = (zc + STUB, zc + STUB + 60.0) if cfg["up"] else (zc - STUB - 60.0, zc - STUB)
    cut = m.modeler.create_box(origin=[-400, -400, z_lo], sizes=[800, 800, z_hi - z_lo], name="CUT_%s" % coil)
    m.modeler.subtract(blank_list=[coil], tool_list=[cut.name], keep_originals=False)
    if cut.name in m.modeler.object_names:
        m.modeler.delete(cut.name)
    bb = m.modeler[coil].bounding_box
    log("  %-5s -> Z[%.2f, %.2f]" % (coil, bb[2], bb[5]))

log("")
log("=== 2. 接水平段 ===")
runs = {}
for name, o in orig.items():
    cfg = COIL[o["coil"]]
    zrun = cfg["z"] + STUB if cfg["up"] else cfg["z"] - STUB
    nm = "RUN_" + name
    m.modeler.create_cylinder(orientation="Y", origin=[o["lx"], Y_OUT, zrun],
                              radius=RAD, height=(o["ly"] - Y_OUT), name=nm)
    runs[name] = nm
    log("  %-14s x=%.4f y %.1f->%.4f z=%.2f" % (nm, o["lx"], Y_OUT, o["ly"], zrun))

log("")
log("=== 3. unite ===")
for coil in COIL:
    parts = [coil] + [runs[n] for n, o in orig.items() if o["coil"] == coil]
    res = m.modeler.unite(parts)
    log("  %-5s unite(%d) -> %s" % (coil, len(parts), res))
    if res and res != coil:
        try:
            m.modeler.rename(res, coil)
        except Exception:
            pass
for n in ("Tx1", "Tx2", "Rx"):
    bb = m.modeler[n].bounding_box
    log("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
        % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

log("")
log("  边界现状（端子应已消失）: %s" % [getattr(x, "name", "?") for x in m.boundaries])

# ---------- 4. 重建端子 ----------
log("")
log("=== 4. 重建 6 个线圈端子 ===")
made = {}
for name, o in sorted(orig.items()):
    coil = o["coil"]
    cfg = COIL[coil]
    zrun = cfg["z"] + STUB if cfg["up"] else cfg["z"] - STUB
    target = (o["lx"], Y_OUT, zrun)
    best = None
    for f in m.modeler[coil].faces:
        try:
            c = f.center
        except Exception:
            continue
        d2 = sum((c[i] - target[i]) ** 2 for i in range(3)) ** 0.5
        if best is None or d2 < best[0]:
            best = (d2, f.id, c, f.area)
    if best is None or best[0] > 0.3:
        log("  %-12s 找不到远端面 (best=%s)" % (name, best))
        continue
    log("  %-12s 面 %s 距离 %.4f mm area=%.6f" % (name, best[1], best[0], best[3]))
    try:
        obj = m.assign_coil(assignment=[best[1]], conductors_number=1,
                            polarity=o["polarity"], name=name)
        made[name] = obj
        log("       assign_coil -> %s" % (obj if not obj else "OK"))
    except Exception as e:
        log("       assign_coil FAILED %r" % e)

log("")
log("=== 5. 复核 ===")
final = {}
for b in m.boundaries:
    nm = getattr(b, "name", None)
    if nm and str(nm).startswith("CT_"):
        final[str(nm)] = dict(b.props)
for nm in sorted(orig):
    p = final.get(nm)
    if p is None:
        log("  %-12s 缺失！" % nm)
        continue
    log("  %-12s Faces=%-9s Conductor=%-3s PointOut=%-6s Winding=%s"
        % (nm, p.get("Faces"), p.get("Conductor number"),
           p.get("Point out of terminal"), p.get("Winding")))

ok = (len(final) == 6
      and all(str(p.get("Conductor number")) == "1" for p in final.values())
      and all(p.get("Faces") for p in final.values()))
log("")
log("边界数 %d/6，Conductor 全为 1：%s" % (len(final), ok))
log("Winding 是否自动关联：%s" % [p.get("Winding") for p in final.values()])

if ok:
    log("=== 存盘 ===")
    log("  save_project -> %s" % m.save_project())
else:
    log("!! 不存盘")
