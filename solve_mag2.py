import time, csv
from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixMagnetostatic, SourceMagnetostatic

DESIGN = "WPT_G"
d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=8016)
m3d = Maxwell3d(project="Projecttonight", design=DESIGN)
print("solution:", m3d.solution_type, flush=True)

# 1) 分配 Magnetostatic 矩阵（group_sources=[]）
w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
try:
    sources = [SourceMagnetostatic(name=wn) for wn in w]
    m3d.assign_matrix(MatrixMagnetostatic(signal_sources=sources, group_sources=[], matrix_name="Lmatrix"))
    print("MATRIX ASSIGNED", flush=True)
except Exception as e:
    print("matrix err:", repr(e), flush=True)

# 2) 求解
try:
    d.odesktop.StopSimulations(True)
    time.sleep(3)
except Exception as e:
    print("stop err:", repr(e), flush=True)
try:
    m3d.analyze(cores=4, run_in_thread=True)
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

# 3) 提取
if solved:
    try:
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
