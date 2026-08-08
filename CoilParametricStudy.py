# -*- coding: utf-8 -*-
# ================================================================
#  3-coil WPT system - Parametric study (Part 1: Geometry)
#  Run in AEDT: Tools -> Run Script -> select this file
#  PREREQUISITE: create 5 design variables MANUALLY in AEDT GUI:
#    Project -> Properties -> Design Variables tab -> Add:
#      spacing = 0mm, fw = 15mm, gw = 15mm, gh = 30mm, ft = 10mm
# ================================================================
import math
import csv

oDesktop.AddMessage("", "", 0, "=== Parametric Study Part 1: Geometry ===")

oProject = oDesktop.GetActiveProject()
oDesign  = oProject.GetActiveDesign()
oEditor  = oDesign.SetActiveEditor("3D Modeler")

# ---------------------------------------------------------------
# 2. Query coil geometry (bounding box returns strings -> float)
# ---------------------------------------------------------------
bb1 = [float(x) for x in oEditor.GetObjectBoundingBox("coil_1")]
bb2 = [float(x) for x in oEditor.GetObjectBoundingBox("coil_2")]

xc     = (bb1[0] + bb1[3]) / 2.0   # coil X center
yMin   = bb1[1]                    # coil Y min
yMax   = bb1[4]                    # coil Y max
lenY   = yMax - yMin               # coil Y full length (ferrite strip length)
spanX  = bb1[3] - bb1[0]           # coil X span
z_tx_top = bb2[2]                  # Tx coil (coil_2) bottom Z
h3     = bb1[5] - bb1[2]           # coil height

oDesktop.AddMessage("", "", 0,
    "Coil: Xc=%.3fmm LenY=%.3fmm SpanX=%.3fmm" % (xc, lenY, spanX))

# ---------------------------------------------------------------
# 3. Rebuild coil_3 (Z = gh + spacing) + recreate excitation
# ---------------------------------------------------------------
oModule = oDesign.GetModule("BoundarySetup")

# 3.0 delete old excitation Current3 if exists
try:
    oModule.DeleteExcitations(["Current3"])
    oDesktop.AddMessage("", "", 0, "Old excitation Current3 deleted")
except Exception:
    pass

# 3.1 delete old coil_3 and its section if exist
try:
    oEditor.Delete(["NAME:Selections", "Selections:=", "coil_3,coil_3_Section1"])
    oDesktop.AddMessage("", "", 0, "Old coil_3 / coil_3_Section1 deleted")
except Exception:
    pass

# 3.2 duplicate coil_1 along Z by gh+spacing -> new coil_3
oEditor.DuplicateAlongLine(
    ["NAME:Selections", "Selections:=", "coil_1", "NewPartsModelFlag:=", "Model"],
    ["NAME:DuplicateToAlongLineParameters", "CreateNewObjects:=", True,
     "XComponent:=", "0mm", "YComponent:=", "0mm", "ZComponent:=", "gh + spacing",
     "NumClones:=", "2"],
    ["NAME:Options", "DuplicateAssignments:=", True],
    ["CreateGroupsForNewObjects:=", False])

# 3.3 rename new body -> coil_3 (try several auto names)
renamed = False
for cand in ["coil_1_1", "coil_1_2", "coil_1_3", "coil_1_4", "coil_1_5"]:
    try:
        oEditor.ChangeProperty(["NAME:AllTabs",
            ["NAME:Geometry3DAttributeTab",
                ["NAME:PropServers", cand],
                ["NAME:ChangedProps",
                    ["NAME:Name", "Value:=", "coil_3"]]]])
        oDesktop.AddMessage("", "", 0, "coil_3 rebuilt (%s -> coil_3)" % cand)
        renamed = True
        break
    except Exception:
        continue
if not renamed:
    oDesktop.AddMessage("", "", 0,
        "WARNING: rename failed, manually rename new coil to coil_3")

# 3.4 section + separate + delete leftovers, keep coil_3_Section1
oEditor.Section(
    ["NAME:Selections", "Selections:=", "coil_3", "NewPartsModelFlag:=", "Model"],
    ["NAME:SectionToParameters", "CreateNewObjects:=", True,
     "SectionPlane:=", "YZ", "SectionCrossObject:=", False])

oEditor.SeparateBody(
    ["NAME:Selections", "Selections:=", "coil_3_Section1", "NewPartsModelFlag:=", "Model"],
    ["CreateGroupsForNewObjects:=", False])

sep_names = ",".join(["coil_3_Section1_Separate%d" % i for i in range(1, 24)])
try:
    oEditor.Delete(["NAME:Selections", "Selections:=", sep_names])
except Exception:
    pass

