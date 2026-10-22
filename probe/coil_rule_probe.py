# -*- coding: utf-8 -*-
"""反推线圈路径的几何规则：匝数、节距、内外半径、圆角、采样方式。
用 extract_paths.py 抽出来的 coil_paths.json。"""
import json
import math
from collections import Counter

P = r"C:\ansys maxwell2024\_work\coil_paths.json"
paths = json.load(open(P, encoding="utf-8"))
pts = [tuple(p) for p in paths["Rx"]]      # Rx 在 z=30 平面，没有引线干扰
print("Rx 路径点数 = %d" % len(pts))

xs = [p[0] for p in pts]
ys = [p[1] for p in pts]
cx = (min(xs) + max(xs)) / 2.0
cy = (min(ys) + max(ys)) / 2.0
print("路径 bbox 中心 = (%.4f, %.4f)   X跨度=%.4f  Y跨度=%.4f" %
      (cx, cy, max(xs) - min(xs), max(ys) - min(ys)))

# 用「切比雪夫半径」= max(|dx|,|dy|) 看方环
ch = [max(abs(p[0] - cx), abs(p[1] - cy)) for p in pts]
print("\n切比雪夫半径: min=%.4f  max=%.4f" % (min(ch), max(ch)))

# 直方图看环
print("\n=== 切比雪夫半径直方图（0.25mm 分箱，只列有点的箱）===")
bins = Counter(int(v / 0.25) for v in ch)
for b in sorted(bins):
    print("   %7.2f ~ %7.2f : %d" % (b * 0.25, b * 0.25 + 0.25, bins[b]))

# 相邻点半径增量（沿路径走一圈应该看到阶梯）
print("\n=== 沿路径的半径变化（每 32 个点采一次）===")
for i in range(0, len(pts), 32):
    print("   i=%3d  (%.2f, %.2f)  ch=%.3f" % (i, pts[i][0], pts[i][1], ch[i]))

# 段长统计
segs = [math.dist(pts[i], pts[i - 1]) for i in range(1, len(pts))]
print("\n段长: min=%.4f  中位=%.4f  max=%.4f  总长=%.3f" %
      (min(segs), sorted(segs)[len(segs) // 2], max(segs), sum(segs)))

# 角点检测：段方向变化
print("\n=== 每圈的采样点数（按半径环分组）===")
# 把点按 ch 值聚类成环
vals = sorted(set(round(v, 3) for v in ch))
print("不同的 ch 取值个数 = %d（前 20 个）: %s" % (len(vals), vals[:20]))
print("后 20 个: %s" % vals[-20:])
