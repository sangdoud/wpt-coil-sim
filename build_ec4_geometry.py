from ansys.aedt.core import Desktop, Maxwell3d

DESIGN = "WPT_EC4"
# 铁氧体参数（单点验证）
W = 15.0   # 铁氧体条宽 (Y)
G = 15.0   # 条间气隙 (Y)
THK = 10.0 # 铁氧体厚 (Z)
Z_GAP = 30.0  # 铁氧体距线圈平面距离
# 引线
RAD = 0.3
LEAD_Z = {"Tx1": (-45.0, 45.0), "Tx2": (-45.0, 45.0), "Rx": (30.0, 45.0)}  # (origin_z, height) -> 末端 z
# 端面 XY
ENDS = {
    "Tx1": [(-56.0, -15.0), (-2.36, -71.87)],
    "Tx2": [(116.0, -15.0), (169.64, -71.87)],
    "Rx":  [(30.0, -15.0), (83.64, -71.87)],
}
# 线圈 X 范围（铁氧体覆盖）
COIL_X = {"Tx1": (-170.0, -1.0), "Tx2": (2.0, 171.0), "Rx": (-84.0, 85.0)}
COIL_Y_HALF = 84.0

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")

# 0) 删除旧设计
try:
    if DESIGN in m3d.design_list:
        m3d._oproject.DeleteDesign(DESIGN)
except Exception as e:
    print("del err:", repr(e))

# 1) 复制几何（重新获取源设计对象以激活），再创建目标设计
src = Maxwell3d(project="Project3", design="Maxwell3DDesign1")
src_ed = src.odesign.SetActiveEditor("3D Modeler")
src_ed.Copy(["NAME:Selections", "Selections:=", "Tx1,Tx2,Rx"])
print("copied from Maxwell3DDesign1")
dst = Maxwell3d(project="Project3", design=DESIGN, solution_type="EddyCurrent")
dst_ed = dst.odesign.SetActiveEditor("3D Modeler")
dst_ed.Paste()
print("geometry pasted to", DESIGN)

# 2) Setup
try:
    dst.create_setup(name="Setup1", props={"Frequency": "85kHz", "MaximumPasses": 10, "PercentRefinement": 30})
    print("Setup1 created")
except Exception as e:
    print("setup err:", repr(e))

# 3) 建引线（独立物体，稍后 Unite）
lead_names = []
for coil, pts in ENDS.items():
    z0, h = LEAD_Z[coil]
    for i, (cx, cy) in enumerate(pts):
        name = "lead_%s_%s" % (coil, "a" if i == 0 else "b")
        try:
            cyl = dst.modeler.create_cylinder(orientation="Z", origin=[cx, cy, z0], radius=RAD, height=h, name=name)
            cyl.material_name = "copper"
            lead_names.append(name)
            print("lead", name, "z[%.1f,%.1f]" % (z0, z0 + h))
        except Exception as e:
            print("lead err:", repr(e))

# 4) 建铁氧体条（Y 排布，中心 0 向两边）
ferr_names = []
for coil, (x0, x1) in COIL_X.items():
    if coil == "Rx":
        z_bot, z_top = 30.0 + Z_GAP, 30.0 + Z_GAP + THK   # [60,70]
    else:
        z_bot, z_top = -Z_GAP - THK, -Z_GAP              # [-40,-30]
    k = 0
    ycenters = []
    while True:
        yc = k * (W + G)
        if yc - W / 2.0 > COIL_Y_HALF:
            break
        if k == 0:
            ycenters.append(0.0)
        else:
            ycenters.append(yc)
            ycenters.append(-yc)
        k += 1
    for yc in ycenters:
        name = "ferrite_%s_%d" % (coil, len([n for n in ferr_names if coil in n]))
        try:
            box = dst.modeler.create_box(
                origin=[x0, yc - W / 2.0, z_bot],
                sizes=[x1 - x0, W, THK],
                name=name,
            )
            box.material_name = "Ferrite"
            ferr_names.append(name)
            print("ferrite", name, "y=%.1f z[%.1f,%.1f]" % (yc, z_bot, z_top))
        except Exception as e:
            print("ferrite err:", repr(e))

# 5) 铁氧体开孔：引线穿过的条
for ln in lead_names:
    # 引线位置
    coil = ln.split("_")[1]
    idx = 0 if ln.endswith("a") else 1
    lx, ly = ENDS[coil][idx]
    z0, h = LEAD_Z[coil]
    lz_lo, lz_hi = min(z0, z0 + h), max(z0, z0 + h)
    for fn in ferr_names:
        if fn.split("_")[1] != coil:
            continue
        try:
            bb = dst.modeler[fn].bounding_box
            fx_lo, fy_lo, fz_lo = bb[0], bb[1], bb[2]
            fx_hi, fy_hi, fz_hi = bb[3], bb[4], bb[5]
            # 相交判断
            if (fx_lo <= lx <= fx_hi) and (fy_lo <= ly <= fy_hi) and (fz_lo <= lz_hi and fz_hi >= lz_lo):
                dst.modeler.subtract(blank_list=[fn], tool_list=[ln], keep_originals=True)
                print("  subtract: %s removed from %s" % (ln, fn))
        except Exception as e:
            print("subtract err", fn, ln, repr(e))

# 6) Unite 引线与线圈
for coil in ["Tx1", "Tx2", "Rx"]:
    parts = [coil] + [n for n in dst.modeler.object_names if n.startswith("lead_" + coil)]
    if len(parts) > 1:
        dst.modeler.unite(parts, keep_originals=False)
        print("united", coil)

# 7) Region
try:
    if "Region" in dst.modeler.object_names:
        dst.modeler.delete("Region")
except Exception:
    pass
try:
    dst.modeler.create_region(pad_value=[50, 50, 50, 50, 0, 0], pad_type="Absolute Offset", name="Region")
    print("Region created")
except Exception as e:
    print("region err:", repr(e))

# 8) 打印物体
for n in dst.modeler.object_names:
    try:
        print(n, "bbox:", [round(v, 1) for v in dst.modeler[n].bounding_box])
    except Exception as e:
        print(n, "bbox err:", repr(e))
