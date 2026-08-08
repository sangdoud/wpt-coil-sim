from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC")
print("solution:", m3d.solution_type)

# 为三个线圈分配 Coil 激励（12 匝，Stranded）
try:
    c1 = m3d.assign_coil(assignment=["Tx1"], conductors_number=12, polarity="Positive", name="Coil1")
    print("Coil1 assigned:", c1)
except Exception as e:
    print("Coil1 err:", repr(e))

try:
    c2 = m3d.assign_coil(assignment=["Tx2"], conductors_number=12, polarity="Positive", name="Coil2")
    print("Coil2 assigned:", c2)
except Exception as e:
    print("Coil2 err:", repr(e))

try:
    c3 = m3d.assign_coil(assignment=["Rx"], conductors_number=12, polarity="Positive", name="Coil3")
    print("Coil3 assigned:", c3)
except Exception as e:
    print("Coil3 err:", repr(e))

# 打印当前边界/激励
try:
    print("EXCITATIONS:", list(m3d.oboundary.GetExcitations()))
except Exception as e:
    print("exc list err:", repr(e))
try:
    print("BOUNDARIES:", [str(b) for b in m3d.boundaries])
except Exception as e:
    print("boundaries err:", repr(e))
