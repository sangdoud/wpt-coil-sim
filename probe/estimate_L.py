# -*- coding: utf-8 -*-
"""估算这个线圈的自感，判断实测值是否合理。

几何（来自 build_ec6.py / 参数修改指南.md）：
  方形螺旋，外半边长 S0=84mm（外尺寸 168mm），内半边长 S_inner=30mm
  匝数 12，线宽 3mm，线厚 0.5mm，圆角 Rc=15mm
  铁氧体 µr=1000，厚 10mm，距线圈 30mm
"""

import math

MU0 = 4e-7 * math.pi

# ---- 几何 ----
S0 = 84.0e-3        # 外半边长 (m)
S_IN = 30.0e-3      # 内半边长 (m)
N = 12              # 匝数
W_WIRE = 3.0e-3     # 线宽
T_WIRE = 0.5e-3     # 线厚

# 等效圆导线半径（矩形截面 3mm x 0.5mm）
A_EQ = math.sqrt(W_WIRE * T_WIRE / math.pi)


def ellipKE(k):
    """完全椭圆积分 K(k), E(k) —— AGM 算法，无需 scipy。"""
    a, b = 1.0, math.sqrt(1.0 - k * k)
    c = k
    sum_c = 0.0
    for _ in range(60):
        sum_c += (c * c) / 4.0 * (2.0 ** 0)  # 占位，见下
        c_new = (a - b) / 2.0
        a, b = (a + b) / 2.0, math.sqrt(a * b)
        if abs(c_new) < 1e-16:
            break
    # 用标准 AGM 计算
    a, b = 1.0, math.sqrt(1.0 - k * k)
    c = k
    s = 0.5 * c * c
    pw = 1.0
    for _ in range(60):
        c_new = (a - b) / 2.0
        a, b = (a + b) / 2.0, math.sqrt(a * b)
        pw *= 2.0
        s += pw * c_new * c_new
        if abs(c_new) < 1e-18:
            break
    K = math.pi / (2.0 * a)
    E = K * (1.0 - s)
    return K, E


# ---- 12 匝方形螺旋 -> 12 个同心圆环等效（等周长） ----
radii = []
for i in range(N):
    s = S_IN + (S0 - S_IN) * i / (N - 1.0)      # 半边长
    perim = 8.0 * s                              # 方形周长（忽略圆角）
    radii.append(perim / (2.0 * math.pi))        # 等周长圆半径

print("=" * 70)
print("线圈几何")
print("=" * 70)
print("  外尺寸          : %.1f mm" % (2 * S0 * 1e3))
print("  内孔尺寸        : %.1f mm" % (2 * S_IN * 1e3))
print("  匝数            : %d" % N)
print("  线截面          : %.1f x %.1f mm  (等效圆半径 %.3f mm)"
      % (W_WIRE * 1e3, T_WIRE * 1e3, A_EQ * 1e3))
print("  等效圆半径范围  : %.2f ~ %.2f mm" % (radii[0] * 1e3, radii[-1] * 1e3))

# ---- 自感（各环自感 + 环间互感） ----
L_self = [MU0 * R * (math.log(8.0 * R / A_EQ) - 2.0) for R in radii]

L_total = sum(L_self)
print()
print("=" * 70)
print("解析估算（同心圆环等效，等周长）")
print("=" * 70)
print("  单环自感        : %.1f ~ %.1f uH" % (L_self[0] * 1e6, L_self[-1] * 1e6))
print("  Σ 单环自感      : %.2f uH   (若 12 环完全不相耦合的下限)" % (sum(L_self) * 1e6))

mut = 0.0
for i in range(N):
    for j in range(i + 1, N):
        R1, R2 = radii[i], radii[j]
        k = 2.0 * math.sqrt(R1 * R2) / (R1 + R2)
        K, E = ellipKE(k)
        m = MU0 * math.sqrt(R1 * R2) * ((2.0 / k - k) * K - (2.0 / k) * E)
        mut += m

print("  2·Σ 环间互感    : %.2f uH" % (2 * mut * 1e6))
L_bare = sum(L_self) + 2 * mut
print("  ------------------------------")
print("  12 匝螺旋 裸电感: %.2f uH" % (L_bare * 1e6))

# ---- Wheeler/Mohan 平面螺旋公式交叉验证 ----
d_out, d_in = 2 * S0, 2 * S_IN
d_avg = (d_out + d_in) / 2.0
rho = (d_out - d_in) / (d_out + d_in)
L_wh = 2.34 * MU0 * N * N * d_avg / (1.0 + 2.75 * rho)
print("  Wheeler 公式验证: %.2f uH" % (L_wh * 1e6))

# ---- 铁氧体增益 ----
print()
print("=" * 70)
print("加上铁氧体（µr=1000, 厚 10mm, 距线圈 30mm, 覆盖 50%）")
print("=" * 70)
for boost in (1.0, 1.3, 2.0, 3.0):
    print("  增益 x%.1f  ->  L ≈ %8.1f uH" % (boost, L_bare * boost * 1e6))

# ---- 与实测对比 ----
print()
print("=" * 70)
print("与实测数据对比")
print("=" * 70)
meas_lo, meas_hi = 3292.438, 4356.462
print("  实测 L11 范围   : %.1f ~ %.1f uH  (即 %.2f ~ %.2f mH)"
      % (meas_lo, meas_hi, meas_lo / 1000, meas_hi / 1000))
print()
print("  实测 / 裸电感   : %.0f x  ~  %.0f x" % (meas_lo / (L_bare * 1e6), meas_hi / (L_bare * 1e6)))
print("  实测 / (裸x1.3) : %.0f x  ~  %.0f x" % (meas_lo / (L_bare * 1.3e6), meas_hi / (L_bare * 1.3e6)))
print()
print("  匝数若被重复计入 N^2 = %d 倍:" % (N * N))
print("    (裸电感 x1.3) x %d = %.0f uH" % (N * N, L_bare * 1.3 * N * N * 1e6))
print("    实测中位 ~%.0f uH" % ((meas_lo + meas_hi) / 2))
print()
print("  要得到实测那个量级，需要多少匝（自由空间 Wheeler）：")
N_need = math.sqrt(((meas_lo + meas_hi) / 2 * 1e-6) * (1 + 2.75 * rho) / (2.34 * MU0 * d_avg))
print("    N ≈ %.0f 匝" % N_need)
