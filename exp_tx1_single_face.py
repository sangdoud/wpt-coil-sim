from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")
print("SOLVER:", m3d.solution_type)

# --- 列出并删除现有激励 ---
try:
    ob = m3d.oboundary
    excs = list(ob.GetExcitations())
    print("EXISTING EXCITATIONS:", excs)
    dels = [e for e in excs if str(e).lower().startswith("coil") or str(e).lower().startswith("current")]
    if dels:
        ob.DeleteExcitations(["NAME:Names"] + dels)
        print("DELETED:", dels)
except Exception as e:
    print("EXC CLEANUP ERR:", repr(e))

# --- 找 Tx1 的端面（理论坐标）---
obj = m3d.modeler["Tx1"]
targets = [(-56.0, -15.0), (-2.36, -71.87)]
found = {}
for f in obj.faces:
    c = list(f.center)
    for (tx, ty) in targets:
        if abs(c[0] - tx) < 2.0 and abs(c[1] - ty) < 2.0:
            found[(tx, ty)] = (f.id, c, list(f.normal))
print("Tx1 END FACES FOUND:", found)

# --- 单面 Assign Current（Stranded, 1A）---
face_id = list(found.values())[0][0]
try:
    m3d.assign_current(assignment=[face_id], amplitude=1, solid=False, swap_direction=False, name="Coil1")
    print("ASSIGNED Coil1 on face", face_id)
except Exception as e:
    print("ASSIGN ERR:", repr(e))

# --- 求解 ---
try:
    m3d.analyze(cores=8, blocking=True)
    print("ANALYZE DONE")
    # 尝试读矩阵
    try:
        mat = m3d.get_L_matrix()
        print("L MATRIX:", mat)
    except Exception as e:
        print("MATRIX ERR:", repr(e))
except Exception as e:
    print("ANALYZE ERR:", repr(e))
