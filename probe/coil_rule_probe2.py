# -*- coding: utf-8 -*-
"""细看路径：起点段结构、最大 ch 的点、圆角圆心与半径、每匝采样点数。"""
import json
import math

paths = json.load(open(r"C:\ansys maxwell2024\_work\coil_paths.json", encoding="utf-8"))
pts = [tuple(p) for p in paths["Rx"]]
xs = [p[0] for p in pts]
ys = [p[1] for p in pts]
cx = (min(xs) + max(xs)) / 2.0
cy = (min(ys) + max(ys)) / 2.0
ch = [max(abs(p[0] - cx), abs(p[1] - cy)) for p in pts]

print("=== 前 40 个点 ===")
for i in range(40):
    d = math.dist(pts[i], pts[i - 1]) if i else 0.0
    print("  i=%3d (%9.4f,%9.4f) ch=%7.3f  段长=%6.3f" % (i, pts[i][0], pts[i][1], ch[i], d))

print("\n=== ch 最大的 12 个点 ===")
order = sorted(range(len(pts)), key=lambda i: -ch[i])[:12]
for i in sorted(order):
    print("  i=%3d (%9.4f,%9.4f) ch=%7.4f  dx=%8.4f dy=%8.4f" %
          (i, pts[i][0], pts[i][1], ch[i], pts[i][0] - cx, pts[i][1] - cy))

print("\n=== ch 最小的 12 个点 ===")
order = sorted(range(len(pts)), key=lambda i: ch[i])[:12]
for i in sorted(order):
    print("  i=%3d (%9.4f,%9.4f) ch=%7.4f  dx=%8.4f dy=%8.4f" %
          (i, pts[i][0], pts[i][1], ch[i], pts[i][0] - cx, pts[i][1] - cy))

# 方向变化 -> 找直线段与圆角
print("\n=== 段方向角变化 > 0.5 度的位置（前 60 个）===")
def ang(p, q):
    return math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
cnt = 0
for i in range(2, len(pts)):
    a1 = ang(pts[i - 2], pts[i - 1])
    a2 = ang(pts[i - 1], pts[i])
    d = (a2 - a1 + 180) % 360 - 180
    if abs(d) > 0.5:
        cnt += 1
        if cnt <= 60:
            print("  i=%3d 转角=%7.3f 度  ch=%7.3f" % (i, d, ch[i]))
print("  方向变化点总数 = %d（12 匝 × 4 角 × N ≈ %d）" % (cnt, cnt))
