from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_G")

# 1) 铁氧体材料属性
try:
    mat = m3d.materials["ferrite"]
    mu = mat.permeability
    print("permeability value:", mu.value, "unit:", getattr(mu, "unit", "?"), "type:", getattr(mu, "type", "?"))
    try:
        print("permeability props:", mu.get_property_data() if hasattr(mu, "get_property_data") else "n/a")
    except Exception as e:
        print("mu props err:", repr(e))
    try:
        cond = mat.conductivity
        print("conductivity value:", cond.value, "unit:", getattr(cond, "unit", "?"))
    except Exception as e:
        print("cond err:", repr(e))
except Exception as e:
    print("mat err:", repr(e))

# 2) 尝试用 setup 导出矩阵文件
try:
    setup = m3d.setups[0]
    out = r"C:/Users/lenovo/Desktop/zidong/matrix_export.txt"
    ok = setup.export_matrix(matrix_type="RL", matrix_name="Lmatrix", output_file=out)
    print("export_matrix ok:", ok)
    import os
    if os.path.exists(out):
        with open(out) as f:
            print("--- matrix file ---")
            print(f.read()[:2000])
except Exception as e:
    print("export err:", repr(e))
