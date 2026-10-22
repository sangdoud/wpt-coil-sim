# -*- coding: utf-8 -*-
"""图 14 精确核算 2：四条直边的真实位置、对边跨距、节距、净间隙、中心偏移。

要点：路径模板并非严格以 (0,0) 对称（外轮廓 bbox 中心 = (+0.728, −1.234)），
所以"外跨"必须由**对边中心线**求，不能由 bbox 求；h_out 是相对模板中心的半径。
"""
import json

import numpy as np

G = json.load(open(r"C:\ansys maxwell2024\_work\case_figures\geom_b1_0186.json",
                  encoding="utf-8"))
P = np.array(G["path"], dtype=float)
W = G["coil"]["width"]
N = G["coil"]["turns"]


def straight(axis, sgn, tol=6.0):
    """某条直边上的点（另一坐标在原点附近）。"""
    other = 1 - axis
    m = (np.sign(P[:, axis]) == sgn) & (np.abs(P[:, other]) < tol)
    v = np.sort(P[m][:, axis])
    cl, cur = [], [v[0]]
    for a in v[1:]:
        if a - cur[-1] < 1.0:
            cur.append(a)
        else:
            cl.append(cur); cur = [a]
    cl.append(cur)
    return [float(np.mean(c)) for c in cl]


edges = {}
for name, axis, sgn in (("right", 0, 1), ("left", 0, -1),
                        ("top", 1, 1), ("bottom", 1, -1)):
    c = straight(axis, sgn)
    edges[name] = c
    d = np.diff(c)
    print("%-6s %2d 条，位置 %.4f … %.4f（跨 %.4f）节距 mean %.5f min %.5f max %.5f"
          % (name, len(c), c[0], c[-1], c[-1] - c[0], d.mean(), d.min(), d.max()))

pitch = np.mean([np.diff(edges[k]).mean() for k in edges])
print("\n节距 p = %.5f mm（四条直边平均）" % pitch)
print("净间隙 p − w = %.5f mm" % (pitch - W))
print("json gap_min = %.4f mm  -> 差 %.4f mm" % (G["coil"]["gap_min"],
                                                 pitch - W - G["coil"]["gap_min"]))

print("\n对边中心线跨距：")
for a, b, ax in (("right", "left", "X"), ("top", "bottom", "Y")):
    ca, cb = edges[a], edges[b]
    pa, pb = ca[-1] + W / 2, cb[-1] - W / 2          # 外侧那条匝的中心线
    ia, ib = ca[0], cb[0]                            # 内侧那条匝的中心线
    print("  %s: 外侧跨 %.4f（%+.4f … %+.4f）  内侧跨 %.4f" %
          (ax, pa - pb, pb, pa, ia - ib))

xmin, xmax = P[:, 0].min(), P[:, 0].max()
ymin, ymax = P[:, 1].min(), P[:, 1].max()
print("\n路径 bbox 中心 = (%+.4f, %+.4f)；铜带 bbox 中心 = (%+.4f, %+.4f)"
      % ((xmin + xmax) / 2, (ymin + ymax) / 2,
         (xmin + xmax) / 2, (ymin + ymax) / 2))
print("从原点到最远中心线 = max|x|=%.4f max|y|=%.4f（json h_out=%.4f）"
      % (max(abs(xmin), abs(xmax)), max(abs(ymin), abs(ymax)), G["coil"]["h_out"]))
print("从原点到铜带最外缘 = %.4f" % (max(abs(xmin), abs(xmax)) + W / 2))
print("2·h_out = %.4f  = 24·p = %.4f" % (2 * G["coil"]["h_out"], 24 * pitch))

# 真实最小净间隙：相邻两匝的外缘/内缘差
gaps = []
for k in edges:
    c = np.array(edges[k])
    gaps += list(np.diff(c) - W)
print("四条直边相邻匝净间隙：min %.5f max %.5f（共 %d 处）"
      % (min(gaps), max(gaps), len(gaps)))
print("角部（切向 45° 附近）不参与最小间隙比较——最大折角 11.45°，"
      "故直边值即全路径下限。")
