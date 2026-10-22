# -*- coding: utf-8 -*-
"""图 14 精确核算 3：这 768 点到底是什么形状。

方法：
 1) 用 ravel 把路径撕成 12 段（每段 64 点），看每段是不是一条闭合环；
 2) 求相邻两匝中心线的最小距离（= 匝节距，最能说明螺旋结构）；
 3) 沿 +X 轴切片，打印每一匝在 y=0 附近的 x 值（= 该匝在该方向的半径）；
 4) 求铜带外缘净跨（真实外轮廓）与最小净间隙。
"""
import json

import numpy as np

G = json.load(open(r"C:\ansys maxwell2024\_work\case_figures\geom_b1_0186.json",
                  encoding="utf-8"))
P = np.array(G["path"], float)
W = G["coil"]["width"]
N = G["coil"]["turns"]
n = len(P)

# ---- 1) 相邻匝中心线最小距离（暴力，768x768 太大 -> 按段做）----
def seg_min_dist(A, B):
    """两段折线之间的最小点距（够用：点数不大）。"""
    d = np.inf
    for p in A:
        v = B - p
        d = min(d, float(np.min(np.hypot(v[:, 0], v[:, 1]))))
    return d


# 假设：路径可以按"匝"切分。先找每匝的起点：与首点半径相同的点
r0 = np.hypot(*P[0])
same = np.where(np.abs(np.hypot(P[:, 0], P[:, 1]) - r0) < 1e-6)[0]
print("与首点同半径(r=%.4f)的点索引：%s" % (r0, same[:20]))

# ---- 3) 沿 +X / +Y 切片，列出每一匝的半径 ----
for axis, name in ((0, "+X 方向"), (1, "+Y 方向")):
    other = 1 - axis
    m = np.abs(P[:, other]) < 0.6
    v = np.round(P[m][:, axis], 4)
    v = np.unique(v)
    print("\n%s：|另一坐标|<0.6 的点共 %d 个" % (name, len(v)))
    print("  取值：", ", ".join("%.3f" % x for x in v))
    d = np.diff(v)
    print("  相邻差：", ", ".join("%.3f" % x for x in d))

# ---- 2) 相邻匝最小距离：把路径按 64 点切，逐段比 ----
K = n // N
segs = [P[i * K:(i + 1) * K] for i in range(N)]
print("\n每段 %d 点；逐段首末点：" % K)
for i, s in enumerate(segs):
    print("  段%2d 首(%8.3f,%8.3f) 末(%8.3f,%8.3f) 半径 %.3f..%.3f"
          % (i + 1, s[0, 0], s[0, 1], s[-1, 0], s[-1, 1],
             np.hypot(s[:, 0], s[:, 1]).min(), np.hypot(s[:, 0], s[:, 1]).max()))
print("\n相邻段最小距离（若为一条螺旋，应≈节距 %.3f）：" % 4.93488)
for i in range(N - 1):
    print("  段%2d-段%2d: %.4f" % (i + 1, i + 2, seg_min_dist(segs[i], segs[i + 1])))

# ---- 4) 铜带外缘：用切向法向偏置求真实外轮廓与净间隙 ----
T = np.zeros_like(P); T[0] = P[1] - P[-1]; T[-1] = P[0] - P[-2]
T[1:-1] = P[2:] - P[:-2]
Nv = np.c_[T[:, 1], -T[:, 0]]
Nv /= np.maximum(np.linalg.norm(Nv, axis=1, keepdims=True), 1e-12)
A = P + Nv * (W / 2)      # 侧 A
B = P - Nv * (W / 2)      # 侧 B
print("\n侧 A bbox X[%.3f, %.3f] Y[%.3f, %.3f]  跨 %.3f x %.3f"
      % (A[:, 0].min(), A[:, 0].max(), A[:, 1].min(), A[:, 1].max(),
         A[:, 0].max() - A[:, 0].min(), A[:, 1].max() - A[:, 1].min()))
print("侧 B bbox X[%.3f, %.3f] Y[%.3f, %.3f]  跨 %.3f x %.3f"
      % (B[:, 0].min(), B[:, 0].max(), B[:, 1].min(), B[:, 1].max(),
         B[:, 0].max() - B[:, 0].min(), B[:, 1].max() - B[:, 1].min()))
both = np.vstack([A, B])
print("铜带整体外轮廓 X = %.3f  Y = %.3f （图 2 文档值 187.351 / 185.895）"
      % (both[:, 0].max() - both[:, 0].min(), both[:, 1].max() - both[:, 1].min()))

# 最小净间隙：对每个点，求到"非本匝"最近点的距离再减线宽
# 简化：同一切片方向上，相邻两个半径之差即该处的净间隙
for axis, name in ((0, "+X 方向"), (1, "+Y 方向")):
    other = 1 - axis
    m = np.abs(P[:, other]) < 0.6
    v = np.unique(np.round(P[m][:, axis], 4))
    d = np.diff(v)
    print("%s：相邻匝中心线间距 min %.4f -> 净间隙 min %.4f"
          % (name, d.min(), d.min() - W))
