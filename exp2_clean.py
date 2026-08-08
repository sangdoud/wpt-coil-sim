from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")

# 1) 清空所有激励
try:
    m3d.oboundary.DeleteAllExcitations()
    print("CLEARED all excitations")
except Exception as e:
    print("CLEAR ERR:", repr(e))

# 2) 找 Tx1 起点端面，单面 Assign Current (Stranded, 1A)
obj = m3d.modeler["Tx1"]
face_id = None
for f in obj.faces:
    c = list(f.center)
    if abs(c[0] - (-56.0)) < 3 and abs(c[1] - (-15.0)) < 3:
        face_id = f.id
        print("Tx1 start face:", face_id, c)
        break
if face_id is None:
    print("ERROR: start face not found")
else:
    try:
        m3d.assign_current(assignment=[face_id], amplitude=1, solid=False, name="Coil1")
        print("ASSIGNED Coil1")
    except Exception as e:
        print("ASSIGN ERR:", repr(e))

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
    msgs = m3d.logger.get_messages()
    if msgs:
        for m in msgs[-15:]:
            print("MSG:", m)
    else:
        print("NO MESSAGES")
except Exception as e:
    print("LOG ERR:", repr(e))
