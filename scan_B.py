import os, time, csv, math
from ansys.aedt.core import Desktop, Maxwell3d

# 方案 B：铁氧体条宽 W 三档 × Rx X 移动 11 点
W_VALS = [10.0, 15.0, 20.0]
G_FIXED = 15.0
DXS = list(range(-50, 51, 10))   # Rx X 偏移 -50~+50 步长10

THK, Z_GAP = 10.0, 30.0
FERR_GROUPS = {"Tx": (-170.0, 171.0), "Rx": (-84.0, 85.0)}
COIL_Y_LO, COIL_Y_HI = -84.0, 84.0
HOLE_RAD = 1.0
RAD = 0.3
ENDS = {
    "Tx1": [(-56.0, -15.0), (-2.36, -71.87)],
    "Tx2": [(116.0, -15.0), (169.64, -71.87)],
    "Rx":  [(30.0, -15.0), (83.64, -71.87)],
}
LEAD_GROUP = {"Tx1": "Tx", "Tx2": "Tx", "Rx": "Rx"}
LEAD_Z = {"Tx1": (-45.0, 45.0), "Tx2": (-45.0, 45.0), "Rx": (30.0, 45.0)}
CSV = r"C:/Users/lenovo/Desktop/zidong/scan_B.csv"
LOG = r"C:/Users/lenovo/Desktop/zidong/scan_B.log"

def log(msg):
    line = "%s | %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def read_done():
    done = set()
    if os.path.exists(CSV):
        with open(CSV) as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                if len(row) >= 3 and row[0].lstrip("-").replace(".", "").isdigit():
                    done.add((float(row[0]), float(row[2])))  # (W, dx)
    return done

def rebuild_ferrite(m3d, W, G):
    for n in [n for n in m3d.modeler.object_names if n.startswith("ferrite_")]:
        try:
            m3d.modeler.delete(n)
        except Exception:
            pass
    def x_centers(target_hi, w, g):
        k = 0
        while True:
            if k * (w + g) + w / 2.0 >= target_hi:
                break
            k += 1
        xs = [0.0]
        for kk in range(1, k + 1):
            xs.append(kk * (w + g)); xs.append(-kk * (w + g))
        return xs
    ferr = []
    for group, (x_lo, x_hi) in FERR_GROUPS.items():
        z_bot = 30.0 + Z_GAP if group == "Rx" else -Z_GAP - THK
        for xc in x_centers(max(abs(x_lo), abs(x_hi)), W, G):
            idx = len([n for n in ferr if n.startswith("ferrite_" + group)])
            name = "ferrite_%s_%d" % (group, idx)
            try:
                box = m3d.modeler.create_box(origin=[xc - W / 2.0, COIL_Y_LO, z_bot],
                                             sizes=[W, COIL_Y_HI - COIL_Y_LO, THK], name=name)
                box.material_name = "ferrite"
                ferr.append(name)
            except Exception as e:
                log("ferrite err: %s" % repr(e))
    for coil, pts in ENDS.items():
        group = LEAD_GROUP[coil]
        for i, (lx, ly) in enumerate(pts):
            z0, h = LEAD_Z[coil]
            lz_lo, lz_hi = min(z0, z0 + h), max(z0, z0 + h)
            aux = None
            try:
                aux = m3d.modeler.create_cylinder(orientation="Z", origin=[lx, ly, lz_lo],
                                                  radius=HOLE_RAD, height=lz_hi - lz_lo, name="aux_hole")
            except Exception:
                pass
            for fn in ferr:
                if not fn.startswith("ferrite_" + group):
                    continue
                try:
                    bb = m3d.modeler[fn].bounding_box
                    if (bb[0] <= lx + RAD and bb[3] >= lx - RAD) and (bb[1] <= ly + RAD and bb[4] >= ly - RAD) and (bb[2] <= lz_hi and bb[5] >= lz_lo):
                        m3d.modeler.subtract(blank_list=[fn], tool_list=[aux.name], keep_originals=False)
                except Exception:
                    pass
            if aux is not None:
                try:
                    if aux.name in m3d.modeler.object_names:
                        m3d.modeler.delete(aux.name)
                except Exception:
                    pass
    return len(ferr)

