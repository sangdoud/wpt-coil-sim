# -*- coding: utf-8 -*-
"""补上 ParentBndID —— 让重建的端子真正挂到绕组上。

上次错误: 'Excitation CT_Tx2_P is not assigned to any winding.'
原因: 只设了 props['Winding']，没设 props['ParentBndID']。
     原模型里两者都 = 绕组 ID（如 ParentBndID=9, Winding=9）。
用 pyAEDT 的 validate 接口快速验证（不用跑完整求解）。
"""

from ansys.aedt.core import Desktop, Maxwell3d

DST = r"C:\wpt\_test_run\Projecttonight_newlead.aedt"

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=DST, design="WPT_G")
print("design=%s" % m.design_name)

wmap = {}
for b in m.boundaries:
    if b.name.startswith("Winding_"):
        wmap[b.name] = b.props.get("ID")
print("绕组:", wmap)

print()
print("=== 修补前 ===")
for b in m.boundaries:
    if b.name.startswith("CT_"):
        print("  %-12s ParentBndID=%-5s Winding=%-5s Faces=%s"
              % (b.name, b.props.get("ParentBndID"), b.props.get("Winding"), b.props.get("Faces")))

print()
print("=== 修补 ===")
for b in list(m.boundaries):
    if not b.name.startswith("CT_"):
        continue
    coil = b.name.split("_")[1]
    wid = wmap.get("Winding_" + coil)
    b.props["ParentBndID"] = wid
    b.props["Winding"] = wid
    try:
        b.update()
        print("  %-12s -> ParentBndID=%s Winding=%s"
              % (b.name, b.props.get("ParentBndID"), b.props.get("Winding")))
    except Exception as e:
        print("  %-12s update FAILED %r" % (b.name, e))

print()
print("=== 修补后（重新读取全部边界）===")
for b in m.boundaries:
    print("  %-14s type=%-14s ParentBndID=%-5s Winding=%-5s Conductor=%s Faces=%s"
          % (b.name, getattr(b, "type", "?"), b.props.get("ParentBndID"),
             b.props.get("Winding"), b.props.get("Conductor number"), b.props.get("Faces")))

print()
print("=== 快速校验（不跑完整求解）===")
ok = False
for api in ("validate_full_design", "validate_simple"):
    fn = getattr(m, api, None)
    if fn is None:
        continue
    try:
        r = fn()
        print("  %s -> %s" % (api, r))
        if r:
            ok = True
        break
    except Exception as e:
        print("  %s err %r" % (api, repr(e)[:120]))

print()
print("=== 存盘 ===")
print("  save_project ->", m.save_project())
