from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)

# 1) 创建新 Eddy Current 设计（用新名字避免幽灵冲突）
dst = Maxwell3d(project="Project3", design="WPT_EC2", solution_type="EddyCurrent")
print("solution:", dst.solution_type)
print("dst objects:", dst.modeler.object_names)

# 2) 从 Maxwell3DDesign1 复制几何
src = Maxwell3d(project="Project3", design="Maxwell3DDesign1")
src_ed = src.odesign.SetActiveEditor("3D Modeler")
try:
    src_ed.Copy(["NAME:Selections", "Selections:=", "Tx1,Tx2,Rx"])
    print("copied from source")
except Exception as e:
    print("copy err:", repr(e))

dst_ed = dst.odesign.SetActiveEditor("3D Modeler")
try:
    dst_ed.Paste()
    print("pasted to dst")
except Exception as e:
    print("paste err:", repr(e))

# 3) 验证
print("dst objects after:", dst.modeler.object_names)
for n in ["Tx1", "Tx2", "Rx"]:
    try:
        print(n, "mat:", dst.modeler[n].material_name, "bbox:", dst.modeler[n].bounding_box)
    except Exception as e:
        print(n, "err:", repr(e))
