# -*- coding: utf-8 -*-
"""图 14 补充核算：角部圆角半径（局部三点圆）+ 最外匝四边位置 + 引线端点归属。"""
import json
import math

import numpy as np

G = json.load(open(r"C:\ansys maxwell2024\_work\case_figures\geom_b1_0186.json",
                   encoding="utf-8"))
P = np.array(G["path"], dtype=float)
W = G["coil"]["width"]


def local_R(P, i):
    a, b, c = P[i - 1], P[i], P[i + 1]
    ab, bc, ca = np.linalg.norm(b - a), np.linalg.norm(c - b), np.linalg.norm(a - c)
    area = abs(np.cross(b - a, c - a)) / 2.0
    if area < 1e-12:
        return float("inf")
    return ab * bc * ca / (4.0 * area)


# 最外匝四角（各象限 |x|,|y| 最大处附近）
for qname, sx, sy in (("右上", 1, 1), ("左上", -1, 1), ("左下", -1, -1), ("右下", 1, -1)):
    m = (np.sign(P[:, 0]) == sx) & (np.sign(P[:, 1]) == sy)
    Q = np.where(m)[0]
    # 象限内半径最大的点索引（角部中点）
    idx = Q[np.argmax(np.maximum(np.abs(P[Q, 0]), np.abs(P[Q, 1])))]
    Rs = [local_R(P, j) for j in range(max(1, idx - 3), min(len(P) - 1, idx + 4))]
    Rs = [r for r in Rs if math.isfinite(r)]
    print("%s角 idx=%d 点=(%.3f, %.3f) 局部曲率半径 min %.4f max %.4f"
          % (qname, idx, P[idx, 0], P[idx, 1], min(Rs), max(Rs)))

# 最外匝四条直边（|其余坐标| < 3 的点）位置
print("\n最外匝直边位置：")
for name, axis, sgn in (("右 x>0", 0, 1), ("左 x<0", 0, -1),
                        ("上 y>0", 1, 1), ("下 y<0", 1, -1)):
    other = 1 - axis
    v = P[(np.sign(P[:, axis]) == sgn) & (np.abs(P[:, other]) < 3.0)][:, axis]
    if len(v):
        print("  %s  x/y 范围 [%.4f, %.4f]  最外 %.4f，最内 %.4f，节距 %.4f（%d 条）"
              % (name, v.min(), v.max(), v[np.argmax(np.abs(v))],
                 v[np.argmin(np.abs(v))],
                 (v.max() - v.min()) / (len(np.unique(np.round(v, 3))) - 1),
                 len(np.unique(np.round(v, 3)))))

# 引线端点：路径首末端点是否落在直边上
print("\n路径首点 (%.4f, %.4f) 末点 (%.4f, %.4f)"
      % (P[0, 0], P[0, 1], P[-1, 0], P[-1, 1]))
print("place.vert = %.1f（Tx 引线竖直段高度）, y_end = %.1f" %
      (G["place"]["vert"], G["place"]["y_end"]))
print("Rx 引线：从 z=%.2f 竖直向上到 z=%.2f" %
      (G["coil"]["plane_z"]["Rx"] + G["coil"]["height"] / 2, G["place"]["rx_ztop"]))
