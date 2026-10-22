# -*- coding: utf-8 -*-
r"""生成生产用的参数化批次脚本 batch_sweep_lc.py（原 batch_sweep_unit30.py 保持不动），
并把参考路径模板写到 C:\wpt\coil_template_Rx.json。

改动点：
  1. COIL_SIZE / ENDS / LEAD_Z / LEAD_REL  ->  LC_RANGE / KR_RANGE + coil_gen 模块
  2. set_tx_gap / rebuild_ferrite 增加 outer 参数；铁氧体覆盖与 Rx 开孔都跟着 LC 走
  3. 主循环增加 LC/KR 两层，几何缓存增加 last_lc/last_kr
  4. 参数表 / 结果 CSV / 续算键增加 LC_mm, KR 两列
"""
import json
import os
import re
import sys

WPT = r"C:\wpt"
SRC = os.path.join(WPT, "batch_sweep_unit30.py")
DST = os.path.join(WPT, "batch_sweep_lc.py")
WORK = r"C:\ansys maxwell2024\_work"

src = open(SRC, encoding="utf-8").read()
orig = src
patches = []


def rep(old, new, tag):
    global src
    n = src.count(old)
    if n != 1:
        print("!! [%s] 匹配到 %d 次（应为 1），中止" % (tag, n))
        sys.exit(1)
    src = src.replace(old, new)
    patches.append(tag)


# ---------------- 1. 参数区 ----------------
rep('''COIL_SIZE = 167.90          # 发射线圈外尺寸（WPT_G 实测；线宽 3mm->2mm 后 由 168.90 变 167.90）
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
}''', '''# 线圈改成参数：LC（中心线外跨，120~220 步长10）x KR（内孔比，0.2~0.5）
# 线圈几何由 coil_gen.py 按 (LC, KR) 生成，匝间隙自动 = (h_out-h_in)/12
import coil_gen as CG
LC_RANGE = [120.0 + 10.0 * i for i in range(11)]          # 120,130,...,220
KR_RANGE = [round(0.2 + 0.1 * i, 2) for i in range(4)]    # 0.2,0.3,0.4,0.5
RX_CENTER = 0.0
_RX_LEADS = None        # 当前接收引线 (x,y)（由线圈重建时更新，铁氧体开孔用）''', "参数区")

# ---------------- 2. set_tx_gap ----------------
rep('''def set_tx_gap(m3d, tx_gap):
    """按外边缘间隔移动两个发射线圈"""
    tx1_center = -tx_gap / 2.0 - COIL_SIZE / 2.0
    tx2_center =  tx_gap / 2.0 + COIL_SIZE / 2.0''',
    '''def set_tx_gap(m3d, tx_gap, outer):
    """按两个发射线圈之间的间隙移动它们（outer = 线圈外边缘尺寸）"""
    tx1_center = -tx_gap / 2.0 - outer / 2.0
    tx2_center =  tx_gap / 2.0 + outer / 2.0''', "set_tx_gap")

# ---------------- 3. rebuild_ferrite ----------------
rep('''def rebuild_ferrite(m3d, W, G, tx_gap, thk):''',
    '''def rebuild_ferrite(m3d, W, G, tx_gap, thk, outer, rx_leads):''', "rebuild_ferrite 签名")

rep('''    tx1_c = -tx_gap / 2.0 - COIL_SIZE / 2.0
    tx2_c =  tx_gap / 2.0 + COIL_SIZE / 2.0
    emit_lo = tx1_c - COIL_SIZE / 2.0   # Tx1 左边缘
    emit_hi = tx2_c + COIL_SIZE / 2.0   # Tx2 右边缘''',
    '''    tx1_c = -tx_gap / 2.0 - outer / 2.0
    tx2_c =  tx_gap / 2.0 + outer / 2.0
    emit_lo = tx1_c - outer / 2.0   # Tx1 左边缘
    emit_hi = tx2_c + outer / 2.0   # Tx2 右边缘''', "铁氧体覆盖范围")

