import os, time, csv, math
from ansys.aedt.core import Desktop, Maxwell3d

DESIGN = "WPT_G"
DXS = list(range(-50, 51, 10))
CSV = r"C:/Users/lenovo/Desktop/zidong/scan_RxX.csv"
LOG = r"C:/Users/lenovo/Desktop/zidong/scan_resume.log"

def log(msg):
    line = "%s | %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

# 读已完成点
done = set()
if os.path.exists(CSV):
    with open(CSV) as f:
        r = csv.reader(f)
        next(r, None)  # header
        for row in r:
            if row and row[0].lstrip("-").isdigit():
                done.add(int(row[0]))
todo = [dx for dx in DXS if dx not in done]
log("todo points: %s" % todo)

if not todo:
    log("ALL DONE - nothing to run")
    raise SystemExit(0)

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=8016)
m3d = Maxwell3d(project="Projecttonight", design=DESIGN)

# 铁氧体 μr=300, 电导率 0
try:
    m3d.materials["ferrite"].conductivity.value = 0
    m3d.materials["ferrite"].permeability.value = 300
except Exception as e:
    log("mat err: %s" % repr(e))

# setup 快配置
try:
    s = m3d.setups[0]
    s.props["MaximumPasses"] = 8
    s.props["PercentError"] = 5
    s.props["PercentRefinement"] = 5
    s.update()
except Exception as e:
    log("setup err: %s" % repr(e))

rx_ferrites = [n for n in m3d.modeler.object_names if n.startswith("ferrite_Rx_")]

# 重置 Rx 到 0
try:
    bb = m3d.modeler["Rx"].bounding_box
    off = (bb[0] + bb[3]) / 2.0
    if abs(off) > 1:
        m3d.modeler.move(["Rx"], [-off, 0, 0])
        for fn in rx_ferrites:
            m3d.modeler.move([fn], [-off, 0, 0])
    log("reset Rx to 0")
except Exception as e:
    log("reset err: %s" % repr(e))

w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
current = 0
new_header = not os.path.exists(CSV) or os.path.getsize(CSV) == 0

for dx in todo:
    log("=== dx = %d mm ===" % dx)
    delta = dx - current
    if abs(delta) > 1e-6:
        try:
            m3d.modeler.move(["Rx"], [delta, 0, 0])
            for fn in rx_ferrites:
                m3d.modeler.move([fn], [delta, 0, 0])
            current = dx
        except Exception as e:
            log("move err: %s" % repr(e))
    try:
        m3d.analyze(cores=8, run_in_thread=True)
    except Exception as e:
        log("analyze err: %s" % repr(e))
    solved = False
    for i in range(80):
        time.sleep(20)
        try:
            solved = m3d.setups[0].is_solved
        except Exception as e:
            log("poll err: %s" % repr(e))
        if solved:
            break
    if not solved:
        log("  dx=%d FAILED" % dx)
        with open(CSV, "a", newline="") as f:
            wr = csv.writer(f)
            if new_header:
                wr.writerow(["dx_mm", "L11_Tx1_uH", "L22_Tx2_uH", "L33_Rx_uH", "M12_uH", "M13_uH", "M23_uH", "k13", "k23"])
                new_header = False
            wr.writerow([dx, "FAIL"])
        continue
    try:
        data = m3d.post.get_solution_data(
            expressions=["Lmatrix.L(%s,%s)" % (wi, wj) for wi in w for wj in w],
            setup_sweep_name="Setup1 : LastAdaptive",
        )
        real, _ = data.full_matrix_real_imag
        def L(i, j):
            return real["Lmatrix.L(%s,%s)" % (w[i], w[j])][0][1] / 1000.0
        L11, L22, L33 = L(0, 0), L(1, 1), L(2, 2)
        M12, M13, M23 = L(0, 1), L(0, 2), L(1, 2)
        k13 = M13 / math.sqrt(L11 * L33) if L11 > 0 and L33 > 0 else 0
        k23 = M23 / math.sqrt(L22 * L33) if L22 > 0 and L33 > 0 else 0
        row = [dx, round(L11, 2), round(L22, 2), round(L33, 2), round(M12, 2), round(M13, 2), round(M23, 2), round(k13, 4), round(k23, 4)]
        log("  dx=%d M13=%.2f M23=%.2f k13=%.4f k23=%.4f" % (dx, M13, M23, k13, k23))
        with open(CSV, "a", newline="") as f:
            wr = csv.writer(f)
            if new_header:
                wr.writerow(["dx_mm", "L11_Tx1_uH", "L22_Tx2_uH", "L33_Rx_uH", "M12_uH", "M13_uH", "M23_uH", "k13", "k23"])
                new_header = False
            wr.writerow(row)
    except Exception as e:
        log("  extract err: %s" % repr(e))
log("RESUME SCAN DONE")
