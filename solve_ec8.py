import csv
from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixACMagnetic, SourceACMagnetic

DESIGN = "WPT_EC8"
ZTERM = {"Tx1": -45.0, "Tx2": -45.0, "Rx": 75.0}
AREA = 3.14159 * 0.3 * 0.3  # 引线端面面积

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design=DESIGN)
print("solution:", m3d.solution_type)

# 0) 清激励（防残留 Coil1）
try:
    m3d.oboundary.DeleteAllExcitations()
    print("excitations cleared")
except Exception as e:
    print("clear err:", repr(e))

# 1) 找引线末端面
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

# 2) Winding + 2 CoilTerminal (10A, 12匝)
winding_names = []
for cname, (f1, f2) in term_faces.items():
    wname = "Winding_%s" % cname
    try:
        m3d.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                           current=10, name=wname)
        c1 = m3d.assign_coil(assignment=[f1], conductors_number=12, polarity="Positive", name="CT_%s_P" % cname)
        c2 = m3d.assign_coil(assignment=[f2], conductors_number=12, polarity="Negative", name="CT_%s_N" % cname)
        m3d.add_winding_coils(wname, [c1.name, c2.name])
        winding_names.append(wname)
        print(wname, "OK (10A)")
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
    m3d.analyze(cores=4, blocking=True)
    print("ANALYZE DONE")
except Exception as e:
    print("ANALYZE ERR:", repr(e))
try:
    for s in m3d.setups:
        print("setup", s.name, "solved:", s.is_solved)
except Exception as e:
    print("setup check err:", repr(e))

# 5) 提取矩阵
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
    print("\n=== L matrix (uH) DESIGN %s ===" % DESIGN)
    out = r"C:/Users/lenovo/Desktop/zidong/Lmatrix_%s.csv" % DESIGN
    with open(out, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["L (uH)", "Tx1", "Tx2", "Rx"])
        for wi in w:
            row = [names[wi]] + ["%.3f" % (real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0) for wj in w]
            wr.writerow(row)
            print("  %s: %s" % (names[wi], ["%.2f" % v for v in [real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0 for wj in w]]))
    print("saved:", out)
except Exception as e:
    print("extract err:", repr(e))