rep('''    rx_lo = RX_CENTER - COIL_SIZE / 2.0
    rx_hi = RX_CENTER + COIL_SIZE / 2.0''',
    '''    rx_lo = RX_CENTER - outer / 2.0
    rx_hi = RX_CENTER + outer / 2.0''', "接收铁氧体覆盖")

rep('''    for coil, pts in ENDS.items():
        if coil in ("Tx1", "Tx2"):
            continue
        base_x = RX_CENTER
        group_pref = "Rx"
        for i, (lx, ly) in enumerate(LEAD_REL[coil]):
            ax = base_x + lx''',
    '''    for coil, pts in (("Rx", rx_leads),):
        if coil in ("Tx1", "Tx2"):
            continue
        base_x = RX_CENTER
        group_pref = "Rx"
        for i, (lx, ly) in enumerate(pts):
            ax = base_x + lx''', "开孔循环")

# ---------------- 4. gen_plan_csv ----------------
rep('''def gen_plan_csv():
    combos = []
    for thk in THK_RANGE:                      # thk 放最外层：同一厚度连着跑完，少切换几何
        for w in W_RANGE:''',
    '''def gen_plan_csv():
    combos = []
    for LC in LC_RANGE:                        # LC/KR 放最外层：同一线圈几何连着跑完
      for KR in KR_RANGE:
        for thk in THK_RANGE:                  # thk 次外层：同一厚度连着跑完
          for w in W_RANGE:''', "gen_plan_csv 头部")

rep('''            g = UNIT - w
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
                        combos.append((w, g, dx, tg, mu, thk))
    with open(PLAN_CSV, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["W_mm", "G_mm", "dx_mm", "tx_gap_mm", "mu", "thk_mm"])
        for w, g, dx, tg, mu, thk in combos:
            wr.writerow([w, g, dx, tg, mu, thk])
    return len(combos)''',
    '''            g = UNIT - w
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
                        combos.append((LC, KR, w, g, dx, tg, mu, thk))
    with open(PLAN_CSV, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["LC_mm", "KR", "W_mm", "G_mm", "dx_mm", "tx_gap_mm", "mu", "thk_mm"])
        for LC, KR, w, g, dx, tg, mu, thk in combos:
            wr.writerow([LC, KR, w, g, dx, tg, mu, thk])
    return len(combos)''', "gen_plan_csv 主体")

# ---------------- 5. read_done / 表头检查 ----------------
rep('''def read_done():
    """已完成的点。要求 6 列键（含 thk_mm）；旧的 5 列行会被忽略。"""
    done = set()
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV) as f:
            r = csv.reader(f)
            next(r, None)
            for row in r:
                if len(row) >= 6 and row[0].lstrip("-").replace(".", "").isdigit():
                    done.add((float(row[0]), float(row[1]), float(row[2]),
                              float(row[3]), float(row[4]), float(row[5])))
    return done''',
    '''def read_done():
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
    return done''', "read_done")

rep('''def out_csv_has_thk():
    """现有结果 CSV 的表头是否已含 thk_mm（旧文件不含 -> 不能混着追加）。"""
    if not os.path.exists(OUT_CSV) or os.path.getsize(OUT_CSV) == 0:
        return True
    try:
        with open(OUT_CSV) as f:
            head = next(csv.reader(f), [])
        return "thk_mm" in head
    except Exception:
        return True''',
    '''def out_csv_has_lc():
    """现有结果 CSV 的表头是否已含 LC_mm/KR（旧文件不含 -> 不能混着追加）。"""
    if not os.path.exists(OUT_CSV) or os.path.getsize(OUT_CSV) == 0:
        return True
    try:
        with open(OUT_CSV) as f:
            head = next(csv.reader(f), [])
        return ("LC_mm" in head) and ("KR" in head)
    except Exception:
        return True''', "out_csv 表头检查")

