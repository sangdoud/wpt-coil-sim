from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC")
print("solution:", m3d.solution_type)

# 理论端面坐标（绝对）：(name, start, end)
coils = {
    "Tx1": ((-56.0, -15.0, 0.0), (-2.36, -71.87, 0.0)),
    "Tx2": ((116.0, -15.0, 0.0), (169.64, -71.87, 0.0)),
    "Rx":  ((30.0, -15.0, 30.0), (83.64, -71.87, 30.0)),
}

for cname, (start, end) in coils.items():
    obj = m3d.modeler[cname]
    found = None
    for f in obj.faces:
        c = list(f.center)
        # 匹配起点端面
        if abs(c[0]-start[0])<3 and abs(c[1]-start[1])<3 and abs(c[2]-start[2])<1:
            found = f.id
            print("%s start face id=%s center=%s" % (cname, f.id, c))
            break
    if found is None:
        print("%s start face NOT FOUND" % cname)
        continue
    # 在端面上 Assign Current (Stranded, 1A)
    try:
        m3d.assign_current(assignment=[found], amplitude=1, solid=False, name="Coil_%s" % cname)
        print("  -> assigned current on face", found)
    except Exception as e:
        print("  assign err:", repr(e))
