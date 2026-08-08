from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")

# 读取设计消息（error=3, warning=2, info=1）
for level, name in [(3, "ERROR"), (2, "WARNING")]:
    try:
        msgs = m3d.odesign.GetDesignMessages("", level)
        print("=== %s MESSAGES ===" % name)
        if msgs:
            for m in msgs:
                print(" ", m)
        else:
            print("  (none)")
    except Exception as e:
        print(name, "ERR:", repr(e))

# 当前激励
try:
    print("EXCITATIONS:", list(m3d.oboundary.GetExcitations()))
except Exception as e:
    print("EXC ERR:", repr(e))
