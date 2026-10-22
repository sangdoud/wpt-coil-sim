# -*- coding: utf-8 -*-
"""看线圈外形的角度-半径分布，判断是圆 / 方 / 八边形。"""

import math
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\wpt\backup\Projecttonight.aedt"
NAME = sys.argv[2] if len(sys.argv) > 2 else "Tx1"

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    lines = f.readlines()

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

pts = []
k = start
while lines[k].strip() != "$end 'PolylineParameters'":
    if lines[k].strip() == "$begin 'PLPoint'":
        pts.append((float(lines[k + 1].split("'")[1].replace("mm", "")),
                    float(lines[k + 2].split("'")[1].replace("mm", ""))))
    k += 1

xs = [p[0] for p in pts]
ys = [p[1] for p in pts]
cx = (min(xs) + max(xs)) / 2.0
cy = (min(ys) + max(ys)) / 2.0
print("%s: %d 点, bbox 中心 (%.3f, %.3f), 半宽 %.3f x %.3f"
      % (NAME, len(pts), cx, cy, (max(xs) - min(xs)) / 2.0, (max(ys) - min(ys)) / 2.0))

# 分段长度统计
segs = [math.hypot(pts[a][0] - pts[a - 1][0], pts[a][1] - pts[a - 1][1]) for a in range(1, len(pts))]
segs.sort()
print("  段长: min %.3f 中位 %.3f max %.3f" % (segs[0], segs[len(segs) // 2], segs[-1]))

# 最外一圈（最后 64 点）的 角度->半径
print("\n  最外圈 64 点，按 15 度分箱的半径:")
bins = {}
for p in pts[-64:]:
    dx, dy = p[0] - cx, p[1] - cy
    r = math.hypot(dx, dy)
    ang = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0
    b = int(ang // 15.0)
    bins.setdefault(b, []).append(r)
for b in range(24):
    if b in bins:
        v = bins[b]
        print("    %3d-%3d deg : n=%2d  r=%.2f ~ %.2f" % (b * 15, b * 15 + 15, len(v), min(v), max(v)))
    else:
        print("    %3d-%3d deg : (空)" % (b * 15, b * 15 + 15))

# 圆度检验：如果外圈是圆，所有 r 应接近常数
outer = [math.hypot(p[0] - cx, p[1] - cy) for p in pts[-64:]]
print("\n  最外圈 r: min %.2f max %.2f 平均值 %.2f  (若是圆，差应很小)"
      % (min(outer), max(outer), sum(outer) / len(outer)))

# 归一化方形距离: 1 = 恰好在 bbox 边上, sqrt(2)=角
hw = (max(xs) - min(xs)) / 2.0
hh = (max(ys) - min(ys)) / 2.0
nrm = [math.hypot((p[0] - cx) / hw, (p[1] - cy) / hh) for p in pts[-64:]]
print("  最外圈 归一化(x/hw, y/hh) 距离: min %.3f max %.3f  (方形=1.0, 圆=1.0~1.414)"
      % (min(nrm), max(nrm)))
