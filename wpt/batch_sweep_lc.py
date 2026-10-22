# -*- coding: utf-8 -*-
# 批量扫描（LC 参数化版）——线圈 LC(120~220 步长10) x KR(0.2~0.5) x W x tg x dx x thk(步长1)
# 线圈几何由 coil_gen.py 生成，匝间隙自适应；铁氧体 Y 向长度随线圈自适应
# 其余与原 batch_sweep_unit30.py 相同
# 求解器：Magnetostatic（WPT_G，已验证稳定）
# 参数：
#   W  铁氧体条宽    10~20 mm 步长 1（11 值）
#   G  条间缝隙      固定 = 30 - W（单元周期 W+G=30，G=20~10）
#   tg Tx1/Tx2 内边缘间隔 = k×(W+G) = k×30（默认 {0,30,60,90,120}）
#   dx Rx 水平偏移   所有 tg 统一 ±150（最大位移，两方向各 1 点，保证每组采样点一致）
#   mu 磁导率        当前模型 ferrite μr = 1000（与 batch_sweep_full.py 一致）
# Region 处理：沿用 batch_sweep_full.py 的 ensure_region()，tg 大时自动扩大 Region
import os, re, sys, time, csv, math, glob, threading, traceback, ctypes
from ctypes import wintypes
from ansys.aedt.core import Desktop, Maxwell3d

# stdout 被管道/计划任务捕获时中文 Windows 默认 GBK，中文日志会抛 UnicodeEncodeError
# 并让整个流程以退出码 1 结束（第一轮 b1_guard.py 正是这样在最后一行崩过）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

# ============ 可配置区 ============
BASE_DIR = r"C:/wpt"
PLAN_CSV = os.path.join(BASE_DIR, "combos_lc.csv")
OUT_CSV  = os.path.join(BASE_DIR, "sweep_all_lc.csv")
LOG_FILE = os.path.join(BASE_DIR, "batch_sweep_lc.log")

PROJECT = r"C:/wpt/Projecttonight.aedt"
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

# ============ 已验证的提速开关（2026-09-18，参考点 8 核实测）============
# 柔性网格：-39.6% 耗时，电感偏差 +0.41%（面向薄层结构，省掉大部分初始网格开销）
FLEX_MESH = True
# 柔性网格适用性闸门：匝间最小净间隙 >= 该值才启用（LC=120/KR=0.5 时仅 0.517mm，
# TAU Flex 会把 surface mesh 修坏 -> Status='Error'，实测于 2026-09-18）
FLEX_MIN_GAP = 1.5
# 整套优化的适用闸门（2026-09-18 实测）：净间隙不足时，连"⑥+pref10+rres"也会变慢且偏 1.44%，
# 因此不满足就整套回退到现行生产口径（非柔性 / pref5 / rres1e-6 / 无 ⑥）。
OPT_MIN_GAP = 1.5
# PercentRefinement 原 5 -> 10：叠在柔性+⑥ 之上再 -22%，同会话增量偏差 <=0.25%
PCT_REFINEMENT = 10
# 迭代求解容差 原 1e-6 -> 1e-5：再 -4%，偏差 <=0.06%
RELATIVE_RESIDUAL = "1e-05"
# ⑥：Region 最大单元尺寸 = Lc / 该值（-9.8%，偏差 <=0.31%）；0 = 关闭
REGION_MAX_LEN_DIV = 5.0

# ============ 看门狗（新增） ============
# 几何重建/求解在 gRPC 下会静默挂死：CPU 0%、不报错、永不返回。
# 没有看门狗时整批会永久卡住。这里超时即强杀 AEDT、重启会话并重试该点。
STAGE_TIMEOUT = 360        # 单次几何重建超时(秒)
SOLVE_TIMEOUT = 1500       # 单点求解超时(秒)
HANG_RETRIES = 1           # 挂死后重启会话并重试同一点的次数（0 = 不重试，直接跳过）

