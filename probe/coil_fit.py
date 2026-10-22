# -*- coding: utf-8 -*-
"""拟合线圈路径的「等间隙方形螺旋」参数。

模型：螺旋 = 以方框 [-a,a]^2 为骨架、按偏移量 d 外扩的圆角方形的等间隙族，
      d 沿路径从 d_in 线性长到 d_out，每匝增 4.5mm。
每个圆角弧的圆心应固定在 (±a, ±a)（相对螺旋中心），半径 = R0 + d。
"""
import json
import math

paths = json.load(open(r"C:\ansys maxwell2024\_work\coil_paths.json", encoding="utf-8"))
pts = [tuple(p) for p in paths["Rx"]]
N = len(pts)
print("点数 %d" % N)

# --- 1. 按 16 点一组找出圆角弧（方向变化最大的那段）---
def ang(p, q):
    return math.atan2(q[1] - p[1], q[0] - p[0])

turn = []
for i in range(2, N):
    d = (ang(pts[i - 2], pts[i - 1]) - ang(pts[i - 1], pts[i]) + math.pi) % (2 * math.pi) - math.pi
    turn.append(abs(d))

# 每组 16 个点，取组内方向变化总和最大的连续窗口做弧
groups = []
for k in range(0, N - 16, 16):
    seg = turn[k:k + 16]
    # 弧的起点：组内累计转角达到 90 度的窗口
    groups.append((k, sum(seg)))

# 用固定相位：弧中心在 i ≡ 13 (mod 16)
ARCS = []
for k in range(48):
    c = 16 * k + 13
    idx = [(c + j) % N for j in range(-4, 5)]
    idx = [i for i in idx if 0 <= i < N]
    if len(idx) >= 6:
        ARCS.append(idx)
print("检出弧段 %d 段（应 48 = 12 匝 × 4 角）" % len(ARCS))

# --- 2. Kasa 圆拟合 ---
def fit_circle(P):
    n = len(P)
    mx = sum(p[0] for p in P) / n
    my = sum(p[1] for p in P) / n
    u = [p[0] - mx for p in P]
    v = [p[1] - my for p in P]
    suu = sum(x * x for x in u); svv = sum(y * y for y in v); suv = sum(x * y for x, y in zip(u, v))
    suuu = sum(x ** 3 for x in u); svvv = sum(y ** 3 for y in v)
    suvv = sum(x * y * y for x, y in zip(u, v)); svuu = sum(y * x * x for x, y in zip(u, v))
    det = suu * svv - suv * suv
    if abs(det) < 1e-12:
        return None
    c1 = (suuu + suvv) / 2.0
    c2 = (svvv + svuu) / 2.0
    uc = (c1 * svv - c2 * suv) / det
    vc = (c2 * suu - c1 * suv) / det
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    return (mx + uc, my + vc, r)

fits = []
for idx in ARCS:
    P = [pts[i] for i in idx]
    f = fit_circle(P)
    if f:
        fits.append(f)

print("\n=== 各弧的拟合圆心/半径（相对路径 bbox 中心）===")
xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
bx = (min(xs) + max(xs)) / 2.0; by = (min(ys) + max(ys)) / 2.0
for i, (fx, fy, r) in enumerate(fits):
    print("  弧%2d  圆心(%8.3f,%8.3f) 半径=%7.3f   相对(%8.3f,%8.3f)  匝=%d 角=%d"
          % (i, fx, fy, r, fx - bx, fy - by, i // 4, i % 4))

# --- 3. 由圆心反推 a 与螺旋中心 ---
print("\n=== 反推 ===")
cxs = [f[0] for f in fits]; cys = [f[1] for f in fits]
# 四个角的圆心：两两成对，中心 = 4 个角的平均（按同匝分组）
for t in range(12):
    g = fits[t * 4:t * 4 + 4]
    if len(g) < 4:
        continue
    ccx = sum(f[0] for f in g) / 4.0
    ccy = sum(f[1] for f in g) / 4.0
    ax = sum(abs(f[0] - ccx) for f in g) / 4.0
    ay = sum(abs(f[1] - ccy) for f in g) / 4.0
    rr = sum(f[2] for f in g) / 4.0
    print("  匝%2d 螺旋中心(%8.3f,%8.3f)  a_x=%6.3f a_y=%6.3f  圆角半径=%7.3f"
          % (t, ccx, ccy, ax, ay, rr))
