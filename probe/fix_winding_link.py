# -*- coding: utf-8 -*-
"""把重建出来的 6 个线圈端子挂回对应的 Winding 组。

第 5 版遗留问题：assign_coil 建出的端子 props 里 Winding=None，
而 Winding 组才是激励（10A / 0A）的载体，Lmatrix 也靠 Source=绕组ID 引用。
"""

from ansys.aedt.core import Desktop, Maxwell3d

DST = r"C:\wpt\_test_run\Projecttonight_newlead.aedt"

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=DST, design="WPT_G")
print("design=%s" % m.design_name)

print()
print("=== 现有边界 ===")
for b in m.boundaries:
    print("  %-14s type=%-14s props=%s" % (b.name, getattr(b, "type", "?"), str(b.props)[:160]))

# 绕组名 -> ID
wmap = {}
for b in m.boundaries:
    if b.name.startswith("Winding_"):
        wmap[b.name] = b.props.get("ID")
print()
print("绕组映射:", wmap)

oModule = m.odesign.GetModule("BoundarySetup")

print()
print("=== 逐个设置 Winding ===")
okcnt = 0
for b in list(m.boundaries):
    if not b.name.startswith("CT_"):
        continue
    coil = b.name.split("_")[1]
    wname = "Winding_" + coil
    wid = wmap.get(wname)
    print("  %-12s -> %s (ID=%s)" % (b.name, wname, wid))

    done = False
    # 方式 1: pyAEDT props + update
    try:
        b.props["Winding"] = wid
        r = b.update()
        if str(b.props.get("Winding")) not in ("None", "null"):
            print("       [props+update] 成功: Winding=%s" % b.props.get("Winding"))
            done = True
    except Exception as e:
        print("       [props+update] 失败 %r" % (repr(e)[:90],))

    # 方式 2: AEDT 模块 API
    if not done:
        for call, args in (
            ("EditCoilTerminal", ["NAME:%s" % b.name, "Winding:=", wname]),
            ("EditCoilTerminal", ["NAME:%s" % b.name, "WindingID:=", wid]),
        ):
            if not hasattr(oModule, call):
                continue
            try:
                getattr(oModule, call)(args)
                print("       [%s %s] 已调用" % (call, args[1:]))
                done = True
                break
            except Exception as e:
                print("       [%s] 失败 %r" % (call, repr(e)[:90]))

    if done:
        okcnt += 1

print()
print("=== 复核 ===")
res = []
for b in m.boundaries:
    if b.name.startswith("CT_"):
        w = b.props.get("Winding")
        res.append(w)
        print("  %-12s Faces=%-9s Conductor=%-3s Winding=%-6s PointOut=%s"
              % (b.name, b.props.get("Faces"), b.props.get("Conductor number"), w,
                 b.props.get("Point out of terminal")))

good = sum(1 for w in res if str(w) not in ("None", "null"))
print()
print("挂上绕组的端子: %d / %d" % (good, len(res)))
if good == 6:
    print("=== 存盘 ===")
    print("  save_project ->", m.save_project())
else:
    print("!! 仍有端子未挂绕组，不存盘")
