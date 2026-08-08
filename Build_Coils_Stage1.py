# -*- coding: utf-8 -*-
# ================================================================
#  Stage 1: Build 3 SQUARE spiral coils with ROUNDED CORNERS
#  (square-like, four straight sides, arc corners)
#  Run in AEDT: Tools -> Run Script
# ================================================================
import math

oDesktop.AddMessage("", "", 0, "=== Stage 1: Rounded-square spiral coils ===")
oProject = oDesktop.GetActiveProject()
if oProject is None:
    oDesktop.AddMessage("", "", 0, "ERROR: no active project. Open project in AEDT first.")
    raise SystemExit("no active project")
oDesign = oProject.GetActiveDesign()
oEditor = oDesign.SetActiveEditor("3D Modeler")

# ================================================================
# Coil design parameters (ADJUSTABLE)
# ================================================================
S0     = 84.0    # outer half-side (mm) -> square ~168x168 (yesterday's size)
S_inner= 30.0    # inner half-side (mm) -> inner ~60mm
pitch  = 4.5     # effective turn pitch (mm) = (S0-S_inner)/turns
turns  = 12      # number of turns
Rc     = 15.0    # corner arc radius (mm)
wire_w = 3.0     # conductor width in plane (mm)
wire_t = 0.5     # conductor thickness Z (mm)
GAP_Z  = 30.0    # air gap Z (Tx plane to Rx plane) mm

TX1_X  = -86.0   # Tx1 center X (adjacent, ~1mm gap, no overlap)
TX2_X  =  86.0   # Tx2 center X

# ================================================================
# Delete old objects (robust re-run)
# ================================================================
old = ["coil_1","coil_2","coil_3","coil_1_Section1","coil_2_Section1","coil_3_Section1","Region"]
old += ["FerriteTx_%d"%i for i in range(9)] + ["FerriteRx_%d"%i for i in range(9)]
old += ["Tx1","Tx2","Rx"]
for pfx in ["Tx1","Tx2","Rx"]:
    for k in range(30):
        old.append("%s_seg_%d" % (pfx, k))
for nm in old:
    try:
        oEditor.Delete(["NAME:Selections","Selections:=",nm])
    except Exception:
        pass

# ================================================================
# Rounded-square spiral points (continuous inward/outward, no self-cross)
# ================================================================
def rs_spiral(S_inner, S0, pitch, turns, Rc, n_per_turn=64):
    pts=[]
    total=turns*n_per_turn
    for i in range(total):
        frac=i/float(total)
        S=S_inner+frac*(S0-S_inner)
        r=min(Rc, S*0.8)
        p=(i%n_per_turn)/float(n_per_turn)
        if p<1/8.0:                       # right straight: x=S, y -S+r .. S-r
            t=p*8; pts.append((S, -S+r+(2*S-2*r)*t))
        elif p<2/8.0:                     # top-right arc, center(S-r,S-r), a 0..pi/2
            t=p*8-1; a=(math.pi/2)*t
            pts.append((S-r+r*math.cos(a), S-r+r*math.sin(a)))
        elif p<3/8.0:                     # top straight: y=S, x S-r .. -S+r
            t=p*8-2; pts.append((S-r-(2*S-2*r)*t, S))
        elif p<4/8.0:                     # top-left arc, center(-S+r,S-r), a pi/2..pi
            t=p*8-3; a=math.pi/2+(math.pi/2)*t
            pts.append((-S+r+r*math.cos(a), S-r+r*math.sin(a)))
        elif p<5/8.0:                     # left straight: x=-S, y S-r .. -S+r
            t=p*8-4; pts.append((-S, S-r-(2*S-2*r)*t))
        elif p<6/8.0:                     # bottom-left arc, center(-S+r,-S+r), a pi..3pi/2
            t=p*8-5; a=math.pi+(math.pi/2)*t
            pts.append((-S+r+r*math.cos(a), -S+r+r*math.sin(a)))
        elif p<7/8.0:                     # bottom straight: y=-S, x -S+r .. S-r
            t=p*8-6; pts.append((-S+r+(2*S-2*r)*t, -S))
        else:                             # bottom-right arc, center(S-r,-S+r), a 3pi/2..2pi
            t=p*8-7; a=3*math.pi/2+(math.pi/2)*t
            pts.append((S-r+r*math.cos(a), -S+r+r*math.sin(a)))
    return pts

def attrs(nm):
    return ["NAME:Attributes","Name:=",nm,"Flags:=","","Color:=","(143 175 143)","Transparency:=",0,
            "PartCoordinateSystem:=","Global","UDMId:=","","MaterialValue:=","\"copper\"",
            "SurfaceMaterialValue:=","\"\"","SolveInside:=",True,"ShellElement:=",False,
            "ShellElementThickness:=","0mm","ReferenceTemperature:=","20cel",
            "IsMaterialEditable:=",True,"UseMaterialAppearance:=",False,"IsLightweight:=",False]

def build_coil(name, Xc, Zc):
    pts = rs_spiral(S_inner, S0, pitch, turns, Rc)
    pl_pts = [["NAME:PLPoint","X:=","%.6fmm"%(Xc+x),"Y:=","%.6fmm"%(y),"Z:=","%.6fmm"%Zc]
              for (x,y) in pts]
    pl_seg = [["NAME:PLSegment","SegmentType:=","Line","StartIndex:=",i,"NoOfPoints:=",2]
              for i in range(len(pts)-1)]
    oEditor.CreatePolyline(
        ["NAME:PolylineParameters","IsPolylineCovered:=",False,"IsPolylineClosed:=",False,
         ["NAME:PolylinePoints"]+pl_pts,
         ["NAME:PolylineSegments"]+pl_seg,
         ["NAME:PolylineXSection","XSectionType:=","Rectangle","XSectionOrient:=","Auto",
          "XSectionWidth:=","%.6fmm"%wire_w,    # in-plane width (3mm)
          "XSectionTopWidth:=","%.6fmm"%wire_w,
          "XSectionHeight:=","%.6fmm"%wire_t,   # Z thickness (0.5mm) -> FLAT
          "XSectionNumSegments:=","0","XSectionBendType:=","Corner"]],
        attrs(name))
    oDesktop.AddMessage("", "", 0, "coil %s built" % name)

# ================================================================
# Build Tx1 (left), Tx2 (right), Rx (center, above)
# ================================================================
build_coil("Tx1", TX1_X, 0.0)
build_coil("Tx2", TX2_X, 0.0)
build_coil("Rx",  0.0,   GAP_Z)

oDesktop.AddMessage("", "", 0, "=== Stage 1 done: Tx1, Tx2, Rx (rounded-square spiral) ===")
