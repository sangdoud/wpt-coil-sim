# -*- coding: utf-8 -*-
"""为「单个线圈俯视图（图 14）」核算全部待标注量（只读 geom_b1_0186.json）。

算的量：
  - 铜带外轮廓（实测，含 2 mm 线宽）X/Y 向
  - 各直边的匝位置（用于数匝数、量匝节距与净间隙）
  - 引线端点（768 点路径首末端点 = 引线起点）
  - 圆角半径估计（角部 4 弦离散）
"""
import json
import math
import os

import numpy as np

GEOM = r"C:\ansys maxwell2024\_work\case_figures\geom_b1_0186.json"
G = json.load(open(GEOM, encoding="utf-8"))
P = np.array(G["path"], dtype=float)
C = G["coil"]
W = C["width"]

print("n_pts =", len(P), " (json coil.n_pts = %d)" % C["n_pts"])
xmin, xmax = P[:, 0].min(), P[:, 0].max()
ymin, ymax = P[:, 1].min(), P[:, 1].max()
print("中心线 bbox X[%.4f, %.4f] Y[%.4f, %.4f]" % (xmin, xmax, ymin, ymax))
print("中心线外跨 X = %.4f  Y = %.4f" % (xmax - xmin, ymax - ymin))
print("铜带外轮廓 X = %.3f  Y = %.3f" % (xmax - xmin + W, ymax - ymin + W))
print("铜带 bbox X[%.3f, %.3f] Y[%.3f, %.3f]" % (xmin - W / 2, xmax + W / 2,
                                                 ymin - W / 2, ymax + W / 2))

s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))     # 切比雪夫半径 = 环半径
print("h_out = %.4f   h_in = %.4f   (json %.4f / %.4f)"
      % (s.max(), s.min(), C["h_out"], C["h_in"]))

# ---- 右侧直边（x>0 且 |y| 小的那一段）：每匝一条竖线 ----
def band(axis, sign, lo, hi, other):
    """取某条直边上的点：axis 方向的符号 = sign，另一坐标在 [lo,hi]。"""
    m = (np.sign(P[:, axis]) == sign) & (P[:, other] >= lo) & (P[:, other] <= hi)
    return P[m]

for name, axis, sign in (("右直边(x>0,Y∈[-10,10])", 0, 1),
                         ("上直边(y>0,X∈[-10,10])", 1, 1),
                         ("左直边(x<0,Y∈[-10,10])", 0, -1),
                         ("下直边(y<0,X∈[-10,10])", 1, -1)):
    other = 1 - axis
    Q = band(axis, sign, -10.0, 10.0, other)
    if len(Q) == 0:
        print(name, "无点"); continue
    v = np.sort(Q[:, axis])
    # 合并成簇（同一匝上相邻离散点）
    cl, cur = [], [v[0]]
    for a in v[1:]:
        if a - cur[-1] < 1.0:
            cur.append(a)
        else:
            cl.append(cur); cur = [a]
    cl.append(cur)
    cen = [float(np.mean(c)) for c in cl]
    d = np.diff(cen)
    print("%s: 簇数 %d，逐匝位置 %s" % (name, len(cen),
          ", ".join("%.3f" % c for c in cen)))
    print("    节距 = %s" % ", ".join("%.4f" % x for x in d))
    if len(d):
        print("    节距 min %.4f max %.4f 均值 %.4f | 净间隙(节距-线宽) min %.4f"
              % (d.min(), d.max(), d.mean(), d.min() - W))
    print("    最内/最外中心线位置 %.3f / %.3f  -> 单边内孔中心线 %.3f，外跨 %.3f"
          % (cen[0], cen[-1], cen[0], cen[-1] + W / 2 if axis == 0 else cen[-1]))

# ---- 引线端点 ----
print("路径首点 %s  末点 %s" % (np.round(P[0], 4), np.round(P[-1], 4)))
print("place.vert=%.1f  y_end=%.1f" % (G["place"]["vert"], G["place"]["y_end"]))

# ---- 角部圆角半径估计：取第一象限角部的点做圆拟合 ----
q = P[(P[:, 0] > 0) & (P[:, 1] > 0) & (np.maximum(P[:, 0], P[:, 1]) > 89.0)]
if len(q) >= 3:
    A = np.c_[2 * q[:, 0], 2 * q[:, 1], np.ones(len(q))]
    b = (q ** 2).sum(axis=1)
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = sol[0], sol[1]
    R = math.sqrt(sol[2] + cx * cx + cy * cy)
    rr = np.hypot(q[:, 0] - cx, q[:, 1] - cy)
    print("最外匝角部圆角：圆心 (%.3f, %.3f)  R = %.4f  (残差 max %.4f)"
          % (cx, cy, R, np.abs(rr - R).max()))

# ---- 整周角度分布（弦角），确认没有尖角 ----
V = np.diff(P, axis=0)
ang = np.degrees(np.arctan2(V[:, 1], V[:, 0]))
dang = np.abs((np.diff(ang) + 180) % 360 - 180)
print("折角：max %.3f deg，>15deg 的点数 %d" % (dang.max(), int((dang > 15).sum())))
seglen = np.hypot(V[:, 0], V[:, 1])
print("段长：min %.4f max %.4f 合计 %.3f mm（单匝周长估计 %.2f mm = 合计/12）"
      % (seglen.min(), seglen.max(), seglen.sum(), seglen.sum() / 12.0))