# 3.5 reassign excitation Current3
oModule.AssignCurrent(
    ["NAME:Current3",
     "Objects:=", ["coil_3_Section1"],
     "Current:=", "1A",
     "IsSolid:=", False,
     "Point out of terminal:=", False])
oDesktop.AddMessage("", "", 0, "Excitation Current3 reassigned")

# ---------------------------------------------------------------
# 4. Ferrite material (mu_r=1000, adjustable)
# ---------------------------------------------------------------
def ensure_ferrite_material():
    dm = oProject.GetDefinitionManager()
    try:
        dm.GetMaterial("Ferrite_mu1000")
        oDesktop.AddMessage("", "", 0, "Material Ferrite_mu1000 exists")
        return
    except Exception:
        pass
    try:
        dm.AddMaterial(["NAME:Ferrite_mu1000",
            "CoordinateSystemType:=", "Cartesian",
            ["NAME:AttachedData"],
            "permeability:=", "1000",
            "conductivity:=", "0",
            "permittivity:=", "1",
            "dielectric_loss_tangent:=", "0",
            "magnetic_loss_tangent:=", "0"])
        oDesktop.AddMessage("", "", 0, "Material Ferrite_mu1000 created (mu_r=1000)")
    except Exception as e:
        oDesktop.AddMessage("", "", 0, "Material creation failed: %s" % e)

ensure_ferrite_material()

# ---------------------------------------------------------------
# 5. Ferrite array (strips along X, N=9 per side)
# ---------------------------------------------------------------
try:
    old_fer = ",".join(["FerriteTx_%d" % i for i in range(9)] +
                       ["FerriteRx_%d" % i for i in range(9)])
    oEditor.Delete(["NAME:Selections", "Selections:=", old_fer])
except Exception:
    pass

N = 7   # 7 strips: just covers coil at nominal fw=gw=15mm (7*15+6*15=195mm)

def make_attrs(name):
    return ["NAME:Attributes", "Name:=", name, "Flags:=", "",
            "Color:=", "(143 175 143)", "Transparency:=", 0,
            "PartCoordinateSystem:=", "Global", "UDMId:=", "",
            "MaterialValue:=", "\"vacuum\"", "SurfaceMaterialValue:=", "\"\"",
            "SolveInside:=", True, "ShellElement:=", False,
            "ShellElementThickness:=", "0mm", "ReferenceTemperature:=", "20cel",
            "IsMaterialEditable:=", True, "UseMaterialAppearance:=", False,
            "IsLightweight:=", False]

# Tx ferrite: top face flush with coil_2 bottom (Z = z_tx_top - ft .. z_tx_top)
z_tx_bottom = "%.6fmm - ft" % z_tx_top
# Rx ferrite: bottom face flush with coil_3 top (Z = gh+spacing+h3 .. +ft)
z_rx_bottom = "gh + spacing + %.6fmm" % h3

for i in range(N):
    x_left = "%.6fmm - (7*fw + 6*gw)/2 + %d*(fw+gw)" % (xc, i)

    oEditor.CreateBox(
        ["NAME:BoxParameters",
         "XPosition:=", x_left,
         "YPosition:=", "%.6fmm" % yMin,
         "ZPosition:=", z_tx_bottom,
         "XSize:=", "fw",
         "YSize:=", "%.6fmm" % lenY,
         "ZSize:=", "ft"],
        make_attrs("FerriteTx_%d" % i))

    oEditor.CreateBox(
        ["NAME:BoxParameters",
         "XPosition:=", x_left,
         "YPosition:=", "%.6fmm" % yMin,
         "ZPosition:=", z_rx_bottom,
         "XSize:=", "fw",
         "YSize:=", "%.6fmm" % lenY,
         "ZSize:=", "ft"],
        make_attrs("FerriteRx_%d" % i))

oDesktop.AddMessage("", "", 0, "Ferrite arrays created: %d strips per side" % N)

tx_names = ",".join("FerriteTx_%d" % i for i in range(N))
rx_names = ",".join("FerriteRx_%d" % i for i in range(N))
for names in (tx_names, rx_names):
    oEditor.AssignMaterial(
        ["NAME:Selections", "Selections:=", names, "NewPartsModelFlag:=", "Model"],
        ["NAME:Attributes", "MaterialValue:=", "\"Ferrite_mu1000\"",
         "SolveInside:=", True, "ShellElement:=", False,
         "ShellElementThickness:=", "nan ", "ReferenceTemperature:=", "nan ",
         "IsMaterialEditable:=", True, "UseMaterialAppearance:=", False,
         "IsLightweight:=", False])

oDesktop.AddMessage("", "", 0, "Ferrite material assigned")
oDesktop.AddMessage("", "", 0, "=== Part 1 done. Check geometry in AEDT ===")
