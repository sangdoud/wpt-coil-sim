# -*- coding: utf-8 -*-
# ================================================================
#  Part 2: Optimetrics parametric sweep + solve + export L table
#  Prerequisite: Part 1 (geometry) done, variables exist
#  TEST_MODE: True  -> quick test (27 combos, fast)
#             False -> full 1331 combos (many hours, run overnight)
# ================================================================
import csv

TEST_MODE = True   # <-- change to False for the full run

if TEST_MODE:
    spacings = [0, 10, 20]
    fws = [10, 15, 20]
    gws = [10, 15, 20]
else:
    spacings = list(range(-50, 51, 10))
    fws = list(range(10, 21))
    gws = list(range(10, 21))

def data_str(vals, unit):
    return " ".join("%d%s" % (v, unit) for v in vals)

oDesktop.AddMessage("", "", 0,
    "=== Part 2: Parametric Sweep [%s] %d combos ===" %
    ("TEST" if TEST_MODE else "FULL",
     len(spacings) * len(fws) * len(gws)))

oProject = oDesktop.GetActiveProject()
oDesign  = oProject.GetActiveDesign()
oEditor  = oDesign.SetActiveEditor("3D Modeler")

# ---------------------------------------------------------------
# 1. Create Optimetrics parametric setup
# ---------------------------------------------------------------
oMod = oDesign.GetModule("Optimetrics")

try:
    oMod.DeleteSetups(["ParametricSetup1"])
except Exception:
    pass

oMod.InsertSetup("OptiParametric", [
    "NAME:ParametricSetup1",
    "IsEnabled:=", True,
    ["NAME:ProdOptiSetupDataV2",
     "SaveFields:=", False,
     "CopyMesh:=", False,
     "SolveWithCopiedMeshOnly:=", False],
    "Sim. File Name:=", "",
    ["NAME:Goals"],
    "Unit:=", "",
    "IntrinsicVar:=", "",
    ["NAME:StartingPoint"],
    ["NAME:Sweeps",
        ["NAME:SweepDefinition", "Variable:=", "spacing",
         "Data:=", data_str(spacings, "mm"),
         "OffsetF1:=", False, "Synchronize:=", 0, "SweepOperations:=", []],
        ["NAME:SweepDefinition", "Variable:=", "fw",
         "Data:=", data_str(fws, "mm"),
         "OffsetF1:=", False, "Synchronize:=", 0, "SweepOperations:=", []],
        ["NAME:SweepDefinition", "Variable:=", "gw",
         "Data:=", data_str(gws, "mm"),
         "OffsetF1:=", False, "Synchronize:=", 0, "SweepOperations:=", []]
    ]
])
oDesktop.AddMessage("", "", 0, "ParametricSetup1 created")

# ---------------------------------------------------------------
# 2. Solve
# ---------------------------------------------------------------
oDesktop.AddMessage("", "", 0, "Solving %d cases, please wait..." %
                    (len(spacings) * len(fws) * len(gws)))
oMod.SolveSetup("ParametricSetup1")
oDesktop.AddMessage("", "", 0, "=== Parametric solve done ===")

# ---------------------------------------------------------------
# 3. Extract inductance matrix per variation -> CSV
# ---------------------------------------------------------------
oModSol = oDesign.GetModule("Solutions")

out_csv = r"C:\Users\lenovo\Desktop\L_Table.csv"
n_ok = 0
n_err = 0

with open(out_csv, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["spacing_mm", "fw_mm", "gw_mm", "L11", "L12", "L13", "L22", "L23", "L33"])
    for sp in spacings:
        for fwv in fws:
            for gwv in gws:
                var = ["spacing:={}mm".format(sp),
                       "fw:={}mm".format(fwv),
                       "gw:={}mm".format(gwv)]
                try:
                    sol = oModSol.GetSolutionDataPerVariation(
                        "Setup1 : LastAdaptive", var, ["Inductance"])
                    val = sol[0].Value   # 3x3 matrix
                    w.writerow([sp, fwv, gwv,
                                val[0][0], val[0][1], val[0][2],
                                val[1][1], val[1][2], val[2][2]])
                    n_ok += 1
                except Exception as e:
                    w.writerow([sp, fwv, gwv,
                                "ERR", "ERR", "ERR", "ERR", "ERR", "ERR"])
                    n_err += 1
                    oDesktop.AddMessage("", "", 0,
                        "Read fail sp=%d fw=%d gw=%d: %s" % (sp, fwv, gwv, e))

oDesktop.AddMessage("", "", 0,
    "Table written: %s (ok %d, fail %d)" % (out_csv, n_ok, n_err))
print("DONE: %s" % out_csv)
