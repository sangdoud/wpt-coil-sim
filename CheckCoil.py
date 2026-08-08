# -*- coding: utf-8 -*-
# Minimal check: report only Z thickness and ranges of the 3 coils
oProject = oDesktop.GetActiveProject()
oDesign  = oProject.GetActiveDesign()
oEditor  = oDesign.SetActiveEditor("3D Modeler")

for n in ["Tx1", "Tx2", "Rx"]:
    try:
        bb = [float(x) for x in oEditor.GetObjectBoundingBox(n)]
        msg = "%s: X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f] -> Z thickness=%.2fmm" % (
            n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5], bb[5]-bb[2])
        oDesktop.AddMessage("", "", 0, msg)
        print(msg)
    except Exception as e:
        oDesktop.AddMessage("", "", 0, "%s ERR: %s" % (n, e))
