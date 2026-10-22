# -*- coding: utf-8 -*-
"""快速拟合 (cx, cy, a)：用 numpy 向量化，判据 = 逐点「到基准方框的距离」增量最均匀。
   到方框的距离 e(p) = |(max(|dx|-a,0), max(|dy|-a,0))|
   等间隙螺旋要求 e 沿路径线性增长（每匝 ≈ 4.5mm）。"""
import json
import math

import numpy as np

paths = json.load(open(r"C:\ansys maxwell2024\_work\coil_paths.json", encoding="utf-8"))
P = np.array(paths["Rx"], dtype=float)
x = P[:, 0]
y = P[:, 1]
N = len(x)
print("点数 %d" % N)


def e_of(cx, cy, a):
    u = np.abs(x - cx)
    v = np.abs(y - cy)
    qx = np.maximum(u - a, 0.0)
    qy = np.maximum(v - a, 0.0)
    return np.hypot(qx, qy)


def score(cx, cy, a):
    e = e_of(cx, cy, a)
    inc = np.diff(e)
    return inc.std(), inc.mean(), e


best = None
for cx in np.arange(-2.0, 2.01, 0.1):
    for cy in np.arange(-3.0, 1.01, 0.1):
        for a in np.arange(8.0, 26.01, 0.1):
            s, m, e = score(cx, cy, a)
            if best is None or s < best[0]:
                best = (s, m, cx, cy, a)

s, m, cx, cy, a = best
print("粗搜: cx=%.2f cy=%.2f a=%.2f  std=%.5f 均值=%.5f" % (cx, cy, a, s, m))

for step, rng in ((0.02, 0.5), (0.005, 0.06)):
    b = None
    for ccx in np.arange(cx - rng, cx + rng + 1e-9, step):
        for ccy in np.arange(cy - rng, cy + rng + 1e-9, step):
            for aa in np.arange(a - rng, a + rng + 1e-9, step):
                sc, mm, ee = score(ccx, ccy, aa)
                if b is None or sc < b[0]:
                    b = (sc, mm, ccx, ccy, aa)
    s, m, cx, cy, a = b
    print("细化(step=%.3f): cx=%.4f cy=%.4f a=%.4f  std=%.6f 均值=%.6f"
          % (step, cx, cy, a, s, m))

s, m, e = score(cx, cy, a)
print("\n最终: 螺旋中心 (%.4f, %.4f)  基准方框半边长 a=%.4f" % (cx, cy, a))
print("到方框距离: 最小 %.4f  最大 %.4f  差 %.4f" % (e.min(), e.max(), e.max() - e.min()))
print("逐点增量: 均值 %.6f  中位 %.6f  std %.6f" % (m, np.median(np.diff(e)), s))
print("等效每匝节距 = %.4f mm (64 点/匝)" % (m * 64))

print("\n=== 每 64 点的 e（应线性）===")
for k in range(0, N, 64):
    print("  i=%3d  e=%8.4f" % (k, e[k]))

print("\n=== 端点 ===")
print("  起点 (%.4f,%.4f) e=%.4f" % (x[0], y[0], e[0]))
print("  终点 (%.4f,%.4f) e=%.4f" % (x[-1], y[-1], e[-1]))

print("\n=== 内/外匝平边位置（中心线半跨）===")
h_in = a + e[0]
h_out = a + e.max()
print("  h_in=%.4f  h_out=%.4f   中心线内跨=%.4f 外跨=%.4f  比值=%.4f"
      % (h_in, h_out, 2 * h_in, 2 * h_out, h_in / h_out))
print("  （用 e 的最小值算内匝: h_in_min=%.4f）" % (a + e.min()))

np.save(r"C:\ansys maxwell2024\_work\fit_params.npy",
        np.array([cx, cy, a, e.min(), e.max()]))
print("\n参数已存 fit_params.npy")