# ---------------- 6. 主循环 ----------------
rep('''    last_wg = None
    last_tg = None
    last_thk = None''',
    '''    last_wg = None
    last_tg = None
    last_thk = None
    last_lc = None
    last_kr = None''', "主循环状态变量")

rep('''    for W, G, dx, tg, mu, thk in combos:
        key = (W, G, dx, tg, mu, thk)''',
    '''    for LC, KR, W, G, dx, tg, mu, thk in combos:
        key = (LC, KR, W, G, dx, tg, mu, thk)''', "主循环解包")

rep('''        def _geometry():
            if last_tg is None or last_tg != tg or last_thk != thk:
                set_rx_dx(m3d, 0.0)
                set_tx_gap(m3d, tg)
                nf = rebuild_ferrite(m3d, W, G, tg, thk)
                ensure_region(m3d, tg)
                log("=== W=%.1f G=%.1f tg=%3d thk=%.0f rebuilt %d bars ===" % (W, G, tg, thk, nf))
                return nf
            if last_wg is None or last_wg != (W, G):
                set_rx_dx(m3d, 0.0)
                nf = rebuild_ferrite(m3d, W, G, tg, thk)
                ensure_region(m3d, tg)
                log("=== W=%.1f G=%.1f thk=%.0f rebuilt %d bars ===" % (W, G, thk, nf))
                return nf
            return None''',
    '''        def _geometry():
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
                log("=== W=%.1f G=%.1f tg=%3d thk=%.0f LC=%.0f rebuilt %d bars ==="
                    % (W, G, tg, thk, LC, nf))
                return nf
            if last_wg is None or last_wg != (W, G):
                set_rx_dx(m3d, 0.0)
                nf = rebuild_ferrite(m3d, W, G, tg, thk, outer, _RX_LEADS)
                ensure_region(m3d, tg)
                log("=== W=%.1f G=%.1f thk=%.0f LC=%.0f rebuilt %d bars ==="
                    % (W, G, thk, LC, nf))
                return nf
            return None''', "_geometry")

rep('''        def _solve():
            set_rx_dx(m3d, dx)
            return solve_and_extract(d, m3d, W, G, dx, tg, mu, thk)''',
    '''        def _solve():
            set_rx_dx(m3d, dx)
            return solve_and_extract(d, m3d, LC, KR, W, G, dx, tg, mu, thk)''', "_solve")

rep('''            if ok:
                last_tg = tg
                last_wg = (W, G)
                last_thk = thk
            else:
                last_tg = last_wg = last_thk = None''',
    '''            if ok:
                last_tg = tg
                last_wg = (W, G)
                last_thk = thk
                last_lc = LC
                last_kr = KR
            else:
                last_tg = last_wg = last_thk = last_lc = last_kr = None''', "成功/失败状态")

# 挂死/异常分支里的状态清零（4 处）
n = src.count("last_tg = last_wg = last_thk = None")
if n != 3:
    print("!! 状态清零分支匹配到 %d 次（应为 3），中止" % n)
    sys.exit(1)
src = src.replace("last_tg = last_wg = last_thk = None",
                  "last_tg = last_wg = last_thk = last_lc = last_kr = None")
patches.append("挂死分支状态清零 x%d" % n)

rep('''            log("  !! 该点未完成，跳过: W=%.1f G=%.1f dx=%.0f tg=%d mu=%.0f thk=%.0f"
                % (W, G, dx, tg, mu, thk))''',
    '''            log("  !! 该点未完成，跳过: LC=%.0f KR=%.2f W=%.1f G=%.1f dx=%.0f tg=%d mu=%.0f thk=%.0f"
                % (LC, KR, W, G, dx, tg, mu, thk))''', "跳过日志")

# ---------------- 7. solve_and_extract ----------------
rep('''def solve_and_extract(d, m3d, W, G, dx, tg, mu, thk):''',
    '''def solve_and_extract(d, m3d, LC, KR, W, G, dx, tg, mu, thk):''', "solve_and_extract 签名")

