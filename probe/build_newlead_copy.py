# -*- coding: utf-8 -*-
"""在【副本】上把 6 根引线改成「短竖直 3mm + 水平沿 -Y 引出」，并重新指派线圈端子。

不动正式模型。验证不过就不存盘。

步骤（每个线圈）：
  1. separate_bodies 把螺旋与 2 根引线拆开
  2. 按 z 跨度认引线（螺旋约 0.5mm，引线约 45mm），删掉
  3. 在引线原接入点建：竖直 3mm + 水平沿 -Y 到 y=-150
  4. unite 回一个对象，改回原线圈名
  5. 把 2 个线圈端子的 Faces 改到新引线的远端面
"""

import os
import shutil

from ansys.aedt.core import Desktop, Maxwell3d

WPT = r"C:\wpt"
TEST = os.path.join(WPT, "_test_run")
SRC = os.path.join(WPT, "Projecttonight.aedt")
DST = os.path.join(TEST, "Projecttonight_newlead.aedt")

Y_OUT = -150.0
STUB = 3.0
RAD = 0.3
COIL_Z = {"Tx1": 0.0, "Tx2": 0.0, "Rx": 30.0}


def log(m):
    print(m, flush=True)


os.makedirs(TEST, exist_ok=True)
shutil.copyfile(SRC, DST)
log("复制模型 -> %s (%d bytes)" % (DST, os.path.getsize(DST)))

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=DST, design="WPT_G")
log("design=%s solution=%s" % (m.design_name, m.solution_type))

# 记录原端子属性
old_terms = {}
for b in m.boundaries:
    if b.name.startswith("CT_"):
        old_terms[b.name] = dict(b.props)
log("记录到 %d 个线圈端子: %s" % (len(old_terms), sorted(old_terms)))

log("")
log("=== 改前包围盒 ===")
for n in ("Tx1", "Tx2", "Rx"):
    bb = m.modeler[n].bounding_box
    log("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
        % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

# ---------- 1. 拆体 ----------
log("")
log("=== 1. separate_bodies ===")
split = {}
for coil in ("Tx1", "Tx2", "Rx"):
    got = None
    for api in ("separate_bodies", "separatebody", "SeparateBody"):
        fn = getattr(m.modeler, api, None)
        if fn is None:
            continue
        try:
            got = fn(coil)
            break
        except Exception as e:
            log("  %s via %s err %r" % (coil, api, repr(e)[:80]))
    log("  %-5s -> %s" % (coil, got))
    if got:
        split[coil] = got if isinstance(got, (list, tuple)) else [got]

# 拆完后所有对象
log("")
log("=== 拆体后全部对象 ===")
for n in sorted(m.modeler.object_names):
    bb = m.modeler[n].bounding_box
    zspan = bb[5] - bb[2]
    log("  %-16s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]  zspan=%.2f"
        % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5], zspan))

# ---------- 2. 认引线并记录接入点 ----------
log("")
log("=== 2. 识别并删除引线（zspan > 10mm 的视为引线）===")
attach = {}
for coil, names in split.items():
    zc = COIL_Z[coil]
    attach[coil] = []
    for n in names:
        if n not in m.modeler.object_names:
            continue
        bb = m.modeler[n].bounding_box
        zspan = bb[5] - bb[2]
        if zspan > 10.0:
            cx = (bb[0] + bb[3]) / 2.0
            cy = (bb[1] + bb[4]) / 2.0
            attach[coil].append((cx, cy))
            log("  删 %-16s  接入点 (%.2f, %.2f)  zspan=%.1f" % (n, cx, cy, zspan))
            try:
                m.modeler.delete(n)
            except Exception as e:
                log("    delete FAILED %r" % e)
        else:
            log("  留 %-16s  （螺旋，zspan=%.2f）" % (n, zspan))
    log("  %s 接入点: %s" % (coil, attach[coil]))

