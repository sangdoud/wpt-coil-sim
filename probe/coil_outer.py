# -*- coding: utf-8 -*-
"""看最外匝四条平边的实际位置，判断线圈是正方螺旋还是长方螺旋，并定出中心。"""
import json
import math

paths = json.load(open(r"C:\ansys maxwell2024\_work\coil_paths.json", encoding="utf-8"))
pts = [tuple(p) for p in paths["Rx"]]

last = pts[700:768]
print("最外匝（i=700..767）坐标:")
for i, p in enumerate(last):
    print("   i=%3d (%9.4f,%9.4f)" % (700 + i, p[0], p[1]))

# 用「平边」点（ch 大的那些）分别拟合四条边的位置
xs = [p[0] for p in last]
ys = [p[1] for p in last]
print("\n最外匝 bbox: X[%.4f,%.4f] Y[%.4f,%.4f]" % (min(xs), max(xs), min(ys), max(ys)))

# 分类：按 |x| 还是 |y| 占优
right = [p for p in last if p[0] > 60]
left = [p for p in last if p[0] < -60]
top = [p for p in last if p[1] > 60]
bot = [p for p in last if p[1] < -60]
print("\n右边点 %d 个: x 范围 [%.4f, %.4f]" % (len(right), min(p[0] for p in right), max(p[0] for p in right)))
print("左边点 %d 个: x 范围 [%.4f, %.4f]" % (len(left), min(p[0] for p in left), max(p[0] for p in left)))
print("上边点 %d 个: y 范围 [%.4f, %.4f]" % (len(top), min(p[1] for p in top), max(p[1] for p in top)))
print("下边点 %d 个: y 范围 [%.4f, %.4f]" % (len(bot), min(p[1] for p in bot), max(p[1] for p in bot)))
print("\n左右中心 x = %.4f   上下中心 y = %.4f"
      % ((max(p[0] for p in right) + min(p[0] for p in left)) / 2.0,
         (max(p[1] for p in top) + min(p[1] for p in bot)) / 2.0))
print("X 半跨 = %.4f   Y 半跨 = %.4f"
      % ((max(p[0] for p in right) - min(p[0] for p in left)) / 2.0,
         (max(p[1] for p in top) - min(p[1] for p in bot)) / 2.0))