rep('''        log("  FAILED W=%.1f G=%.1f dx=%3d tg=%3d mu=%.0f thk=%.0f" % (W, G, dx, tg, mu, thk))''',
    '''        log("  FAILED LC=%.0f KR=%.2f W=%.1f G=%.1f dx=%3d tg=%3d mu=%.0f thk=%.0f"
            % (LC, KR, W, G, dx, tg, mu, thk))''', "FAILED 日志")

rep('''        row = [W, G, dx, tg, mu, thk, round(L11, 3), round(L22, 3), round(L33, 3),''',
    '''        row = [LC, KR, W, G, dx, tg, mu, thk, round(L11, 3), round(L22, 3), round(L33, 3),''',
    "结果行")

rep('''        log("  W=%.1f G=%.1f dx=%3d tg=%3d mu=%.0f thk=%.0f L11=%.1f M13=%.2f k13=%.4f"
            % (W, G, dx, tg, mu, thk, L11, M13, k13))''',
    '''        log("  LC=%.0f KR=%.2f W=%.1f G=%.1f dx=%3d tg=%3d mu=%.0f thk=%.0f L11=%.1f M13=%.2f k13=%.4f"
            % (LC, KR, W, G, dx, tg, mu, thk, L11, M13, k13))''', "结果日志")

rep('''                wr.writerow(["W_mm", "G_mm", "dx_mm", "tx_gap_mm", "mu", "thk_mm",
                             "L11_uH", "L22_uH", "L33_uH",
                             "M12_uH", "M13_uH", "M23_uH", "k13", "k23"])''',
    '''                wr.writerow(["LC_mm", "KR", "W_mm", "G_mm", "dx_mm", "tx_gap_mm", "mu", "thk_mm",
                             "L11_uH", "L22_uH", "L33_uH",
                             "M12_uH", "M13_uH", "M23_uH", "k13", "k23"])''', "结果表头")

# ---------------- 8. 文件路径与参数表加载 ----------------
rep('''PLAN_CSV = os.path.join(BASE_DIR, "combos_unit30.csv")
OUT_CSV  = os.path.join(BASE_DIR, "sweep_all_unit30.csv")
LOG_FILE = os.path.join(BASE_DIR, "batch_sweep_unit30.log")''',
    '''PLAN_CSV = os.path.join(BASE_DIR, "combos_lc.csv")
OUT_CSV  = os.path.join(BASE_DIR, "sweep_all_lc.csv")
LOG_FILE = os.path.join(BASE_DIR, "batch_sweep_lc.log")''', "输出文件路径")

rep('''        if "thk_mm" not in head:
            print("!! 参数表 %s 里没有 thk_mm 列，请先运行: python batch_sweep_unit30.py --gen-plan" % PLAN_CSV)
            sys.exit(1)
        for row in r:
            if len(row) >= 6 and row[0].lstrip("-").replace(".", "").isdigit():
                combos.append((float(row[0]), float(row[1]), float(row[2]),
                               float(row[3]), float(row[4]), float(row[5])))''',
    '''        if ("LC_mm" not in head) or ("KR" not in head):
            print("!! 参数表 %s 里没有 LC_mm/KR 列，请先运行: python batch_sweep_lc.py --gen-plan" % PLAN_CSV)
            sys.exit(1)
        for row in r:
            if len(row) >= 8:
                try:
                    combos.append(tuple(float(x) for x in row[:8]))
                except ValueError:
                    continue''', "参数表加载")

rep('''    if not out_csv_has_thk():
        legacy = OUT_CSV.replace(".csv", "_legacy_noTHK.csv")''',
    '''    if not out_csv_has_lc():
        legacy = OUT_CSV.replace(".csv", "_legacy_noLC.csv")''', "旧结果归档")

