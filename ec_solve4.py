from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixACMagnetic, SourceACMagnetic

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC2")

# 0) 清理
try:
    m3d.oboundary.DeleteAllExcitations()
    print("cleared")
except Exception as e:
    print("clear err:", repr(e))

# 1) 找每个线圈的两个引线末端面
term_faces = {}  # coil -> [face1, face2]
for cname, zterm in [("Tx1", -20.0), ("Tx2", -20.0), ("Rx", 45.0)]:
    obj = m3d.modeler[cname]
    hits = []
    for f in obj.faces:
        c = list(f.center)
        area = getattr(f, "area", None)
        if area is None:
            continue
        if abs(c[2] - zterm) < 0.5 and abs(area - 2.01) < 0.5:
            hits.append((f.id, abs(area - 2.01)))
    hits.sort(key=lambda x: x[1])
    term_faces[cname] = [h[0] for h in hits[:2]]
    print(cname, "term faces:", term_faces[cname])

# 2) 建 Winding + 两个 CoilTerminal（匝数 12，Positive/Negative）
winding_names = []
for cname, (f1, f2) in term_faces.items():
    wname = "Winding_%s" % cname
    try:
        m3d.assign_winding(assignment=None, winding_type="Current", is_solid=False,
                           current=1, name=wname)
        c1 = m3d.assign_coil(assignment=[f1], conductors_number=12, polarity="Positive",
                             name="CT_%s_P" % cname)
        c2 = m3d.assign_coil(assignment=[f2], conductors_number=12, polarity="Negative",
                             name="CT_%s_N" % cname)
        m3d.add_winding_coils(wname, [c1.name, c2.name])
        winding_names.append(wname)
        print(wname, "OK with 2 coils:", c1.name, c2.name)
    except Exception as e:
        print(wname, "err:", repr(e))

# 3) 矩阵
if len(winding_names) == 3:
    try:
        m3d.assign_matrix(MatrixACMagnetic(
            signal_sources=[SourceACMagnetic(name=w) for w in winding_names],
            matrix_name="Lmatrix"))
        print("MATRIX ASSIGNED")
    except Exception as e:
        print("matrix err:", repr(e))

# 4) 求解
try:
    m3d.analyze(cores=4, blocking=True)
    print("ANALYZE DONE")
except Exception as e:
    print("ANALYZE ERR:", repr(e))

# 5) 检查
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