# 模型固定参数
Z_GAP = 30.0                # 线圈到铁氧体表面的气隙（固定 30mm）
# 铁氧体厚度 —— 扫描变量，5~10mm 步长1（Tx 条与 Rx 条共用同一个厚度）
#   Tx 条：顶面固定在 z=-Z_GAP，往 +Z 加厚（origin z = -Z_GAP-thk）
#   Rx 条：底面固定在 z=30+Z_GAP，往 +Z 加厚
#   所以改 thk 不会动线圈到铁氧体的 30mm 气隙
THK_RANGE = [5.0 + i for i in range(6)]
COIL_Y_LO, COIL_Y_HI = -84.0, 84.0
HOLE_RAD = 1.0
RAD = 0.3
# 线圈改成参数：LC（中心线外跨，120~220 步长10）x KR（内孔比，0.2~0.5）
# 线圈几何由 coil_gen.py 按 (LC, KR) 生成，匝间隙自动 = (h_out-h_in)/12
import coil_gen as CG
LC_RANGE = [120.0 + 10.0 * i for i in range(11)]          # 120,130,...,220
KR_RANGE = [round(0.2 + 0.1 * i, 2) for i in range(4)]    # 0.2,0.3,0.4,0.5
# KX = 两个发射线圈边沿间隙 / LC，无量纲，负值 = 投影重叠
#   实际间隙 tg = KX * LC（mm）；KX=-0.5 时两线圈重叠 50%
KX_RANGE = [round(-0.5 + 0.1 * i, 2) for i in range(11)]  # -0.5,-0.4,...,+0.5
RX_CENTER = 0.0
_RX_LEADS = None        # 当前接收引线 (x,y)（由线圈重建时更新，铁氧体开孔用）

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

# 固定空气域：按最坏情况（LC=220、tg=120）定死，不随线圈大小变。
# 原因：Region 原来跟着物体 50mm 自适应，LC 变小/变大时空气域跟着变，
# 磁通回流路径也跟着变 -> LC 轴上会混进"空气域大小"的假效应（实测 LC=180 时 L33 偏低 15%）。
# x/y/z 的单位是 mm；-Y 面必须落在发射引线端面(y=-134.94)上、+Z 面落在接收引线顶端(75)上，
# 否则 Maxwell 会报 "Illegal external terminal"。
REGION_FIXED = {"x": (-330.0, 330.0), "y": (-134.94, 161.0), "z": (-45.0, 75.0)}


def ensure_region(m3d, tg):
    """确保 Region 完全包住所有对象（含铁氧体过覆盖，≥20mm 余量）；不够则删除重建。

    padding = [+X, -X, +Y, -Y, +Z, -Z] = [50, 50, 50, 0, 0, 5] mm：
      -Y 必须为 0  —— Tx1/Tx2 引线改成沿 -Y 出线后，端子面在 y=-134.94，
                    Maxwell 把线端端子当 external terminal，必须正好贴在区域边界上；
                    -Y padding=0 让区域 -Y 面自动落在引线末端（也就是端子面）上。
      -Z 给 5mm    —— 原来是 0，因为那时引线最低到 z=-45；现在引线只到 z=-2.3，
                    最低物体是铁氧体底面 z=-40，补 5mm 把空气域底面还原成 -45。
      +Z 保持 0    —— Rx 引线顶端 z=+75 是区域顶面，Rx 端子贴在上面。
    """
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
    # 由当前物体包围盒反算 padding，使每次建出来的都是同一个 REGION_FIXED 盒子
    # 物体到目标盒面的距离（2026-09-18 修正）
    # 原写法是"目标面 - 物体面"，在物体位于盒内时必为负，被 max(0,·) 夹成 0 -> 区域面贴在物体上；
    # 再叠一句 min(need)<-1e-6 就 return 的守门 -> 整段从不执行（实测每次都是 need=[175,-175,...]）。
    need = [REGION_FIXED["x"][1] - bb[3], bb[0] - REGION_FIXED["x"][0],
            REGION_FIXED["y"][1] - bb[4], bb[1] - REGION_FIXED["y"][0],
            REGION_FIXED["z"][1] - bb[5], bb[2] - REGION_FIXED["z"][0]]
    if any(v < -1e-6 for v in need):
        log("!! 物体超出固定 Region: 需要 padding %s，物体 bbox=%s"
            % (["%.1f" % v for v in need], ["%.1f" % v for v in bb]))
        return None
    PAD = ["%.4fmm" % max(0.0, v) for v in need]
    try:
        rbb = m3d.modeler["Region"].bounding_box
        want = [REGION_FIXED["x"][0], REGION_FIXED["y"][0], REGION_FIXED["z"][0],
                REGION_FIXED["x"][1], REGION_FIXED["y"][1], REGION_FIXED["z"][1]]
        if max(abs(rbb[i] - want[i]) for i in range(6)) < 0.05:
            return rbb  # 已经是固定盒子
    except Exception:
        pass
    try:
        m3d.modeler.delete("Region")
        time.sleep(1)
    except Exception as e:
        log("region delete err: %s" % repr(e))
        return None
    try:
        m3d.modeler.create_region(pad_value=PAD, pad_type="Absolute Offset")
        rbb = m3d.modeler["Region"].bounding_box
        log("Region 重建: X[%.1f, %.1f] (tg=%.0f)" % (rbb[0], rbb[3], tg))
        return rbb
    except Exception as e:
        log("region create err: %s" % repr(e))
        return None

