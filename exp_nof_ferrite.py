from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_F")

# 停止任何运行中的求解
try:
    d.odesktop.StopSimulations(True)
except Exception as e:
    print("stop err:", repr(e))

# 删除所有铁氧体
ferr = [n for n in m3d.modeler.object_names if n.startswith("ferrite_")]
print("deleting ferrite:", len(ferr))
for n in ferr:
    try:
        m3d.modeler.delete(n)
    except Exception as e:
        print(n, "del err:", repr(e))
print("objects now:", m3d.modeler.object_names)

# 求解
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

# 提取矩阵
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
    print("=== L matrix (uH) no ferrite, long leads ===")
    for wi in w:
        row = [real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0 for wj in w]
        print("  %s: %s" % (names[wi], ["%.2f" % v for v in row]))
except Exception as e:
    print("extract err:", repr(e))
