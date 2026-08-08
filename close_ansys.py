import time
from ansys.aedt.core import Desktop

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)

# 1) 停止所有运行中的求解
try:
    d.odesktop.StopSimulations(True)
    time.sleep(2)
    print("simulations stopped", flush=True)
except Exception as e:
    print("stop err:", repr(e), flush=True)

# 2) 保存所有打开的项目
try:
    projs = d.project_list
    print("open projects:", projs, flush=True)
    for p in projs:
        try:
            proj = d.load_project(p)
            proj.save_project()
            print("saved:", p, flush=True)
        except Exception as e:
            print("save", p, "err:", repr(e), flush=True)
except Exception as e:
    print("list projects err:", repr(e), flush=True)

# 3) 关闭 AEDT
try:
    d.release_desktop(close_projects=True, close_on_exit=True)
    print("AEDT closed", flush=True)
except Exception as e:
    print("close err:", repr(e), flush=True)
print("DONE", flush=True)
