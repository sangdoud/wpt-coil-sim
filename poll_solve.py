import time
from ansys.aedt.core import Desktop, Maxwell3d

DESIGN = "WPT_G"
d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design=DESIGN)
for i in range(80):
    try:
        solved = m3d.setups[0].is_solved
        print("[poll %d] solved: %s" % (i, solved), flush=True)
        if solved:
            break
    except Exception as e:
        print("[poll %d] err: %s" % (i, repr(e)), flush=True)
    time.sleep(30)
print("POLL DONE", flush=True)
