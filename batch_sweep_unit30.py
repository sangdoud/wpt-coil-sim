# -*- coding: utf-8 -*-
# 批量扫描（UNIT=30 版）——固定单元周期 W+G=30，铁氧体条宽 W=10~20 步长1
# 求解器：Magnetostatic（WPT_G，已验证稳定）
# 参数：
#   W  铁氧体条宽    10~20 mm 步长 1（11 值）
#   G  条间缝隙      固定 = 30 - W（单元周期 W+G=30，G=20~10）
#   tg Tx1/Tx2 内边缘间隔 = k×(W+G) = k×30（默认 {0,30,60,90,120}）
#   dx Rx 水平偏移   所有 tg 统一 ±150（最大位移，两方向各 1 点，保证每组采样点一致）
#   mu 磁导率        当前模型 ferrite μr = 1000（与 batch_sweep_full.py 一致）
# Region 处理：沿用 batch_sweep_full.py 的 ensure_region()，tg 大时自动扩大 Region
import os, sys, time, csv, math
from ansys.aedt.core import Desktop, Maxwell3d

# ============ 可配置区 ============
BASE_DIR = r"C:/Users/lenovo/Desktop/zidong"
PLAN_CSV = os.path.join(BASE_DIR, "combos_unit30.csv")
OUT_CSV  = os.path.join(BASE_DIR, "sweep_all_unit30.csv")
LOG_FILE = os.path.join(BASE_DIR, "batch_sweep_unit30.log")

PROJECT = r"C:/Users/lenovo/Documents/Ansoft/Projecttonight.aedt"
DESIGN  = "WPT_G"
AEDT_VERSION = "2024.1"

NEW_DESKTOP = False
NON_GRAPHICAL = False
AEDT_PROCESS_ID = None
GRPC_PORT = None

CORES = 8
MAX_PASSES = 8
PCT_ERROR = 5
PCT_REFINEMENT = 5

# 模型固定参数
THK, Z_GAP = 10.0, 30.0
COIL_Y_LO, COIL_Y_HI = -84.0, 84.0
HOLE_RAD = 1.0
RAD = 0.3
COIL_SIZE = 168.9          # 发射线圈外尺寸（从 WPT_G 实测）
RX_CENTER = 0.0
ENDS = {
    "Tx1": [(-56.0, -15.0), (-2.36, -71.87)],
    "Tx2": [(116.0, -15.0), (169.64, -71.87)],
    "Rx":  [(30.0, -15.0), (83.64, -71.87)],
}
LEAD_Z = {"Tx1": (-45.0, 45.0), "Tx2": (-45.0, 45.0), "Rx": (30.0, 45.0)}
LEAD_REL = {
    "Tx1": [(29.4, -15.0), (83.0, -71.87)],
    "Tx2": [(29.4, -15.0), (83.0, -71.87)],
    "Rx":  [(30.0, -15.0), (83.64, -71.87)],
}

# ============ 参数范围（UNIT=30：W+G=30，W=10~20 步长1） ============
UNIT = 30.0            # 固定单元周期（原 40 → 30）
W_RANGE = [10.0 + i for i in range(11)]   # 铁氧体条宽 10~20 步长 1（11 值）
# G = UNIT - W（20~10）

SWEEP_TG = True        # True: tg = k×UNIT (0,30,60,90,120)；False: 只跑 tg=0
SWEEP_DX = True        # True: dx = -150~150 步长10（所有 tg 统一全范围）；False: 只跑 dx=0
DX_MODE = "range"      # "range" = 固定全范围 ±DX_FIXED_MAX 步长 DX_STEP（所有 tg 统一）；"max" = 只扫 ±DX_FIXED_MAX（2点）
DX_FIXED_MAX = 150.0   # dx 固定全范围半宽：所有 tg 的 dx 都扫 -150~150 步长10（31 点，每组采样点一致）
DX_STEP = 10           # dx 步长
TG_MAX = 120.0         # tg 上限
DX_MAX_LIMIT = 150     # dx 半宽上限
MU_RANGE = [1000.0]

