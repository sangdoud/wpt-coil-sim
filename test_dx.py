import time
from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=8016)
m3d = Maxwell3d(project="Projecttonight", design="WPT_G")

rx_ferrites = [n for n in m3d.modeler.object_names if n.startswith("ferrite_Rx_")]

def set_dx(target):
    bb = m3d.modeler["Rx"].bounding_box
    cur = (bb[0] + bb[3]) / 2.0
    delta = target - cur
    print("current=%.1f target=%.1f delta=%.1f" % (cur, target, delta), flush=True)
    if abs(delta) > 1e-6:
        m3d.modeler.move(["Rx"], [delta, 0, 0])
        for fn in rx_ferrites:
            m3d.modeler.move([fn], [delta, 0, 0])

# 测 dx=0
set_dx(0)
try:
    m3d.analyze(cores=8, run_in_thread=True)
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
print("dx=0 solved:", solved, flush=True)

if solved:
    # 提取
    try:
        w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
        data = m3d.post.get_solution_data(
            expressions=["Lmatrix.L(%s,%s)" % (wi, wj) for wi in w for wj in w],
            setup_sweep_name="Setup1 : LastAdaptive",
        )
        real, _ = data.full_matrix_real_imag
        print("L11=%.1f M13=%.2f" % (real["Lmatrix.L(Winding_Tx1,Winding_Tx1)"][0][1]/1000.0,
                                      real["Lmatrix.L(Winding_Tx1,Winding_Rx)"][0][1]/1000.0), flush=True)
    except Exception as e:
        print("extract err:", repr(e), flush=True)
else:
    # 读错误
    try:
        for e in m3d.logger.aedt_error_messages:
            if "WPT_G" in str(e) and "10:2" in str(e):
                print("ERR:", e, flush=True)
    except Exception as ex:
        print("log err:", repr(ex), flush=True)

# 测 dx=-50
set_dx(-50)
try:
    m3d.analyze(cores=8, run_in_thread=True)
except Exception as e:
    print("analyze err:", repr(e), flush=True)
solved2 = False
for i in range(40):
    time.sleep(15)
    try:
        solved2 = m3d.setups[0].is_solved
    except Exception as e:
        print("poll err:", repr(e), flush=True)
    if solved2:
        break
print("dx=-50 solved:", solved2, flush=True)
if not solved2:
    try:
        for e in m3d.logger.aedt_error_messages:
            if "WPT_G" in str(e):
                print("ERR:", e, flush=True)
    except Exception as ex:
        print("log err:", repr(ex), flush=True)
print("TEST DONE", flush=True)
