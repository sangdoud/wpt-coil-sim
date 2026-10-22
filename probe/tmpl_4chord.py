# -*- coding: utf-8 -*-
"""⑤改：把参考模板（768 点 / 767 段直线）重采样成「每角 4 弦」的新模板。

结构（curve_path_test.py 已反推、本脚本复核）：每 16 点 = 8 段弦圆角 + 8 段弦直边，
12 匝 = 48 个圆角 + 48 条直边。

做法（与点数无关的通用做法，不写死 768）：
  1. 按每段弦的转角把路径切成「弧 run」和「直 run」
  2. 弧 run -> 4 段弦；直 run -> 1 段弦
  3. 连接点共享，不重复出点

弧的两种取点方式（都存，供求解比对）：
  inscribed : 顶点落在拟合圆上（内接，路径略短、铜量略少）
  length    : 顶点半径 R' = R*θ/(2n*sin(θ/2n))，使弦长总和 = 原弧长（保长）

输出：
  _work\coil_template_Rx_4chord.json        新模板（inscribed，默认口径）
  _work\coil_template_Rx_4chord_len.json    新模板（保长口径）
  _work\tmpl_4chord_report.json             全部指标
本脚本纯离线，不启动 AEDT。
"""
import json
import math
import os

import numpy as np

SRC = r"C:\wpt\coil_template_Rx.json"
WORK = r"C:\ansys maxwell2024\_work"
OUT_INS = os.path.join(WORK, "coil_template_Rx_4chord.json")
OUT_LEN = os.path.join(WORK, "coil_template_Rx_4chord_len.json")
OUT_REP = os.path.join(WORK, "tmpl_4chord_report.json")

TURN_ARC = 1.0          # 单段转角阈值（度）：>1 视为弧段
N_CHORD_ARC = 4         # 每角弦数（目标）
N_CHORD_STRAIGHT = 1    # 直边弦数

P3 = np.array(json.load(open(SRC, encoding="utf-8")), dtype=float)
if P3.ndim != 2:
    raise SystemExit("模板格式异常: %s" % (P3.shape,))
if P3.shape[1] == 2:
    P3 = np.hstack([P3, np.zeros((len(P3), 1))])
P = P3[:, :2]
N = len(P)
print("原路径: %d 点 / %d 段   shape=%s" % (N, N - 1, P3.shape))


def seg_len(a, b):
    return float(math.hypot(b[0] - a[0], b[1] - a[1]))


def turn_deg(i):
    """点 i 处的转角（度，带符号）：seg(i-1->i) 与 seg(i->i+1) 的夹角。"""
    a0 = math.atan2(P[i][1] - P[i - 1][1], P[i][0] - P[i - 1][0])
    a1 = math.atan2(P[i + 1][1] - P[i][1], P[i + 1][0] - P[i][0])
    d = math.degrees(a1 - a0)
    while d > 180:
        d -= 360
    while d < -180:
        d += 360
    return d


# ---------------- 1) 分段：按点 i (1..N-2) 的转角切 run ----------------
turns = [0.0] + [turn_deg(i) for i in range(1, N - 1)] + [0.0]
kind = ["arc" if abs(t) > TURN_ARC else "straight" for t in turns]
runs = []                      # [(kind, i0, i1)] 点区间闭区间
i = 0
while i < N:
    j = i
    while j + 1 < N and kind[j + 1] == kind[i]:
        j += 1
    runs.append((kind[i], i, j))
    i = j + 1

n_arc = sum(1 for r in runs if r[0] == "arc")
n_str = sum(1 for r in runs if r[0] == "straight")
arc_chords = [r[2] - r[1] for r in runs if r[0] == "arc"]
str_chords = [r[2] - r[1] for r in runs if r[0] == "straight"]
print("run 数: 弧 %d / 直 %d" % (n_arc, n_str))
print("每弧弦数: %s" % (sorted(set(arc_chords))))
print("每直边弦数: %s" % (sorted(set(str_chords))))
print("弧总弦数 %d + 直总弦数 %d = %d（应 = %d）"
      % (sum(arc_chords), sum(str_chords), sum(arc_chords) + sum(str_chords), N - 1))


def fit_circle(Q):
    n = len(Q)
    mx, my = Q[:, 0].mean(), Q[:, 1].mean()
    u, v = Q[:, 0] - mx, Q[:, 1] - my
    suu, svv, suv = (u * u).sum(), (v * v).sum(), (u * v).sum()
    suuu, svvv = (u ** 3).sum(), (v ** 3).sum()
    suvv, svuu = (u * v * v).sum(), (v * u * u).sum()
    det = suu * svv - suv * suv
    if abs(det) < 1e-12:
        return None, None
    c1, c2 = (suuu + suvv) / 2, (svvv + svuu) / 2
    uc = (c1 * svv - c2 * suv) / det
    vc = (c2 * suu - c1 * suv) / det
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    return np.array([mx + uc, my + vc]), r


