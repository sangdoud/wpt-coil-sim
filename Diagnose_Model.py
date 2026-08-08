# -*- coding: utf-8 -*-
# Dump all objects and their bounding boxes
oProject = oDesktop.GetActiveProject()
oDesign  = oProject.GetActiveDesign()
oEditor  = oDesign.SetActiveEditor("3D Modeler")

names = []
for g in ["Solids", "Sheets", "Lines", "Unclassified"]:
    try:
        names.extend(oEditor.GetObjectsInGroup(g))
    except Exception:
        pass

seen = set()
oDesktop.AddMessage("", "", 0, "--- Objects in model ---")
for n in names:
    if n in seen:
        continue
    seen.add(n)
    try:
        bb = oEditor.GetObjectBoundingBox(n)
        oDesktop.AddMessage("", "", 0, "%s : %s" % (n, list(bb)))
    except Exception:
        oDesktop.AddMessage("", "", 0, "%s : (no bbox)" % n)
oDesktop.AddMessage("", "", 0, "--- End ---")
