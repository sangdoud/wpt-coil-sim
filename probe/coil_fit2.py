# -*- coding: utf-8 -*-
"""拟合「等间隙方形螺旋」的基准参数：
  螺旋 = 以方框 [-a,a]^2 为骨架的等偏移族：dist(p, 方框) = R0 + d
  d 沿路径均匀增长（每匝 4.5mm，即每点 4.5/64）。
搜索 (cx, cy, a) 使逐点偏移增量最均匀。"""
import json
import math

paths = json.load(open(r"C:\ansys maxwell2024\_work\coil_paths.json", encoding="utf-8"))
pts = [tuple(p) for p in paths["Rx"]]
N = len(pts)


def dist_sq(p, cx, cy, a):
    u = abs(p[0] - cx)
    v = abs(p[1] - cy)
    return math.hypot(max(u - a, 0.0), max(v - a, 0.0))


def score(cx, cy, a):
    d = [dist_sq(p, cx, cy, a) for p in pts]
    inc = [d[i] - d[i - 1] for i in range(1, N)]
    m = sum(inc) / len(inc)
    var = sum((x - m) ** 2 for x in inc) / len(inc)
    return math.sqrt(var), m, d


best = None
for cx in [x / 40.0 for x in range(-40, 41)]:
    for cy in [-1.0 + x / 40.0 for x in range(-40, 41)]:
        for a in [10.0 + x / 8.0 for x in range(0, 161)]:
            s, m, d = score(cx, cy, a)
            if best is None or s < best[0]:
                best = (s, m, cx, cy, a, d)

s, m, cx, cy, a, d = best
print("最优拟合:")
print("  螺旋中心 (%.4f, %.4f)   基准方框半边长 a = %.4f" % (cx, cy, a))
print("  逐点偏移增量的标准差 = %.6f mm  (均值 %.6f)" % (s, m))
print("  等效每匝节距 = %.4f mm  (64 点/匝)" % (m * 64))
print("  偏移范围: d_in=%.4f  d_out=%.4f  差=%.4f" % (d[0], d[-1], d[-1] - d[0]))

print("\n=== 每匝起点的偏移量（每 64 点）===")
for k in range(0, N, 64):
    print("  点%3d  d=%8.4f  (d-d_in)/pitch = %6.3f 匝" % (k, d[k], (d[k] - d[0]) / m / 64 * 64 / (m * 64) * (m * 64) if False else (d[k] - d[0]) / (m * 64)))

print("\n=== 由基准参数导出的物理尺寸 ===")
h_in = a + d[0]      # 最内匝平边位置
h_out = a + d[-1]    # 最外匝平边位置
print("  平边位置（中心线）: 内 %.4f  外 %.4f" % (h_in, h_out))
print("  中心线外跨 = %.4f   中心线内跨 = %.4f" % (2 * h_out, 2 * h_in))
for w in (3.0, 2.0):
    print("  线宽%.0fmm: 外边缘尺寸=%.4f  内孔(孔壁)=%.4f  内孔比=%.4f / %.4f"
          % (w, 2 * h_out + w, 2 * h_in - w, h_in / h_out, (2 * h_in - w) / (2 * h_out + w)))

# 圆角：用最内匝的四段弧拟合，得到 R0 + d_in
print("\n=== 圆角半径核对 ===")
def ang(p, q):
    return math.atan2(q[1] - p[1], q[0] - p[0])

def fit_circle(P):
    n = len(P)
    mx = sum(p[0] for p in P) / n; my = sum(p[1] for p in P) / n
    u = [p[0] - mx for p in P]; v = [p[1] - my for p in P]
    suu = sum(x * x for x in u); svv = sum(y * y for y in v); suv = sum(x * y for x, y in zip(u, v))
    suuu = sum(x ** 3 for x in u); svvv = sum(y ** 3 for y in v)
    suvv = sum(x * y * y for x, y in zip(u, v)); svuu = sum(y * x * x for x, y in zip(u, v))
    det = suu * svv - suv * suv
    c1 = (suuu + suvv) / 2.0; c2 = (svvv + svuu) / 2.0
    uc = (c1 * svv - c2 * suv) / det; vc = (c2 * suu - c1 * suv) / det
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    return (mx + uc, my + vc, r)

for k in (0, 1, 11):
    c = 16 * k + 13
    idx = [i for i in range(c - 4, c + 5) if 0 <= i < N]
    f = fit_circle([pts[i] for i in idx])
    print("  第%2d段弧: 圆心(%8.3f,%8.3f) R=%7.3f   圆心相对螺旋中心=(%7.3f,%7.3f)  |.|/sqrt2=%6.3f"
          % (k, f[0], f[1], f[2], f[0] - cx, f[1] - cy,
             max(abs(f[0] - cx), abs(f[1] - cy)) / math.sqrt(2)))
