from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixACMagnetic, SourceACMagnetic

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC")
print("solution:", m3d.solution_type)

# 0) 清掉 Current 激励
try:
    m3d.oboundary.DeleteAllExcitations()
    print("excitations cleared")
except Exception as e:
    print("clear err:", repr(e))

# 1) 对每个线圈建 Winding（Current type, Stranded, 1A），端面作为 Coil Terminal
coils = {
    "Tx1": ((-56.0, -15.0, 0.0), (-2.36, -71.87, 0.0)),
    "Tx2": ((116.0, -15.0, 0.0), (169.64, -71.87, 0.0)),
    "Rx":  ((30.0, -15.0, 30.0), (83.64, -71.87, 30.0)),
}
winding_names = []
for cname, (start, end) in coils.items():
    obj = m3d.modeler[cname]
    face_id = None
    for f in obj.faces:
        c = list(f.center)
        if abs(c[0]-start[0])<3 and abs(c[1]-start[1])<3 and abs(c[2]-start[2])<1:
            face_id = f.id
            break
    if face_id is None:
        print("%s face NOT FOUND" % cname)
        continue
    wname = "Winding_%s" % cname
    try:
        m3d.assign_winding(assignment=[face_id], winding_type="Current",
                           is_solid=False, current=1, name=wname)
        winding_names.append(wname)
        print("%s winding assigned on face %s -> %s" % (cname, face_id, wname))
    except Exception as e:
        print("%s winding err: %s" % (cname, repr(e)))

print("winding_names:", winding_names)

# 2) 分配矩阵
if len(winding_names) == 3:
    try:
        sources = [SourceACMagnetic(name=w) for w in winding_names]
        matrix_args = MatrixACMagnetic(signal_sources=sources, matrix_name="Lmatrix")
        m3d.assign_matrix(matrix_args)
        print("MATRIX ASSIGNED")
    except Exception as e:
        print("matrix assign err:", repr(e))
else:
    print("SKIP matrix (not 3 windings)")

# 3) 求解
try:
    m3d.analyze(cores=4, blocking=True)
    print("ANALYZE CALLED")
except Exception as e:
    print("ANALYZE ERR:", repr(e))

# 4) 检查
try:
    for s in m3d.setups:
        print("setup", s.name, "solved:", s.is_solved)
except Exception as e:
    print("SETUP CHECK ERR:", repr(e))
try:
    for e in m3d.logger.aedt_error_messages:
        print("ERRMSG:", e)
except Exception as e:
    print("LOG ERR:", repr(e))
