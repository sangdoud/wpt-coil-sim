import math
from ansys.aedt.core import Desktop, Maxwell3d

DESIGN = "WPT_EC5"
W, G, THK, Z_GAP = 15.0, 15.0, 10.0, 30.0
RAD = 0.3
LEAD_Z = {"Tx1": (-45.0, 45.0), "Tx2": (-45.0, 45.0), "Rx": (30.0, 45.0)}
ENDS = {
    "Tx1": [(-56.0, -15.0), (-2.36, -71.87)],
    "Tx2": [(116.0, -15.0), (169.64, -71.87)],
    "Rx":  [(30.0, -15.0), (83.64, -71.87)],
}
COIL_X = {"Tx1": (-170.0, -1.0), "Tx2": (2.0, 171.0), "Rx": (-84.0, 85.0)}
COIL_Y_HALF = 84.0

# 线圈几何参数（与 Build_Coils_Stage1.py 一致）
S0, S_inner, pitch, turns, Rc, wire_w, wire_t = 84.0, 30.0, 4.5, 12, 15.0, 3.0, 0.5
TX1_X, TX2_X, GAP_Z = -86.0, 86.0, 30.0

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)

# 0) 删除旧设计
try:
    m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")
    if DESIGN in m3d.design_list:
        m3d._oproject.DeleteDesign(DESIGN)
        print("deleted old", DESIGN)
except Exception as e:
    print("del err:", repr(e))

# 1) 创建新设计
dst = Maxwell3d(project="Project3", design=DESIGN, solution_type="EddyCurrent")
oEditor = dst.odesign.SetActiveEditor("3D Modeler")
print("design created:", DESIGN)

# 2) 螺旋点生成（抄 Build_Coils_Stage1）
def rs_spiral(S_inner, S0, pitch, turns, Rc, n_per_turn=64):
    pts = []
    total = turns * n_per_turn
    for i in range(total):
        frac = i / float(total)
        S = S_inner + frac * (S0 - S_inner)
        r = min(Rc, S * 0.8)
        p = (i % n_per_turn) / float(n_per_turn)
        if p < 1/8.0:
            t = p * 8; pts.append((S, -S + r + (2*S - 2*r) * t))
        elif p < 2/8.0:
            t = p * 8 - 1; a = (math.pi/2) * t
            pts.append((S - r + r * math.cos(a), S - r + r * math.sin(a)))
        elif p < 3/8.0:
            t = p * 8 - 2; pts.append((S - r - (2*S - 2*r) * t, S))
        elif p < 4/8.0:
            t = p * 8 - 3; a = math.pi/2 + (math.pi/2) * t
            pts.append((-S + r + r * math.cos(a), S - r + r * math.sin(a)))
        elif p < 5/8.0:
            t = p * 8 - 4; pts.append((-S, S - r - (2*S - 2*r) * t))
        elif p < 6/8.0:
            t = p * 8 - 5; a = math.pi + (math.pi/2) * t
            pts.append((-S + r + r * math.cos(a), -S + r + r * math.sin(a)))
        elif p < 7/8.0:
            t = p * 8 - 6; pts.append((-S + r + (2*S - 2*r) * t, -S))
        else:
            t = p * 8 - 7; a = 3*math.pi/2 + (math.pi/2) * t
            pts.append((S - r + r * math.cos(a), -S + r + r * math.sin(a)))
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
         ["NAME:PolylinePoints"] + pl_pts,
         ["NAME:PolylineSegments"] + pl_seg,
         ["NAME:PolylineXSection", "XSectionType:=", "Rectangle", "XSectionOrient:=", "Auto",
          "XSectionWidth:=", "%.6fmm" % wire_w, "XSectionTopWidth:=", "%.6fmm" % wire_w,
          "XSectionHeight:=", "%.6fmm" % wire_t, "XSectionNumSegments:=", "0",
          "XSectionBendType:=", "Corner"]],
        attrs(name))
    print("coil", name, "built")

build_coil("Tx1", TX1_X, 0.0)
build_coil("Tx2", TX2_X, 0.0)
build_coil("Rx", 0.0, GAP_Z)

# 3) Setup
try:
    dst.create_setup(name="Setup1", props={"Frequency": "85kHz", "MaximumPasses": 10, "PercentRefinement": 30})
    print("Setup1 created")
except Exception as e:
    print("setup err:", repr(e))

# 4) 引线
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
print("leads created:", lead_names)

# 5) 铁氧体条 + 开孔
ferr_names = []
for coil, (x0, x1) in COIL_X.items():
    if coil == "Rx":
        z_bot, z_top = 30.0 + Z_GAP, 30.0 + Z_GAP + THK
    else:
        z_bot, z_top = -Z_GAP - THK, -Z_GAP
    k, ycenters = 0, []
    while True:
        yc = k * (W + G)
        if yc - W / 2.0 > COIL_Y_HALF:
            break
        if k == 0:
            ycenters.append(0.0)
        else:
            ycenters.append(yc); ycenters.append(-yc)
        k += 1
    for yc in ycenters:
        idx = len([n for n in ferr_names if n.startswith("ferrite_" + coil)])
        name = "ferrite_%s_%d" % (coil, idx)
        try:
            box = dst.modeler.create_box(origin=[x0, yc - W / 2.0, z_bot],
                                         sizes=[x1 - x0, W, THK], name=name)
            box.material_name = "Ferrite"
            ferr_names.append(name)
        except Exception as e:
            print("ferrite err:", repr(e))
print("ferrite bars:", len(ferr_names))

# 开孔：引线穿过的铁氧体条
for ln in lead_names:
    coil = ln.split("_")[1]
    idx = 0 if ln.endswith("a") else 1
    lx, ly = ENDS[coil][idx]
    z0, h = LEAD_Z[coil]
    lz_lo, lz_hi = min(z0, z0 + h), max(z0, z0 + h)
    for fn in ferr_names:
        if not fn.startswith("ferrite_" + coil):
            continue
        try:
            bb = dst.modeler[fn].bounding_box
            fx_lo, fy_lo, fz_lo, fx_hi, fy_hi, fz_hi = bb[0], bb[1], bb[2], bb[3], bb[4], bb[5]
            if (fx_lo <= lx <= fx_hi) and (fy_lo <= ly <= fy_hi) and (fz_lo <= lz_hi and fz_hi >= lz_lo):
                dst.modeler.subtract(blank_list=[fn], tool_list=[ln], keep_originals=True)
                print("  hole:", ln, "->", fn)
        except Exception as e:
            print("subtract err:", repr(e))

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
