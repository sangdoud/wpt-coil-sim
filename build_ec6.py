import math
from ansys.aedt.core import Desktop, Maxwell3d

DESIGN = "WPT_EC9"
W, G, THK, Z_GAP = 15.0, 15.0, 10.0, 30.0
X_OFFSET = 0.0  # 铁氧体阵列整体 X 偏移（扫描变量，单点=0）
RAD = 0.3
LEAD_Z = {"Tx1": (-45.0, 45.0), "Tx2": (-45.0, 45.0), "Rx": (30.0, 45.0)}
ENDS = {
    "Tx1": [(-56.0, -15.0), (-2.36, -71.87)],
    "Tx2": [(116.0, -15.0), (169.64, -71.87)],
    "Rx":  [(30.0, -15.0), (83.64, -71.87)],
}
# 铁氧体覆盖的 X 范围（发射区一套、接收区一套）
FERR_GROUPS = {"Tx": (-170.0, 171.0), "Rx": (-84.0, 85.0)}
LEAD_GROUP = {"Tx1": "Tx", "Tx2": "Tx", "Rx": "Rx"}
COIL_Y_LO, COIL_Y_HI = -84.0, 84.0   # 铁氧体条 Y 覆盖长度

# 线圈几何参数
S0, S_inner, pitch, turns, Rc, wire_w, wire_t = 84.0, 30.0, 4.5, 12, 15.0, 3.0, 0.5
TX1_X, TX2_X, GAP_Z = -86.0, 86.0, 30.0

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)

try:
    m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")
    try:
        m3d._oproject.DeleteDesign(DESIGN)
        print("deleted old", DESIGN)
    except Exception:
        pass
except Exception as e:
    print("del err:", repr(e))

dst = Maxwell3d(project="Project3", design=DESIGN, solution_type="EddyCurrent")
oEditor = dst.odesign.SetActiveEditor("3D Modeler")
print("design created:", DESIGN)

# ---- 线圈 ----
def rs_spiral(S_inner, S0, pitch, turns, Rc, n_per_turn=64):
    pts, total = [], turns * n_per_turn
    for i in range(total):
        frac = i / float(total); S = S_inner + frac * (S0 - S_inner); r = min(Rc, S * 0.8)
        p = (i % n_per_turn) / float(n_per_turn)
        if p < 1/8.0:
            t = p * 8; pts.append((S, -S + r + (2*S - 2*r) * t))
        elif p < 2/8.0:
            t = p * 8 - 1; a = (math.pi/2) * t; pts.append((S - r + r*math.cos(a), S - r + r*math.sin(a)))
        elif p < 3/8.0:
            t = p * 8 - 2; pts.append((S - r - (2*S - 2*r) * t, S))
        elif p < 4/8.0:
            t = p * 8 - 3; a = math.pi/2 + (math.pi/2) * t; pts.append((-S + r + r*math.cos(a), S - r + r*math.sin(a)))
        elif p < 5/8.0:
            t = p * 8 - 4; pts.append((-S, S - r - (2*S - 2*r) * t))
        elif p < 6/8.0:
            t = p * 8 - 5; a = math.pi + (math.pi/2) * t; pts.append((-S + r + r*math.cos(a), -S + r + r*math.sin(a)))
        elif p < 7/8.0:
            t = p * 8 - 6; pts.append((-S + r + (2*S - 2*r) * t, -S))
        else:
            t = p * 8 - 7; a = 3*math.pi/2 + (math.pi/2) * t; pts.append((S - r + r*math.cos(a), -S + r + r*math.sin(a)))
    return pts

def attrs(nm):
    return ["NAME:Attributes", "Name:=", nm, "Flags:=", "", "Color:=", "(143 175 143)",
            "Transparency:=", 0, "PartCoordinateSystem:=", "Global", "UDMId:=", "",
            "MaterialValue:=", "\"copper\"", "SurfaceMaterialValue:=", "\"\"",
            "SolveInside:=", True, "ShellElement:=", False, "ShellElementThickness:=", "0mm",
            "ReferenceTemperature:=", "20cel", "IsMaterialEditable:=", True,
            "UseMaterialAppearance:=", False, "IsLightweight:=", False]

def build_coil(name, Xc, Zc):
    pts = rs_spiral(S_inner, S0, pitch, turns, Rc)
    pl_pts = [["NAME:PLPoint", "X:=", "%.6fmm" % (Xc + x), "Y:=", "%.6fmm" % y, "Z:=", "%.6fmm" % Zc]
              for (x, y) in pts]
    pl_seg = [["NAME:PLSegment", "SegmentType:=", "Line", "StartIndex:=", i, "NoOfPoints:=", 2]
              for i in range(len(pts) - 1)]
    oEditor.CreatePolyline(
        ["NAME:PolylineParameters", "IsPolylineCovered:=", False, "IsPolylineClosed:=", False,
         ["NAME:PolylinePoints"] + pl_pts, ["NAME:PolylineSegments"] + pl_seg,
         ["NAME:PolylineXSection", "XSectionType:=", "Rectangle", "XSectionOrient:=", "Auto",
          "XSectionWidth:=", "%.6fmm" % wire_w, "XSectionTopWidth:=", "%.6fmm" % wire_w,
          "XSectionHeight:=", "%.6fmm" % wire_t, "XSectionNumSegments:=", "0",
          "XSectionBendType:=", "Corner"]],
        attrs(name))
    print("coil", name, "built")

