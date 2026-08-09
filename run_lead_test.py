import sys
from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixACMagnetic, SourceACMagnetic

DESIGN = "WPT_EC3"
RAD = 0.3
# Tx1/Tx2 引线: z[-5,0]; Rx 引线: z[30,35]
LEADS = [
    ("Tx1", (-56.0,    -15.0), -5.0, 5.0),
    ("Tx1", (-2.36,   -71.87), -5.0, 5.0),
    ("Tx2", (116.0,   -15.0), -5.0, 5.0),
    ("Tx2", (169.64,  -71.87), -5.0, 5.0),
    ("Rx",  (30.0,    -15.0), 30.0, 5.0),
    ("Rx",  (83.64,   -71.87), 30.0, 5.0),
]
ZTERM = {"Tx1": -5.0, "Tx2": -5.0, "Rx": 35.0}
AREA = 3.14159 * RAD * RAD

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")

# 1) 删除旧设计
try:
    if DESIGN in m3d.design_list:
        m3d._oproject.DeleteDesign(DESIGN)
        print("deleted old", DESIGN)
except Exception as e:
    print("del err:", repr(e))

# 2) 创建新设计 + 复制几何
dst = Maxwell3d(project="Project3", design=DESIGN, solution_type="EddyCurrent")
src_ed = m3d.odesign.SetActiveEditor("3D Modeler")
src_ed.Copy(["NAME:Selections", "Selections:=", "Tx1,Tx2,Rx"])
dst_ed = dst.odesign.SetActiveEditor("3D Modeler")
dst_ed.Paste()
print("geometry copied")

# 3) Setup
try:
    dst.create_setup(name="Setup1", props={"Frequency": "85kHz", "MaximumPasses": 10, "PercentRefinement": 30})
    print("Setup1 created")
except Exception as e:
    print("setup err:", repr(e))

# 4) 引线
for coil, (cx, cy), z0, h in LEADS:
    name = "lead_%s" % coil
    try:
        cyl = dst.modeler.create_cylinder(orientation="Z", origin=[cx, cy, z0], radius=RAD, height=h, name=name)
        cyl.material_name = "copper"
    except Exception as e:
        print("lead err:", repr(e))
print("leads created (R=%.1f)" % RAD)

# 5) Unite
for coil in ["Tx1", "Tx2", "Rx"]:
    parts = [coil] + [n for n in dst.modeler.object_names if n.startswith("lead_" + coil)]
    if len(parts) > 1:
        dst.modeler.unite(parts, keep_originals=False)
print("united")

# 6) Region
try:
    if "Region" in dst.modeler.object_names:
        dst.modeler.delete("Region")
except Exception as e:
    print("region del err:", repr(e))
try:
    dst.modeler.create_region(pad_value=[50, 50, 50, 50, 0, 0], pad_type="Absolute Offset", name="Region")
    print("Region created")
except Exception as e:
    print("region err:", repr(e))
for n in dst.modeler.object_names:
    print(n, "bbox:", dst.modeler[n].bounding_box)

# 7) 激励：Winding + 2 CoilTerminal
term_faces = {}
for cname, zt in ZTERM.items():
    obj = dst.modeler[cname]
    hits = []
    for f in obj.faces:
        c = list(f.center)
        area = getattr(f, "area", None)
        if area is None:
            continue
        if abs(c[2] - zt) < 0.5 and abs(area - AREA) < AREA * 0.3:
            hits.append((f.id, abs(area - AREA)))
    hits.sort(key=lambda x: x[1])
    term_faces[cname] = [h[0] for h in hits[:2]]
    print(cname, "term faces:", term_faces[cname])

winding_names = []
for cname, (f1, f2) in term_faces.items():
    wname = "Winding_%s" % cname
    try:
        dst.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                           current=1, name=wname)
        c1 = dst.assign_coil(assignment=[f1], conductors_number=12, polarity="Positive", name="CT_%s_P" % cname)
        c2 = dst.assign_coil(assignment=[f2], conductors_number=12, polarity="Negative", name="CT_%s_N" % cname)
        dst.add_winding_coils(wname, [c1.name, c2.name])
        winding_names.append(wname)
        print(wname, "OK")
    except Exception as e:
        print(wname, "err:", repr(e))

# 8) 矩阵
if len(winding_names) == 3:
    try:
        dst.assign_matrix(MatrixACMagnetic(
            signal_sources=[SourceACMagnetic(name=w) for w in winding_names],
            matrix_name="Lmatrix"))
        print("MATRIX ASSIGNED")
    except Exception as e:
        print("matrix err:", repr(e))

# 9) 求解
try:
    dst.analyze(cores=8, blocking=True)
    print("ANALYZE DONE")
except Exception as e:
    print("ANALYZE ERR:", repr(e))
try:
    for s in dst.setups:
        print("setup", s.name, "solved:", s.is_solved)
except Exception as e:
    print("setup check err:", repr(e))

# 10) 提取矩阵
try:
    w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
    data = dst.post.get_solution_data(
        expressions=["L(%s,%s)" % (wi, wj) for wi in w for wj in w],
        setup_sweep_name="Setup1 : LastAdaptive",
        context={"Lmatrix": ""},
        primary_sweep_variable="Freq",
    )
    real, _ = data.full_matrix_real_imag
    names = {"Winding_Tx1": "Tx1", "Winding_Tx2": "Tx2", "Winding_Rx": "Rx"}
    print("\n=== L matrix (uH), RAD=%.1f, leads 5mm ===" % RAD)
    for wi in w:
        row = [real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0 for wj in w]
        print("  %s: %s" % (names[wi], ["%.2f" % v for v in row]))
except Exception as e:
    print("extract err:", repr(e))
