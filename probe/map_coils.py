# -*- coding: utf-8 -*-
"""解析 .aedt 里的 Polyline 对象（线圈），输出 bbox / 半径分布 / 首尾点。"""

import math
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\wpt\backup\Projecttonight.aedt"
print("模型:", P)

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    lines = f.readlines()

blocks = []
i = 0
while i < len(lines):
    if lines[i].strip() == "$begin 'PolylineParameters'":
        j = i
        while j < len(lines) and lines[j].strip() != "$end 'PolylineParameters'":
            j += 1
        # 往前找最近的 Name=
        name = "?"
        for k in range(i - 1, max(0, i - 400), -1):
            m = re.match(r"^\s*Name='([^']+)'\s*$", lines[k])
            if m:
                name = m.group(1)
                break
        blocks.append((name, i + 1, j + 1))
        i = j
    i += 1

print("找到 %d 个 Polyline 对象\n" % len(blocks))

for name, a, b in blocks:
    pts = []
    for k in range(a - 1, b):
        s = lines[k].strip()
        if s == "$begin 'PLPoint'":
            xs = lines[k + 1].split("'")[1]
            ys = lines[k + 2].split("'")[1]
            zs = lines[k + 3].split("'")[1]
            pts.append((float(xs.replace("mm", "")),
                        float(ys.replace("mm", "")),
                        float(zs.replace("mm", ""))))
    if not pts:
        print("%-10s 无点" % name)
        continue
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    rr = [math.hypot(p[0] - cx, p[1] - cy) for p in pts]
    print("=== %s ===  %d 点" % (name, len(pts)))
    print("  bbox X[%.2f, %.2f] Y[%.2f, %.2f] Z[%.3f, %.3f]"
          % (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)))
    print("  bbox 中心 (%.3f, %.3f)  半宽 %.2f x %.2f"
          % (cx, cy, (max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0))
    print("  到 bbox 中心半径: min %.2f  max %.2f" % (min(rr), max(rr)))
    print("  首点 %s" % (pts[0],))
    print("  末点 %s" % (pts[-1],))
    # 半径随索引的变化（抽样 12 个）
    n = len(pts)
    sample = [rr[int(k * (n - 1) / 11.0)] for k in range(12)]
    print("  r 抽样: " + " ".join("%.1f" % v for v in sample))
    print()
