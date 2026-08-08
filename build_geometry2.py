from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC2")
print("solution:", m3d.solution_type)

# 1) Setup1 85kHz
try:
    m3d.create_setup(name="Setup1", props={"Frequency": "85kHz", "MaximumPasses": 10, "PercentRefinement": 30})
    print("Setup1 created")
except Exception as e:
    print("setup err:", repr(e))

# 2) 引线：Tx1/Tx2 向下 z[-20,0]，Rx 向上 z[30,45]
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
        cyl = m3d.modeler.create_cylinder(orientation="Z", origin=[cx, cy, z0], radius=RAD, height=h, name=name)
        cyl.material_name = "copper"
        print("lead", name, "z[%.1f,%.1f]" % (z0, z0 + h))
    except Exception as e:
        print("lead err:", repr(e))

# 3) Unite
for coil in ["Tx1", "Tx2", "Rx"]:
    parts = [coil] + [n for n in m3d.modeler.object_names if n.startswith("lead_" + coil)]
    if len(parts) > 1:
        try:
            m3d.modeler.unite(parts, keep_originals=False)
            print("united", coil)
        except Exception as e:
            print("unite err:", repr(e))

# 4) Region：绝对偏移，Z 方向 0
try:
    if "Region" in m3d.modeler.object_names:
        m3d.modeler.delete("Region")
except Exception as e:
    print("del Region err:", repr(e))
try:
    m3d.modeler.create_region(pad_value=[5, 5, 5, 5, 0, 0], pad_type="Absolute Offset", name="Region")
    print("Region created")
except Exception as e:
    print("region err:", repr(e))

# 5) 打印包围盒
for n in m3d.modeler.object_names:
    try:
        print(n, "bbox:", m3d.modeler[n].bounding_box)
    except Exception as e:
        print(n, "bbox err:", repr(e))
