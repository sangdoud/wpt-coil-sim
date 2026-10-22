# -*- coding: utf-8 -*-
"""从 Projecttonight.aedt 的活动设计(WPT_G)里抽出 Tx1/Tx2/Rx 三个线圈的路径点，
存成 JSON 供重建脚本使用；顺便算路径长度 -> 预测改线宽后的体积。"""

import json
import math
import re
import sys

P = r"C:\wpt\Projecttonight.aedt"
OUT = r"C:\ansys maxwell2024\_work\coil_paths.json"

TARGET = {297717: "Tx1", 397567: "Tx2", 497229: "Rx"}

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    lines = f.readlines()

n = len(lines)
res = {}

for ln0, nm in TARGET.items():
    i = ln0 - 1
    pts = []
    j = i
    inpts = False
    while j < n and lines[j].strip() != "$end 'Operation'":
        s = lines[j].strip()
        if s == "$begin 'PolylinePoints'":
            inpts = True
        elif s == "$end 'PolylinePoints'":
            inpts = False
        elif inpts and s == "$begin 'PLPoint'":
            x = float(lines[j + 1].split("'")[1].replace("mm", ""))
            y = float(lines[j + 2].split("'")[1].replace("mm", ""))
            z = float(lines[j + 3].split("'")[1].replace("mm", ""))
            pts.append([x, y, z])
        j += 1

    L = 0.0
    for a in range(1, len(pts)):
        L += math.dist(pts[a], pts[a - 1])

    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    res[nm] = pts
    print("%-4s 点数=%d  路径长=%.4f mm" % (nm, len(pts), L))
    print("     路径 bbox X[%.4f, %.4f] Y[%.4f, %.4f] Z[%.4f, %.4f]"
          % (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    print("     路径中心 (%.4f, %.4f, %.4f)" % ((min(xs) + max(xs)) / 2,
                                                (min(ys) + max(ys)) / 2,
                                                (min(zs) + max(zs)) / 2))
    print("     首点 %s  尾点 %s" % (pts[0], pts[-1]))
    # 预测铜带体积（Corner 弯折 = 长度 x 宽 x 厚）
    for w in (3.0, 2.0):
        print("     预测铜带体积(宽%.0fmm, 厚0.5mm) = %.4f mm^3" % (w, L * w * 0.5))
    print("     两宽度体积差 = %.4f mm^3" % (L * 0.5 * 1.0))

import os
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(res, f)
print("\n已写出: %s  (%.1f KB)" % (OUT, os.path.getsize(OUT) / 1024))