build_coil("Tx1", TX1_X, 0.0)
build_coil("Tx2", TX2_X, 0.0)
build_coil("Rx", 0.0, GAP_Z)

try:
    dst.create_setup(name="Setup1", props={"Frequency": "85kHz", "MaximumPasses": 10, "PercentRefinement": 30})
except Exception as e:
    print("setup err:", repr(e))

# ---- 引线 ----
lead_names = []
for coil, pts in ENDS.items():
    z0, h = LEAD_Z[coil]
    for i, (cx, cy) in enumerate(pts):
        name = "lead_%s_%s" % (coil, "a" if i == 0 else "b")
        try:
            cyl = dst.modeler.create_cylinder(orientation="Z", origin=[cx, cy, z0], radius=RAD, height=h, name=name)
            cyl.material_name = "copper"
            lead_names.append(name)
        except Exception as e:
            print("lead err:", repr(e))
print("leads:", lead_names)

# ---- 铁氧体：沿 Y 延伸，X 排布，中心对齐 X=0(+offset) ----
def x_centers(target_hi, w, g, off):
    k = 0
    while True:
        if k * (w + g) + w / 2.0 >= target_hi:
            break
        k += 1
    xs = [0.0]
    for kk in range(1, k + 1):
        xs.append(kk * (w + g)); xs.append(-kk * (w + g))
    return [x + off for x in xs]

ferr_names = []
for group, (x_lo, x_hi) in FERR_GROUPS.items():
    if group == "Rx":
        z_bot, z_top = 30.0 + Z_GAP, 30.0 + Z_GAP + THK
    else:
        z_bot, z_top = -Z_GAP - THK, -Z_GAP
    for xc in x_centers(max(abs(x_lo), abs(x_hi)), W, G, X_OFFSET):
        idx = len([n for n in ferr_names if n.startswith("ferrite_" + group)])
        name = "ferrite_%s_%d" % (group, idx)
        try:
            box = dst.modeler.create_box(origin=[xc - W / 2.0, COIL_Y_LO, z_bot],
                                         sizes=[W, COIL_Y_HI - COIL_Y_LO, THK], name=name)
            box.material_name = "Ferrite"
            ferr_names.append(name)
        except Exception as e:
            print("ferrite err:", repr(e))
print("ferrite bars:", len(ferr_names), "per group:", {c: len([n for n in ferr_names if n.startswith("ferrite_" + c)]) for c in ["Tx", "Rx"]})

# ---- 开孔：引线穿过的铁氧体条（用稍大辅助圆柱留间隙）----
HOLE_RAD = 0.5  # 比引线 0.3 大，留 0.2mm 间隙
for ln in lead_names:
    coil = ln.split("_")[1]
    group = LEAD_GROUP[coil]
    idx = 0 if ln.endswith("a") else 1
    lx, ly = ENDS[coil][idx]
    z0, h = LEAD_Z[coil]
    lz_lo, lz_hi = min(z0, z0 + h), max(z0, z0 + h)
    # 创建辅助开孔圆柱
    aux = None
    try:
        aux = dst.modeler.create_cylinder(orientation="Z", origin=[lx, ly, lz_lo],
                                          radius=HOLE_RAD, height=lz_hi - lz_lo, name="aux_hole")
    except Exception as e:
        print("aux cyl err:", repr(e))
    for fn in ferr_names:
        if not fn.startswith("ferrite_" + group):
            continue
        try:
            bb = dst.modeler[fn].bounding_box
            if (bb[0] <= lx <= bb[3]) and (bb[1] <= ly <= bb[4]) and (bb[2] <= lz_hi and bb[5] >= lz_lo):
                dst.modeler.subtract(blank_list=[fn], tool_list=[aux.name], keep_originals=False)
                print("  hole:", ln, "->", fn)
        except Exception as e:
            print("subtract err:", repr(e))
    # 删除辅助圆柱（如未被子tract删除）
    if aux is not None:
        try:
            if aux.name in dst.modeler.object_names:
                dst.modeler.delete(aux.name)
        except Exception:
            pass

# ---- Unite ----
for coil in ["Tx1", "Tx2", "Rx"]:
    parts = [coil] + [n for n in dst.modeler.object_names if n.startswith("lead_" + coil)]
    if len(parts) > 1:
        dst.modeler.unite(parts, keep_originals=False)

# ---- Region ----
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

# ---- 打印 ----
print("=== OBJECTS ===")
for n in dst.modeler.object_names:
    if n.startswith("ferrite"):
        bb = dst.modeler[n].bounding_box
        print(n, "X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]" % (bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))
    elif n in ("Tx1", "Tx2", "Rx", "Region"):
        print(n, "bbox:", [round(v, 1) for v in dst.modeler[n].bounding_box])
