import time
from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=8016)
m3d = Maxwell3d(project="Projecttonight", design="WPT_G")
rx_ferrites = [n for n in m3d.modeler.object_names if n.startswith("ferrite_Rx_")]
print("start", flush=True)

# 优化：MaxPass=4, Refine=10, PercentError=5
try:
    s = m3d.setups[0]
    s.props["MaximumPasses"] = 8
    s.props["PercentRefinement"] = 5
    s.props["PercentError"] = 5
    s.props["UseIterativeSolver"] = True
    s.update()
    print("setup MaxPass=4 Refine=10 PctErr=5", flush=True)
except Exception as e:
    print("setup err:", repr(e), flush=True)

# 移到 -50
bb = m3d.modeler["Rx"].bounding_box
cur = (bb[0] + bb[3]) / 2.0
delta = -50 - cur
print("cur=%.1f delta=%.2f" % (cur, delta), flush=True)
if abs(delta) > 1e-6:
    m3d.modeler.move(["Rx"], [delta, 0, 0])
    for fn in rx_ferrites:
        m3d.modeler.move([fn], [delta, 0, 0])

t0 = time.time()
try:
    m3d.analyze(cores=4, run_in_thread=True)
except Exception as e:
    print("analyze err:", repr(e), flush=True)
solved = False
for i in range(50):
    time.sleep(20)
    try:
        solved = m3d.setups[0].is_solved
    except Exception as e:
        print("poll err:", repr(e), flush=True)
    if solved:
        break
dt = time.time() - t0
print("dx=-50 solved:", solved, "elapsed %.0f s" % dt, flush=True)
if solved:
    try:
        w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
        data = m3d.post.get_solution_data(
            expressions=["Lmatrix.L(%s,%s)" % (wi, wj) for wi in w for wj in w],
            setup_sweep_name="Setup1 : LastAdaptive",
        )
        real, _ = data.full_matrix_real_imag
        print("M13=%.2f" % (real["Lmatrix.L(Winding_Tx1,Winding_Rx)"][0][1]/1000.0), flush=True)
    except Exception as e:
        print("extract err:", repr(e), flush=True)
else:
    try:
        for e in m3d.logger.aedt_error_messages:
            s2 = str(e)
            if "WPT_G" in s2:
                print("ERR:", s2, flush=True)
    except Exception as ex:
        print("log err:", repr(ex), flush=True)
print("DONE", flush=True)
