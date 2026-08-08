from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")

# 1) 确保 WPT_EC 不存在
try:
    proj = m3d._oproject
    print("designs before:", m3d.design_list)
    if "WPT_EC" in m3d.design_list:
        try:
            proj.DeleteDesign("WPT_EC")
            print("DeleteDesign called")
        except Exception as e:
            print("DeleteDesign err:", repr(e))
        import time
        time.sleep(2)
    print("designs after del:", m3d.design_list)
except Exception as e:
    print("step1 err:", repr(e))

# 2) 复制为 WPT_EC
try:
    ok = m3d.duplicate_design("WPT_EC")
    print("duplicate ok:", ok)
    print("designs now:", m3d.design_list)
except Exception as e:
    print("duplicate err:", repr(e))

# 3) 打开并改求解器
m3d_ec = Maxwell3d(project="Project3", design="WPT_EC")
m3d_ec.solution_type = "EddyCurrent"
print("solution:", m3d_ec.solution_type)
print("objects:", m3d_ec.modeler.object_names)
