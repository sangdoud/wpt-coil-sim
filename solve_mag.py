import time, csv
from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixMagnetostatic, SourceMagnetostatic

DESIGN = "WPT_G"
d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=8016)
m3d = Maxwell3d(project="Projecttonight", design=DESIGN)
print("current solution:", m3d.solution_type, flush=True)

# 铁氧体：电导率 0，磁导率 1000（Magnetostatic 只关心磁导率）
try:
    m3d.materials["ferrite"].conductivity.value = 0
    m3d.materials["ferrite"].permeability.value = 1000
    print("ferrite set (mu=1000, cond=0)", flush=True)
except Exception as e:
    print("mat err:", repr(e), flush=True)

# 1) 改求解器为 Magnetostatic
try:
    m3d.solution_type = "Magnetostatic"
    print("solution type ->", m3d.solution_type, flush=True)
except Exception as e:
    print("soltype err:", repr(e), flush=True)

# 2) 清激励、删旧 setup
try:
    m3d.oboundary.DeleteAllExcitations()
    print("excitations cleared", flush=True)
except Exception as e:
    print("clear err:", repr(e), flush=True)
try:
    for s in list(m3d.setups):
        m3d.delete_setup(s.name)
    print("setups deleted", flush=True)
except Exception as e:
    print("setup del err:", repr(e), flush=True)

# 3) 重建 Winding + CoilTerminal（10A, 12匝）
ZTERM = {"Tx1": -45.0, "Tx2": -45.0, "Rx": 75.0}
AREA = 3.14159 * 0.3 * 0.3
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
    print(cname, "term faces:", term_faces[cname], flush=True)

winding_names = []
for cname, (f1, f2) in term_faces.items():
    wname = "Winding_%s" % cname
    try:
        m3d.assign_winding(assignment=None, winding_type="Current", is_solid=False, current=10, name=wname)
        c1 = m3d.assign_coil(assignment=[f1], conductors_number=12, polarity="Positive", name="CT_%s_P" % cname)
        c2 = m3d.assign_coil(assignment=[f2], conductors_number=12, polarity="Negative", name="CT_%s_N" % cname)
        m3d.add_winding_coils(wname, [c1.name, c2.name])
        winding_names.append(wname)
        print(wname, "OK", flush=True)
    except Exception as e:
        print(wname, "err:", repr(e), flush=True)

# 4) Magnetostatic 矩阵
if len(winding_names) == 3:
    try:
        sources = [SourceMagnetostatic(name=w) for w in winding_names]
        m3d.assign_matrix(MatrixMagnetostatic(signal_sources=sources, matrix_name="Lmatrix"))
        print("MATRIX ASSIGNED (Magnetostatic)", flush=True)
    except Exception as e:
        print("matrix err:", repr(e), flush=True)

# 5) 新建 Magnetostatic setup
try:
    m3d.create_setup(name="Setup1", props={"MaximumPasses": 10, "PercentRefinement": 30})
    print("Magnetostatic Setup1 created", flush=True)
except Exception as e:
    print("setup err:", repr(e), flush=True)

# 6) 求解
try:
    d.odesktop.StopSimulations(True)
    time.sleep(3)
except Exception as e:
    print("stop err:", repr(e), flush=True)
try:
    m3d.analyze(cores=8, run_in_thread=True)
    print("solve triggered", flush=True)
except Exception as e:
    print("analyze err:", repr(e), flush=True)

solved = False
for i in range(100):
    time.sleep(30)
    try:
        solved = m3d.setups[0].is_solved
        print("[poll %d] solved: %s" % (i, solved), flush=True)
        if solved:
            break
    except Exception as e:
        print("[poll %d] err: %s" % (i, repr(e)), flush=True)
print("final solved:", solved, flush=True)

# 7) 提取
if solved:
    try:
        w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
        data = m3d.post.get_solution_data(
            expressions=["L(%s,%s)" % (wi, wj) for wi in w for wj in w],
            setup_sweep_name="Setup1 : LastAdaptive",
            context={"Lmatrix": ""},
        )
        real, _ = data.full_matrix_real_imag
        names = {"Winding_Tx1": "Tx1", "Winding_Tx2": "Tx2", "Winding_Rx": "Rx"}
        out = r"C:/Users/lenovo/Desktop/zidong/Lmatrix_%s_mag.csv" % DESIGN
        with open(out, "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["L (uH)", "Tx1", "Tx2", "Rx"])
            print("=== L matrix (uH) %s Magnetostatic ===" % DESIGN, flush=True)
            for wi in w:
                row = [real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0 for wj in w]
                wr.writerow([names[wi]] + ["%.3f" % v for v in row])
                print("  %s: %s" % (names[wi], ["%.2f" % v for v in row]), flush=True)
        print("saved:", out, flush=True)
    except Exception as e:
        print("extract err:", repr(e), flush=True)
else:
    print("NOT SOLVED", flush=True)
print("SCRIPT DONE", flush=True)
