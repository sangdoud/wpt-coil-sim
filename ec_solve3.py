from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixACMagnetic, SourceACMagnetic

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC2")

# 0) 清掉所有激励（含残留 Coil1）
try:
    m3d.oboundary.DeleteAllExcitations()
    print("all excitations cleared")
except Exception as e:
    print("clear err:", repr(e))

# 1) 找引线末端面
term_face = {}
for cname, zterm in [("Tx1", -20.0), ("Tx2", -20.0), ("Rx", 45.0)]:
    obj = m3d.modeler[cname]
    fid, best = None, 1e9
    for f in obj.faces:
        c = list(f.center)
        if abs(c[2] - zterm) < 0.5:
            area = getattr(f, "area", None)
            if area is None:
                continue
            if abs(area - 2.01) < best:
                best = abs(area - 2.01)
                fid = f.id
    if fid is None:
        print("face NOT FOUND for", cname)
    else:
        term_face[cname] = fid
        print(cname, "term face", fid)

# 2) assign_winding
winding_names = []
for cname, fid in term_face.items():
    wname = "Winding_%s" % cname
    try:
        m3d.assign_winding(assignment=[fid], winding_type="Current", is_solid=False,
                           current=1, name=wname)
        winding_names.append(wname)
        print("winding", wname, "OK")
    except Exception as e:
        print("winding", wname, "err:", repr(e))

# 3) assign_matrix
if len(winding_names) == 3:
    try:
        m3d.assign_matrix(MatrixACMagnetic(
            signal_sources=[SourceACMagnetic(name=w) for w in winding_names],
            matrix_name="Lmatrix"))
        print("MATRIX ASSIGNED")
    except Exception as e:
        print("matrix err:", repr(e))

# 4) solve
try:
    m3d.analyze(cores=4, blocking=True)
    print("ANALYZE DONE")
except Exception as e:
    print("ANALYZE ERR:", repr(e))

# 5) check
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
