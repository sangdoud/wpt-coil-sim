# -*- coding: utf-8 -*-
# ============================================================
# 实验组 A：固定铁氧体单元周期 Unit=W+G=40 的基础扫描框架
# 求解器：Eddy-Current @ 85kHz
# 目标：采集互感 M、耦合系数 k；Bmax/ferrite_loss 占位 np.nan
# 复用已有项目 Projecttonight（其下新建 EddyCurrent 设计）
# ============================================================
import os, time, csv, math, sys
import numpy as np
from ansys.aedt.core import Desktop, Maxwell3d

# ============ 常量（用户规格） ============
UNIT = 40.0            # 铁氧体固定单元周期 W+G=40mm
COIL_SIZE = 168.9      # 发射区总外轮廓宽 mm
THK = 10.0             # 铁氧体厚度 mm
Z_GAP = 30.0           # 线圈-铁氧体 Z 向气隙 mm
MU_R = 300             # 铁氧体相对磁导率
SIGMA = 0.01           # 铁氧体电导率 S/m
FREQ = 85e3            # 频率 85kHz
EDDY_SOLUTION = "EddyCurrent"

# 发射线圈几何（DD线圈，X向为行车方向）
# 每个发射线圈宽 W_D_coil=(COIL_SIZE-TX_GAP)/2，沿 X 方向
COIL_Y_LO, COIL_Y_HI = -84.45, 84.45   # 发射线圈 Y 范围（固定）
COIL_Y_LO_RX = -84.45
COIL_Y_HI_RX = 84.45

# 磁条：长沿X，宽W沿Y，缝隙G沿Y，阵列Y向[-84.45, +84.45]
# 磁条 X 长度：覆盖发射区宽度（约 COIL_SIZE）
FERR_X_LEN = 170.0     # 磁条 X 长度（略大于发射区）

# Rx 自适应 dx 范围
DX_RANGE = {40: list(range(-50, 51, 10)),     # TX_GAP=40 -> [-50,50]
            80: list(range(-110, 111, 10)),   # TX_GAP=80 -> [-110,110]
            120: list(range(-110, 111, 10))}  # TX_GAP=120 -> [-110,110]

# 参数范围
TX_GAP_RANGE = [40, 80, 120]
W_RANGE = list(range(10, 21))   # 10~20 步长1

# 输出
CSV = r"C:/Users/lenovo/Desktop/zidong/expA_results.csv"
LOG = r"C:/Users/lenovo/Desktop/zidong/expA_scan.log"
GROUP = "A_Fixed_Unit_40"

PROJECT = "Projecttonight"
DESIGN = "EXP_A"       # 新建设计（在 Projecttonight 下）

def log(msg):
    line = "%s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def build_tx_coil(m3d, oeditor, name, x_center, w_coil, z):
    """构建发射 DD 线圈（矩形螺旋，X宽 w_coil, Y长 168.9）"""
    # 简化为矩形路径（覆盖 X宽 w_coil, Y长 168.9）
    # 若需真实螺旋可替换为 rs_spiral
    hw = w_coil / 2.0
    hy = COIL_Y_HI
    pts = [
        (x_center - hw, -hy, z), (x_center + hw, -hy, z),
        (x_center + hw, +hy, z), (x_center - hw, +hy, z),
    ]
    pl_pts = [["NAME:PLPoint", "X:=", "%.6fmm" % p[0], "Y:=", "%.6fmm" % p[1], "Z:=", "%.6fmm" % p[2]] for p in pts]
    pl_seg = [["NAME:PLSegment", "SegmentType:=", "Line", "StartIndex:=", i, "NoOfPoints:=", 2] for i in range(3)]
    attrs = ["NAME:Attributes", "Name:=", name, "Flags:=", "", "Color:=", "(143 175 143)",
             "Transparency:=", 0, "PartCoordinateSystem:=", "Global", "UDMId:=", "",
             "MaterialValue:=", "\"copper\"", "SurfaceMaterialValue:=", "\"\"",
             "SolveInside:=", True, "ShellElement:=", False, "ShellElementThickness:=", "0mm",
             "ReferenceTemperature:=", "20cel", "IsMaterialEditable:=", True,
             "UseMaterialAppearance:=", False, "IsLightweight:=", False]
    oeditor.CreatePolyline(
        ["NAME:PolylineParameters", "IsPolylineCovered:=", False, "IsPolylineClosed:=", False,
         ["NAME:PolylinePoints"] + pl_pts, ["NAME:PolylineSegments"] + pl_seg,
         ["NAME:PolylineXSection", "XSectionType:=", "Rectangle", "XSectionOrient:=", "Auto",
          "XSectionWidth:=", "3mm", "XSectionTopWidth:=", "3mm",
          "XSectionHeight:=", "0.5mm", "XSectionNumSegments:=", "0",
          "XSectionBendType:=", "Corner"]],
        attrs)
    return name