rep('''# 批量扫描（UNIT=30 版）——固定单元周期 W+G=30，铁氧体条宽 W=10~20 步长1''',
    '''# 批量扫描（LC 参数化版）——线圈 LC(120~220 步长10) x KR(0.2~0.5) x W x tg x dx x thk(步长1)
# 线圈几何由 coil_gen.py 生成，匝间隙自适应；铁氧体 Y 向长度随线圈自适应
# 其余与原 batch_sweep_unit30.py 相同''', "文件头注释")

rep('''        for i, (lx, ly) in enumerate(pts):
            ax = base_x + lx
            z0, h = LEAD_Z[coil]''',
    '''        for i, (lx, ly) in enumerate(pts):
            ax = base_x + lx
            z0, h = CG.RX_Z0, CG.RX_ZTOP - CG.RX_Z0   # 接收引线的 z 范围''', "开孔 z 范围")

# ---------------- 9. 铁氧体 Y 向长度随线圈自适应 ----------------
rep('''def ensure_region(m3d, tg):''',
    '''# 固定空气域：按最坏情况（LC=220、tg=120）定死，不随线圈大小变。
# 原因：Region 原来跟着物体 50mm 自适应，LC 变小/变大时空气域跟着变，
# 磁通回流路径也跟着变 -> LC 轴上会混进"空气域大小"的假效应（实测 LC=180 时 L33 偏低 15%）。
# x/y/z 的单位是 mm；-Y 面必须落在发射引线端面(y=-134.94)上、+Z 面落在接收引线顶端(75)上，
# 否则 Maxwell 会报 "Illegal external terminal"。
REGION_FIXED = {"x": (-272.0, 272.0), "y": (-134.94, 161.0), "z": (-45.0, 75.0)}


def ensure_region(m3d, tg):''', "Region 固定目标")

rep('''    PAD = ["50mm", "50mm", "50mm", "0mm", "0mm", "5mm"]
    objs = [o for o in m3d.modeler.object_names if o != "Region"]''',
    '''    objs = [o for o in m3d.modeler.object_names if o != "Region"]''', "Region 旧 padding")

rep('''    if bb is None:
        return None
    try:
        rbb = m3d.modeler["Region"].bounding_box
        if rbb[0] <= bb[0] - 20.0 and rbb[3] >= bb[3] + 20.0:
            return rbb  # 已有 ≥20mm 余量
    except Exception:
        pass''',
    '''    if bb is None:
        return None
    # 由当前物体包围盒反算 padding，使每次建出来的都是同一个 REGION_FIXED 盒子
    need = [REGION_FIXED["x"][1] - bb[3], REGION_FIXED["x"][0] - bb[0],
            REGION_FIXED["y"][1] - bb[4], REGION_FIXED["y"][0] - bb[1],
            REGION_FIXED["z"][1] - bb[5], REGION_FIXED["z"][0] - bb[2]]
    if min(need) < -1e-6:
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
        pass''', "Region 反算 padding")
rep('''    ferr = []
    for xc in x_centers_continuous(emit_lo, emit_hi, W, G):
        name = "ferrite_Tx_%d" % len([n for n in ferr if n.startswith("ferrite_Tx_")])
        try:
            box = m3d.modeler.create_box(origin=[xc - W / 2.0, COIL_Y_LO, -Z_GAP - thk],
                                         sizes=[W, COIL_Y_HI - COIL_Y_LO, thk], name=name)''',
    '''    ferr = []
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
                                         sizes=[W, 2.0 * y_half, thk], name=name)''', "铁氧体 Y-Tx")

rep('''            box = m3d.modeler.create_box(origin=[xc - W / 2.0, COIL_Y_LO, 30.0 + Z_GAP],
                                         sizes=[W, COIL_Y_HI - COIL_Y_LO, thk], name=name)''',
    '''            box = m3d.modeler.create_box(origin=[xc - W / 2.0, -y_half, 30.0 + Z_GAP],
                                         sizes=[W, 2.0 * y_half, thk], name=name)''', "铁氧体 Y-Rx")

