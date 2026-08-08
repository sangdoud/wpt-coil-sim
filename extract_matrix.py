from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC2")

out = r"C:/Users/lenovo/Desktop/zidong/Lmatrix.txt"
try:
    setup = m3d.setups[0]
    ok = setup.export_matrix(matrix_type="RL", matrix_name="Lmatrix",
                             output_file=out, precision=8)
    print("export ok:", ok)
except Exception as e:
    print("export err:", repr(e))

import os
if os.path.exists(out):
    with open(out, "r") as f:
        content = f.read()
    print("=== Lmatrix.txt ===")
    print(content[:3000])