def gen_plan_csv():
    combos = []
    for LC in LC_RANGE:                        # LC/KR 放最外层：同一线圈几何连着跑完
      for KR in KR_RANGE:
        for thk in THK_RANGE:                  # thk 次外层：同一厚度连着跑完
          for w in W_RANGE:
            g = UNIT - w
            tgs = KX_RANGE if SWEEP_TG else [0.0]
            for KX in tgs:
                # dx 不再是独立变量：dx = S/40，其中 S = Lc(2+KX) = 两个发射线圈阵列的总外宽
                #   （S = 2*Lc + 间隙，间隙 = KX*Lc）
                dxs = [LC * (2.0 + KX) / 40.0]
                for dx in dxs:
                    for mu in MU_RANGE:
                        combos.append((LC, KR, w, g, dx, KX, mu, thk))
    with open(PLAN_CSV, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["LC_mm", "KR", "KX", "W_mm", "G_mm", "dx_mm", "mu", "thk_mm"])
        for LC, KR, w, g, dx, KX, mu, thk in combos:
            wr.writerow([LC, KR, KX, w, g, dx, mu, thk])
    return len(combos)

def log(msg):
    line = "%s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    # ⚠️ 2026-10-12 修（第二轮启动前）：原来没有 encoding=，中文 Windows 下本函数把
    # 日志写成 **GBK**，而 contract_worker.py 的 log() 用 UTF-8 写**同一个文件** ——
    # 结果 worker 日志是两种编码混编，UTF-8 读取直接报错（第一轮 8 份
    # b1_worker_run*.log 实测全部非法 UTF-8，诊断时极易误判为"日志损坏"）。
    # 必须显式 utf-8；errors="replace" 保证个别异常字符不会让写日志本身抛异常。
    with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
        f.write(line + "\n")

# ============ ④ 多实例：环境变量参数化（2026-09-18）============
# WPT_RUN=0..N-1 时，本进程只用自己那份工程副本、自己的参数表分片、自己的结果文件与日志。
# 不设 WPT_RUN（或为 -1）时行为与原来完全一致（单实例）。
RUN_ID = int(os.environ.get("WPT_RUN", "-1"))
_OWN_PID = [None]
if RUN_ID >= 0:
    PROJECT = os.path.join(BASE_DIR, "Projecttonight_run%d.aedt" % RUN_ID)
    PLAN_CSV = os.path.join(BASE_DIR, "combos_lc_shard%d.csv" % RUN_ID)
    OUT_CSV = os.path.join(BASE_DIR, "sweep_all_lc_run%d.csv" % RUN_ID)
    LOG_FILE = os.path.join(BASE_DIR, "batch_sweep_lc_run%d.log" % RUN_ID)

def kill_aedt():
    """强杀残留的 AEDT 进程并清理锁文件。

    ④ 多实例模式（RUN_ID>=0）：**只杀自己那个 PID**，否则会互杀。
    """
    if RUN_ID >= 0:
        pid = AEDT_PROCESS_ID or _OWN_PID[0]
        if pid:
            try:
                import subprocess as _sp
                _sp.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                         "Stop-Process -Id %d -Force -ErrorAction SilentlyContinue" % int(pid)],
                        capture_output=True, text=True)
            except Exception:
                pass
        try:
            for f in glob.glob(os.path.join(BASE_DIR, "Projecttonight_run%d.aedt.lock" % RUN_ID)):
                os.remove(f)
        except Exception:
            pass
        time.sleep(3)
        return
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info["name"] or "").lower().startswith("ansysedt"):
                    p.kill()
            except Exception:
                pass
    except Exception:
        os.system('taskkill /F /IM ansysedt.exe >nul 2>&1')
    time.sleep(3)
    for f in glob.glob(os.path.join(BASE_DIR, "*.lock")):
        try:
            os.remove(f)
        except Exception:
            pass


def run_stage(name, fn, timeout):
    """带看门狗执行 fn，返回 ("OK", 值) / ("HANG", None) / ("ERR", 异常)。

    线程里跑 fn，超时未返回即判定静默挂死，强杀 AEDT 并返回 HANG，
    避免整批永久卡在这里。"""
    box = {}

    def target():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e
            box["tb"] = traceback.format_exc()

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        log("  !! %s 超过 %ds 未返回，判定挂死，强杀 AEDT" % (name, timeout))
        kill_aedt()
        return "HANG", None
    if "e" in box:
        log("  !! %s 异常: %s" % (name, repr(box["e"])[:150]))
        tb = (box.get("tb") or "").strip().replace("\n", " | ")
        if tb:
            log("     " + tb[-400:])
        return "ERR", box["e"]
    return "OK", box.get("v")