# ---------------- 11. 发射线圈重叠参数 KX ----------------
rep('''KR_RANGE = [round(0.2 + 0.1 * i, 2) for i in range(4)]    # 0.2,0.3,0.4,0.5''',
    '''KR_RANGE = [round(0.2 + 0.1 * i, 2) for i in range(4)]    # 0.2,0.3,0.4,0.5
# KX = 两个发射线圈边沿间隙 / LC，无量纲，负值 = 投影重叠
#   实际间隙 tg = KX * LC（mm）；KX=-0.5 时两线圈重叠 50%
KX_RANGE = [round(-0.5 + 0.1 * i, 2) for i in range(11)]  # -0.5,-0.4,...,+0.5''', "KX 参数")

rep('''            tgs = txgap_plan(w, g) if SWEEP_TG else [0.0]
            for tg in tgs:''',
    '''            tgs = KX_RANGE if SWEEP_TG else [0.0]
            for KX in tgs:''', "KX 循环")

rep('''                        combos.append((LC, KR, w, g, dx, tg, mu, thk))''',
    '''                        combos.append((LC, KR, w, g, dx, KX, mu, thk))''', "KX 入列")

rep('''        wr.writerow(["LC_mm", "KR", "W_mm", "G_mm", "dx_mm", "tx_gap_mm", "mu", "thk_mm"])
        for LC, KR, w, g, dx, tg, mu, thk in combos:
            wr.writerow([LC, KR, w, g, dx, tg, mu, thk])''',
    '''        wr.writerow(["LC_mm", "KR", "KX", "W_mm", "G_mm", "dx_mm", "mu", "thk_mm"])
        for LC, KR, w, g, dx, KX, mu, thk in combos:
            wr.writerow([LC, KR, KX, w, g, dx, mu, thk])''', "KX 表头")

rep('''    for LC, KR, W, G, dx, tg, mu, thk in combos:
        key = (LC, KR, W, G, dx, tg, mu, thk)''',
    '''    for LC, KR, KX, W, G, dx, mu, thk in combos:
        key = (LC, KR, KX, W, G, dx, mu, thk)
        tg = KX * LC          # 实际边沿间隙(mm)，负值 = 重叠''', "KX 解包")

rep('''            if len(row) >= 8:
                try:
                    combos.append(tuple(float(x) for x in row[:8]))''',
    '''            if len(row) >= 8:
                try:
                    combos.append(tuple(float(x) for x in row[:8]))''', "KX 参数表读取(不变)")

rep('''        if ("LC_mm" not in head) or ("KR" not in head):''',
    '''        if ("LC_mm" not in head) or ("KR" not in head) or ("KX" not in head):''', "KX 表头校验")

rep('''    row = [LC, KR, W, G, dx, tg, mu, thk, round(L11, 3), round(L22, 3), round(L33, 3),''',
    '''    row = [LC, KR, KX, W, G, dx, mu, thk, round(L11, 3), round(L22, 3), round(L33, 3),''',
    "KX 结果行")

rep('''                wr.writerow(["LC_mm", "KR", "W_mm", "G_mm", "dx_mm", "tx_gap_mm", "mu", "thk_mm",''',
    '''                wr.writerow(["LC_mm", "KR", "KX", "W_mm", "G_mm", "dx_mm", "mu", "thk_mm",''',
    "KX 结果表头")

rep('''def solve_and_extract(d, m3d, LC, KR, W, G, dx, tg, mu, thk):''',
    '''def solve_and_extract(d, m3d, LC, KR, KX, W, G, dx, mu, thk):
    tg = KX * LC          # 实际边沿间隙(mm)''', "KX 求解签名")

rep('''            return solve_and_extract(d, m3d, LC, KR, W, G, dx, tg, mu, thk)''',
    '''            return solve_and_extract(d, m3d, LC, KR, KX, W, G, dx, mu, thk)''', "KX 求解调用")

