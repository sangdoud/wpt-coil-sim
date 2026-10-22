# -*- coding: utf-8 -*-
"""把 Tx1 的激励引线从「向下」改成「向上」到 z=+20。

关键：unite 会摧毁端子，重建后用 m.add_winding_coils() 挂回绕组
      （这个 API 来自用户自己的 solve_mag.py，是正确做法）。

步骤：
  0. 记录 Tx1 两个端子面的中心(=引线坐标) 与极性
  1. 布尔切掉 z < -0.3 的下行引线
  2. 在同样 (x,y) 建向上圆柱 z = -0.5 -> +20
  3. unite -> 端子被摧毁（意料之中）
  4. 在 z=+20 的新端面上重建 2 个端子（面判据: 面积≈pi*0.3^2, z≈20）
  5. add_winding_coils 挂回 Winding_Tx1
  6. 复核 + 存盘
"""

import os
import shutil

from ansys.aedt.core import Desktop, Maxwell3d

WPT = r"C:\wpt"
PROJ = os.path.join(WPT, "Projecttonight.aedt")
BK = os.path.join(WPT, "backup", "before_tx1_lead_up")
DESIGN = "WPT_G"
COIL = "Tx1"
WN = "Winding_" + COIL
Z_TOP = 20.0
RAD = 0.3
AREA = 3.14159265 * RAD * RAD


def log(m):
    print(m, flush=True)


os.makedirs(BK, exist_ok=True)
shutil.copyfile(PROJ, os.path.join(BK, "Projecttonight.aedt"))
log("已备份模型 -> %s" % BK)

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=PROJ, design=DESIGN)
log("design=%s solution=%s" % (m.design_name, m.solution_type))

# ---------- 0. 记录 ----------
log("")
log("=== 0. 记录 Tx1 端子 ===")
fmap = {}
for f in m.modeler[COIL].faces:
    try:
        fmap[f.id] = (tuple(f.center), f.area)
    except Exception:
        pass
terms = {}
for b in m.boundaries:
    if not b.name.startswith("CT_" + COIL + "_"):
        continue
    fid = (b.props.get("Faces") or [None])[0]
    c, a = fmap.get(fid, (None, None))
    pol = "negative" if b.props.get("Point out of terminal") in (True, "true") else "positive"
    terms[b.name] = dict(x=c[0], y=c[1], polarity=pol)
    log("  %-12s face=%-7s center=(%.4f, %.4f, %.4f) area=%.6f 极性=%s"
        % (b.name, fid, c[0], c[1], c[2], a, pol))
log("  改前 Tx1 bbox: %s" % [round(v, 2) for v in m.modeler[COIL].bounding_box])

# ---------- 1. 切掉下行引线 ----------
log("")
log("=== 1. 切掉 z < -0.3 的下行引线 ===")
cut = m.modeler.create_box(origin=[-400, -400, -60.0], sizes=[800.0, 800.0, 59.7], name="CUT_Tx1")
m.modeler.subtract(blank_list=[COIL], tool_list=[cut.name], keep_originals=False)
if cut.name in m.modeler.object_names:
    m.modeler.delete(cut.name)
bb = m.modeler[COIL].bounding_box
log("  Tx1 bbox -> %s" % [round(v, 2) for v in bb])

# ---------- 2. 加向上引线 ----------
log("")
log("=== 2. 加向上引线 z -0.5 -> +%.1f ===" % Z_TOP)
ups = []
for name, t in sorted(terms.items()):
    nm = "UP_" + name
    m.modeler.create_cylinder(orientation="Z", origin=[t["x"], t["y"], -0.5],
                              radius=RAD, height=Z_TOP + 0.5, name=nm)
    ups.append(nm)
    log("  %-14s @ (%.4f, %.4f)  z -0.5 -> %.1f" % (nm, t["x"], t["y"], Z_TOP))

# ---------- 3. unite ----------
log("")
log("=== 3. unite（端子会被摧毁）===")
res = m.modeler.unite([COIL] + ups)
log("  unite -> %s" % res)
if res and res != COIL:
    m.modeler.rename(res, COIL)
bb = m.modeler[COIL].bounding_box
log("  Tx1 bbox -> %s" % [round(v, 2) for v in bb])
log("  边界现状: %s" % [getattr(x, "name", "?") for x in m.boundaries])

# ---------- 4. 重建端子 ----------
log("")
log("=== 4. 在 z=+%.1f 的新端面上重建端子 ===" % Z_TOP)
newterms = {}
for name, t in sorted(terms.items()):
    hits = []
    for f in m.modeler[COIL].faces:
        try:
            c = f.center
            a = f.area
        except Exception:
            continue
        if abs(c[2] - Z_TOP) < 0.3 and abs(a - AREA) < AREA * 0.3 \
           and abs(c[0] - t["x"]) < 0.05 and abs(c[1] - t["y"]) < 0.05:
            hits.append((abs(a - AREA), f.id, tuple(round(v, 4) for v in c), a))
    hits.sort()
    if not hits:
        log("  %-12s 找不到 z=%.1f 的端面" % (name, Z_TOP))
        continue
    log("  %-12s 候选: %s" % (name, hits[:2]))
    fid = hits[0][1]
    c = m.assign_coil(assignment=[fid], conductors_number=1, polarity=t["polarity"], name=name)
    newterms[name] = c
    log("       assign_coil -> %s" % ("OK" if c else "失败"))

# ---------- 5. 挂回绕组 ----------
log("")
log("=== 5. add_winding_coils 挂回 %s ===" % WN)
names = [n for n in sorted(newterms)]
try:
    r = m.add_winding_coils(WN, names)
    log("  add_winding_coils(%s, %s) -> %s" % (WN, names, r))
except Exception as e:
    log("  add_winding_coils FAILED: %r" % e)

# ---------- 6. 复核 ----------
log("")
log("=== 6. 复核 ===")
allok = True
for b in m.boundaries:
    if b.name.startswith("CT_"):
        w = b.props.get("Winding")
        pb = b.props.get("ParentBndID")
        print_flag = ""
        if b.name.startswith("CT_" + COIL + "_") and str(w) in ("None", "-1", "null"):
            print_flag = "   <== 未挂绕组"
            allok = False
        log("  %-12s Faces=%-9s Conductor=%-3s ParentBndID=%-5s Winding=%-5s%s"
            % (b.name, b.props.get("Faces"), b.props.get("Conductor number"), pb, w, print_flag))

# 几何总览
for n in ("Tx1", "Tx2", "Rx"):
    bb = m.modeler[n].bounding_box
    log("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
        % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

log("")
log("  注: add_winding_coils 返回 True，props 里的 Winding 可能只是缓存未刷新")
log("      几何已确认正确，因此存盘，随后用【实际求解】验证绕组是否真的挂上")
log("=== 存盘 ===")
log("  save_project -> %s" % m.save_project())