def dx_max_for_tg(tg):
    """dx 移动范围半宽（取整到 10）：tg≤20 时 ±50，之后 tg 每增 20 半宽 +20，封顶 ±150"""
    raw = 50.0 + max(0.0, tg - 20.0)
    raw = min(raw, DX_MAX_LIMIT)
    return int(raw // DX_STEP) * DX_STEP

def txgap_plan(w, g):
    """发射线圈间隔 = k×(W+G)，k 整数，≤ TG_MAX"""
    p = w + g
    tgs, k = [], 0
    while k * p <= TG_MAX + 1e-9:
        tgs.append(k * p)
        k += 1
    return tgs

def ensure_region(m3d, tg):
    """确保 Region 完全包住所有对象（含铁氧体过覆盖，≥20mm 余量）；不够则删除重建（50mm 边距）"""
    objs = [o for o in m3d.modeler.object_names if o != "Region"]
    bb = None
    for o in objs:
        try:
            b = m3d.modeler[o].bounding_box
        except Exception:
            continue
        if bb is None:
            bb = list(b)
        else:
            bb[0] = min(bb[0], b[0]); bb[1] = min(bb[1], b[1]); bb[2] = min(bb[2], b[2])
            bb[3] = max(bb[3], b[3]); bb[4] = max(bb[4], b[4]); bb[5] = max(bb[5], b[5])
    if bb is None:
        return None
    try:
        rbb = m3d.modeler["Region"].bounding_box
        if rbb[0] <= bb[0] - 20.0 and rbb[3] >= bb[3] + 20.0:
            return rbb  # 已有 ≥20mm 余量
    except Exception:
        pass
    try:
        m3d.modeler.delete("Region")
        time.sleep(1)
    except Exception as e:
        log("region delete err: %s" % repr(e))
        return None
    try:
        m3d.modeler.create_region(pad_value=["50mm", "50mm", "50mm", "50mm", "0mm", "0mm"])
        rbb = m3d.modeler["Region"].bounding_box
        log("Region 重建: X[%.1f, %.1f] (tg=%.0f)" % (rbb[0], rbb[3], tg))
        return rbb
    except Exception as e:
        log("region create err: %s" % repr(e))
        return None

def gen_plan_csv():
    combos = []
    for w in W_RANGE:
        g = UNIT - w
        tgs = txgap_plan(w, g) if SWEEP_TG else [0.0]
        for tg in tgs:
            if SWEEP_DX:
                if DX_MODE == "range":
                    dxs = range(-int(DX_FIXED_MAX), int(DX_FIXED_MAX) + 1, DX_STEP)  # 固定全范围 -150~150 步长10（所有 tg 统一）
                else:
                    dxs = [-DX_FIXED_MAX, DX_FIXED_MAX]   # 只扫 ±150（2 点）
            else:
                dxs = [0]
            for dx in dxs:
                for mu in MU_RANGE:
                    combos.append((w, g, dx, tg, mu))
    with open(PLAN_CSV, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["W_mm", "G_mm", "dx_mm", "tx_gap_mm", "mu"])
        for w, g, dx, tg, mu in combos:
            wr.writerow([w, g, dx, tg, mu])
    return len(combos)

def log(msg):
    line = "%s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def read_done():
    done = set()
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV) as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                if len(row) >= 5 and row[0].lstrip("-").replace(".", "").isdigit():
                    done.add((float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4])))
    return done

def set_tx_gap(m3d, tx_gap):
    """按外边缘间隔移动两个发射线圈"""
    tx1_center = -tx_gap / 2.0 - COIL_SIZE / 2.0
    tx2_center =  tx_gap / 2.0 + COIL_SIZE / 2.0
    bb1 = m3d.modeler["Tx1"].bounding_box
    cur1 = (bb1[0] + bb1[3]) / 2.0
    bb2 = m3d.modeler["Tx2"].bounding_box
    cur2 = (bb2[0] + bb2[3]) / 2.0
    d1 = tx1_center - cur1
    d2 = tx2_center - cur2
    if abs(d1) > 1e-6:
        m3d.modeler.move(["Tx1"], [d1, 0, 0])
    if abs(d2) > 1e-6:
        m3d.modeler.move(["Tx2"], [d2, 0, 0])
    return tx1_center, tx2_center

