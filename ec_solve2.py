from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixACMagnetic, SourceACMagnetic

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC2")
print("solution:", m3d.solution_type)

# 1) 找每个线圈的引线末端面（Tx1/Tx2: z=-20；Rx: z=45）
# 特征：中心 z≈zterm，面积≈π*0.8^2≈2.01（圆柱截面）
term_face = {}
for cname, zterm in [("Tx1", -20.0), ("Tx2", -20.0), ("Rx", 45.0)]:
    obj = m3d.modeler[cname]
    fid = None
    best = 1e9
    for f in obj.faces:
        c = list(f.center)
        if abs(c[2] - zterm) < 0.5:
            area = getattr(f, "area", None)
            if area is None:
                continue
            # 面积最接近圆柱截面的优先
            if abs(area - 2.01) < best:
                best = abs(area - 2.01)
                fid = f.id
    if fid is None:
        print("%s terminal face NOT FOUND" % cname)
    else:
        print("%s terminal face id=%s (matched by z=%s, area diff %s)" % (cname, fid, zterm, best))
        term_face[cname] = fid

# 2) 给每个线圈的引线末端面 Assign Winding（Stranded, 1A）
winding_names = []
for cname, fid in term_face.items():
    wname = "Winding_%s" % cname
    try:
        m3d.assign_winding(assignment=[fid], winding_type="Current", is_solid=False,
                           current=1, name=wname)
        winding_names.append(wname)
        print("winding", wname, "assigned on face", fid)
    except Exception as e:
        print("winding", wname, "err:", repr(e))

# 3) 分配矩阵
if len(winding_names) == 3:
    try:
        sources = [SourceACMagnetic(name=w) for w in winding_names]
        m3d.assign_matrix(MatrixACMagnetic(signal_sources=sources, matrix_name="Lmatrix"))
        print("MATRIX ASSIGNED:", winding_names)
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
