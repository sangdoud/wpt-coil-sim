from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="WPT_EC2")

# 1) 读 CoilTerminal 匝数（conductor number）
try:
    for b in m3d.boundaries:
        name = str(b)
        if "Coil_" in name or name.startswith("CT_"):
            try:
                print(name, "props:", dict(b.props) if hasattr(b, "props") else "n/a")
            except Exception as e:
                print(name, "props err:", repr(e))
except Exception as e:
    print("boundary read err:", repr(e))

# 2) 重建 Region：X/Y padding 50mm，Z 保持 0（引线末端落边）
try:
    m3d.modeler.delete("Region")
    print("old Region deleted")
except Exception as e:
    print("del region err:", repr(e))
try:
    m3d.modeler.create_region(pad_value=[50, 50, 50, 50, 0, 0], pad_type="Absolute Offset", name="Region")
    print("new Region created, X/Y pad 50mm")
except Exception as e:
    print("create region err:", repr(e))

# 3) 重新求解
try:
    m3d.analyze(cores=4, blocking=True)
    print("ANALYZE DONE")
except Exception as e:
    print("ANALYZE ERR:", repr(e))
try:
    for s in m3d.setups:
        print("setup", s.name, "solved:", s.is_solved)
except Exception as e:
    print("setup check err:", repr(e))