def rebuild_ferrite(m3d, W, G, tx_gap):
    # 清理旧的铁氧体 + 残留的 aux_hole 开孔圆柱（gRPC 删除偶发失败，重试 2 次）
    for n in [n for n in m3d.modeler.object_names if n.startswith("ferrite_") or n.startswith("aux_hole")]:
        for _attempt in range(2):
            try:
                m3d.modeler.delete(n)
                break
            except Exception:
                time.sleep(1)
                continue
    tx1_c = -tx_gap / 2.0 - COIL_SIZE / 2.0
    tx2_c =  tx_gap / 2.0 + COIL_SIZE / 2.0
    emit_lo = tx1_c - COIL_SIZE / 2.0   # Tx1 左边缘
    emit_hi = tx2_c + COIL_SIZE / 2.0   # Tx2 右边缘

    def x_centers_continuous(lo, hi, w, g):
        """从 lo 到 hi 按 W+G 周期居中排布铁氧体条，两端过覆盖"""
        p = w + g
        span = hi - lo
        n = int(math.ceil(span / p)) + 1
        center = (lo + hi) / 2.0
        start = center - (n - 1) * p / 2.0
        return [start + k * p for k in range(n)]

    ferr = []
    for xc in x_centers_continuous(emit_lo, emit_hi, W, G):
        name = "ferrite_Tx_%d" % len([n for n in ferr if n.startswith("ferrite_Tx_")])
        try:
            box = m3d.modeler.create_box(origin=[xc - W / 2.0, COIL_Y_LO, -Z_GAP - THK],
                                         sizes=[W, COIL_Y_HI - COIL_Y_LO, THK], name=name)
            box.material_name = "ferrite"
            ferr.append(name)
        except Exception as e:
            log("ferrite Tx err: %s" % repr(e))
    rx_lo = RX_CENTER - COIL_SIZE / 2.0
    rx_hi = RX_CENTER + COIL_SIZE / 2.0
    for xc in x_centers_continuous(rx_lo, rx_hi, W, G):
        name = "ferrite_Rx_%d" % len([n for n in ferr if n.startswith("ferrite_Rx_")])
        try:
            box = m3d.modeler.create_box(origin=[xc - W / 2.0, COIL_Y_LO, 30.0 + Z_GAP],
                                         sizes=[W, COIL_Y_HI - COIL_Y_LO, THK], name=name)
            box.material_name = "ferrite"
            ferr.append(name)
        except Exception as e:
            log("ferrite Rx err: %s" % repr(e))
    # 开孔：引线穿过铁氧体
    for coil, pts in ENDS.items():
        if coil == "Tx1":
            base_x = tx1_c
        elif coil == "Tx2":
            base_x = tx2_c
        else:
            base_x = RX_CENTER
        group_pref = {"Tx1": "Tx", "Tx2": "Tx", "Rx": "Rx"}[coil]
        for i, (lx, ly) in enumerate(LEAD_REL[coil]):
            ax = base_x + lx
            z0, h = LEAD_Z[coil]
            lz_lo, lz_hi = min(z0, z0 + h), max(z0, z0 + h)
            aux = None
            try:
                aux = m3d.modeler.create_cylinder(orientation="Z", origin=[ax, ly, lz_lo],
                                                  radius=HOLE_RAD, height=lz_hi - lz_lo, name="aux_hole")
            except Exception:
                pass
            for fn in ferr:
                if not fn.startswith("ferrite_" + group_pref):
                    continue
                try:
                    bb = m3d.modeler[fn].bounding_box
                    if (bb[0] <= ax + RAD and bb[3] >= ax - RAD) and (bb[1] <= ly + RAD and bb[4] >= ly - RAD) and (bb[2] <= lz_hi and bb[5] >= lz_lo):
                        m3d.modeler.subtract(blank_list=[fn], tool_list=[aux.name], keep_originals=False)
                except Exception:
                    pass
            if aux is not None:
                for _attempt in range(2):
                    try:
                        if aux.name in m3d.modeler.object_names:
                            m3d.modeler.delete(aux.name)
                        break
                    except Exception:
                        time.sleep(1)
                        continue
    return len(ferr)