def read_done():
    """已完成的点。要求 8 列键（含 LC_mm/KR）；旧行会被忽略。"""
    done = set()
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV) as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                if len(row) >= 8:
                    try:
                        done.add(tuple(float(x) for x in row[:8]))
                    except ValueError:
                        continue
    return done


def out_csv_has_lc():
    """现有结果 CSV 的表头是否已含 LC_mm/KR（旧文件不含 -> 不能混着追加）。"""
    if not os.path.exists(OUT_CSV) or os.path.getsize(OUT_CSV) == 0:
        return True
    try:
        with open(OUT_CSV) as f:
            head = next(csv.reader(f), [])
        return ("LC_mm" in head) and ("KR" in head)
    except Exception:
        return True

def set_tx_gap(m3d, tx_gap, outer):
    """按两个发射线圈之间的间隙移动它们（outer = 线圈外边缘尺寸）"""
    tx1_center = -tx_gap / 2.0 - outer / 2.0
    tx2_center =  tx_gap / 2.0 + outer / 2.0
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

def rebuild_ferrite(m3d, W, G, tx_gap, thk, outer, rx_leads):
    # 清理旧的铁氧体 + 残留的 aux_hole 开孔圆柱（gRPC 删除偶发失败，重试 2 次）
    for n in [n for n in m3d.modeler.object_names if n.startswith("ferrite_") or n.startswith("aux_hole")]:
        for _attempt in range(2):
            try:
                m3d.modeler.delete(n)
                break
            except Exception:
                time.sleep(1)
                continue
    tx1_c = -tx_gap / 2.0 - outer / 2.0
    tx2_c =  tx_gap / 2.0 + outer / 2.0
    emit_lo = tx1_c - outer / 2.0   # Tx1 左边缘
    emit_hi = tx2_c + outer / 2.0   # Tx2 右边缘

    def x_centers_continuous(lo, hi, w, g):
        """从 lo 到 hi 按 W+G 周期居中排布铁氧体条，两端过覆盖"""
        p = w + g
        span = hi - lo
        n = int(math.ceil(span / p)) + 1
        center = (lo + hi) / 2.0
        start = center - (n - 1) * p / 2.0
        return [start + k * p for k in range(n)]

    ferr = []
    # 铁氧体条的 Y 向半长跟着线圈走：
    #   原来硬编码 ±84，参考线圈(Y 向半跨 83.4)正好盖住；
    #   LC 变大后线圈 Y 向也变大（LC=180 时 90mm），铁氧体就盖不住了
    #   -> Rx 的铁氧体增益会凭空消失（实测 L33 少 17%）。
    #   这里取 outer/2 - 0.6415：参考线圈(outer=169.283)时正好 = 84.0，与原模型逐位一致。
    y_half = outer / 2.0 - 0.6415
    for xc in x_centers_continuous(emit_lo, emit_hi, W, G):
        name = "ferrite_Tx_%d" % len([n for n in ferr if n.startswith("ferrite_Tx_")])
        try:
            box = m3d.modeler.create_box(origin=[xc - W / 2.0, -y_half, -Z_GAP - thk],
                                         sizes=[W, 2.0 * y_half, thk], name=name)
            box.material_name = "ferrite"
            ferr.append(name)
        except Exception as e:
            log("ferrite Tx err: %s" % repr(e))
    rx_lo = RX_CENTER - outer / 2.0
    rx_hi = RX_CENTER + outer / 2.0
    for xc in x_centers_continuous(rx_lo, rx_hi, W, G):
        name = "ferrite_Rx_%d" % len([n for n in ferr if n.startswith("ferrite_Rx_")])
        try:
            box = m3d.modeler.create_box(origin=[xc - W / 2.0, -y_half, 30.0 + Z_GAP],
                                         sizes=[W, 2.0 * y_half, thk], name=name)
            box.material_name = "ferrite"
            ferr.append(name)
        except Exception as e:
            log("ferrite Rx err: %s" % repr(e))
    # 开孔：引线穿过铁氧体
    # Tx1/Tx2 的引线已改成「先竖直一小段，再沿 -Y 出线」：
    #   Tx1 引线 z 只到 +2.3，Tx2 引线 z 只到 -2.3，而铁氧体在 z=-40~-30，
    #   所以两个发射线圈的引线都不再穿铁氧体，不需要开孔。只有 Rx 需要。
    for coil, pts in (("Rx", rx_leads),):
        if coil in ("Tx1", "Tx2"):
            continue
        base_x = RX_CENTER
        group_pref = "Rx"
        for i, (lx, ly) in enumerate(pts):
            ax = base_x + lx
            z0, h = CG.RX_Z0, CG.RX_ZTOP - CG.RX_Z0   # 接收引线的 z 范围
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

