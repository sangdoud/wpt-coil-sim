import os, sys, time, csv, math, itertools
from ansys.aedt.core import Desktop, Maxwell3d

# ============================================================
# 全参数批量扫描脚本（服务器可部署）
# ------------------------------------------------------------
# 参数表驱动：从 combos.csv 读取参数组合，逐点求解。
# 断点续跑：读结果 CSV，已算点自动跳过；每点算完立即写盘。
#
# 使用前修改下方「可配置区」：
#   1) CSV / LOG / PLAN 路径
#   2) PROJECT / DESIGN 名称（若服务器项目名不同）
#   3) AEDT 连接方式（new_desktop / aedt_process_id / 端口）
#   4) 求解核数、精度
#
# 生成参数表：
#   python batch_sweep.py --gen-plan
#   （自动生成 W=10~20 步长1 × G=10~20 步长1 × dx=-50~50 步长10 全组合 1331 点）
# 运行扫描：
#   python batch_sweep.py
# 后台脱离终端：
#   nohup python batch_sweep.py > /dev/null 2>&1 &
# ============================================================

# ============ 可配置区（按服务器实际修改） ============
BASE_DIR = r"C:/Users/lenovo/Desktop/zidong"
PLAN_CSV = os.path.join(BASE_DIR, "combos.csv")          # 参数组合表（输入）
OUT_CSV  = os.path.join(BASE_DIR, "sweep_all.csv")       # 结果汇总（输出）
LOG_FILE = os.path.join(BASE_DIR, "batch_sweep.log")     # 运行日志

PROJECT = "Projecttonight"
DESIGN  = "WPT_G"
AEDT_VERSION = "2024.1"

# AEDT 连接方式：
#  - 连接已运行的 AEDT: new_desktop=False
#  - 让脚本自己启动 AEDT: new_desktop=True, non_graphical 建议 False(有GUI) 或 True(服务器无桌面)
NEW_DESKTOP = False
NON_GRAPHICAL = False
AEDT_PROCESS_ID = None      # 若连接指定进程，填 PID；None 自动找
GRPC_PORT = None            # 默认 50051；若 AEDT 用别的端口填这里

CORES = 8                   # 求解核数
MAX_PASSES = 8              # 求解精度
PCT_ERROR = 5
PCT_REFINEMENT = 5

# 模型固定参数（与建模脚本一致，一般不用改）
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

# ============ 参数表生成（默认全组合） ============
W_RANGE = list(range(10, 21))        # 10~20 步长 1
G_RANGE = list(range(10, 21))        # 10~20 步长 1
DX_RANGE = list(range(-50, 51, 10))  # -50~50 步长 10
MU_RANGE = [300.0]                   # 铁氧体磁导率（可多值）

def gen_plan_csv():
    combos = list(itertools.product(W_RANGE, G_RANGE, DX_RANGE, MU_RANGE))
    with open(PLAN_CSV, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["W_mm", "G_mm", "dx_mm", "mu"])
        for w, g, dx, mu in combos:
            wr.writerow([w, g, dx, mu])
    return len(combos)

# ============ 工具函数 ============
def log(msg):
    line = "%s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def read_done():
    """读结果 CSV，返回已完成 (W,G,dx,mu) 集合"""
    done = set()
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV) as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                if len(row) >= 4 and row[0].lstrip("-").replace(".", "").isdigit():
                    done.add((float(row[0]), float(row[1]), float(row[2]), float(row[3])))
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

def set_rx_dx(m3d, dx):
    """用 Rx bbox 实际位置移动，避免断点续跑位置错位"""
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

