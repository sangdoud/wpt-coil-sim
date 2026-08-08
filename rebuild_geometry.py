from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")

# 1) 清理多余设计
dl = list(m3d.design_list)
print("designs:", dl)
for extra in [n for n in dl if n not in ("Maxwell3DDesign1", "WPT_EC")]:
    try:
        m3d._oproject.DeleteDesign(extra)
        print("deleted", extra)
    except Exception as e:
        print("del", extra, "err:", repr(e))
try:
    if "WPT_EC" in m3d.design_list:
        m3d._oproject.DeleteDesign("WPT_EC")
        print("deleted old WPT_EC")
except Exception as e:
    print("del WPT_EC err:", repr(e))

# 2) 复制为 WPT_EC
ok = m3d.duplicate_design("WPT_EC")
print("duplicate ok:", ok, "designs:", m3d.design_list)

# 3) 打开副本，改求解器
m3d_ec = Maxwell3d(project="Project3", design="WPT_EC")
m3d_ec.solution_type = "EddyCurrent"
print("solution:", m3d_ec.solution_type)

# 4) 清激励、删 setup、建 Setup1(85kHz)
try:
    m3d_ec.oboundary.DeleteAllExcitations()
except Exception as e:
    print("clear exc err:", repr(e))
try:
    for s in list(m3d_ec.setups):
        m3d_ec.delete_setup(s.name)
except Exception as e:
    print("del setup err:", repr(e))
try:
    m3d_ec.create_setup(name="Setup1", props={"Frequency": "85kHz", "MaximumPasses": 10, "PercentRefinement": 30})
    print("Setup1 85kHz created")
except Exception as e:
    print("setup err:", repr(e))

# 5) 建引线：Tx1/Tx2 向下 z[-20,0]，Rx 向上 z[30,45]
leads = [
    ("Tx1", (-56.0,    -15.0), -20.0, 20.0),
    ("Tx1", (-2.36,   -71.87), -20.0, 20.0),
    ("Tx2", (116.0,   -15.0), -20.0, 20.0),
    ("Tx2", (169.64,  -71.87), -20.0, 20.0),
    ("Rx",  (30.0,    -15.0),  30.0, 15.0),
    ("Rx",  (83.64,   -71.87), 30.0, 15.0),
]
RAD = 0.8
for coil, (cx, cy), z0, h in leads:
    name = "lead_%s" % coil
    try:
        cyl = m3d_ec.modeler.create_cylinder(orientation="Z", origin=[cx, cy, z0], radius=RAD, height=h, name=name)
        cyl.material_name = "copper"
        print("lead", name, "z[%.1f,%.1f]" % (z0, z0 + h))
    except Exception as e:
        print("lead err:", repr(e))

# 6) Unite
for coil in ["Tx1", "Tx2", "Rx"]:
    parts = [coil] + [n for n in m3d_ec.modeler.object_names if n.startswith("lead_" + coil)]
    if len(parts) > 1:
        try:
            m3d_ec.modeler.unite(parts, keep_originals=False)
            print("united", coil)
        except Exception as e:
            print("unite err:", repr(e))

# 7) Region（绝对偏移，Z=0）
try:
    if "Region" in m3d_ec.modeler.object_names:
        m3d_ec.modeler.delete("Region")
except Exception as e:
    print("del Region err:", repr(e))
try:
    m3d_ec.modeler.create_region(pad_value=[5, 5, 5, 5, 0, 0], pad_type="Absolute Offset", name="Region")
    print("Region created")
except Exception as e:
    print("region err:", repr(e))

# 8) 打印
for n in m3d_ec.modeler.object_names:
    try:
        print(n, "bbox:", m3d_ec.modeler[n].bounding_box)
    except Exception as e:
        print(n, "bbox err:", repr(e))
