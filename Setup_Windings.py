# -*- coding: utf-8 -*-
# Setup coil windings - tries multiple GetFaceByPosition formats + dense search
import math

LOG = r"C:\Users\lenovo\Desktop\zidong\winding_log.txt"
_log = open(LOG, "w")
def msg(s):
    _log.write(s + "\n"); _log.flush()
    try: oDesktop.AddMessage("", "", 0, s)
    except Exception: pass

msg("=== Setup windings ===")
try:
    oProject = oDesktop.GetActiveProject()
    if oProject is None: raise SystemExit("no active project")
    oDesign = oProject.GetActiveDesign()
    oEditor = oDesign.SetActiveEditor("3D Modeler")
    oModule = oDesign.GetModule("BoundarySetup")
except Exception as e:
    msg("Connect failed: %s" % e); _log.close(); raise

TURNS = 12
S0, S_INNER, RC = 84.0, 30.0, 15.0

def rs_spiral(S_inner, S0, turns, Rc, n_per_turn=64):
    pts=[]; total=turns*n_per_turn
    for i in range(total):
        frac=i/float(total); S=S_inner+frac*(S0-S_inner); r=min(Rc, S*0.8)
        p=(i%n_per_turn)/float(n_per_turn)
        if p<1/8.0:    t=p*8; pts.append((S, -S+r+(2*S-2*r)*t))
        elif p<2/8.0:  t=p*8-1; a=(math.pi/2)*t; pts.append((S-r+r*math.cos(a), S-r+r*math.sin(a)))
        elif p<3/8.0:  t=p*8-2; pts.append((S-r-(2*S-2*r)*t, S))
        elif p<4/8.0:  t=p*8-3; a=math.pi/2+(math.pi/2)*t; pts.append((-S+r+r*math.cos(a), S-r+r*math.sin(a)))
        elif p<5/8.0:  t=p*8-4; pts.append((-S, S-r-(2*S-2*r)*t))
        elif p<6/8.0:  t=p*8-5; a=math.pi+(math.pi/2)*t; pts.append((-S+r+r*math.cos(a), -S+r+r*math.sin(a)))
        elif p<7/8.0:  t=p*8-6; pts.append((-S+r+(2*S-2*r)*t, -S))
        else:          t=p*8-7; a=3*math.pi/2+(math.pi/2)*t; pts.append((S-r+r*math.cos(a), -S+r+r*math.sin(a)))
    return pts

pts = rs_spiral(S_INNER, S0, TURNS, RC)
sx, sy = pts[0]; ex, ey = pts[-1]
msg("spiral start (%.3f,%.3f) end (%.3f,%.3f)" % (sx,sy,ex,ey))

def get_face(x, y, z):
    formats = [
        (["X:=", x, "Y:=", y, "Z:=", z], "numeric"),
        (["X:=", "%.6fmm"%x, "Y:=", "%.6fmm"%y, "Z:=", "%.6fmm"%z], "string"),
        ([x, y, z], "plain"),
    ]
    for args, tag in formats:
        try:
            fid = oEditor.GetFaceByPosition(args)
            return int(fid), tag
        except Exception:
            continue
    return None, "none"

def find_face_near(cx, cy, cz):
    # coarse then fine search
    for dx in [-4,-2,0,2,4]:
        for dy in [-4,-2,0,2,4]:
            for dz in [-0.3,0,0.3]:
                fid, tag = get_face(cx+dx, cy+dy, cz+dz)
                if fid is not None:
                    msg("  found face %s near (%.1f,%.1f,%.1f) [%s]" % (fid, cx+dx,cy+dy,cz+dz, tag))
                    return fid
    return None

# also test on a known coil body point: use bounding box top surface near left edge
try:
    bb = [float(v) for v in oEditor.GetObjectBoundingBox("Tx1")]
    test_pt = ((bb[0]+bb[3])/2, (bb[1]+bb[4])/2, bb[5]-0.05)
    fid, tag = get_face(*test_pt)
    msg("GetFaceByPosition test on coil body center-top: face=%s tag=%s at (%.1f,%.1f,%.1f)" % (fid, tag, test_pt[0],test_pt[1],test_pt[2]))
except Exception as e:
    msg("bbox test failed: %s" % e)

coils = [("Tx1", -86.0, 0.0), ("Tx2", 86.0, 0.0), ("Rx", 0.0, 30.0)]
winding_names = ["Coil1", "Coil2", "Coil3"]
for (coil, Xc, Zc), wname in zip(coils, winding_names):
    msg("=== %s -> %s ===" % (coil, wname))
    f_start = find_face_near(Xc+sx, sy, Zc)
    f_end   = find_face_near(Xc+ex, ey, Zc)
    msg("%s start face=%s end face=%s" % (coil, f_start, f_end))
    if f_start is None or f_end is None:
        msg("  skipping (faces not found)")
        continue
    try:
        oModule.AddWinding(["NAME:%s"%wname,"Type:=","Coil","IsSolid:=",False,"Current:=","1A",
            "Resistance:=","0ohm","Inductance:=","0H","Voltage:=","0V",
            "ParallelBranches:=","1","SeriesBranches:=","1","Turns:=","%d"%TURNS,
            "IsTurnsPerBranch:=",True,"BranchDirection:=","Positive","SymmetryFactor:=","1"])
        msg("Winding %s created" % wname)
    except Exception as e:
        msg("AddWinding %s FAILED: %s" % (wname, e))
    for pol, fid in [("Positive", f_start), ("Negative", f_end)]:
        try:
            oModule.AssignCoil(["NAME:%s_%s"%(wname,pol),"Objects:=",[coil],"Faces:=",[fid],
                "Winding:=",wname,"Polarity:=",pol,"Resistance:=","0ohm","Inductance:=","0H",
                "IsTurnsPerBranch:=",True,"Turns:=","%d"%TURNS,"BranchDirection:=","Positive"])
            msg("Terminal %s %s face %s OK" % (wname, pol, fid))
        except Exception as e:
            msg("AssignCoil %s %s FAILED: %s" % (wname, pol, e))

msg("=== Winding setup done ===")
_log.close()
