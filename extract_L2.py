from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC2")
post = m3d.post

w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]

# 用 full_matrix_real_imag 读完整矩阵（传 9 个表达式或单个）
try:
    data = post.get_solution_data(
        expressions=["L(%s,%s)" % (wi, wj) for wi in w for wj in w],
        setup_sweep_name="Setup1 : LastAdaptive",
        context={"Lmatrix": ""},
        primary_sweep_variable="Freq",
    )
    print("expressions:", data.expressions)
    ri = data.full_matrix_real_imag
    print("full_matrix_real_imag type:", type(ri))
    print(ri)
except Exception as e:
    print("full_matrix err:", repr(e))