# ---------- 3. 建新引线 ----------
log("")
log("=== 3. 建新引线（竖直 %.0fmm + 水平到 y=%.0f）===")
new_objs = {}
for coil, pts in attach.items():
    zc = COIL_Z[coil]
    zrun = zc - STUB
    made = []
    for i, (x, y) in enumerate(pts):
        tag = "a" if i == 0 else "b"
        n1 = "NL_%s_%s_v" % (coil, tag)
        n2 = "NL_%s_%s_h" % (coil, tag)
        try:
            m.modeler.create_cylinder(orientation="Z", origin=[x, y, zrun],
                                      radius=RAD, height=STUB, name=n1)
            made.append(n1)
        except Exception as e:
            log("  %s FAILED %r" % (n1, e))
        try:
            m.modeler.create_cylinder(orientation="Y", origin=[x, Y_OUT, zrun],
                                      radius=RAD, height=(y - Y_OUT), name=n2)
            made.append(n2)
        except Exception as e:
            log("  %s FAILED %r" % (n2, e))
        log("  %-5s 端%s 竖 z %.1f->%.1f + 平 y %.1f->%.1f @ (%.2f, z=%.1f)"
            % (coil, tag, zrun, zc, Y_OUT, y, x, zrun))
    new_objs[coil] = made

# ---------- 4. unite 回线圈 ----------
log("")
log("=== 4. unite 回原线圈 ===")
for coil, made in new_objs.items():
    spiral = [n for n in split.get(coil, []) if n in m.modeler.object_names]
    parts = spiral + [n for n in made if n in m.modeler.object_names]
    log("  %s: 合并 %s" % (coil, parts))
    if len(parts) < 2:
        log("    !! 部件不足，跳过")
        continue
    try:
        res = m.modeler.unite(parts)
        log("    unite -> %s" % res)
        if res and res != coil:
            try:
                m.modeler.rename(res, coil)
                log("    rename -> %s" % coil)
            except Exception as e:
                log("    rename FAILED %r" % e)
    except Exception as e:
        log("    unite FAILED %r" % e)

log("")
log("=== unite 后包围盒（应与改前 X/Y 一致，Z 上限应下降）===")
for n in ("Tx1", "Tx2", "Rx"):
    if n in m.modeler.object_names:
        bb = m.modeler[n].bounding_box
        log("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
            % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))
    else:
        log("  %-5s 不存在！" % n)

# ---------- 5. 重新指派端子 ----------
log("")
log("=== 5. 找新端面并改端子 ===")
for name, props in old_terms.items():
    coil = name.split("_")[1]
    zc = COIL_Z[coil]
    zrun = zc - STUB
    obj = m.modeler[coil]
    want = None
    for f in obj.faces:
        try:
            c = f.center
            area = f.area
        except Exception:
            continue
        if abs(c[1] - Y_OUT) < 0.05 and abs(c[2] - zrun) < 0.2 and area < 1e-6:
            want = f.id
            break
    log("  %-12s 目标端面 (y=%.0f, z=%.1f) -> face %s" % (name, Y_OUT, zrun, want))
    if want is None:
        log("    !! 未找到端面，跳过该端子")
        continue
    b = None
    for x in m.boundaries:
        if x.name == name:
            b = x
            break
    if b is None:
        log("    !! 找不到该端子对象")
        continue
    b.props["Faces"] = [want]
    try:
        ok = b.update()
        log("    update=%s  Faces=%s  Winding=%s  Conductor=%s"
            % (ok, b.props.get("Faces"), b.props.get("Winding"), b.props.get("Conductor number")))
    except Exception as e:
        log("    update FAILED %r" % e)

log("")
log("=== 最终复核 ===")
nok = 0
for b in m.boundaries:
    if b.name.startswith("CT_"):
        f = b.props.get("Faces")
        ok = f and f[0] not in (27677, 27668, 27695, 27686, 27714, 27705)
        if ok:
            nok += 1
        log("  %-12s Faces=%-10s Conductor=%-3s Winding=%-3s %s"
            % (b.name, f, b.props.get("Conductor number"), b.props.get("Winding"),
               "OK" if ok else "<== 仍是旧面！"))
log("  已换到新端面的端子: %d / 6" % nok)

if nok == 6:
    log("")
    log("=== 存盘 ===")
    log("  save_project -> %s" % m.save_project())
else:
    log("")
    log("!! 未全部成功，不存盘")