def build_rx_coil(m3d, oeditor, name, x_center, z):
    """构建接收线圈（方形螺旋，仅平移不改几何）"""
    hw = COIL_SIZE / 2.0
    hy = COIL_Y_HI_RX
    pts = [
        (x_center - hw, -hy, z), (x_center + hw, -hy, z),
        (x_center + hw, +hy, z), (x_center - hw, +hy, z),
    ]
    pl_pts = [["NAME:PLPoint", "X:=", "%.6fmm" % p[0], "Y:=", "%.6fmm" % p[1], "Z:=", "%.6fmm" % p[2]] for p in pts]
    pl_seg = [["NAME:PLSegment", "SegmentType:=", "Line", "StartIndex:=", i, "NoOfPoints:=", 2] for i in range(3)]
    attrs = ["NAME:Attributes", "Name:=", name, "Flags:=", "", "Color:=", "(143 175 143)",
             "Transparency:=", 0, "PartCoordinateSystem:=", "Global", "UDMId:=", "",
             "MaterialValue:=", "\"copper\"", "SurfaceMaterialValue:=", "\"\"",
             "SolveInside:=", True, "ShellElement:=", False, "ShellElementThickness:=", "0mm",
             "ReferenceTemperature:=", "20cel", "IsMaterialEditable:=", True,
             "UseMaterialAppearance:=", False, "IsLightweight:=", False]
    oeditor.CreatePolyline(
        ["NAME:PolylineParameters", "IsPolylineCovered:=", False, "IsPolylineClosed:=", False,
         ["NAME:PolylinePoints"] + pl_pts, ["NAME:PolylineSegments"] + pl_seg,
         ["NAME:PolylineXSection", "XSectionType:=", "Rectangle", "XSectionOrient:=", "Auto",
          "XSectionWidth:=", "3mm", "XSectionTopWidth:=", "3mm",
          "XSectionHeight:=", "0.5mm", "XSectionNumSegments:=", "0",
          "XSectionBendType:=", "Corner"]],
        attrs)
    return name

def build_ferrite_array(m3d, w, g, y_lo, y_hi, x_center, z_bot, prefix):
    """构建铁氧体阵列：磁条长沿X，宽W/缝隙G沿Y，Y向[y_lo,y_hi]"""
    names = []
    # 沿 Y 排布：从 y_lo 开始，条宽 w + 缝隙 g
    y = y_lo
    idx = 0
    while y + w <= y_hi:
        name = "%s_%d" % (prefix, idx)
        try:
            box = m3d.modeler.create_box(
                origin=[x_center - FERR_X_LEN/2.0, y, z_bot],
                sizes=[FERR_X_LEN, w, THK], name=name)
            box.material_name = "ferrite"
            names.append(name)
            idx += 1
        except Exception as e:
            log("ferrite err: %s" % repr(e))
        y += w + g
    return names

def solve_and_extract(m3d, d):
    """Eddy-Current 求解并提取 M/k"""
    try:
        d.odesktop.StopSimulations(True)
        time.sleep(3)
    except Exception:
        pass
    try:
        m3d.analyze(cores=8, run_in_thread=True)
    except Exception as e:
        log("analyze err: %s" % repr(e))
        return None
    solved = False
    for i in range(90):
        time.sleep(20)
        try:
            solved = m3d.setups[0].is_solved
        except Exception as e:
            log("poll err: %s" % repr(e))
        if solved:
            break
    if not solved:
        log("  NOT SOLVED")
        return None
    try:
        w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
        data = m3d.post.get_solution_data(
            expressions=["Lmatrix.L(%s,%s)" % (wi, wj) for wi in w for wj in w],
            setup_sweep_name="Setup1 : LastAdaptive")
        real, _ = data.full_matrix_real_imag
        def L(i, j):
            return real["Lmatrix.L(%s,%s)" % (w[i], w[j])][0][1] / 1000.0
        M12, M13, M23 = L(0,1), L(0,2), L(1,2)
        L11, L22, L33 = L(0,0), L(1,1), L(2,2)
        k13 = M13/math.sqrt(L11*L33) if L11>0 and L33>0 else 0
        k23 = M23/math.sqrt(L22*L33) if L22>0 and L33>0 else 0
        return {"M13": M13, "M23": M23, "k13": k13, "k23": k23, "M12": M12}
    except Exception as e:
        log("extract err: %s" % repr(e))
        return None

