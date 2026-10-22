# -*- coding: utf-8 -*-
"""只读探针：打开工作区里的工程副本，打印活动设计的完整状态。
不存盘。"""
import os
import sys

from ansys.aedt.core import Desktop, Maxwell3d

WORK = r"C:\ansys maxwell2024\_work"
PROJ = os.path.join(WORK, "Projecttonight.aedt")
DESIGN = "WPT_G"


def log(m):
    print(m, flush=True)


log("PROJ exists: %s (%d bytes)" % (os.path.exists(PROJ),
                                    os.path.getsize(PROJ) if os.path.exists(PROJ) else -1))

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
log("Desktop 启动: " + str(d))
m = Maxwell3d(project=PROJ, design=DESIGN)
log("design=%s  solution=%s" % (m.design_name, m.solution_type))

log("")
log("=== 对象清单 ===")
for n in m.modeler.object_names:
    try:
        o = m.modeler[n]
        bb = o.bounding_box
        log("  %-16s %-10s vol=%-12.4f faces=%-5d X[%9.2f,%9.2f] Y[%9.2f,%9.2f] Z[%8.2f,%8.2f]"
            % (n, o.material_name, o.volume, len(o.faces),
               bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))
    except Exception as e:
        log("  %-16s 读取失败 %r" % (n, e))

log("")
log("=== 边界 (boundaries) ===")
for b in m.boundaries:
    try:
        p = b.props
    except Exception as e:
        log("  %-14s type=%-22s props 读取失败 %r" % (b.name, b.type, e))
        continue
    keys = ("Faces", "Winding", "Conductor number", "Point out of terminal", "Current")
    kv = "  ".join("%s=%s" % (k, p.get(k)) for k in keys if k in p)
    log("  %-14s type=%-22s %s" % (b.name, b.type, kv))

log("")
log("=== Region ===")
try:
    bb = m.modeler["Region"].bounding_box
    log("  X[%.3f,%.3f] Y[%.3f,%.3f] Z[%.3f,%.3f]" % (bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))
except Exception as e:
    log("  %r" % e)

log("")
log("=== 材料 ===")
for mn in m.materials.material_keys:
    try:
        mm = m.materials[mn]
        log("  %-12s mu=%s  cond=%s" % (mn, mm.permeability.value, mm.conductivity.value))
    except Exception as e:
        log("  %-12s %r" % (mn, e))

log("")
log("=== Setup ===")
for s in m.setups:
    log("  %s  props=%s" % (s.name, {k: v for k, v in s.props.items()
                                     if k in ("MaximumPasses", "PercentError", "PercentRefinement",
                                              "MinimumPasses", "MinimumConvergedPasses", "SolveType",
                                              "Frequency", "MaximumIterations")}))
log("")
log("不存盘，结束。")