def _results_dir():
    """当前工程的 AEDT 结果目录（用于读取 .profile 判定求解状态）。"""
    base = os.path.splitext(os.path.basename(PROJECT))[0] + ".aedtresults"
    return os.path.join(BASE_DIR, base, DESIGN + ".results")


def _profile_status():
    """读最新 .profile 里的 Status 字段；取不到返回 None。"""
    try:
        d = _results_dir()
        fs = [f for f in os.listdir(d) if f.endswith(".profile")]
        if not fs:
            return None
        f = max((os.path.join(d, x) for x in fs), key=os.path.getmtime)
        txt = open(f, encoding="utf-8", errors="replace").read()
        # 2026-09-19 修正：AEDT 写出的 profile 里引号是**转义**的（\'Stop Time\'），
        # 而原正则要求未转义的 'Stop Time' -> 永远匹配不上、恒返回 None，
        # 导致「求解失败快速退出」实际从未生效（失败点会空转满 SOLVE_TIMEOUT）。
        # 实测证据：run3/run5 的 profile 明确是 Status='Error'，但轮询仍继续 40 分钟。
        txt = txt.replace("\\'", "'")
        m = re.search(r"ProfileFootnote\('I\(\d+, 1, 'Stop Time', '([^']+)', 1, 'Status', '([^']+)'", txt)
        return m.group(2) if m else None
    except Exception:
        return None


# ============ AEDT 进程 CPU 存活探针（2026-09-23 新增）============
# 事故背景：本批实测 8 个实例先后僵死在 `网格: 整套优化=True` 之后——日志再无新增，
# AEDT 进程仍在（Responding=True）但 CPU 利用率掉到 0.1~0.2 核、工作集从 ~3.7 GB
# 缩到 13~846 MB，gRPC 全断（累计 7996 条 poll err）。关键是：**is_solved 一次异常
# 都不抛**——它是**阻塞**在 pyaedt 的 gRPC 调用里，所以「连续异常计数」这种判据根本
# 触发不了。worker 因此既不出点也不退出，最长白停 9.2 小时。
#
# 唯一在僵死时仍然可靠的信号是**进程自身的 CPU 时间**：正在求解的实例每秒都在烧
# 1~16 核，停下来的实例 CPU 时间纹丝不动。这里直接问内核（不依赖 pyaedt、不依赖
# gRPC、不依赖 .profile 是否落盘），是最底层也最可靠的一层。
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_k32.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.POINTER(wintypes.FILETIME), ctypes.c_void_p]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_STILL_ACTIVE = 259


def _aedt_cpu_seconds(pid):
    """该进程累计占用的 CPU 秒数。

    返回 float 正常；返回 None 表示**进程已不存在**（这是比 CPU 不动更强的证据）。
    """
    if not pid:
        return None
    h = _k32.OpenProcess(0x1000, False, int(pid))      # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        h = _k32.OpenProcess(0x0400, False, int(pid))  # 退回 PROCESS_QUERY_INFORMATION
        if not h:
            return None
    try:
        code = wintypes.DWORD()
        if not _k32.GetExitCodeProcess(h, ctypes.byref(code)):
            return None
        if code.value != _STILL_ACTIVE:
            return None
        _cre = wintypes.FILETIME()
        _exi = wintypes.FILETIME()
        kern = wintypes.FILETIME()
        _usr = wintypes.FILETIME()
        # 注意：GetProcessTimes 的 4 个出参都必须传**真实结构地址**，
        # 传 NULL 会直接 access violation（2026-09-23 实测踩过）。
        if not _k32.GetProcessTimes(h, ctypes.byref(_cre), ctypes.byref(_exi),
                                    ctypes.byref(kern), ctypes.byref(_usr)):
            return None
        return (kern.dwHighDateTime * 4294967296.0 + kern.dwLowDateTime) / 1e7
    finally:
        _k32.CloseHandle(h)


def _aedt_pid_of(d):
    """从 pyaedt Desktop 对象取 AEDT 进程 PID（不同版本属性名不同，逐个兜底）。"""
    for attr in ("aedt_process_id", "aedt_processId", "process_id"):
        try:
            v = getattr(d, attr, None)
            if v:
                return int(v)
        except Exception:
            continue
    return None


