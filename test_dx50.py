import time
from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=8016)
m3d = Maxwell3d(project="Projecttonight", design="WPT_G")
rx_ferrites = [n for n in m3d.modeler.object_names if n.startswith("ferrite_Rx_")]
print("start", flush=True)

# 移到 -50
bb = m3d.modeler["Rx"].bounding_box
cur = (bb[0] + bb[3]) / 2.0
delta = -50 - cur
print("move to -50, delta=%.2f" % delta, flush=True)
if abs(delta) > 1e-6:
    m3d.modeler.move(["Rx"], [delta, 0, 0])
    for fn in rx_ferrites:
        m3d.modeler.move([fn], [delta, 0, 0])
print("moved", flush=True)

try:
    m3d.analyze(cores=4, run_in_thread=True)
    print("solve triggered", flush=True)
except Exception as e:
    print("analyze err:", repr(e), flush=True)

solved = False
for i in range(40):
    time.sleep(15)
    try:
        solved = m3d.setups[0].is_solved
    except Exception as e:
        print("poll err:", repr(e), flush=True)
    if solved:
        break
print("dx=-50 solved:", solved, flush=True)

# 读错误
try:
    errs = m3d.logger.aedt_error_messages
    seen = set()
    for e in errs:
        s = str(e)
        if "WPT_G" not in s:
            continue
        k = s.split("(")[0].strip()
        if k in seen:
            continue
        seen.add(k)
        print("ERR:", s, flush=True)
except Exception as e:
    print("log err:", repr(e), flush=True)
print("DONE", flush=True)