def set_rx_dx(m3d, dx):
    try:
        bb = m3d.modeler["Rx"].bounding_box
        cur_x = (bb[0] + bb[3]) / 2.0
    except Exception:
        cur_x = 0.0
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

def solve_and_extract(d, m3d, W, G, dx, tg, mu):
    try:
        m3d.materials["ferrite"].conductivity.value = 0
        m3d.materials["ferrite"].permeability.value = mu
    except Exception as e:
        log("mat err: %s" % repr(e))
    try:
        d.odesktop.StopSimulations(True)
        time.sleep(5)
    except Exception as e:
        log("stop err: %s" % repr(e))
    try:
        s = m3d.setups[0]
        s.props["MaximumPasses"] = MAX_PASSES
        s.props["PercentError"] = PCT_ERROR
        s.props["PercentRefinement"] = PCT_REFINEMENT
        s.update()
    except Exception as e:
        log("setup err: %s" % repr(e))
    try:
        m3d.analyze(cores=CORES, run_in_thread=True)
    except Exception as e:
        log("analyze err: %s" % repr(e))
    w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
    solved = False
    err_streak = 0
    for i in range(90):
        time.sleep(20)
        try:
            solved = m3d.setups[0].is_solved
            err_streak = 0
        except Exception as e:
            err_streak += 1
            log("poll err(%d): %s" % (err_streak, repr(e)))
        if solved:
            break
        if err_streak >= 3:
            log("  is_solved 查询异常，直接尝试提取验证")
            try:
                data = m3d.post.get_solution_data(
                    expressions=["Lmatrix.L(%s,%s)" % (wi, wj) for wi in w for wj in w],
                    setup_sweep_name="Setup1 : LastAdaptive")
                real, _ = data.full_matrix_real_imag
                solved = True
                break
            except Exception as e2:
                log("  extract probe err: %s" % repr(e2)[:120])
                err_streak = 0
    if not solved:
        log("  FAILED W=%.1f G=%.1f dx=%3d tg=%3d mu=%.0f" % (W, G, dx, tg, mu))
        try:
            d.odesktop.StopSimulations(True)
            time.sleep(3)
        except Exception:
            pass
        return False
    data = None
    for attempt in range(3):
        try:
            data = m3d.post.get_solution_data(
                expressions=["Lmatrix.L(%s,%s)" % (wi, wj) for wi in w for wj in w],
                setup_sweep_name="Setup1 : LastAdaptive",
            )
            real, _ = data.full_matrix_real_imag
            break
        except Exception as e:
            log("  extract attempt %d err: %s" % (attempt + 1, repr(e)))
            time.sleep(10)
    if data is None:
        return False
    try:
        real, _ = data.full_matrix_real_imag
        def L(i, j):
            return real["Lmatrix.L(%s,%s)" % (w[i], w[j])][0][1] / 1000.0
        L11, L22, L33 = L(0, 0), L(1, 1), L(2, 2)
        M12, M13, M23 = L(0, 1), L(0, 2), L(1, 2)
        k13 = M13 / math.sqrt(L11 * L33) if L11 > 0 and L33 > 0 else 0
        k23 = M23 / math.sqrt(L22 * L33) if L22 > 0 and L33 > 0 else 0
        row = [W, G, dx, tg, mu, round(L11, 3), round(L22, 3), round(L33, 3),
               round(M12, 3), round(M13, 3), round(M23, 3), round(k13, 5), round(k23, 5)]
        log("  W=%.1f G=%.1f dx=%3d tg=%3d mu=%.0f L11=%.1f M13=%.2f k13=%.4f"
            % (W, G, dx, tg, mu, L11, M13, k13))
        new_file = not os.path.exists(OUT_CSV) or os.path.getsize(OUT_CSV) == 0
        with open(OUT_CSV, "a", newline="") as f:
            wr = csv.writer(f)
            if new_file:
                wr.writerow(["W_mm", "G_mm", "dx_mm", "tx_gap_mm", "mu", "L11_uH", "L22_uH", "L33_uH",
                             "M12_uH", "M13_uH", "M23_uH", "k13", "k23"])
            wr.writerow(row)
        return True
    except Exception as e:
        log("  extract err: %s" % repr(e))
        return False

