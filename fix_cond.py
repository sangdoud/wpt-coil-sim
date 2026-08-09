import time
from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_G")

# 改铁氧体电导率为 0（纯磁性，PC40 涡流可忽略）
try:
    mat = m3d.materials["ferrite"]
    mat.conductivity.value = 0
    print("conductivity set to 0")
except Exception as e:
    print("set cond err:", repr(e))

# 停止旧求解，重新触发求解（后台）
try:
    d.odesktop.StopSimulations(True)
    time.sleep(3)
except Exception as e:
    print("stop err:", repr(e))
try:
    m3d.analyze(cores=8, run_in_thread=True)
    print("solve triggered in thread")
except Exception as e:
    print("analyze err:", repr(e))
