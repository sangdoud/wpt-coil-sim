from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC8")

# 记录原磁导率并降低到 10
mat = m3d.materials["ferrite"]
orig = mat.permeability.value
print("orig permeability:", orig)
try:
    mat.permeability.value = 10
    print("permeability set to 10")
except Exception as e:
    print("set perm err:", repr(e))

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
    print("=== L matrix (uH) with mu=10 ===")
    for wi in w:
        row = [real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0 for wj in w]
        print("  %s: %s" % (names[wi], ["%.2f" % v for v in row]))
except Exception as e:
    print("extract err:", repr(e))

# 恢复磁导率
try:
    mat.permeability.value = orig
    print("permeability restored to", orig)
except Exception as e:
    print("restore err:", repr(e))
