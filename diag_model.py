from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")
print("SOLVER:", m3d.solution_type)
print("OBJECTS:", m3d.modeler.object_names)

for name in m3d.modeler.object_names:
    try:
        obj = m3d.modeler[name]
        bb = obj.bounding_box
        print("\n== %s ==" % name)
        print("  bbox:", bb)
        try:
            faces = obj.faces
            print("  nfaces:", len(faces))
            for f in faces:
                try:
                    print("   face id=%s area=%.4f center=%s normal=%s" % (
                        f.id, f.area, list(f.center), list(f.normal)))
                except Exception as fe:
                    print("   face id=%s area=%.4f (err: %s)" % (f.id, f.area, repr(fe)))
        except Exception as e:
            print("  faces err:", repr(e))
    except Exception as e:
        print("\n== %s ERR: %s" % (name, repr(e)))
