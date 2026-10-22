# -*- coding: utf-8 -*-
"""离线复算 b1_0186 的精确几何（不启动 AEDT、不写工程）。

复用生产同一套代码：coil_gen(路径/引线/分层) + wpt_contract(派生量/铁氧体铺条)。
输出 JSON 供绘图脚本使用，同时打印人可读摘要。
"""
import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import coil_gen as CG          # noqa: E402
import wpt_contract as WC      # noqa: E402

OUT = r"C:\ansys maxwell2024\_work\case_figures\geom_b1_0186.json"

# ---- b1_0186 的 7 个主变量（来自 b1_plan.csv）----
V = dict(coil_size=184.2572, hole_ratio=0.3702, tx_fill=0.6461,
         rx_fill=0.5078, tx_thick=5.8831, rx_thick=6.8723, spacing_ratio=0.3304)

LC, KR, g = V["coil_size"], V["hole_ratio"], V["spacing_ratio"]
outer = CG.coil_outer(LC)
d = WC.derived(LC, g, V["tx_fill"], V["rx_fill"], V["rx_thick"])
tg = float(d["edge_gap"])

# ---- 线圈摆位（set_tx_gap 口径）----
tx1_cx = -tg / 2.0 - outer / 2.0
tx2_cx = tg / 2.0 + outer / 2.0
rx_cx = 0.0

# ---- 路径（中心线，三线圈同一路径，仅 x 平移与 z 分层不同）----
P = CG.make_path(LC, KR)
dims = CG.path_dims(LC, KR)

# ---- 铁氧体铺条（wpt_contract.build_ferrite 的排布规则）----
tx1_fc = -tg / 2.0 - LC / 2.0
tx2_fc = tg / 2.0 + LC / 2.0
emit_lo, emit_hi = tx1_fc - LC / 2.0, tx2_fc + LC / 2.0
tx_bar_x = WC._x_centers(emit_lo, emit_hi, d["tx_bar_w"])
rx_bar_x = WC._x_centers(-LC / 2.0, LC / 2.0, d["rx_bar_w"])

y_half = d["ferrite_len"] / 2.0

geom = dict(
    case_id="b1_0186",
    vars=V,
    derived=dict(
        tx_bar_w=round(d["tx_bar_w"], 4), rx_bar_w=round(d["rx_bar_w"], 4),
        ferrite_len=d["ferrite_len"], edge_gap=d["edge_gap"],
        center_dist=round(d["center_dist"], 4), sweep_span=round(d["sweep_span"], 4),
        n_points=d["n_points"], n_bars_rx=len(rx_bar_x), n_bars_tx=len(tx_bar_x),
        rx_volume=round(len(rx_bar_x) * d["rx_bar_w"] * V["rx_thick"] * d["ferrite_len"], 2),
    ),
    coil=dict(
        h_in=round(dims["h_in"], 4), h_out=round(dims["h_out"], 4),
        outer_edge=round(dims["outer"], 4), hole_edge=round(dims["hole"], 4),
        gap_min=round(dims["gap_min"], 4), neighbour_min=round(dims["neighbour_min"], 4),
        width=CG.WIDTH, height=CG.HEIGHT, turns=CG.TURNS, rad=CG.RAD,
        layer_gap=CG.LAYER_GAP, plane_z=CG.PLANE_Z, n_pts=len(P),
    ),
    place=dict(tx1_cx=round(tx1_cx, 4), tx2_cx=round(tx2_cx, 4), rx_cx=rx_cx,
               y_end=CG.Y_END, rx_z0=CG.RX_Z0, rx_ztop=CG.RX_ZTOP, vert=CG.VERT),
    ferrite=dict(tx_bar_x=[round(v, 3) for v in tx_bar_x],
                 rx_bar_x=[round(v, 3) for v in rx_bar_x],
                 y_half=y_half, z_tx=(-WC.Z_GAP - V["tx_thick"], -WC.Z_GAP),
                 z_rx=(WC.Z_GAP + 30.0, WC.Z_GAP + 30.0 + V["rx_thick"])),
    region=dict(x=(-420.0, 420.0), y=(-134.94, 161.0), z=(-45.0, 75.0)),
    sweep_half=[round(v, 4) for v in WC.sweep_positions_half(LC, g)],
    path=[[round(float(p[0]), 4), round(float(p[1]), 4)] for p in P],
)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(geom, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ---------------- 人可读摘要 ----------------
print("=" * 78)
print("b1_0186 几何复算（离线，同一套生产代码）")
print("=" * 78)
print("主变量 : " + "  ".join("%s=%.4f" % (k, v) for k, v in V.items()))
print("-" * 78)
print("线圈   : 12 匝方螺旋，铜带 %.2f(宽) x %.2f(厚) mm，角圆角"
      % (CG.WIDTH, CG.HEIGHT))
print("         中心线外跨 h_out=%.3f  内跨 h_in=%.3f  外边缘=%.2f  内孔边缘=%.2f mm"
      % (dims["h_out"], dims["h_in"], dims["outer"], dims["hole"]))
print("         直边最小净匝间隙 gap_min=%.3f mm  相邻匝最小间距=%.3f mm"
      % (dims["gap_min"], dims["neighbour_min"]))
print("         路径点数 = %d" % len(P))
print("         铜带平面 z: Tx1=%+.4f  Tx2=%+.4f  Rx=%+.1f (层间隙 %.2f mm)"
      % (CG.PLANE_Z["Tx1"], CG.PLANE_Z["Tx2"], CG.PLANE_Z["Rx"], CG.LAYER_GAP))
print("摆位   : Tx1 中心 x=%+.3f   Tx2 中心 x=%+.3f  (中心距 %.3f mm)"
      % (tx1_cx, tx2_cx, tx2_cx - tx1_cx))
print("         边沿间隙 tg=%d mm  -> 线圈外边缘间隙 = %.3f mm" % (tg, tg - CG.WIDTH))
print("-" * 78)
print("铁氧体 : 条长(2*y_half)=%d mm  Tx 条宽=%.3f Rx 条宽=%.3f mm  单元节距=%.1f mm"
      % (d["ferrite_len"], d["tx_bar_w"], d["rx_bar_w"], WC.UNIT))
print("         Tx %d 条: x 从 %+.2f 到 %+.2f (步距 %.1f)"
      % (len(tx_bar_x), tx_bar_x[0], tx_bar_x[-1], WC.UNIT))
print("         Rx %d 条: x 从 %+.2f 到 %+.2f (步距 %.1f)"
      % (len(rx_bar_x), rx_bar_x[0], rx_bar_x[-1], WC.UNIT))
print("         Tx 条 z ∈ [%.2f, %.2f]   Rx 条 z ∈ [%.2f, %.2f]"
      % (-WC.Z_GAP - V["tx_thick"], -WC.Z_GAP,
         WC.Z_GAP + 30.0, WC.Z_GAP + 30.0 + V["rx_thick"]))
print("-" * 78)
xh = WC.sweep_positions_half(LC, g)
print("扫描   : 半扫 %d 点  x = 0 .. %.3f mm，步长 %.4f mm（S=Lc(2+g)=%.3f）"
      % (len(xh), xh[-1], xh[1] - xh[0], d["sweep_span"]))
print("空气域 : X[%.0f,%.0f] Y[%.2f,%.0f] Z[%.0f,%.0f] mm"
      % (-420, 420, -134.94, 161, -45, 75))
print("=" * 78)
print("已写出 ->", OUT)