def main():
    # 1) 连接现有项目
    d = Desktop(version="2024.1", new_desktop=False, non_graphical=False, close_on_exit=False)
    p = d.load_project(PROJECT)
    log("connected: %s" % PROJECT)

    # 2) 新建设计（Eddy-Current）
    # 删除旧设计（若存在）
    try:
        p.delete_design(DESIGN)
    except Exception:
        pass
    try:
        m3d = Maxwell3d(project=PROJECT, design=DESIGN, solution_type=EDDY_SOLUTION)
        log("设计创建: %s (EddyCurrent)" % DESIGN)
    except Exception as e:
        log("设计创建失败: %s" % repr(e))
        sys.exit(1)

    oeditor = m3d.odesign.SetActiveEditor("3D Modeler")

    # 3) 设置铁氧体材料
    try:
        m3d.materials["ferrite"].permeability.value = MU_R
        m3d.materials["ferrite"].conductivity.value = SIGMA
    except Exception as e:
        log("mat err: %s" % repr(e))

    # 4) 创建 Setup（Eddy-Current 85kHz）
    try:
        m3d.create_setup(name="Setup1", props={
            "Frequency": "85kHz",
            "MaximumPasses": 8, "PercentError": 5, "PercentRefinement": 30})
        log("Setup1 created (85kHz)")
    except Exception as e:
        log("setup err: %s" % repr(e))

    # 5) 初始化 CSV
    if not os.path.exists(CSV) or os.path.getsize(CSV) == 0:
        with open(CSV, "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["TX_GAP", "W", "G", "dx", "M", "k", "Group", "Bmax", "ferrite_loss"])

    # 6) 主循环：外层 TX_GAP → 中层 W → 内层 dx
    for tg in TX_GAP_RANGE:
        w_coil = (COIL_SIZE - tg) / 2.0   # 发射线圈 X 宽
        log("=== TX_GAP=%d, W_D_coil=%.2f ===" % (tg, w_coil))

        # 6a) 重建发射 DD 线圈（Tx1/Tx2）
        # 发射线圈中心位置
        tx1_c = -(tg/2 + w_coil/2)
        tx2_c =  (tg/2 + w_coil/2)
        build_tx_coil(m3d, oeditor, "Tx1", tx1_c, w_coil, 0.0)
        build_tx_coil(m3d, oeditor, "Tx2", tx2_c, w_coil, 0.0)
        # 接收线圈（固定几何，仅平移）
        build_rx_coil(m3d, oeditor, "Rx", 0.0, Z_GAP)

        for W in W_RANGE:
            G = UNIT - W
            if G <= 0:
                log("  skip W=%d (G=%.0f<=0)" % (W, G))
                continue
            # 重建铁氧体：Tx 组（下方 z=-THK-Z_GAP）和 Rx 组（上方 z=Z_GAP）
            # 删除旧铁氧体
            for fn in [o for o in m3d.modeler.object_names if o.startswith("ferrite_")]:
                try: m3d.modeler.delete(fn)
                except: pass
            # Tx 铁氧体：线圈下方
            ferr_tx = build_ferrite_array(m3d, W, G, -84.45, 84.45, 0.0, -Z_GAP-THK, "ferrite_Tx")
            # Rx 铁氧体：线圈上方
            ferr_rx = build_ferrite_array(m3d, W, G, -84.45, 84.45, 0.0, Z_GAP, "ferrite_Rx")
            log("  W=%d G=%.0f 铁氧体: Tx%d Rx%d" % (W, G, len(ferr_tx), len(ferr_rx)))

            for dx in DX_RANGE[tg]:
                # 平移 Rx 线圈（不改几何）
                try:
                    cur = (m3d.modeler["Rx"].bounding_box[0] + m3d.modeler["Rx"].bounding_box[3])/2
                    delta = dx - cur
                    if abs(delta) > 1e-6:
                        m3d.modeler.move(["Rx"], [delta, 0, 0])
                        for fr in [o for o in m3d.modeler.object_names if o.startswith("ferrite_Rx_")]:
                            try: m3d.modeler.move([fr], [delta, 0, 0])
                            except: pass
                except Exception as e:
                    log("  move Rx err: %s" % repr(e))

                res = solve_and_extract(m3d, d)
                if res:
                    # 取 M13、k13（Tx1-Rx 耦合）作为代表值
                    M = res["M13"]
                    k = res["k13"]
                    log("    tg=%d W=%d G=%.0f dx=%3d M13=%.2f k13=%.4f" % (tg, W, G, dx, M, k))
                else:
                    M, k = np.nan, np.nan
                    log("    tg=%d W=%d dx=%3d FAILED" % (tg, W, dx))

                with open(CSV, "a", newline="") as f:
                    wr = csv.writer(f)
                    wr.writerow([tg, W, G, dx, M, k, GROUP, np.nan, np.nan])

        # 每组仿真完成：删除发射线圈 + 全部铁氧体（保留 Rx？用户说删除发射线圈和铁氧体）
        for obj in ["Tx1", "Tx2"] + [o for o in m3d.modeler.object_names if o.startswith("ferrite_")]:
            try:
                if obj in m3d.modeler.object_names:
                    m3d.modeler.delete(obj)
            except: pass
        # 删除 Rx（下组重建）
        try:
            if "Rx" in m3d.modeler.object_names:
                m3d.modeler.delete("Rx")
        except: pass

    m3d.save_project()
    log("EXP A DONE")

if __name__ == "__main__":
    main()
