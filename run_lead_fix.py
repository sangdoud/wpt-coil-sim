from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixACMagnetic, SourceACMagnetic

DESIGN = "WPT_EC3"
ZTERM = {"Tx1": -5.0, "Tx2": -5.0, "Rx": 35.0}
AREA = 3.14159 * 0.3 * 0.3  # R=0.3mm

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design=DESIGN)

# 0) 清掉所有激励（含残留 Coil1）
try:
    m3d.oboundary.DeleteAllExcitations()
    print("cleared, exc now:", list(m3d.oboundary.GetExcitations()))
except Exception as e:
    print("clear err:", repr(e))

# 1) 找端子面（z=-5 或 35，面积≈0.283）
term_faces = {}
for cname, zt in ZTERM.items():
    obj = m3d.modeler[cname]
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

# 2) 重建激励
winding_names = []
for cname, (f1, f2) in term_faces.items():
    wname = "Winding_%s" % cname
    try:
        m3d.assign_winding(assignment=None, winding_type="Current", is_solid=False, current=1, name=wname)
        c1 = m3d.assign_coil(assignment=[f1], conductors_number=12, polarity="Positive", name="CT_%s_P" % cname)
        c2 = m3d.assign_coil(assignment=[f2], conductors_number=12, polarity="Negative", name="CT_%s_N" % cname)
        m3d.add_winding_coils(wname, [c1.name, c2.name])
        winding_names.append(wname)
        print(wname, "OK")
    except Exception as e:
        print(wname, "err:", repr(e))

# 3) 矩阵
if len(winding_names) == 3:
    try:
        m3d.assign_matrix(MatrixACMagnetic(
            signal_sources=[SourceACMagnetic(name=w) for w in winding_names],
            matrix_name="Lmatrix"))
        print("MATRIX ASSIGNED")
    except Exception as e:
        print("matrix err:", repr(e))

# 4) 求解
try:
    m3d.analyze(cores=8, blocking=True)
    print("ANALYZE DONE")
except Exception as e:
    print("ANALYZE ERR:", repr(e))
try:
    for s in m3d.setups:
        print("setup", s.name, "solved:", s.is_solved)
except Exception as e:
    print("setup check err:", repr(e))

# 5) 提取
try:
    w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
    data = m3d.post.get_solution_data(
        expressions=["L(%s,%s)" % (wi, wj) for wi in w for wj in w],
        setup_sweep_name="Setup1 : LastAdaptive",
        context={"Lmatrix": ""},
        primary_sweep_variable="Freq",
    )
    real, _ = data.full_matrix_real_imag
    names = {"Winding_Tx1": "Tx1", "Winding_Tx2": "Tx2", "Winding_Rx": "Rx"}
    print("\n=== L matrix (uH) R=0.3mm leads 5mm ===")
    for wi in w:
        row = [real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0 for wj in w]
        print("  %s: %s" % (names[wi], ["%.2f" % v for v in row]))
except Exception as e:
    print("extract err:", repr(e))