# ============ 主流程 ============
if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--gen-plan":
        n = gen_plan_csv()
        print("参数表已生成: %s (%d 组合)" % (PLAN_CSV, n))
        sys.exit(0)

    if not os.path.exists(PLAN_CSV):
        print("未找到参数表 %s，先运行: python batch_sweep_unit30.py --gen-plan" % PLAN_CSV)
        sys.exit(1)
    combos = []
    with open(PLAN_CSV) as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) >= 5 and row[0].lstrip("-").replace(".", "").isdigit():
                combos.append((float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4])))
    log("loaded %d combos from %s" % (len(combos), PLAN_CSV))

    def _connect(new_desktop, process_id, port):
        kwargs = dict(version=AEDT_VERSION, new_desktop=new_desktop,
                      non_graphical=NON_GRAPHICAL, close_on_exit=False)
        if process_id:
            kwargs["aedt_process_id"] = process_id
        if port:
            kwargs["port"] = port
        dd = Desktop(**kwargs)
        return dd, Maxwell3d(project=PROJECT, design=DESIGN)

    d = None
    m3d = None
    if not NEW_DESKTOP:
        try:
            d, m3d = _connect(False, AEDT_PROCESS_ID, GRPC_PORT)
            log("connected to running AEDT: %s / %s, solution=%s" % (PROJECT, DESIGN, m3d.solution_type))
        except Exception as e:
            log("connect to running AEDT failed: %s" % repr(e))
            log("attempting to start a new AEDT session...")
            d = None
    if d is None:
        try:
            d, m3d = _connect(True, None, None)
            log("started new AEDT: %s / %s, solution=%s" % (PROJECT, DESIGN, m3d.solution_type))
        except Exception as e:
            log("START AEDT FAILED: %s" % repr(e))
            sys.exit(1)

    done = read_done()
    log("already done: %d" % len(done))

    import backup_upload as _bu
    _last_backup = time.time()

    last_wg = None
    last_tg = None
    for W, G, dx, tg, mu in combos:
        key = (W, G, dx, tg, mu)
        if key in done:
            continue
        # 每小时自动备份：git 本地提交 + gh 上传 GitHub（用户要求）
        if time.time() - _last_backup >= 3600:
            try:
                _bu.run_backup()
            except Exception as e:
                log("backup err: %s" % repr(e)[:120])
            _last_backup = time.time()
        if last_tg is None or last_tg != tg:
            set_rx_dx(m3d, 0.0)
            set_tx_gap(m3d, tg)
            nf = rebuild_ferrite(m3d, W, G, tg)
            ensure_region(m3d, tg)
            log("=== W=%.1f G=%.1f tg=%3d rebuilt %d bars ===" % (W, G, tg, nf))
            last_tg = tg
            last_wg = (W, G)
        elif last_wg is None or last_wg != (W, G):
            set_rx_dx(m3d, 0.0)
            nf = rebuild_ferrite(m3d, W, G, tg)
            ensure_region(m3d, tg)
            log("=== W=%.1f G=%.1f rebuilt %d bars ===" % (W, G, nf))
            last_wg = (W, G)
        set_rx_dx(m3d, dx)
        ok = solve_and_extract(d, m3d, W, G, dx, tg, mu)
        if ok:
            done.add(key)
    log("BATCH SWEEP UNIT30 DONE")
