# -*- coding: utf-8 -*-
"""确定线圈螺旋中心、r 单调性、以及首尾是否为引出段。"""

import math
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\wpt\backup\Projecttonight.aedt"
NAME = sys.argv[2] if len(sys.argv) > 2 else "Tx1"

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    lines = f.readlines()

# 找第一个名为 NAME 的 Polyline
start = None
i = 0
while i < len(lines):
    if lines[i].strip() == "$begin 'PolylineParameters'":
        nm = "?"
        for k in range(i - 1, max(0, i - 400), -1):
            m = re.match(r"^\s*Name='([^']+)'\s*$", lines[k])
            if m:
                nm = m.group(1)
                break
        if nm == NAME:
            start = i
            break
    i += 1
if start is None:
    raise SystemExit("找不到 " + NAME)

pts = []
k = start
while lines[k].strip() != "$end 'PolylineParameters'":
    if lines[k].strip() == "$begin 'PLPoint'":
        pts.append((float(lines[k + 1].split("'")[1].replace("mm", "")),
                    float(lines[k + 2].split("'")[1].replace("mm", "")),
                    float(lines[k + 3].split("'")[1].replace("mm", ""))))
    k += 1

n = len(pts)
cxs = sum(p[0] for p in pts) / n
cys = sum(p[1] for p in pts) / n
print("%s: %d 点, 质心 (%.3f, %.3f)" % (NAME, n, cxs, cys))

rr = [math.hypot(p[0] - cxs, p[1] - cys) for p in pts]
print("  相对质心 r: min %.2f max %.2f" % (min(rr), max(rr)))

# r 单调性（允许小回落）
bad = 0
for a in range(1, n):
    if rr[a] < rr[a - 1] - 0.05:
        bad += 1
print("  r 回落次数 (>0.05mm): %d / %d" % (bad, n - 1))

# 每 1/12 个索引抽样
print("  每 64 点一个 r:", " ".join("%.1f" % rr[i] for i in range(0, n, 64)))

print("\n  前 10 点:")
for i in range(10):
    print("    %3d  (%9.4f, %9.4f, %6.2f)  r=%7.3f" % (i, pts[i][0], pts[i][1], pts[i][2], rr[i]))
print("  后 10 点:")
for i in range(n - 10, n):
    print("    %3d  (%9.4f, %9.4f, %6.2f)  r=%7.3f" % (i, pts[i][0], pts[i][1], pts[i][2], rr[i]))

# 外接：所有点到质心的最大 r 对应的点
mi = rr.index(max(rr))
print("\n  最外点 index=%d %s r=%.3f" % (mi, pts[mi], rr[mi]))