rep('''        log("  LC=%.0f KR=%.2f W=%.1f G=%.1f dx=%3d tg=%3d mu=%.0f thk=%.0f L11=%.1f M13=%.2f k13=%.4f"
            % (LC, KR, W, G, dx, tg, mu, thk, L11, M13, k13))''',
    '''        log("  LC=%.0f KR=%.2f KX=%+.2f W=%.1f G=%.1f dx=%3d tg=%7.2f mu=%.0f thk=%.0f L11=%.1f M13=%.2f k13=%.4f"
            % (LC, KR, KX, W, G, dx, tg, mu, thk, L11, M13, k13))''', "KX 结果日志")

rep('''        log("  FAILED LC=%.0f KR=%.2f W=%.1f G=%.1f dx=%3d tg=%3d mu=%.0f thk=%.0f"
            % (LC, KR, W, G, dx, tg, mu, thk))''',
    '''        log("  FAILED LC=%.0f KR=%.2f KX=%+.2f W=%.1f G=%.1f dx=%3d tg=%7.2f mu=%.0f thk=%.0f"
            % (LC, KR, KX, W, G, dx, tg, mu, thk))''', "KX FAILED 日志")

rep('''            log("  !! 该点未完成，跳过: LC=%.0f KR=%.2f W=%.1f G=%.1f dx=%.0f tg=%d mu=%.0f thk=%.0f"
                % (LC, KR, W, G, dx, tg, mu, thk))''',
    '''            log("  !! 该点未完成，跳过: LC=%.0f KR=%.2f KX=%+.2f W=%.1f G=%.1f dx=%.0f tg=%7.2f mu=%.0f thk=%.0f"
                % (LC, KR, KX, W, G, dx, tg, mu, thk))''', "KX 跳过日志")

rep('''                log("=== W=%.1f G=%.1f tg=%3d thk=%.0f LC=%.0f rebuilt %d bars ==="
                    % (W, G, tg, thk, LC, nf))''',
    '''                log("=== W=%.1f G=%.1f tg=%7.2f(KX=%+.2f) thk=%.0f LC=%.0f rebuilt %d bars ==="
                    % (W, G, tg, KX, thk, LC, nf))''', "KX 几何日志")

rep('''REGION_FIXED = {"x": (-272.0, 272.0), "y": (-134.94, 161.0), "z": (-45.0, 75.0)}''',
    '''REGION_FIXED = {"x": (-330.0, 330.0), "y": (-134.94, 161.0), "z": (-45.0, 75.0)}''',
    "Region 扩到 ±330")

# ---------------- 12. dx 改为派生量：dx = S/40, S = Lc(2+KX) ----------------
rep('''                if SWEEP_DX:
                    if DX_MODE == "range":
                        dxs = range(-int(DX_FIXED_MAX), int(DX_FIXED_MAX) + 1, DX_STEP)  # 固定全范围 -150~150 步长10（所有 tg 统一）
                    else:
                        dxs = [-DX_FIXED_MAX, DX_FIXED_MAX]   # 只扫 ±150（2 点）
                else:
                    dxs = [0]''',
    '''                # dx 不再是独立变量：dx = S/40，其中 S = Lc(2+KX) = 两个发射线圈阵列的总外宽
                #   （S = 2*Lc + 间隙，间隙 = KX*Lc）
                dxs = [LC * (2.0 + KX) / 40.0]''', "dx 派生")

# ---------------- 13. 核数 8 -> 16 ----------------
rep('''CORES = 8''', '''CORES = 8''', "核数保持 8")

open(DST, "w", encoding="utf-8").write(src)
print("已生成 %s" % DST)
for p in patches:
    print("   - " + p)

# ---------------- 模板路径 ----------------
tpl = json.load(open(os.path.join(WORK, "coil_paths.json"), encoding="utf-8"))["Rx"]
out = os.path.join(WPT, "coil_template_Rx.json")
json.dump(tpl, open(out, "w", encoding="utf-8"))
print("模板路径 -> %s (%d 点)" % (out, len(tpl)))