def resample_arc(qs, mode):
    """弧 run 的点列 qs（k+1 点，k 段弦）-> n 段弦的点列。"""
    k = len(qs) - 1
    n = min(N_CHORD_ARC, k)
    if n < 1:
        return list(qs)
    ctr, r = fit_circle(np.array(qs))
    if ctr is None:
        return list(qs)
    a = [math.atan2(p[1] - ctr[1], p[0] - ctr[0]) for p in qs]
    # 连续化角度
    for t in range(1, len(a)):
        d = a[t] - a[t - 1]
        while d > math.pi:
            a[t] -= 2 * math.pi
            d = a[t] - a[t - 1]
        while d < -math.pi:
            a[t] += 2 * math.pi
            d = a[t] - a[t - 1]
    a0, a1 = a[0], a[-1]
    theta = abs(a1 - a0)                       # 该 run 的总转角（弧度）
    if theta < 1e-9:
        return list(qs)
    rr = r
    if mode == "length":
        phi = theta / n
        rr = r * theta / (2.0 * n * math.sin(phi / 2.0))
    out = []
    for t in range(n + 1):
        ang = a0 + (a1 - a0) * t / float(n)
        out.append((ctr[0] + rr * math.cos(ang), ctr[1] + rr * math.sin(ang)))
    return out


def build(mode):
    pts = []
    for idx, (kd, i0, i1) in enumerate(runs):
        qs = [tuple(P[i]) for i in range(i0, i1 + 1)]
        if kd == "arc":
            new = resample_arc(qs, mode)
        else:
            new = [qs[0], qs[-1]] if N_CHORD_STRAIGHT == 1 else list(qs)
        if idx == 0:
            pts.extend(new)
        else:
            pts.extend(new[1:])               # 共享连接点
    return np.array(pts, dtype=float)


def polyline_len(A):
    return float(sum(seg_len(A[i - 1], A[i]) for i in range(1, len(A))))


def dist_to_polyline(pt, A):
    best = 1e9
    for i in range(1, len(A)):
        ax, ay = A[i - 1]
        bx, by = A[i]
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        if L2 < 1e-18:
            t = 0.0
        else:
            t = ((pt[0] - ax) * vx + (pt[1] - ay) * vy) / L2
            t = max(0.0, min(1.0, t))
        dx = pt[0] - (ax + t * vx)
        dy = pt[1] - (ay + t * vy)
        d = math.hypot(dx, dy)
        if d < best:
            best = d
    return best


def densify(A, step=0.25):
    out = []
    for i in range(1, len(A)):
        a, b = A[i - 1], A[i]
        L = seg_len(a, b)
        k = max(1, int(math.ceil(L / step)))
        for t in range(k):
            f = t / float(k)
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    out.append((A[-1][0], A[-1][1]))
    return np.array(out)


def cheb(A):
    return np.maximum(np.abs(A[:, 0]), np.abs(A[:, 1]))


# ---------------- 2) 自检：8 弦重建应还原原路径 ----------------
chk = build("inscribed")     # 这是 4 弦版；下面另做 8 弦自检
N_CHORD_ARC_HOLD = N_CHORD_ARC
N_CHORD_ARC = 8
chk8 = build("inscribed")
N_CHORD_ARC = N_CHORD_ARC_HOLD
d8 = max(dist_to_polyline(tuple(p), chk8) for p in P)
print("\n[自检] 8 弦重建 vs 原路径: 点数 %d, 最大偏差 %.6f mm" % (len(chk8), d8))

report = dict(src=SRC, n_src=N, arc_runs=n_arc, straight_runs=n_str,
              arc_chords_sorted=sorted(set(arc_chords)),
              straight_chords_sorted=sorted(set(str_chords)),
              selftest_8chord_n=len(chk8), selftest_8chord_dev=d8)

# ---------------- 3) 4 弦模板 + 偏差评估 ----------------
s_old = cheb(P)
L_old = polyline_len(P)
for mode, outp in (("inscribed", OUT_INS), ("length", OUT_LEN)):
    A = build(mode)
    L_new = polyline_len(A)
    s_new = cheb(A)
    # 双向偏差
    d_fwd = max(dist_to_polyline(tuple(p), A) for p in P)             # 原点 -> 新线
    Ad = densify(A, 0.25)
    d_bwd = max(dist_to_polyline(tuple(p), P) for p in Ad[::4])       # 新线 -> 原点
    bb_o = [P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max()]
    bb_n = [A[:, 0].min(), A[:, 1].min(), A[:, 0].max(), A[:, 1].max()]
    info = dict(mode=mode, n=len(A), segs=len(A) - 1,
                len_old=L_old, len_new=L_new,
                len_pct=100 * (L_new - L_old) / L_old,
                s0_old=float(s_old[0]), s0_new=float(s_new[0]),
                s_max_old=float(s_old.max()), s_max_new=float(s_new.max()),
                dev_fwd=d_fwd, dev_bwd=d_bwd,
                bbox_old=[float(v) for v in bb_o], bbox_new=[float(v) for v in bb_n],
                bbox_diff=[float(bb_n[i] - bb_o[i]) for i in range(4)])
    report[mode] = info
    print("\n[%s] 点数 %d / 段 %d  (原 768/767)" % (mode, info["n"], info["segs"]))
    print("  路径长 %.4f -> %.4f mm  (%+.4f%%)" % (L_old, L_new, info["len_pct"]))
    print("  s0 %.4f -> %.4f   s_max %.4f -> %.4f"
          % (info["s0_old"], info["s0_new"], info["s_max_old"], info["s_max_new"]))
    print("  偏差: 原点->新线 %.4f mm   新线->原点 %.4f mm" % (d_fwd, d_bwd))
    print("  bbox 差 %s" % (["%+.4f" % v for v in info["bbox_diff"]]))
    z = float(P3[0, 2]) if P3.shape[1] > 2 else 0.0
    json.dump([[float(p[0]), float(p[1]), z] for p in A],
              open(outp, "w", encoding="utf-8"))
    print("  -> %s" % outp)

json.dump(report, open(OUT_REP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("\n报告 -> %s" % OUT_REP)
