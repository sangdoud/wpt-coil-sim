from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)

# 1) 删除旧的 WPT_EC 设计
try:
    old = Maxwell3d(project="Project3", design="WPT_EC")
    old.delete_design("WPT_EC", fallback_design="Maxwell3DDesign1")
    print("deleted WPT_EC")
except Exception as e:
    print("delete err:", repr(e))

# 2) 重新从 Magnetostatic 设计复制
try:
    src = Maxwell3d(project="Project3", design="Maxwell3DDesign1")
    src.duplicate_design("WPT_EC")
    print("duplicated to WPT_EC")
except Exception as e:
    print("duplicate err:", repr(e))

# 3) 打开 WPT_EC
m3d = Maxwell3d(project="Project3", design="WPT_EC")
m3d.solution_type = "EddyCurrent"
print("solution:", m3d.solution_type)

# 4) 清激励、删旧 setup
try:
    m3d.oboundary.DeleteAllExcitations()
    print("excitations cleared")
except Exception as e:
    print("clear err:", repr(e))
try:
    for s in list(m3d.setups):
        m3d.delete_setup(s.name)
except Exception as e:
    print("setup del err:", repr(e))
try:
    m3d.create_setup(name="Setup1", props={"Frequency": "85kHz", "MaximumPasses": 10, "PercentRefinement": 30})
    print("Setup1 (85kHz) created")
except Exception as e:
    print("setup err:", repr(e))

# 5) 创建引线（圆柱从端点外沿 Z 伸到 Region 边界）
# Tx1/Tx2: z 从 -20 到 0（顶端在端面）；Rx: z 从 30 到 45
leads = [
    ("Tx1", (-56.0,    -15.0), -20.0, 20.0),   # origin z=-20, height=20 -> [-20,0]
    ("Tx1", (-2.36,   -71.87), -20.0, 20.0),
    ("Tx2", (116.0,   -15.0), -20.0, 20.0),
    ("Tx2", (169.64,  -71.87), -20.0, 20.0),
    ("Rx",  (30.0,    -15.0),  30.0, 15.0),    # origin z=30, height=15 -> [30,45]
    ("Rx",  (83.64,   -71.87), 30.0, 15.0),
]
RAD = 0.8
for coil, (cx, cy), z0, h in leads:
    name = "lead_%s" % coil
    try:
        cyl = m3d.modeler.create_cylinder(orientation="Z", origin=[cx, cy, z0], radius=RAD, height=h, name=name)
        cyl.material_name = "copper"
        print("lead", name, "z[%.1f, %.1f]" % (z0, z0 + h))
    except Exception as e:
        print("lead create err:", repr(e))

# 6) Unite 线圈与引线
for coil in ["Tx1", "Tx2", "Rx"]:
    parts = [coil] + [n for n in m3d.modeler.object_names if n.startswith("lead_" + coil)]
    if len(parts) > 1:
        try:
            m3d.modeler.unite(parts, keep_originals=False)
            print("united", coil)
        except Exception as e:
            print("unite err:", repr(e))

# 7) 删旧 Region，建新 Region（绝对偏移，Z 方向 0）
try:
    if "Region" in m3d.modeler.object_names:
        m3d.modeler.delete("Region")
        print("old Region deleted")
except Exception as e:
    print("region del err:", repr(e))
try:
    m3d.modeler.create_region(pad_value=[5, 5, 5, 5, 0, 0], pad_type="Absolute Offset", name="Region")
    print("new Region created (Z pads 0)")
except Exception as e:
    print("region create err:", repr(e))

# 8) 打印物体与包围盒
for n in m3d.modeler.object_names:
    try:
        print(n, "bbox:", m3d.modeler[n].bounding_box)
    except Exception as e:
        print(n, "bbox err:", repr(e))
