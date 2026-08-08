# -*- coding: utf-8 -*-
# Quick validation: single solve to confirm model is OK before Part 2
oProject = oDesktop.GetActiveProject()
oDesign  = oProject.GetActiveDesign()
oDesktop.AddMessage("", "", 0, "Design: %s" % oDesign.GetName())

try:
    oDesign.Analyze("Setup1")
    oDesktop.AddMessage("", "", 0, "SINGLE SOLVE OK - model is valid")
except Exception as e:
    oDesktop.AddMessage("", "", 0, "SOLVE FAILED: %s" % e)
