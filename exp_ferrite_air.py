from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC8")

# 1) 记录并改铁氧体为 air
ferr = [n for n in m3d.modeler.object_names if n.startswith("ferrite_")]
print("ferrite objects:", len(ferr))
for n in ferr:
    try:
        m3d.modeler[n].material_name = "air"
    except Exception as e:
        print(n, "mat err:", repr(e))
print("ferrite -> air (temporary)")

# 2) 求解
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

# 3) 提取矩阵
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
    print("=== L matrix (uH) with ferrite=air ===")
    for wi in w:
        row = [real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0 for wj in w]
        print("  %s: %s" % (names[wi], ["%.2f" % v for v in row]))
except Exception as e:
    print("extract err:", repr(e))

# 4) 恢复铁氧体材料
for n in ferr:
    try:
        m3d.modeler[n].material_name = "ferrite"
    except Exception as e:
        print(n, "restore err:", repr(e))
print("ferrite restored")