def solve_and_extract(d, m3d, W, G, dx, mu):
    # 铁氧体材料属性
    try:
        m3d.materials["ferrite"].conductivity.value = 0
        m3d.materials["ferrite"].permeability.value = mu
    except Exception as e:
        log("mat err: %s" % repr(e))
    # 求解前停掉可能残留的旧模拟，避免 gRPC 状态冲突（历史教训：G=12 失败后 G=14 报 GetAvailableReportTypes）
    try:
        d.odesktop.StopSimulations(True)
        time.sleep(5)
    except Exception as e:
        log("stop err: %s" % repr(e))
    # 求解精度
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
    solved = False
    for i in range(90):   # 最多 30 分钟
        time.sleep(20)
        try:
            solved = m3d.setups[0].is_solved
        except Exception as e:
            log("poll err: %s" % repr(e))
        if solved:
            break
    if not solved:
        log("  FAILED W=%.0f G=%.0f dx=%3d mu=%.0f" % (W, G, dx, mu))
        # 失败后停掉残留求解，防止污染下一点
        try:
            d.odesktop.StopSimulations(True)
            time.sleep(3)
        except Exception:
            pass
        return False
    w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
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
        row = [W, G, dx, mu, round(L11, 3), round(L22, 3), round(L33, 3),
               round(M12, 3), round(M13, 3), round(M23, 3), round(k13, 5), round(k23, 5)]
        log("  W=%.0f G=%.0f dx=%3d mu=%.0f L11=%.1f M13=%.2f k13=%.4f"
            % (W, G, dx, mu, L11, M13, k13))
        new_file = not os.path.exists(OUT_CSV) or os.path.getsize(OUT_CSV) == 0
        with open(OUT_CSV, "a", newline="") as f:
            wr = csv.writer(f)
            if new_file:
                wr.writerow(["W_mm", "G_mm", "dx_mm", "mu", "L11_uH", "L22_uH", "L33_uH",
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

    # 1) 读取参数表
    if not os.path.exists(PLAN_CSV):
        print("未找到参数表 %s，先运行: python batch_sweep.py --gen-plan" % PLAN_CSV)
        sys.exit(1)
    combos = []
    with open(PLAN_CSV) as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) >= 4 and row[0].lstrip("-").replace(".", "").isdigit():
                combos.append((float(row[0]), float(row[1]), float(row[2]), float(row[3])))
    log("loaded %d combos from %s" % (len(combos), PLAN_CSV))

    # 2) 连接 AEDT（先尝试连接已运行实例，失败则自动启动）
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
            log("connected to running AEDT: %s / %s, solution=%s"
                % (PROJECT, DESIGN, m3d.solution_type))
        except Exception as e:
            log("connect to running AEDT failed: %s" % repr(e))
            log("attempting to start a new AEDT session...")
            d = None
    if d is None:
        try:
            d, m3d = _connect(True, None, None)   # 自动启动新 AEDT
            log("started new AEDT: %s / %s, solution=%s"
                % (PROJECT, DESIGN, m3d.solution_type))
        except Exception as e:
            log("START AEDT FAILED: %s" % repr(e))
            sys.exit(1)

    # 3) 断点续跑
    done = read_done()
    log("already done: %d" % len(done))

    # 4) 逐点求解（铁氧体按 W,G 分组重建，dx 移动 Rx）
    last_wg = None
    for W, G, dx, mu in combos:
        key = (W, G, dx, mu)
        if key in done:
            continue
        # 铁氧体配置变化才重建（同一 W,G 下只移动 Rx）
        if last_wg is None or last_wg != (W, G):
            # 重要顺序：必须先归零 Rx（连同旧铁氧体），再重建新铁氧体。
            # 若先重建后归零，新铁氧体 Rx 组会被 set_rx_dx(0) 误移走，数据全错。
            set_rx_dx(m3d, 0.0)
            nf = rebuild_ferrite(m3d, W, G)
            log("=== W=%.0f G=%.0f rebuilt %d bars ===" % (W, G, nf))
            last_wg = (W, G)
        set_rx_dx(m3d, dx)
        ok = solve_and_extract(d, m3d, W, G, dx, mu)
        if ok:
            done.add(key)
    log("BATCH SWEEP DONE")
