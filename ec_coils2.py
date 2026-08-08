from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC")
print("solution:", m3d.solution_type)

# Eddy Current: Assign Current 到导体对象（Stranded）
try:
    c1 = m3d.assign_current(assignment=["Tx1"], amplitude=1, solid=False, name="Coil1")
    print("Coil1 assigned:", c1)
except Exception as e:
    print("Coil1 err:", repr(e))

try:
    c2 = m3d.assign_current(assignment=["Tx2"], amplitude=1, solid=False, name="Coil2")
    print("Coil2 assigned:", c2)
except Exception as e:
    print("Coil2 err:", repr(e))

try:
    c3 = m3d.assign_current(assignment=["Rx"], amplitude=1, solid=False, name="Coil3")
    print("Coil3 assigned:", c3)
except Exception as e:
    print("Coil3 err:", repr(e))

try:
    print("EXCITATIONS:", list(m3d.oboundary.GetExcitations()))
except Exception as e:
    print("exc list err:", repr(e))
