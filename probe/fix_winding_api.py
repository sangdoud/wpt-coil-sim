# -*- coding: utf-8 -*-
"""最终尝试：用 AEDT 模块 API 重建端子，并显式指定 Winding。

先回滚上一次的文本编辑（那用了错误的 ID 体系）。
然后删掉 6 个端子，用 oModule.AssignCoilTerminal 带 Winding 参数重建。
"""

import os
import shutil

from ansys.aedt.core import Desktop, Maxwell3d

TEST = r"C:\wpt\_test_run"
DST = os.path.join(TEST, "Projecttonight_newlead.aedt")
BAK = os.path.join(TEST, "Projecttonight_newlead_before_txtfix.aedt")

if os.path.isfile(BAK):
    shutil.copyfile(BAK, DST)
    print("已回滚文本编辑（从 %s）" % os.path.basename(BAK))

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=DST, design="WPT_G")
print("design=%s" % m.design_name)

# 记录要重建的端子
want = {}
for b in m.boundaries:
    if b.name.startswith("CT_"):
        want[b.name] = dict(faces=list(b.props.get("Faces") or []),
                            cn=str(b.props.get("Conductor number")),
                            po=b.props.get("Point out of terminal"))
print("待重建: %s" % sorted(want))

oModule = m.odesign.GetModule("BoundarySetup")

print()
print("=== 删除旧端子 ===")
for name in list(want):
    for b in list(m.boundaries):
        if b.name == name:
            try:
                b.delete()
                print("  deleted %s" % name)
            except Exception as e:
                print("  delete %s FAILED %r" % (name, e))

print()
print("=== 用 AEDT API 重建（带 Winding）===")
ok = {}
for name, w in sorted(want.items()):
    coil = name.split("_")[1]
    wname = "Winding_" + coil
    got = None
    variants = [
        ["NAME:%s" % name, "Faces:=", w["faces"], "Conductor number:=", w["cn"],
         "Point out of terminal:=", w["po"], "Winding:=", wname],
        ["NAME:%s" % name, "Faces:=", w["faces"], "Conductor number:=", w["cn"],
         "Point out of terminal:=", w["po"], "WindingName:=", wname],
        ["NAME:%s" % name, "Faces:=", w["faces"], "Conductor number:=", w["cn"],
         "Point out of terminal:=", w["po"], "Winding:=", coil],
    ]
    for i, args in enumerate(variants):
        try:
            r = oModule.AssignCoilTerminal(args)
            got = r
            print("  %-12s 变体%d 成功 -> %s" % (name, i + 1, r))
            break
        except Exception as e:
            print("  %-12s 变体%d 失败 %r" % (name, i + 1, repr(e)[:80]))
    ok[name] = got

print()
print("=== 复核（含文本层）===")
for b in m.boundaries:
    if b.name.startswith("CT_"):
        print("  %-12s ParentBndID=%-5s Winding=%-5s Conductor=%-3s Faces=%s"
              % (b.name, b.props.get("ParentBndID"), b.props.get("Winding"),
                 b.props.get("Conductor number"), b.props.get("Faces")))

print()
print("save ->", m.save_project())
