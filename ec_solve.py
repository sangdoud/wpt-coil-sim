from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixACMagnetic, SourceACMagnetic

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC")
print("solution:", m3d.solution_type)

# 1) 检查 Region
objs = m3d.modeler.object_names
print("objects:", objs)
if "Region" not in objs:
    try:
        m3d.modeler.create_region([500, 500, 500, 500, 500, 500])
        print("Region created")
        objs = m3d.modeler.object_names
        print("objects now:", objs)
    except Exception as e:
        print("create region err:", repr(e))

# 2) 分配电感矩阵
try:
    sources = [
        SourceACMagnetic(name="Coil_Tx1"),
        SourceACMagnetic(name="Coil_Tx2"),
        SourceACMagnetic(name="Coil_Rx"),
    ]
    matrix_args = MatrixACMagnetic(signal_sources=sources, matrix_name="Lmatrix")
    m3d.assign_matrix(matrix_args)
    print("MATRIX ASSIGNED")
except Exception as e:
    print("matrix assign err:", repr(e))

# 3) 求解
try:
    m3d.analyze(cores=4, blocking=True)
    print("ANALYZE CALLED")
except Exception as e:
    print("ANALYZE ERR:", repr(e))

# 4) 检查求解状态
try:
    for s in m3d.setups:
        print("setup", s.name, "solved:", s.is_solved)
except Exception as e:
    print("SETUP CHECK ERR:", repr(e))

# 5) 读错误消息
try:
    for e in m3d.logger.aedt_error_messages:
        print("ERRMSG:", e)
except Exception as e:
    print("LOG ERR:", repr(e))
