from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC")
print("objects before:", m3d.modeler.object_names)

# 6 个引出段：(线圈名, 端面中心, 引出方向 z 目标)
# Tx1/Tx2 向下引到 z=-20，Rx 向上引到 z=45
leads = [
    ("Tx1", (-56.0,    -15.0,  0.0), -20.0),
    ("Tx1", (-2.36,   -71.87, 0.0), -20.0),
    ("Tx2", (116.0,   -15.0,  0.0), -20.0),
    ("Tx2", (169.64,  -71.87, 0.0), -20.0),
    ("Rx",  (30.0,    -15.0, 30.0),  45.0),
    ("Rx",  (83.64,   -71.87, 30.0),  45.0),
]

RAD = 0.8  # 引出线半径 mm

for coil, (cx, cy, cz), zend in leads:
    zstart = cz
    height = abs(zend - zstart)
    name = "lead_%s_%s" % (coil, "p" if zend > cz else "n")
    try:
        cyl = m3d.modeler.create_cylinder(
            orientation="Z",
            origin=[cx, cy, zstart],
            radius=RAD,
            height=height,
            name=name,
        )
        cyl.material_name = "copper"
        print("created", name, "from z=%.1f to z=%.1f" % (zstart, zstart + height))
    except Exception as e:
        print("create", name, "err:", repr(e))

# Unite 每个线圈与它的引线
for coil in ["Tx1", "Tx2", "Rx"]:
    parts = [coil] + [n for n in m3d.modeler.object_names if n.startswith("lead_" + coil + "_")]
    if len(parts) > 1:
        try:
            m3d.modeler.unite(parts, keep_originals=False)
            print("united", parts)
        except Exception as e:
            print("unite", coil, "err:", repr(e))

print("objects after:", m3d.modeler.object_names)
