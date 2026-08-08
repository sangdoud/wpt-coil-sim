import sys
from ansys.aedt.core import Desktop

print("import OK")
try:
    d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
                close_on_exit=False, aedt_process_id=13520)
    print("Connected to AEDT")
    try:
        print("Projects:", d.project_list)
    except Exception as e:
        print("project_list err:", repr(e))
except Exception as e:
    print("CONNECT_ERROR:", repr(e))
    sys.exit(1)
