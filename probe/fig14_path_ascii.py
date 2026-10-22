# -*- coding: utf-8 -*-
"""把路径逐点画成 ASCII，直接看清 768 点到底是什么形状（不再猜）。"""
import json

import numpy as np

G = json.load(open(r"C:\ansys maxwell2024\_work\case_figures\geom_b1_0186.json",
                  encoding="utf-8"))
P = np.array(G["path"], float)

# 只画中心线本身（粗线：每个点落 3x3），X 横向压缩 2:1 以近似等比例
COLS, ROWS = 156, 78
lo, hi = -150.0, 150.0
grid = [[" "] * COLS for _ in range(ROWS)]


def put(x, y, ch):
    c = int(round((x - lo) / (hi - lo) * (COLS - 1)))
    r = int(round((hi - y) / (hi - lo) * (ROWS - 1) * 2))   # y 方向 2 倍行距补偿
    for dr in (0,):
        for dc in (0,):
            rr, cc = r + dr, c + dc
            if 0 <= rr < ROWS and 0 <= cc < COLS:
                grid[rr][cc] = ch


# 用不同字符标出匝序：每 64 点换一个字符（768/64 = 12 匝）
marks = "123456789ABC"
for i, (x, y) in enumerate(P):
    put(x, y, marks[min(i // 64, 11)])

print("路径点序着色（1..C 各 64 点，共 12 组）；坐标框 ±150 mm，X:Y = 2:1")
print("+" + "-" * COLS + "+")
for r in range(ROWS):
    print("|" + "".join(grid[r]) + "|")
print("+" + "-" * COLS + "+")

# 数值：每 64 点的圆心角与半径
print("\n组号  首点              末点              r 范围        角度范围(deg)")
for g in range(12):
    Q = P[g * 64:(g + 1) * 64]
    a = np.degrees(np.arctan2(Q[:, 1], Q[:, 0]))
    r = np.hypot(Q[:, 0], Q[:, 1])
    print("%2d (%8.2f,%8.2f) (%8.2f,%8.2f)  %6.1f..%6.1f  %7.1f..%7.1f"
          % (g + 1, Q[0, 0], Q[0, 1], Q[-1, 0], Q[-1, 1], r.min(), r.max(),
             a.min(), a.max()))
