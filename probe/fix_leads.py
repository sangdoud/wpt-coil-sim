# -*- coding: utf-8 -*-
"""把 6 根竖直引线改成「短竖直 3mm + 水平引出」，使其不再穿透铁氧体。

方案 B：
  每个引出点 (x, y, z_coil)：
    1) 竖直短柱：从 z = z_coil-3 到 z_coil（3mm），让开线圈所在平面
    2) 水平引出：在 z = z_coil-3 平面内，沿 -Y 引到 y = -150

间隙核算：
  Tx: 引线水平段在 z=-3，铁氧体在 z=-40~-30  -> 余量 27mm
  Rx: 引线水平段在 z=27，铁氧体在 z= 60~70   -> 余量 33mm
  线圈本体厚 0.5mm（z 上下各 0.25），水平段离它 2.75mm
"""

import sys

from ansys.aedt.core import Desktop, Maxwell3d

PROJECT = r"C:\wpt\Projecttonight.aedt"
DESIGN = "WPT_G"

# (线圈, 端, x, y, 线圈所在 z)
LEADS = [
    ("Tx1", "a", -56.00, -15.00, 0.0),
    ("Tx1", "b", -2.36, -71.87, 0.0),
    ("Tx2", "a", 116.00, -15.00, 0.0),
    ("Tx2", "b", 169.64, -71.87, 0.0),
    ("Rx", "a", 30.00, -15.00, 30.0),
    ("Rx", "b", 83.64, -71.87, 30.0),
]

STUB = 3.0
Y_OUT = -150.0
RAD = 0.3


def log(m):
    print(m, flush=True)


log("=== 打开工程 ===")
d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=PROJECT, design=DESIGN)
log("  design=%s  solution=%s" % (m.design_name, m.solution_type))

names = list(m.modeler.object_names)
log("  对象数 %d" % len(names))
old_leads = [n for n in names if n.startswith("lead_")]
log("  旧引线: %s" % sorted(old_leads))
others = [n for n in names if not n.startswith("lead_")]
log("  其它对象: %s" % sorted(others))

log("")
log("=== 记录线圈与铁氧体的包围盒（改前） ===")
for n in ("Tx1", "Tx2", "Rx"):
    if n in m.modeler.object_names:
        bb = m.modeler[n].bounding_box
        log("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
            % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

ferr = [n for n in m.modeler.object_names if n.startswith("ferrite_")]
if ferr:
    zlo = min(m.modeler[n].bounding_box[2] for n in ferr)
    zhi = max(m.modeler[n].bounding_box[5] for n in ferr)
    log("  铁氧体 %d 条, 整体 Z[%.2f, %.2f]" % (len(ferr), zlo, zhi))

log("")
log("=== 删除旧引线 ===")
for n in old_leads:
    try:
        m.modeler.delete(n)
        log("  deleted %s" % n)
    except Exception as e:
        log("  delete %s FAILED: %r" % (n, e))

log("")
log("=== 创建新引线 ===")
new_names = []
for coil, end, x, y, zc in LEADS:
    z_run = zc - STUB
    # 1) 竖直短柱
    n1 = "lead_%s_%s" % (coil, end)
    try:
        c = m.modeler.create_cylinder(orientation="Z", origin=[x, y, z_run],
                                      radius=RAD, height=STUB, name=n1)
        new_names.append(n1)
        log("  %-14s 竖 z %.2f -> %.2f  @ (%.2f, %.2f)" % (n1, z_run, zc, x, y))
    except Exception as e:
        log("  create %s FAILED: %r" % (n1, e))
    # 2) 水平引出（沿 -Y，圆柱轴为 Y，底面在 y=Y_OUT，向 +Y 长 len）
    n2 = "lead_%s_%s_run" % (coil, end)
    length = y - Y_OUT
    try:
        c = m.modeler.create_cylinder(orientation="Y", origin=[x, Y_OUT, z_run],
                                      radius=RAD, height=length, name=n2)
        new_names.append(n2)
        log("  %-14s 平 y %.2f -> %.2f  @ (%.2f, z=%.2f)  长 %.2f"
            % (n2, Y_OUT, y, x, z_run, length))
    except Exception as e:
        log("  create %s FAILED: %r" % (n2, e))

log("")
log("=== 改后验证：新引线包围盒 + 与铁氧体的间隙 ===")
for n in new_names:
    if n in m.modeler.object_names:
        bb = m.modeler[n].bounding_box
        log("  %-18s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
            % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

if ferr:
    zlo = min(m.modeler[n].bounding_box[2] for n in ferr)
    zhi = max(m.modeler[n].bounding_box[5] for n in ferr)
    lead_z = [m.modeler[n].bounding_box[2] for n in new_names if n in m.modeler.object_names]
    lead_zhi = [m.modeler[n].bounding_box[5] for n in new_names if n in m.modeler.object_names]
    log("")
    log("  铁氧体 Z[%.2f, %.2f]" % (zlo, zhi))
    log("  引线   Z[%.2f, %.2f]" % (min(lead_z), max(lead_zhi)))
    clear_tx = min(lead_z) - zlo
    log("  引线最低点与铁氧体整体区间的重叠: %s"
        % ("有" if (min(lead_z) <= zhi and max(lead_zhi) >= zlo) else "无"))

log("")
log("=== 存盘 ===")
ok = m.save_project()
log("  save_project -> %s" % ok)
