import time, csv
from ansys.aedt.core import Desktop, Maxwell3d

DESIGN = "WPT_G"
d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design=DESIGN)
print("connected to", DESIGN, flush=True)

# 确认铁氧体电导率 0
try:
    m3d.materials["ferrite"].conductivity.value = 0
    m3d.materials["ferrite"].permeability.value = 100
    print("ferrite conductivity=0 confirmed", flush=True)
except Exception as e:
    print("cond set err:", repr(e), flush=True)

# 停止任何运行中的求解
try:
    d.odesktop.StopSimulations(True)
    time.sleep(3)
    print("old sims stopped", flush=True)
except Exception as e:
    print("stop err:", repr(e), flush=True)

# 触发求解（后台线程）
try:
    m3d.analyze(cores=4, run_in_thread=True)
    print("solve triggered", flush=True)
except Exception as e:
    print("analyze err:", repr(e), flush=True)

# 轮询等待（最长 60 分钟）
solved = False
for i in range(120):
    time.sleep(30)
    try:
        solved = m3d.setups[0].is_solved
        print("[poll %d] solved: %s" % (i, solved), flush=True)
        if solved:
            break
    except Exception as e:
        print("[poll %d] err: %s" % (i, repr(e)), flush=True)
print("final solved:", solved, flush=True)

# 提取矩阵
if solved:
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
        out = r"C:/Users/lenovo/Desktop/zidong/Lmatrix_%s.csv" % DESIGN
        with open(out, "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["L (uH)", "Tx1", "Tx2", "Rx"])
            print("=== L matrix (uH) %s ===" % DESIGN, flush=True)
            for wi in w:
                row = [real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0 for wj in w]
                wr.writerow([names[wi]] + ["%.3f" % v for v in row])
                print("  %s: %s" % (names[wi], ["%.2f" % v for v in row]), flush=True)
        print("saved:", out, flush=True)
    except Exception as e:
        print("extract err:", repr(e), flush=True)
else:
    print("NOT SOLVED - skip extraction", flush=True)

# 正确释放（不停止求解、不关 AEDT）
try:
    d.release_desktop(close_projects=False, close_desktop=False)
    print("desktop released cleanly", flush=True)
except Exception as e:
    print("release err:", repr(e), flush=True)
print("SCRIPT DONE", flush=True)
