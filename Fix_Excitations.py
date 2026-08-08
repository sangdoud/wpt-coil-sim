# -*- coding: utf-8 -*-
# Verify and fix the 3 current excitations
oProject = oDesktop.GetActiveProject()
oDesign  = oProject.GetActiveDesign()
oModule  = oDesign.GetModule("BoundarySetup")

try:
    ex = oModule.GetExcitations()
    oDesktop.AddMessage("", "", 0, "Current excitations: %s" % str(ex))
except Exception as e:
    oDesktop.AddMessage("", "", 0, "GetExcitations failed: %s" % e)

# Ensure all three exist
for name, obj in [("Current1", "coil_1_Section1"),
                  ("Current2", "coil_2_Section1"),
                  ("Current3", "coil_3_Section1")]:
    try:
        ex = oModule.GetExcitations()
        if name in ex:
            oDesktop.AddMessage("", "", 0, "%s exists" % name)
        else:
            oModule.AssignCurrent(["NAME:%s" % name,
                                   "Objects:=", [obj],
                                   "Current:=", "1A",
                                   "IsSolid:=", False,
                                   "Point out of terminal:=", False])
            oDesktop.AddMessage("", "", 0, "%s reassigned" % name)
    except Exception as e:
        oDesktop.AddMessage("", "", 0, "%s check failed: %s" % (name, e))
