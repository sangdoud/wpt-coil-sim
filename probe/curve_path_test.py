# -*- coding: utf-8 -*-
"""⑤ 路径曲线化：把 768 点/767 段直线的模板，按「每 8 段弦合成 1 段弧/直线」重建。

结构（前面已反推清楚）：每 16 个点 = 1 个圆角弧（8 段弦）+ 1 条直边（8 段弦），
12 匝 = 48 个弧 + 48 条直边。合成后 = 96 段，面数从 1548 降到约 200。
本脚本只做离线拟合与误差评估，不启动 AEDT。
"""
import json
import math

import numpy as np

SRC = r"C:\wpt\coil_template_Rx.json"
OUT = r"C:\ansys maxwell2024\_work\path_curve_report.json"

P = np.array(json.load(open(SRC, encoding="utf-8")), dtype=float)[:, :2]
N = len(P)
print("原路径: %d 点 / %d 段" % (N, N - 1))


def fit_circle(Q):
    n = len(Q)
    mx, my = Q[:, 0].mean(), Q[:, 1].mean()
    u, v = Q[:, 0] - mx, Q[:, 1] - my
    suu, svv, suv = (u * u).sum(), (v * v).sum(), (u * v).sum()
    suuu, svvv = (u ** 3).sum(), (v ** 3).sum()
    suvv, svuu = (u * v * v).sum(), (v * u * u).sum()
    det = suu * svv - suv * suv
    c1, c2 = (suuu + suvv) / 2, (svvv + svuu) / 2
    uc = (c1 * svv - c2 * suv) / det
    vc = (c2 * suu - c1 * suv) / det
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    return np.array([mx + uc, my + vc]), r


# 弧组：中心在 i≡13 (mod 16)，取 ±4 共 9 点
arcs, devs, lens_old, lens_new = [], [], 0.0, 0.0
for k in range(48):
    c = 16 * k + 13
    idx = [i for i in range(c - 4, c + 5) if 0 <= i < N]
    if len(idx) < 7:
        continue
    Q = P[idx]
    ctr, r = fit_circle(Q)
    arcs.append((ctr, r, idx[0], idx[-1]))
    d = np.abs(np.hypot(Q[:, 0] - ctr[0], Q[:, 1] - ctr[1]) - r)
    devs.append(d.max())
    # 弦长总和 vs 弧长
    chord = sum(math.dist(Q[i], Q[i - 1]) for i in range(1, len(Q)))
    a0 = math.atan2(Q[0][1] - ctr[1], Q[0][0] - ctr[0])
    a1 = math.atan2(Q[-1][1] - ctr[1], Q[-1][0] - ctr[0])
    da = abs((a1 - a0 + math.pi) % (2 * math.pi) - math.pi)
    lens_old += chord
    lens_new += r * da

print("弧数: %d（应 48）" % len(arcs))
print("每个弧内点到拟合圆的最大偏差: 中位 %.4f  最大 %.4f mm" % (np.median(devs), max(devs)))
print("弧长(拟合) vs 弦长(现在): %.2f vs %.2f mm  → 路径长变化 %+.3f%%"
      % (lens_new, lens_old, 100 * (lens_new - lens_old) / lens_old))
tot_old = sum(math.dist(P[i], P[i - 1]) for i in range(1, N))
print("整条路径: 现在 %.2f mm → 曲线化后约 %.2f mm（%+.3f%%）"
      % (tot_old, tot_old - lens_old + lens_new, 100 * (lens_new - lens_old) / tot_old))
print("")
print("段数: %d → 96（12 匝 x (4 弧 + 4 直边)）" % (N - 1))
print("预估单线圈面数: 1548 → 约 200（−87%）")
json.dump(dict(arcs=len(arcs), dev_med=float(np.median(devs)), dev_max=float(max(devs)),
               len_old=float(lens_old), len_new=float(lens_new),
               total_old=float(tot_old)), open(OUT, "w"), indent=2)
print("\n报告 -> %s" % OUT)