def solve_and_extract(d, m3d, LC, KR, KX, W, G, dx, mu, thk):
    tg = KX * LC          # 实际边沿间隙(mm)
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
        s.props["RelativeResidual"] = RELATIVE_RESIDUAL
        s.update()
        # 提速开关（幂等：同名网格操作先删再加）
        try:
            _gap = None
            try:
                _gap = CG.path_dims(LC, KR).get("gap_min")
            except Exception:
                pass
            _use_opt = (_gap is None) or (_gap >= OPT_MIN_GAP)
            log("  网格: 整套优化=%s (gap_min=%s, 阈值 %.2f)" % (_use_opt, _gap, OPT_MIN_GAP))
            m3d.mesh.assign_initial_mesh_from_slider(level=5, method="Auto",
                                                     flex_mesh=bool(FLEX_MESH and _use_opt))
            for _mo in list(m3d.mesh.meshoperations):
                if _mo.name.startswith("region_coarse"):
                    _mo.delete()
            if REGION_MAX_LEN_DIV and _use_opt:
                m3d.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                            maximum_length="%.4fmm" % (LC / REGION_MAX_LEN_DIV),
                                            maximum_elements=None, name="region_coarse")
            # 不满足闸门时整套回退到现行生产口径
            s.props["PercentRefinement"] = PCT_REFINEMENT if _use_opt else 5
            s.props["RelativeResidual"] = RELATIVE_RESIDUAL if _use_opt else "1e-06"
            s.update()
        except Exception as e:
            log("speed switch err: %s" % repr(e))
    except Exception as e:
        log("setup err: %s" % repr(e))
    try:
        m3d.analyze(cores=CORES, run_in_thread=True)
    except Exception as e:
        log("analyze err: %s" % repr(e))
    w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
    solved = False
    err_streak = 0
    # 2026-09-23 新增：会话死亡计数。**只增不减**，与 err_streak 不同——
    # err_streak 会在下面"提取验证"兜底失败时被清零（见第 546 行），
    # 导致 is_solved 持续抛 GrpcApiError 时计数永远长不到退出条件，
    # 轮询既不出点也不退出（实测 run1/2/3/5/6 僵死最长 9.2 h，白耗 24 实例·小时）。
    session_err = 0
    SESSION_DEAD_POLLS = 12      # 连续 12 次（约 6 min）gRPC 不通即判定会话已死
    # 2026-09-23 新增：CPU 存活探针。僵死会话**不抛异常**（阻塞在 gRPC 里），
    # 所以异常计数救不了它；只有"进程 CPU 时间不再增长 / 进程已消失"能可靠判定。
    # 实测健康实例每 20 s 烧 20~320 CPU·秒（1~16 核），僵死实例为 0。
    # 阈值 360 s 远高于任何单次轮询的正常增量，不会误杀。
    CPU_STALL_SECS = 360.0       # 连续 6 min CPU 时间零增长 -> 判会话已死
    _aedt_pid = _aedt_pid_of(d)
    _cpu0 = _aedt_cpu_seconds(_aedt_pid)
    _cpu_moved = time.time()
    for i in range(180):         # 90 -> 180：BASE 单点实测可达 41 min，原 30 min 上限会误判
        time.sleep(20)
        # 快速失败：AEDT 若已明确报错（.profile 里 Status='Error'），不再空转
        if i % 5 == 4:
            _st = _profile_status()
            if _st and _st.lower().startswith("error"):
                log("  !! 求解已报错(Status=%s)，第 %d 次轮询提前退出" % (_st, i + 1))
                try:
                    d.odesktop.StopSimulations(True)
                except Exception:
                    pass
                return False
        # ---- 第一层：进程还在不在 + CPU 还动不动（不依赖 gRPC）----
        _cpu = _aedt_cpu_seconds(_aedt_pid)
        if _aedt_pid and _cpu is None:
            log("  !! AEDT 进程 %s 已不存在 -> 放弃本点" % _aedt_pid)
            break
        if _cpu is not None:
            if _cpu0 is not None and _cpu - _cpu0 > 5.0:
                _cpu_moved = time.time()
            _cpu0 = _cpu
            if time.time() - _cpu_moved > CPU_STALL_SECS:
                log("  !! AEDT(pid=%s) CPU 时间已 %.0f min 零增长 -> 判定会话已死，放弃本点"
                    % (_aedt_pid, (time.time() - _cpu_moved) / 60.0))
                try:
                    kill_aedt()
                except Exception:
                    pass
                break
        try:
            solved = m3d.setups[0].is_solved
            err_streak = 0
            session_err = 0
        except Exception as e:
            err_streak += 1
            session_err += 1
            log("poll err(%d/%d): %s" % (err_streak, session_err, repr(e)))
        if session_err >= SESSION_DEAD_POLLS:
            # 会话已死（gRPC 通道全断）：唯一出路是返回 False，
            # 交给 worker 既有的「重开会话后重试 / BASE 回退」路径。
            log("  !! 连续 %d 次轮询 gRPC 不通，判定 AEDT 会话已死 -> 放弃本点（由 worker 重开会话续跑）"
                % session_err)
            break
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
        log("  FAILED LC=%.0f KR=%.2f KX=%+.2f W=%.1f G=%.1f dx=%3d tg=%7.2f mu=%.0f thk=%.0f"
            % (LC, KR, KX, W, G, dx, tg, mu, thk))
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
        row = [LC, KR, KX, W, G, dx, mu, thk, round(L11, 3), round(L22, 3), round(L33, 3),
               round(M12, 3), round(M13, 3), round(M23, 3), round(k13, 5), round(k23, 5)]
        log("  LC=%.0f KR=%.2f KX=%+.2f W=%.1f G=%.1f dx=%3d tg=%7.2f mu=%.0f thk=%.0f L11=%.1f M13=%.2f k13=%.4f"
            % (LC, KR, KX, W, G, dx, tg, mu, thk, L11, M13, k13))
        new_file = not os.path.exists(OUT_CSV) or os.path.getsize(OUT_CSV) == 0
        with open(OUT_CSV, "a", newline="") as f:
            wr = csv.writer(f)
            if new_file:
                wr.writerow(["LC_mm", "KR", "KX", "W_mm", "G_mm", "dx_mm", "mu", "thk_mm",
                             "L11_uH", "L22_uH", "L33_uH",
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
        head = next(r, None) or []
        if ("LC_mm" not in head) or ("KR" not in head) or ("KX" not in head):
            print("!! 参数表 %s 里没有 LC_mm/KR 列，请先运行: python batch_sweep_lc.py --gen-plan" % PLAN_CSV)
            sys.exit(1)
        for row in r:
            if len(row) >= 8:
                try:
                    combos.append(tuple(float(x) for x in row[:8]))
                except ValueError:
                    continue
    log("loaded %d combos from %s" % (len(combos), PLAN_CSV))

    # 旧的 5 列结果文件不能和新的 6 列键混着追加，挪到一边
    if not out_csv_has_lc():
        legacy = OUT_CSV.replace(".csv", "_legacy_noLC.csv")
        try:
            if os.path.exists(legacy):
                os.remove(legacy)
            os.rename(OUT_CSV, legacy)
            log("!! 旧结果(无 thk_mm 列)已挪到 %s，本次从空文件重新开始" % legacy)
        except Exception as e:
            log("!! 旧结果文件无法挪动: %r，请手动处理" % e)
            sys.exit(1)

    def _connect(new_desktop, process_id, port):
        kwargs = dict(version=AEDT_VERSION, new_desktop=new_desktop,
                      non_graphical=NON_GRAPHICAL, close_on_exit=False)
        if process_id:
            kwargs["aedt_process_id"] = process_id
        if port:
            kwargs["port"] = port
        dd = Desktop(**kwargs)
        return dd, Maxwell3d(project=PROJECT, design=DESIGN)

    def open_session():
        """连上已有 AEDT，或新起一个。失败返回 (None, None)。"""
        if not NEW_DESKTOP:
            try:
                dd, mm = _connect(False, AEDT_PROCESS_ID, GRPC_PORT)
                log("connected to running AEDT: %s / %s, solution=%s" % (PROJECT, DESIGN, mm.solution_type))
                return dd, mm
            except Exception as e:
                log("connect to running AEDT failed: %s" % repr(e))
                log("attempting to start a new AEDT session...")
        try:
            dd, mm = _connect(True, None, None)
            log("started new AEDT: %s / %s, solution=%s" % (PROJECT, DESIGN, mm.solution_type))
            return dd, mm
        except Exception as e:
            log("START AEDT FAILED: %s" % repr(e))
            return None, None

    d, m3d = open_session()
    if d is None:
        sys.exit(1)
    try:
        _OWN_PID[0] = d.aedt_process_id
        log("my AEDT pid=%s (run=%d)" % (_OWN_PID[0], RUN_ID))
    except Exception:
        pass

    done = read_done()
    log("already done: %d" % len(done))

    # 自动备份：backup_upload.py 缺失时只禁用备份，不拖垮批量
    try:
        import backup_upload as _bu
    except Exception as e:
        _bu = None
        log("backup_upload 不可用，自动备份已禁用: %s" % repr(e)[:120])
    _last_backup = time.time()

    last_wg = None
    last_tg = None
    last_thk = None
    last_lc = None
    last_kr = None
    n_hang = 0
    n_skip = 0
    for LC, KR, KX, W, G, dx, mu, thk in combos:
        key = (LC, KR, KX, W, G, dx, mu, thk)
        tg = KX * LC          # 实际边沿间隙(mm)，负值 = 重叠
        if key in done:
            continue
        # 每小时自动备份：提交并推送到 GitHub（用户要求）
        if _bu is not None and time.time() - _last_backup >= 3600:
            try:
                _bu.run_backup()
            except Exception as e:
                log("backup err: %s" % repr(e)[:120])
            _last_backup = time.time()

        def _geometry():
            global _RX_LEADS
            outer = CG.coil_outer(LC)
            if last_lc is None or last_lc != LC or last_kr != KR:
                set_rx_dx(m3d, 0.0)
                CG.rebuild_all(m3d, LC, KR, log=log)
                _RX_LEADS = CG.current_leads(m3d, "Rx")
                ensure_region(m3d, tg)
                log("=== 线圈重建 LC=%.1f KR=%.2f outer=%.2f 接收引线=%s ==="
                    % (LC, KR, outer, _RX_LEADS))
            if last_tg is None or last_tg != tg or last_thk != thk:
                set_rx_dx(m3d, 0.0)
                set_tx_gap(m3d, tg, outer)
                nf = rebuild_ferrite(m3d, W, G, tg, thk, outer, _RX_LEADS)
                ensure_region(m3d, tg)
                log("=== W=%.1f G=%.1f tg=%7.2f(KX=%+.2f) thk=%.0f LC=%.0f rebuilt %d bars ==="
                    % (W, G, tg, KX, thk, LC, nf))
                return nf
            if last_wg is None or last_wg != (W, G):
                set_rx_dx(m3d, 0.0)
                nf = rebuild_ferrite(m3d, W, G, tg, thk, outer, _RX_LEADS)
                ensure_region(m3d, tg)
                log("=== W=%.1f G=%.1f thk=%.0f LC=%.0f rebuilt %d bars ==="
                    % (W, G, thk, LC, nf))
                return nf
            return None

        def _solve():
            set_rx_dx(m3d, dx)
            return solve_and_extract(d, m3d, LC, KR, KX, W, G, dx, mu, thk)

        ok = False
        for attempt in range(HANG_RETRIES + 1):
            last_attempt = (attempt == HANG_RETRIES)

            st, _v = run_stage("几何重建 W=%.1f G=%.1f tg=%d thk=%.0f" % (W, G, tg, thk),
                               _geometry, STAGE_TIMEOUT)
            if st == "HANG":
                n_hang += 1
                last_tg = last_wg = last_thk = last_lc = last_kr = None   # 会话已死，强制重建
                if last_attempt:
                    log("  !! 几何重建连续挂死，跳过该点")
                    break
                log("  -> 重启 AEDT 会话并重试该点")
                d, m3d = open_session()
                if d is None:
                    log("!! 无法重建 AEDT 会话，停止本次批量")
                    log("BATCH SWEEP UNIT30 ABORTED (AEDT 会话无法恢复)")
                    sys.exit(2)
                continue
            if st == "ERR":
                last_tg = last_wg = last_thk = last_lc = last_kr = None
                break

            st2, res = run_stage("求解 W=%.1f G=%.1f dx=%.0f tg=%d thk=%.0f" % (W, G, dx, tg, thk),
                                 _solve, SOLVE_TIMEOUT)
            if st2 == "HANG":
                n_hang += 1
                last_tg = last_wg = last_thk = last_lc = last_kr = None
                if last_attempt:
                    log("  !! 求解连续挂死，跳过该点")
                    break
                log("  -> 重启 AEDT 会话并重试该点")
                d, m3d = open_session()
                if d is None:
                    log("!! 无法重建 AEDT 会话，停止本次批量")
                    log("BATCH SWEEP UNIT30 ABORTED (AEDT 会话无法恢复)")
                    sys.exit(2)
                continue

            ok = (st2 == "OK" and bool(res))
            if ok:
                last_tg = tg
                last_wg = (W, G)
                last_thk = thk
                last_lc = LC
                last_kr = KR
            else:
                last_tg = last_wg = last_thk = last_lc = last_kr = None
            break

        if ok:
            done.add(key)
        else:
            n_skip += 1
            log("  !! 该点未完成，跳过: LC=%.0f KR=%.2f KX=%+.2f W=%.1f G=%.1f dx=%.0f tg=%7.2f mu=%.0f thk=%.0f"
                % (LC, KR, KX, W, G, dx, tg, mu, thk))

    log("BATCH SWEEP UNIT30 DONE")
    if n_hang or n_skip:
        log("!! 本次挂死 %d 次，跳过 %d 点（重跑会从 sweep CSV 自动续算未完成的点）" % (n_hang, n_skip))
