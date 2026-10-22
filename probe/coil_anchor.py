# -*- coding: utf-8 -*-
"""定出重映射用的锚点：
   螺旋中心 = 四个圆角弧圆心的平均（前面已测得 ≈ (0,-1)）
   内锚 h_in  = 最内匝平边到中心的距离（中心线半跨）
   外锚 h_out = 最外匝平边到中心的距离
端点小尾巴（引线桩）不计入锚点。"""
import json

paths = json.load(open(r"C:\ansys maxwell2024\_work\coil_paths.json", encoding="utf-8"))
pts = [tuple(p) for p in paths["Rx"]]
N = len(pts)

CX, CY = 0.0, -1.0     # 螺旋中心（Rx 局部坐标，dx=0 时）
print("螺旋中心取 (%.3f, %.3f)" % (CX, CY))


def ch(p):
    return max(abs(p[0] - CX), abs(p[1] - CY))


chs = [ch(p) for p in pts]
print("ch: min=%.4f max=%.4f" % (min(chs), max(chs)))

# 外锚：最后一个整匝（i=704..767）里去掉末尾几个引线桩点后的最大 ch
tail = chs[704:768]
print("\n最后一匝 ch 序列（每点）:")
for i, v in enumerate(tail):
    print("   i=%3d ch=%.4f" % (704 + i, v))
