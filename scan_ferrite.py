import os, time, csv, math
from ansys.aedt.core import Desktop, Maxwell3d

# 扫描②：铁氧体条宽 W 10-20（G=15 固定）
# 扫描③：X向条间气隙 G 10-20（W=15 固定）
W_VALS = [10, 12, 14, 16, 18, 20]
G_VALS = [10, 12, 14, 16, 18, 20]
G_FIXED_W_SCAN = 15.0
W_FIXED_G_SCAN = 15.0

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
CSV_W = r"C:/Users/lenovo/Desktop/zidong/scan_W.csv"
CSV_G = r"C:/Users/lenovo/Desktop/zidong/scan_G.csv"
LOG = r"C:/Users/lenovo/Desktop/zidong/scan_ferrite.log"

def log(msg):
    line = "%s | %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def read_done(csv_path):
    done = set()
    if os.path.exists(csv_path):
        with open(csv_path) as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                if row and row[0].lstrip("-").replace(".", "").isdigit():
                    done.add(float(row[0]))
    return done

def rebuild_ferrite(m3d, W, G):
    # 删旧铁氧体
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
    # 开孔
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

def solve_and_extract(m3d, W, G, csv_path):
    # setup 精度
    try:
        s = m3d.setups[0]
        s.props["MaximumPasses"] = 8
        s.props["PercentError"] = 5
        s.props["PercentRefinement"] = 5
        s.update()
    except Exception as e:
        log("setup err: %s" % repr(e))
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
        log("  FAILED (W=%.0f G=%.0f)" % (W, G))
        return
    try:
        w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
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
        row = [W, G, round(L11, 2), round(L22, 2), round(L33, 2), round(M12, 2), round(M13, 2), round(M23, 2), round(k13, 4), round(k23, 4)]
        log("  W=%.0f G=%.0f L11=%.1f M13=%.2f M23=%.2f k13=%.4f" % (W, G, L11, M13, M23, k13))
        new_file = not os.path.exists(csv_path) or os.path.getsize(csv_path) == 0
        with open(csv_path, "a", newline="") as f:
            wr = csv.writer(f)
            if new_file:
                wr.writerow(["W_mm", "G_mm", "L11_uH", "L22_uH", "L33_uH", "M12_uH", "M13_uH", "M23_uH", "k13", "k23"])
            wr.writerow(row)
    except Exception as e:
        log("  extract err: %s" % repr(e))

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False, close_on_exit=False)
m3d = Maxwell3d(project="Projecttonight", design="WPT_G")
log("connected, solution: %s" % m3d.solution_type)

try:
    m3d.materials["ferrite"].conductivity.value = 0
    m3d.materials["ferrite"].permeability.value = 300
except Exception as e:
    log("mat err: %s" % repr(e))

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
            log("reset Rx to 0")
    except Exception as e:
        log("reset err: %s" % repr(e))

# === 扫描②：W 变化，G=15 固定 ===
log("=== SCAN W (bar width), G=%.0f fixed ===" % G_FIXED_W_SCAN)
done_w = read_done(CSV_W)
for w_val in W_VALS:
    if w_val in done_w:
        log("skip W=%d (done)" % w_val)
        continue
    log("=== W = %d mm (G=15) ===" % w_val)
    reset_rx(m3d)
    n_ferr = rebuild_ferrite(m3d, float(w_val), G_FIXED_W_SCAN)
    log("  rebuilt %d bars" % n_ferr)
    solve_and_extract(m3d, float(w_val), G_FIXED_W_SCAN, CSV_W)
log("SCAN W done")

# === 扫描③：G 变化，W=15 固定 ===
log("=== SCAN G (gap), W=%.0f fixed ===" % W_FIXED_G_SCAN)
done_g = read_done(CSV_G)
for g_val in G_VALS:
    if g_val in done_g:
        log("skip G=%d (done)" % g_val)
        continue
    log("=== G = %d mm (W=15) ===" % g_val)
    reset_rx(m3d)
    n_ferr = rebuild_ferrite(m3d, W_FIXED_G_SCAN, float(g_val))
    log("  rebuilt %d bars" % n_ferr)
    solve_and_extract(m3d, W_FIXED_G_SCAN, float(g_val), CSV_G)
log("SCAN G done")
log("ALL DONE")
