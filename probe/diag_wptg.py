# -*- coding: utf-8 -*-
"""诊断 WPT_G：对象、边界、线圈端子及其 Conductor number。只读，不存盘。"""

from ansys.aedt.core import Desktop, Maxwell3d

PROJECT = r"C:\wpt\Projecttonight.aedt"
DESIGN = "WPT_G"


def sec(t):
    print()
    print("=" * 78)
    print(t)
    print("=" * 78)


d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=PROJECT, design=DESIGN)
print("design=%s  solution=%s" % (m.design_name, m.solution_type))

sec("1. 全部对象与包围盒")
for n in sorted(m.modeler.object_names):
    try:
        bb = m.modeler[n].bounding_box
        print("  %-18s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
              % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))
    except Exception as e:
        print("  %-18s bbox err %r" % (n, e))

sec("2. 边界列表（多个 API 都试）")
oModule = m.odesign.GetModule("BoundarySetup")
names = []
for api in ("GetBoundaries", "GetBoundariesOfType", "GetAllBoundaries"):
    if hasattr(oModule, api):
        try:
            if api == "GetBoundariesOfType":
                continue
            r = getattr(oModule, api)()
            names = list(r)
            print("  %s() -> %d 个: %s" % (api, len(names), names))
            break
        except Exception as e:
            print("  %s() err %r" % (api, e))
for t in ("CoilTerminal", "WindingGroup", "Coil"):
    try:
        r = oModule.GetBoundariesOfType(t)
        print("  GetBoundariesOfType('%s') -> %s" % (t, list(r)))
    except Exception as e:
        print("  GetBoundariesOfType('%s') err %r" % (t, repr(e)[:80]))

sec("3. 每个线圈端子的 Conductor number（关键！）")
cands = [n for n in names if n.startswith("CT_")] or \
        ["CT_Tx1_P", "CT_Tx1_N", "CT_Tx2_P", "CT_Tx2_N", "CT_Rx_P", "CT_Rx_N"]
for n in cands:
    got = None
    for meth in ("GetPropertyValue",):
        try:
            got = getattr(oModule, meth)(n, "Conductor number")
            break
        except Exception:
            try:
                got = oModule.GetPropertyValue(n, "Conductor number", True)
                break
            except Exception as e:
                got = "ERR %r" % (repr(e)[:60],)
    print("  %-14s Conductor number = %s" % (n, got))

sec("4. 线圈端子的面 ID")
for n in cands:
    for meth in ("GetFaceIDs", "GetAssignment"):
        try:
            r = getattr(oModule, meth)(n)
            print("  %-14s %s -> %s" % (n, meth, r))
            break
        except Exception as e:
            pass

sec("5. pyAEDT 视角看边界")
try:
    for b in m.boundaries:
        try:
            props = getattr(b, "props", None)
            print("  %-16s type=%-18s props=%s" % (b.name, getattr(b, "type", "?"), str(props)[:200]))
        except Exception as e:
            print("  %s err %r" % (b.name, e))
except Exception as e:
    print("  m.boundaries err %r" % e)

sec("6. 各设计的线圈端子（确认我上次改的是哪个设计）")
for des in ("Maxwell3DDesign1", "WPT_F", "WPT_G"):
    try:
        mm = Maxwell3d(project=PROJECT, design=des)
        oM = mm.odesign.GetModule("BoundarySetup")
        try:
            ns = list(oM.GetBoundaries())
        except Exception:
            ns = []
        cts = [x for x in ns if x.startswith("CT_")]
        print("  %-18s 边界 %d 个, 其中 CT_*: %s" % (des, len(ns), cts))
    except Exception as e:
        print("  %-18s err %r" % (des, repr(e)[:80]))

print()
print("=== 诊断结束（未存盘） ===")
