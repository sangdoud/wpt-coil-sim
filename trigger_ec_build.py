import math, csv, time
from ansys.aedt.core import Desktop, Maxwell3d
from ansys.aedt.core.modules.boundary.maxwell_boundary import MatrixACMagnetic, SourceACMagnetic

DESIGN = "WPT_G"
W, G, THK, Z_GAP = 15.0, 15.0, 10.0, 30.0
X_OFFSET = 0.0
RAD = 0.3
LEAD_Z = {"Tx1": (-45.0, 45.0), "Tx2": (-45.0, 45.0), "Rx": (30.0, 45.0)}
ENDS = {
    "Tx1": [(-56.0, -15.0), (-2.36, -71.87)],
    "Tx2": [(116.0, -15.0), (169.64, -71.87)],
    "Rx":  [(30.0, -15.0), (83.64, -71.87)],
}
FERR_GROUPS = {"Tx": (-170.0, 171.0), "Rx": (-84.0, 85.0)}
LEAD_GROUP = {"Tx1": "Tx", "Tx2": "Tx", "Rx": "Rx"}
COIL_Y_LO, COIL_Y_HI = -84.0, 84.0
S0, S_inner, pitch, turns, Rc, wire_w, wire_t = 84.0, 30.0, 4.5, 12, 15.0, 3.0, 0.5
TX1_X, TX2_X, GAP_Z = -86.0, 86.0, 30.0
HOLE_RAD = 0.5

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)

# 0) 停止任何运行中的求解 + 删除旧设计
try:
    d.odesktop.StopSimulations(True)
except Exception as e:
    print("stop sim err:", repr(e))
try:
    m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")
    try:
        m3d._oproject.DeleteDesign(DESIGN)
        print("deleted old", DESIGN)
    except Exception:
        pass
except Exception as e:
    print("del err:", repr(e))

# 1) 创建新设计
dst = Maxwell3d(project="Project3", design=DESIGN, solution_type="EddyCurrent")
oEditor = dst.odesign.SetActiveEditor("3D Modeler")
print("design created:", DESIGN)

# 2) 线圈
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

# 3) 引线
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

# 4) 铁氧体
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
            box.material_name = "ferrite"
            ferr_names.append(name)
        except Exception as e:
            print("ferrite err:", repr(e))
print("ferrite bars:", len(ferr_names))

# 5) 开孔（辅助圆柱留间隙）
for ln in lead_names:
    coil = ln.split("_")[1]
    group = LEAD_GROUP[coil]
    idx = 0 if ln.endswith("a") else 1
    lx, ly = ENDS[coil][idx]
    z0, h = LEAD_Z[coil]
    lz_lo, lz_hi = min(z0, z0 + h), max(z0, z0 + h)
    aux = None
    try:
        aux = dst.modeler.create_cylinder(orientation="Z", origin=[lx, ly, lz_lo],
                                          radius=HOLE_RAD, height=lz_hi - lz_lo, name="aux_hole")
    except Exception as e:
        print("aux err:", repr(e))
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
    if aux is not None:
        try:
            if aux.name in dst.modeler.object_names:
                dst.modeler.delete(aux.name)
        except Exception:
            pass

# 6) Unite
for coil in ["Tx1", "Tx2", "Rx"]:
    parts = [coil] + [n for n in dst.modeler.object_names if n.startswith("lead_" + coil)]
    if len(parts) > 1:
        dst.modeler.unite(parts, keep_originals=False)
print("united")

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

# 8) 激励（10A）
try:
    dst.oboundary.DeleteAllExcitations()
except Exception as e:
    print("clear exc err:", repr(e))
ZTERM = {"Tx1": -45.0, "Tx2": -45.0, "Rx": 75.0}
AREA = 3.14159 * 0.3 * 0.3
term_faces = {}
for cname, zt in ZTERM.items():
    obj = dst.modeler[cname]
    hits = []
    for f in obj.faces:
        c = list(f.center)
        area = getattr(f, "area", None)
        if area is None:
            continue
        if abs(c[2] - zt) < 0.5 and abs(area - AREA) < AREA * 0.3:
            hits.append((f.id, abs(area - AREA)))
    hits.sort(key=lambda x: x[1])
    term_faces[cname] = [h[0] for h in hits[:2]]
    print(cname, "term faces:", term_faces[cname])
winding_names = []
for cname, (f1, f2) in term_faces.items():
    wname = "Winding_%s" % cname
    try:
        dst.assign_winding(assignment=None, winding_type="Current", is_solid=False, current=10, name=wname)
        c1 = dst.assign_coil(assignment=[f1], conductors_number=12, polarity="Positive", name="CT_%s_P" % cname)
        c2 = dst.assign_coil(assignment=[f2], conductors_number=12, polarity="Negative", name="CT_%s_N" % cname)
        dst.add_winding_coils(wname, [c1.name, c2.name])
        winding_names.append(wname)
    except Exception as e:
        print(wname, "err:", repr(e))
if len(winding_names) == 3:
    try:
        dst.assign_matrix(MatrixACMagnetic(
            signal_sources=[SourceACMagnetic(name=w) for w in winding_names],
            matrix_name="Lmatrix"))
        print("MATRIX ASSIGNED")
    except Exception as e:
        print("matrix err:", repr(e))

# 9) 求解
print("solving...")
try:
    dst.analyze(cores=4, run_in_thread=True)
    print("ANALYZE DONE")
except Exception as e:
    print("ANALYZE ERR:", repr(e))
try:
    for s in dst.setups:
        print("setup", s.name, "solved:", s.is_solved)
except Exception as e:
    print("setup check err:", repr(e))

# 10) 提取矩阵
try:
    w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
    data = dst.post.get_solution_data(
        expressions=["L(%s,%s)" % (wi, wj) for wi in w for wj in w],
        setup_sweep_name="Setup1 : LastAdaptive",
        context={"Lmatrix": ""},
        primary_sweep_variable="Freq",
    )
    real, _ = data.full_matrix_real_imag
    names = {"Winding_Tx1": "Tx1", "Winding_Tx2": "Tx2", "Winding_Rx": "Rx"}
    out = r"C:/Users/lenovo/Desktop/zidong/Lmatrix_%s.csv" % DESIGN
    with open(out, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["L (uH)", "Tx1", "Tx2", "Rx"])
        print("=== L matrix (uH) %s ===" % DESIGN)
        for wi in w:
            row = [real["L(%s,%s)" % (wi, wj)][0][1] / 1000.0 for wj in w]
            wr.writerow([names[wi]] + ["%.3f" % v for v in row])
            print("  %s: %s" % (names[wi], ["%.2f" % v for v in row]))
    print("saved:", out)
except Exception as e:
    print("extract err:", repr(e))
