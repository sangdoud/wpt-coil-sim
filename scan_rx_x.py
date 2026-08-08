import time, csv, math
from ansys.aedt.core import Desktop, Maxwell3d

DESIGN = "WPT_G"
DXS = list(range(-50, 51, 10))  # -50 ~ +50, 步长10
print("scan points:", DXS, flush=True)

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=8016)
m3d = Maxwell3d(project="Projecttonight", design=DESIGN)
print("connected:", m3d.solution_type, flush=True)

# 铁氧体材料确保设置好
try:
    m3d.materials["ferrite"].conductivity.value = 0
    m3d.materials["ferrite"].permeability.value = 300
except Exception as e:
    print("mat err:", repr(e), flush=True)

# 确认激励存在
w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
try:
    excs = list(m3d.oboundary.GetExcitations())
    print("excitations:", excs[:5], "...", flush=True)
    if not any("Winding" in str(e) for e in excs):
        print("ERROR: windings missing!", flush=True)
except Exception as e:
    print("exc check err:", repr(e), flush=True)

# Rx 组铁氧体（跟着 Rx 移动）
rx_ferrites = [n for n in m3d.modeler.object_names if n.startswith("ferrite_Rx_")]
print("rx ferrites:", rx_ferrites, flush=True)

# 重置 Rx 到中心（dx=0），应对上次中断留下的偏移
try:
    bb = m3d.modeler["Rx"].bounding_box
    offset = (bb[0] + bb[3]) / 2.0
    print("Rx current X center: %.2f" % offset, flush=True)
    if abs(offset) > 1:
        m3d.modeler.move(["Rx"], [-offset, 0, 0])
        for fn in rx_ferrites:
            m3d.modeler.move([fn], [-offset, 0, 0])
        print("reset Rx to 0", flush=True)
except Exception as e:
    print("reset err:", repr(e), flush=True)

# 降低求解精度以加快扫描（趋势研究足够）
try:
    setup = m3d.setups[0]
    setup.props["MaximumPasses"] = 8
    setup.props["PercentError"] = 5
    setup.props["PercentRefinement"] = 5
    setup.update()
    print("setup precision reduced: MaxPass=5, Refine=20%%", flush=True)
except Exception as e:
    print("setup update err:", repr(e), flush=True)

results = []
current_dx = 0
for dx in DXS:
    print("=== dx = %d mm ===" % dx, flush=True)
    # 移动 Rx + Rx 铁氧体到目标 dx
    delta = dx - current_dx
    if abs(delta) > 1e-6:
        try:
            m3d.modeler.move(["Rx"], [delta, 0, 0])
            for fn in rx_ferrites:
                m3d.modeler.move([fn], [delta, 0, 0])
            print("moved Rx+ferrite by delta %.1f" % delta, flush=True)
        except Exception as e:
            print("move err:", repr(e), flush=True)
        current_dx = dx

    # 求解（触发+轮询，保持连接）
    try:
        m3d.analyze(cores=4, run_in_thread=True)
    except Exception as e:
        print("analyze err:", repr(e), flush=True)
    solved = False
    for i in range(60):
        time.sleep(20)
        try:
            solved = m3d.setups[0].is_solved
        except Exception as e:
            print("poll err:", repr(e), flush=True)
        if solved:
            break
    print("  solved:", solved, flush=True)
    if not solved:
        results.append((dx, None))
        continue

    # 提取 L 矩阵
    try:
        data = m3d.post.get_solution_data(
            expressions=["Lmatrix.L(%s,%s)" % (wi, wj) for wi in w for wj in w],
            setup_sweep_name="Setup1 : LastAdaptive",
        )
        real, _ = data.full_matrix_real_imag
        def L(i, j):
            return real["Lmatrix.L(%s,%s)" % (w[i], w[j])][0][1] / 1000.0  # uH
        L11, L22, L33 = L(0, 0), L(1, 1), L(2, 2)
        M12, M13, M23 = L(0, 1), L(0, 2), L(1, 2)
        k13 = M13 / math.sqrt(L11 * L33) if L11 > 0 and L33 > 0 else 0
        k23 = M23 / math.sqrt(L22 * L33) if L22 > 0 and L33 > 0 else 0
        print("  L11=%.1f L22=%.1f L33=%.1f | M13=%.2f M23=%.2f k13=%.4f k23=%.4f" %
              (L11, L22, L33, M13, M23, k13, k23), flush=True)
        results.append((dx, L11, L22, L33, M12, M13, M23, k13, k23))
    except Exception as e:
        print("  extract err:", repr(e), flush=True)
        results.append((dx, None))

# 存 CSV
out = r"C:/Users/lenovo/Desktop/zidong/scan_RxX.csv"
with open(out, "w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["dx_mm", "L11_Tx1_uH", "L22_Tx2_uH", "L33_Rx_uH", "M12_uH", "M13_uH", "M23_uH", "k13", "k23"])
    for r in results:
        if r[1] is None:
            wr.writerow([r[0], "FAIL"])
        else:
            wr.writerow(r)
print("saved:", out, flush=True)
print("SCAN DONE", flush=True)
