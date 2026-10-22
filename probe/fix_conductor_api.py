# -*- coding: utf-8 -*-
"""用 pyAEDT 正规地把 6 个线圈端子的 Conductor number 改成 1。

pyAEDT 的 m.boundaries 能读到并改写边界属性，这是正规做法（比改 .aedt 文本更稳）。
改完先复核，确认无误再存盘。
"""

from ansys.aedt.core import Desktop, Maxwell3d

PROJECT = r"C:\wpt\Projecttonight.aedt"
DESIGN = "WPT_G"

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=PROJECT, design=DESIGN)
print("design=%s solution=%s" % (m.design_name, m.solution_type))

cts = [b for b in m.boundaries if b.name.startswith("CT_")]
print("找到线圈端子 %d 个" % len(cts))

print()
print("=== 改前 ===")
for b in cts:
    print("  %-12s Conductor number = %-4s  Faces=%s"
          % (b.name, b.props.get("Conductor number"), b.props.get("Faces")))

print()
print("=== 改为 1 ===")
fails = []
for b in cts:
    old = b.props.get("Conductor number")
    b.props["Conductor number"] = "1"
    try:
        ok = b.update()
        print("  %-12s %s -> 1   update=%s" % (b.name, old, ok))
    except Exception as e:
        fails.append((b.name, repr(e)[:100]))
        print("  %-12s update FAILED: %r" % (b.name, e))

print()
print("=== 改后复核（重新读取） ===")
cts2 = [b for b in m.boundaries if b.name.startswith("CT_")]
bad = []
for b in cts2:
    v = b.props.get("Conductor number")
    f = b.props.get("Faces")
    flag = "" if str(v) == "1" else "   <== 没改成功"
    if str(v) != "1":
        bad.append(b.name)
    print("  %-12s Conductor number = %-4s  Faces=%s%s" % (b.name, v, f, flag))

print()
print("=== 几何未受影响检查 ===")
for n in ("Tx1", "Tx2", "Rx"):
    bb = m.modeler[n].bounding_box
    print("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
          % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

print()
if fails or bad:
    print("!! 有问题，不存盘。fails=%s bad=%s" % (fails, bad))
else:
    print("=== 全部 6 个已改为 1，存盘 ===")
    print("  save_project ->", m.save_project())
