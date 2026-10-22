# -*- coding: utf-8 -*-
"""估算引线改动对自感 L 的影响量级。"""

import math

MU0 = 4e-7 * math.pi
R = 0.3e-3          # 引线半径 m

print("=" * 74)
print("1. 引线本身的电感贡献（双线回路近似）")
print("=" * 74)
print("   公式: L ≈ (mu0*h/pi) * ln(d/r)   h=平行段长度, d=两线间距, r=线半径")
print()

# 现状：Tx1 两根竖直引线
x1, y1 = -56.0, -15.0
x2, y2 = -2.36, -71.87
d_vert = math.hypot(x2 - x1, y2 - y1) * 1e-3
h_vert = 45.0e-3
L_vert = (MU0 * h_vert / math.pi) * math.log(d_vert / R)

print("现状（竖直，z 0 -> -45）:")
print("   两线位置 (%.2f,%.2f) 与 (%.2f,%.2f) mm" % (x1, y1, x2, y2))
print("   间距 d = %.2f mm,  平行段 h = %.1f mm" % (d_vert * 1e3, h_vert * 1e3))
print("   -> L_lead ≈ %.4f uH" % (L_vert * 1e6))

# 新方案：短竖直 3mm + 水平段沿 -Y
z_run = -3.0
Y_OUT = -150.0
h_new = (max(y1, y2) - min(y1, y2))     # 两水平段重叠长度
d_new = abs(x2 - x1) * 1e-3
L_new = (MU0 * h_new * 1e-3 / math.pi) * math.log(d_new / R)

print()
print("新方案（3mm 竖直 + 水平沿 -Y 到 y=%.0f）:" % Y_OUT)
print("   两水平段间距 d = %.2f mm,  重叠长度 h = %.2f mm" % (d_new * 1e3, h_new))
print("   -> L_lead ≈ %.4f uH" % (L_new * 1e6))
print()
print("   引线贡献之差: %+.4f uH" % ((L_new - L_vert) * 1e6))

print()
print("=" * 74)
print("2. 相对于线圈自感有多大")
print("=" * 74)
L_COIL = 23.3   # uH，实测值
print("   线圈自感（实测）      : %.2f uH" % L_COIL)
print("   引线贡献(现状)        : %.4f uH  = %.3f%%" % (L_vert * 1e6, L_vert * 1e6 / L_COIL * 100))
print("   引线贡献(新方案)      : %.4f uH  = %.3f%%" % (L_new * 1e6, L_new * 1e6 / L_COIL * 100))
print("   改动引起的相对变化    : %.3f%%" % ((L_new - L_vert) * 1e6 / L_COIL * 100))

print()
print("=" * 74)
print("3. 去掉铁氧体开孔的影响")
print("=" * 74)
W_F, LEN_F, THK = 20.0, 168.0, 10.0     # 当前模型: W=20, y 168mm, 厚 10mm
V_bar = W_F * LEN_F * THK
for hole_r in (1.0, 0.5):
    V_hole = math.pi * hole_r ** 2 * THK
    print("   孔径 %.1fmm -> 单条铁氧体挖掉 %.1f mm^3 / %.0f mm^3 = %.3f%%"
          % (hole_r, V_hole, V_bar, V_hole / V_bar * 100))
print("   （只影响被引线穿过的那几条，且电感对铁氧体面积不是线性，实际影响更小）")

print()
print("=" * 74)
print("4. 结论")
print("=" * 74)
tot = (L_new - L_vert) * 1e6 / L_COIL * 100
print("   引线改动      : %+.3f%%" % tot)
print("   去开孔        : 约 +0.05~0.10%%（铁氧体略增）")
print("   ------------------------------------")
print("   合计估计      : 约 %+.1f%% ~ %+.1f%%" % (tot, tot + 0.10))
print()
print("   参考：数据集自身的运行间波动约 0.3%%（同点同设置两次独立运行）")
print("   -> 若合计 < 0.3%%，则现有数据集仍然有效，不必重算")