def reset_rx(m3d):
    try:
        bb = m3d.modeler["Rx"].bounding_box
        off = (bb[0] + bb[3]) / 2.0
        if abs(off) > 1:
            m3d.modeler.move(["Rx"], [-off, 0, 0])
            for fn in [n for n in m3d.modeler.object_names if n.startswith("ferrite_Rx_")]:
                try:
                    m3d.modeler.move([fn], [-off, 0, 0])
                except Exception:
                    pass
    except Exception:
        pass

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False, close_on_exit=False)
m3d = Maxwell3d(project="Projecttonight", design="WPT_G")
log("connected, solution: %s" % m3d.solution_type)
try:
    m3d.materials["ferrite"].conductivity.value = 0
    m3d.materials["ferrite"].permeability.value = 300
except Exception as e:
    log("mat err: %s" % repr(e))
try:
    s = m3d.setups[0]
    s.props["MaximumPasses"] = 8
    s.props["PercentError"] = 5
    s.props["PercentRefinement"] = 5
    s.update()
except Exception as e:
    log("setup err: %s" % repr(e))

done = read_done()
log("done combos: %d" % len(done))

w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
for W in W_VALS:
    reset_rx(m3d)
    nf = rebuild_ferrite(m3d, W, G_FIXED)
    log("=== W=%.0f G=%.0f rebuilt %d bars ===" % (W, G_FIXED, nf))
    current = 0.0
    for dx in DXS:
        if (W, float(dx)) in done:
            log("skip W=%.0f dx=%d" % (W, dx))
            continue
        # 用 Rx 实际位置（bbox）计算移动量，避免断点续跑位置错位
        try:
            bb = m3d.modeler["Rx"].bounding_box
            cur_x = (bb[0] + bb[3]) / 2.0
        except Exception:
            cur_x = current
        delta = dx - cur_x
        if abs(delta) > 1e-6:
            try:
                m3d.modeler.move(["Rx"], [delta, 0, 0])
                for fn in [n for n in m3d.modeler.object_names if n.startswith("ferrite_Rx_")]:
                    try:
                        m3d.modeler.move([fn], [delta, 0, 0])
                    except Exception:
                        pass
            except Exception as e:
                log("move err: %s" % repr(e))
        current = float(dx)
        try:
            m3d.analyze(cores=8, run_in_thread=True)
        except Exception as e:
            log("analyze err: %s" % repr(e))
        solved = False
        for i in range(60):
            time.sleep(20)
            try:
                solved = m3d.setups[0].is_solved
            except Exception as e:
                log("poll err: %s" % repr(e))
            if solved:
                break
        if not solved:
            log("  FAIL W=%.0f dx=%d" % (W, dx))
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
            row = [W, G_FIXED, dx, round(L11, 3), round(L22, 3), round(L33, 3),
                   round(M12, 3), round(M13, 3), round(M23, 3), round(k13, 5), round(k23, 5)]
            log("  W=%.0f dx=%3d L11=%.1f M13=%.2f k13=%.4f" % (W, dx, L11, M13, k13))
            new_file = not os.path.exists(CSV) or os.path.getsize(CSV) == 0
            with open(CSV, "a", newline="") as f:
                wr = csv.writer(f)
                if new_file:
                    wr.writerow(["W_mm", "G_mm", "dx_mm", "L11_uH", "L22_uH", "L33_uH",
                                 "M12_uH", "M13_uH", "M23_uH", "k13", "k23"])
                wr.writerow(row)
        except Exception as e:
            log("  extract err: %s" % repr(e))
log("SCAN B DONE")
