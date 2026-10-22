# -*- coding: utf-8 -*-
"""生成 b1_0186 案例的全部结构图（离线，不接触 AEDT）。

图：
  fig2_top_view.png   俯视结构图（XY 平面，含尺寸标注与扫描范围）
  fig3_section_xz.png XZ 剖面结构图（y=0 真实切割）
  fig4_iso3d.png      三维轴测结构图（真实扫掠铜带 + 铁氧体条）
  fig5_sweep_curve.png 实测互感-位移曲线（run0 真实已解数据 + 镜像展开）
  fig6_flow.png       工艺步骤 / 动作关系流程图
"""
import csv
import json
import math
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch, FancyBboxPatch, Polygon
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 130

FIGDIR = r"C:\ansys maxwell2024\_work\case_figures"
GEOM = os.path.join(FIGDIR, "geom_b1_0186.json")
RAW0 = r"C:\ansys maxwell2024\_work\b1\b1_raw_run0.csv"

C_COPPER = "#C87137"
C_COPPER_D = "#8C4A1E"
C_FERRITE = "#7A8B99"
C_AIR = "#2E86C1"
C_RX = "#1E8449"
C_BG = "#FFFFFF"

G = json.load(open(GEOM, encoding="utf-8"))
P = np.array(G["path"], dtype=float)          # 768 x 2，中心在原点
CX = {c: G["place"][c + "_cx"] for c in ("tx1", "tx2", "rx")}
PZ = G["coil"]["plane_z"]
W = G["coil"]["width"]
H = G["coil"]["height"]


# ---------------------------------------------------------------- 工具
def coil_path(which):
    """返回某线圈的中心线 XY（已按摆位平移）。"""
    Q = P.copy()
    Q[:, 0] += CX[which]
    return Q


def section_cross(which, y0=0.0):
    """求线圈中心线在 y=y0 平面上的所有交点 x（真实切割）。"""
    Q = coil_path(which)
    xs = []
    for i in range(len(Q) - 1):
        y1, y2 = Q[i, 1], Q[i + 1, 1]
        if (y1 - y0) * (y2 - y0) <= 0 and abs(y2 - y1) > 1e-12:
            t = (y0 - y1) / (y2 - y1)
            xs.append(Q[i, 0] + t * (Q[i + 1, 0] - Q[i, 0]))
    xs = sorted(xs)
    # 合并重复（相邻段共享端点）
    out = []
    for x in xs:
        if not out or abs(x - out[-1]) > 0.05:
            out.append(x)
    return out


def ribbon_quads(which, ztop):
    """把铜带顶面离散成四边形（用于三维轴测）。"""
    Q = coil_path(which)
    c = Q.mean(axis=0)
    n = len(Q)
    outer, inner = np.zeros_like(Q), np.zeros_like(Q)
    for i in range(n):
        a, b = Q[(i - 1) % n], Q[(i + 1) % n]
        t = b - a
        nt = np.array([t[1], -t[0]])
        ln = np.linalg.norm(nt)
        if ln < 1e-12:
            nt = np.array([1.0, 0.0]); ln = 1.0
        nt = nt / ln
        sgn = 1.0 if np.dot(nt, Q[i] - c) >= 0 else -1.0
        outer[i] = Q[i] + sgn * (W / 2.0) * nt
        inner[i] = Q[i] - sgn * (W / 2.0) * nt
    quads = []
    for i in range(n - 1):
        o1, o2, i2, i1 = outer[i], outer[i + 1], inner[i + 1], inner[i]
        quads.append([(o1[0], o1[1], ztop), (o2[0], o2[1], ztop),
                      (i2[0], i2[1], ztop), (i1[0], i1[1], ztop)])
    return quads


def lead_points(which):
    """引线（用于俯视/轴测的简化折线）。Tx: 竖直段 + 沿 -Y 出线；Rx: 竖直段到 z=75。"""
    Q = coil_path(which)
    e0, e1 = Q[0], Q[-1]
    return e0, e1


# ---------------------------------------------------------------- 图2 俯视图
def fig_top():
    fig, ax = plt.subplots(figsize=(13.2, 8.2))
    R = G["region"]
    d = G["derived"]

    # 空气域
    ax.add_patch(Rectangle((R["x"][0], R["y"][0]), R["x"][1] - R["x"][0],
                           R["y"][1] - R["y"][0], fill=False, ec=C_AIR,
                           lw=1.8, ls="--", zorder=1))
    ax.text(R["x"][0] + 8, R["y"][1] - 16,
            "空气域 Region  X ∈ [−420, +420] mm，Y ∈ [−134.94, +161] mm\n"
            "（固定盒，全批 256 工况不变；−Y 面 = 发射引线端子面）",
            color=C_AIR, fontsize=9.5, va="top", zorder=9)

    # 铁氧体条
    yh = G["ferrite"]["y_half"]
    for x in G["ferrite"]["tx_bar_x"]:
        ax.add_patch(Rectangle((x - d["tx_bar_w"] / 2, -yh), d["tx_bar_w"], 2 * yh,
                               fc=C_FERRITE, ec="none", alpha=0.40, zorder=2))
    for x in G["ferrite"]["rx_bar_x"]:
        ax.add_patch(Rectangle((x - d["rx_bar_w"] / 2, -yh), d["rx_bar_w"], 2 * yh,
                               fc=C_RX, ec="none", alpha=0.28, zorder=2))

    # 线圈
    for which, col, lab, z in (("tx1", C_COPPER_D, "Tx1 发射线圈（下层 z=−0.325）", 5),
                               ("tx2", C_COPPER, "Tx2 发射线圈（上层 z=+0.325）", 5),
                               ("rx", C_RX, "Rx 接收线圈（z=+30）", 6)):
        Q = coil_path(which)
        ax.plot(Q[:, 0], Q[:, 1], color=col, lw=2.0, zorder=z, solid_capstyle="round")

    # 引线
    for which, col in (("tx1", C_COPPER_D), ("tx2", C_COPPER)):
        e0, e1 = lead_points(which)
        for e in (e0, e1):
            ax.plot([e[0], e[0]], [G["place"]["y_end"], e[1]], color=col,
                    lw=1.0, ls="-", zorder=4)
    e0, e1 = lead_points("rx")
    for e in (e0, e1):
        ax.plot([e[0]], [e[1]], marker="o", ms=4.5, color=C_RX, zorder=7)

    # 扫描范围
    S = d["sweep_span"]
    ax.annotate("", xy=(-S / 2, 150), xytext=(S / 2, 150),
                arrowprops=dict(arrowstyle="<->", color="#B03A2E", lw=1.6))
    ax.text(0, 155, "接收线圈扫描跨度 S = Lc(2+g) = %.1f mm（41 点，半扫 21 点）" % S,
            color="#B03A2E", ha="center", fontsize=9.5)
    for xs, ls in ((-S / 2, ":"), (S / 2, ":")):
        ax.axvline(xs, color="#B03A2E", ls=ls, lw=0.9, alpha=0.7, zorder=1)

    # 中心距标注
    yb = -yh - 12
    ax.annotate("", xy=(CX["tx1"], yb), xytext=(CX["tx2"], yb),
                arrowprops=dict(arrowstyle="<->", color="#333", lw=1.3))
    ax.text(0, yb - 12, "两发射线圈中心距 = Lc + 边沿间隙 = %.1f + %d = %.1f mm"
            % (G["vars"]["coil_size"], d["edge_gap"], d["center_dist"]),
            ha="center", fontsize=9.5, color="#333")

    # 尺寸标注：线圈铜带真实外轮廓（注意：文档口径 Lc 是标称值，
    # 真实几何 = 模板路径 x K_LC=1.013836，故外轮廓 187.35 而非 Lc+线宽=186.26）
    YBW = P[:, 1].max() - P[:, 1].min() + W
    XBW = P[:, 0].max() - P[:, 0].min() + W
    oh = XBW / 2.0
    yt = yh + 10
    ax.annotate("", xy=(CX["tx2"] - oh, yt), xytext=(CX["tx2"] + oh, yt),
                arrowprops=dict(arrowstyle="<->", color=C_COPPER_D, lw=1.2))
    ax.text(CX["tx2"], yt + 5,
            "线圈铜带外轮廓 X = %.2f mm，Y = %.2f mm\n"
            "（中心线外跨 %.2f；参数 Lc = %.2f 为文档标称口径，真实几何乘 K_LC = 1.013836）"
            % (XBW, YBW, 2 * G["coil"]["h_out"], G["vars"]["coil_size"]),
            color=C_COPPER_D, ha="center", fontsize=8.6)

    # 图例
    handles = [
        plt.Line2D([], [], color=C_COPPER_D, lw=2.4, label="Tx1 发射线圈（12 匝方螺旋，铜带 2×0.5 mm）"),
        plt.Line2D([], [], color=C_COPPER, lw=2.4, label="Tx2 发射线圈（与 Tx1 同参数，x 镜像摆位）"),
        plt.Line2D([], [], color=C_RX, lw=2.4, label="Rx 接收线圈（可沿 X 平动）"),
        Rectangle((0, 0), 1, 1, fc=C_FERRITE, alpha=0.40, label="Tx 铁氧体条（16 条，宽 %.2f mm，节距 30 mm）" % d["tx_bar_w"]),
        Rectangle((0, 0), 1, 1, fc=C_RX, alpha=0.28, label="Rx 铁氧体条（8 条，宽 %.2f mm，节距 30 mm）" % d["rx_bar_w"]),
        plt.Line2D([], [], color=C_AIR, ls="--", lw=1.8, label="空气域 Region 边界"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=9, framealpha=0.95)

    ax.set_aspect("equal")
    ax.set_xlim(-440, 440)
    ax.set_ylim(-190, 200)
    ax.set_xlabel("X (mm)  —— 接收线圈平动方向 / 发射线圈排布方向")
    ax.set_ylabel("Y (mm)  —— 引线出线方向（−Y）")
    ax.set_title("图 2  WPT 磁耦合机构 俯视结构图（工况 b1_0186，Maxwell 3D 模型真实几何）",
                 fontsize=13, pad=12)
    ax.grid(alpha=0.22, lw=0.5)
    fig.tight_layout()
    p = os.path.join(FIGDIR, "fig2_top_view.png")
    fig.savefig(p, facecolor=C_BG); plt.close(fig)
    print("OK", p)


# ---------------------------------------------------------------- 图3 剖面
def fig_section():
    """(a) 真实比例剖面总览 + (b) 厚度放大的层叠详图。

    为什么要分两幅：铜带只有 2 x 0.5 mm，在 880 mm 宽的 1:1 剖面里不足 1 个像素，
    直接画会完全看不见 —— 所以 (a) 用加粗线+刻度表示铜带位置，(b) 把 Z 向放大来表达层序。
    """
    fig, (ax, ax2) = plt.subplots(
        2, 1, figsize=(13.2, 10.6),
        gridspec_kw=dict(height_ratios=[1.10, 1.00], hspace=0.28))
    R = G["region"]
    d = G["derived"]
    ztx = G["ferrite"]["z_tx"]
    zrx = G["ferrite"]["z_rx"]
    THX = 8.0        # 详图的 Z 向放大倍数

    # ================= (a) 1:1 剖面总览 =================
    ax.add_patch(Rectangle((R["x"][0], R["z"][0]), R["x"][1] - R["x"][0],
                           R["z"][1] - R["z"][0], fill=False, ec=C_AIR, lw=1.6, ls="--"))
    ax.text(-436, 86, "空气域 Region（固定盒）：X ∈ [−420, +420] mm，Z ∈ [−45, +75] mm",
            color=C_AIR, fontsize=9.5, va="top")

    for x in G["ferrite"]["tx_bar_x"]:
        ax.add_patch(Rectangle((x - d["tx_bar_w"] / 2, ztx[0]), d["tx_bar_w"],
                               ztx[1] - ztx[0], fc=C_FERRITE, ec="#44525C", lw=0.5))
    for x in G["ferrite"]["rx_bar_x"]:
        ax.add_patch(Rectangle((x - d["rx_bar_w"] / 2, zrx[0]), d["rx_bar_w"],
                               zrx[1] - zrx[0], fc=C_RX, ec="#145A32", lw=0.5, alpha=0.85))

    for which, col, zplane, lab, ty in (
            ("tx1", C_COPPER_D, PZ["Tx1"], "Tx1 铜带（剖面处 24 个截面）", 8),
            ("tx2", C_COPPER, PZ["Tx2"], "Tx2 铜带", -16),
            ("rx", C_RX, PZ["Rx"], "Rx 铜带", 36)):
        xs = section_cross(which, 0.0)
        ax.plot([min(xs), max(xs)], [zplane, zplane], color=col, lw=2.6,
                solid_capstyle="butt", zorder=6)
        ax.plot(xs, [zplane] * len(xs), "|", color=col, ms=10, mew=1.8, zorder=7)
        ax.text(min(xs) - 10, ty, lab, color=col, fontsize=9, va="center", ha="right")

    ax.annotate("", xy=(-392, -30), xytext=(-392, 30),
                arrowprops=dict(arrowstyle="<->", color="#7D3C98", lw=1.6))
    ax.text(-386, 0, "线圈—铁氧体气隙 30 mm\n（发射线圈 z≈0 → 接收平面 z=+30）",
            color="#7D3C98", fontsize=9, va="center")
    ax.annotate("", xy=(-330, ztx[1]), xytext=(-330, zrx[0]),
                arrowprops=dict(arrowstyle="<->", color="#7D3C98", lw=1.2))
    ax.text(-324, 16, "Tx 铁氧体上表面 z = −30\nRx 铁氧体下表面 z = +60",
            color="#7D3C98", fontsize=8.6, va="center")

    ax.text(0, -52, "Tx 铁氧体 16 条（宽 19.383 mm，节距 30 mm，厚 5.883 mm）",
            color="#44525C", fontsize=9, ha="center",
            bbox=dict(fc="#EEF2F5", ec="#44525C", alpha=0.95, boxstyle="round,pad=0.3"))
    ax.text(0, 70, "Rx 铁氧体 8 条（宽 15.234 mm，节距 30 mm，厚 6.872 mm）",
            color="#145A32", fontsize=9, ha="center",
            bbox=dict(fc="#EAF7EF", ec="#145A32", alpha=0.95, boxstyle="round,pad=0.3"))

    ax.set_aspect("equal")
    ax.set_xlim(-450, 450)
    ax.set_ylim(-62, 92)
    ax.set_xlabel("X (mm)")
    ax.set_ylabel("Z (mm)")
    ax.set_title("图 3(a)  XZ 剖面结构总览 —— y = 0 平面的真实切割，比例 1:1\n"
                 "（铜带实际仅 2 × 0.5 mm，在此比例下以加粗横线＋截面刻度表示；矩形块为铁氧体的真实截面）",
                 fontsize=11.2, pad=10)
    ax.grid(alpha=0.2, lw=0.5)

    # ================= (b) 层叠详图（Z 向放大） =================
    ax2.set_xlim(0, 100); ax2.set_ylim(-48, 104); ax2.axis("off")
    ax2.text(50, 100, "图 3(b)  Z 向层叠关系详图 —— 厚度按 %.0f 倍放大绘制（非等比），图中标注均为真实尺寸"
             % THX, ha="center", fontsize=11.2, fontweight="bold")

    x0, xw = 32, 26

    def zz(z):
        return z * THX

    # Tx 铁氧体
    ax2.add_patch(Rectangle((x0, zz(ztx[0])), xw, (ztx[1] - ztx[0]) * THX,
                            fc=C_FERRITE, ec="#44525C", lw=1.3))
    ax2.text(x0 + xw + 4, zz((ztx[0] + ztx[1]) / 2),
             "Tx 铁氧体（μr = 1000，σ = 0）\nz ∈ [−%.2f, −30.00] mm，厚 %.2f mm"
             % (-ztx[0], G["vars"]["tx_thick"]), fontsize=9.2, va="center")
    # Tx2 铜带 / 介质层 / Tx1 铜带
    ax2.add_patch(Rectangle((x0, zz(PZ["Tx2"] - H / 2)), xw, H * THX,
                            fc=C_COPPER, ec="#5E2F12", lw=1.2))
    ax2.add_patch(Rectangle((x0, zz(PZ["Tx2"] + H / 2)), xw,
                            (PZ["Tx1"] - H / 2 - (PZ["Tx2"] + H / 2)) * THX,
                            fc="#F7DC6F", ec="#B7950B", lw=1.0, hatch="///"))
    ax2.add_patch(Rectangle((x0, zz(PZ["Tx1"] - H / 2)), xw, H * THX,
                            fc=C_COPPER_D, ec="#5E2F12", lw=1.2))
    ax2.annotate("", xy=(x0 - 5, zz(PZ["Tx2"] - H / 2)),
                 xytext=(x0 - 5, zz(PZ["Tx1"] + H / 2)),
                 arrowprops=dict(arrowstyle="<->", color="#B7950B", lw=1.5))
    ax2.text(x0 - 7, zz(0.4),
             "Tx2 铜带  z = −0.325 mm（厚 0.5）\n"
             "层间介质  0.15 mm\n"
             "Tx1 铜带  z = +0.325 mm（厚 0.5）\n"
             "（两发射线圈分两层，投影重叠也不相碰）",
             fontsize=9.2, ha="right", va="center", color="#7D6608")
    # 空气气隙
    ax2.annotate("", xy=(x0 + xw / 2, zz(0)), xytext=(x0 + xw / 2, zz(30)),
                 arrowprops=dict(arrowstyle="<->", color=C_AIR, lw=2.2))
    ax2.text(x0 + xw / 2 + 3, zz(15), "空气气隙 30 mm\n（磁耦合主路径）",
             fontsize=9.6, color=C_AIR, va="center")
    # Rx 铜带
    ax2.add_patch(Rectangle((x0, zz(PZ["Rx"] - H / 2)), xw, H * THX,
                            fc=C_RX, ec="#145A32", lw=1.2))
    ax2.text(x0 + xw + 4, zz(PZ["Rx"]), "Rx 铜带  z = +30.00 mm（厚 0.5 mm）",
             fontsize=9.2, va="center", color=C_RX)
    # Rx 铁氧体
    ax2.add_patch(Rectangle((x0, zz(zrx[0])), xw, (zrx[1] - zrx[0]) * THX,
                            fc=C_RX, ec="#145A32", lw=1.3, alpha=0.75))
    ax2.text(x0 + xw + 4, zz((zrx[0] + zrx[1]) / 2),
             "Rx 铁氧体（随接收线圈一起平动）\nz ∈ [+60.00, +%.2f] mm，厚 %.2f mm"
             % (zrx[1], G["vars"]["rx_thick"]), fontsize=9.2, va="center", color="#145A32")

    ax2.annotate("", xy=(8, zz(ztx[0])), xytext=(8, zz(zrx[1])),
                 arrowprops=dict(arrowstyle="<->", color="#555", lw=1.3))
    ax2.text(6, zz(16), "结构总层厚 %.2f mm\n（z 从 −%.2f 到 +%.2f）"
             % (zrx[1] - ztx[0], -ztx[0], zrx[1]),
             fontsize=9, color="#555", ha="right", va="center")
    ax2.text(50, -42,
             "注：铜带 0.5 mm 与介质层 0.15 mm 在 1:1 剖面中不足 1 个像素，"
             "故此处按 %.0f 倍放大绘制，目的是表达层序与相对位置。" % THX,
             ha="center", fontsize=9, color="#666")

    fig.subplots_adjust(left=0.055, right=0.975, top=0.925, bottom=0.055)
    p = os.path.join(FIGDIR, "fig3_section_xz.png")
    fig.savefig(p, facecolor=C_BG); plt.close(fig)
    print("OK", p)


# ---------------------------------------------------------------- 图4 轴测
def fig_iso():
    fig = plt.figure(figsize=(13.2, 8.6))
    ax = fig.add_subplot(111, projection="3d")
    d = G["derived"]
    yh = G["ferrite"]["y_half"]
    ztx = G["ferrite"]["z_tx"]
    zrx = G["ferrite"]["z_rx"]

    def add_box(x0, x1, y0, y1, z0, z1, color, alpha):
        v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                      [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]])
        f = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4],
             [2, 3, 7, 6], [1, 2, 6, 5], [0, 3, 7, 4]]
        pc = Poly3DCollection([v[i] for i in f], facecolor=color, edgecolor="none",
                              alpha=alpha)
        ax.add_collection3d(pc)

    for x in G["ferrite"]["tx_bar_x"]:
        add_box(x - d["tx_bar_w"] / 2, x + d["tx_bar_w"] / 2, -yh, yh,
                ztx[0], ztx[1], C_FERRITE, 0.85)
    for x in G["ferrite"]["rx_bar_x"]:
        add_box(x - d["rx_bar_w"] / 2, x + d["rx_bar_w"] / 2, -yh, yh,
                zrx[0], zrx[1], C_RX, 0.65)

    for which, col, ztop in (("tx1", C_COPPER_D, PZ["Tx1"] + H / 2),
                             ("tx2", C_COPPER, PZ["Tx2"] + H / 2),
                             ("rx", C_RX, PZ["Rx"] + H / 2)):
        q = ribbon_quads(which, ztop)
        pc = Poly3DCollection(q, facecolor=col, edgecolor="none", alpha=1.0)
        ax.add_collection3d(pc)

    # 空气域
    R = G["region"]
    for zz in (R["z"][0], R["z"][1]):
        ax.plot([R["x"][0], R["x"][1], R["x"][1], R["x"][0], R["x"][0]],
                [R["y"][0], R["y"][0], R["y"][1], R["y"][1], R["y"][0]],
                [zz] * 5, color=C_AIR, ls="--", lw=1.0, alpha=0.8)

    ax.set_xlim(-330, 330); ax.set_ylim(-180, 180); ax.set_zlim(-60, 90)
    ax.set_box_aspect((660, 360, 150))
    ax.view_init(elev=22, azim=-58)
    ax.set_xlabel("X (mm)"); ax.set_ylabel("Y (mm)"); ax.set_zlabel("Z (mm)")
    ax.set_title("图 4  WPT 磁耦合机构三维轴测结构图（工况 b1_0186：2 个发射线圈 + 1 个接收线圈 + 24 条铁氧体条）",
                 fontsize=12.5, pad=6)
    handles = [
        plt.Line2D([], [], color=C_COPPER_D, lw=3, label="Tx1 铜带（z=+0.325 mm）"),
        plt.Line2D([], [], color=C_COPPER, lw=3, label="Tx2 铜带（z=−0.325 mm）"),
        plt.Line2D([], [], color=C_RX, lw=3, label="Rx 铜带（z=+30 mm）"),
        plt.Line2D([], [], color=C_FERRITE, lw=6, label="Tx 铁氧体条 ×16（μr=1000，厚 %.2f mm）" % G["vars"]["tx_thick"]),
        plt.Line2D([], [], color=C_RX, lw=6, alpha=0.6, label="Rx 铁氧体条 ×8（厚 %.2f mm）" % G["vars"]["rx_thick"]),
        plt.Line2D([], [], color=C_AIR, ls="--", lw=1.4, label="空气域 Region 顶/底面"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=9)
    fig.tight_layout()
    p = os.path.join(FIGDIR, "fig4_iso3d.png")
    fig.savefig(p, facecolor=C_BG); plt.close(fig)
    print("OK", p)


# ---------------------------------------------------------------- 图5 实测曲线
def read_case_rows(case="b1_0186", path=RAW0):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["case_id"] == case:
                rows.append(r)
    rows.sort(key=lambda r: float(r["x_mm"]))
    return rows


def fig_curve():
    rows = read_case_rows()
    xs = [float(r["x_mm"]) for r in rows]
    M13 = [float(r["M13"]) for r in rows]
    M23 = [float(r["M23"]) for r in rows]
    L11 = [float(r["L11"]) for r in rows]
    L22 = [float(r["L22"]) for r in rows]
    L33 = [float(r["L33"]) for r in rows]
    meshes = [r["mesh"] for r in rows]

    # 镜像展开（M1(x)=M2(-x)）
    full = [(-x, m2, m1) for x, m1, m2 in zip(xs, M13, M23)][::-1][:-1] \
        + list(zip(xs, M13, M23))
    fx = [p[0] for p in full]; fM1 = [p[1] for p in full]; fM2 = [p[2] for p in full]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12.4, 8.6), sharex=True,
                                   gridspec_kw=dict(height_ratios=[2.0, 1.0]))
    ax1.plot(xs, M13, "o-", color=C_COPPER_D, lw=1.9, ms=5,
             label="M13 = M(Tx1<->Rx)  实测（半扫 x ≥ 0）")
    ax1.plot(xs, M23, "s-", color=C_RX, lw=1.9, ms=5,
             label="M23 = M(Tx2<->Rx)  实测（半扫 x ≥ 0）")
    ax1.plot(fx, fM1, ":", color=C_COPPER_D, lw=1.1, alpha=0.65,
             label="M13 镜像展开（M13(x) = M23(−x)）")
    ax1.plot(fx, fM2, ":", color=C_RX, lw=1.1, alpha=0.65,
             label="M23 镜像展开")
    ax1.axhline(0, color="#888", lw=0.8)
    ax1.set_ylabel("互感 (μH)")
    ax1.set_title("图 5  接收线圈沿 X 平动时的互感曲线（b1_0186 真实已解数据，run0 实例，共 %d 个已解点）"
                  % len(xs), fontsize=12.5)
    ax1.legend(fontsize=9, loc="upper left")
    ax1.grid(alpha=0.25, lw=0.5)
    ax1.annotate("M23 在 x≈%.0f mm 达峰值 %.2f μH ——\n接收线圈正对 Tx2 时耦合最强"
                 % (xs[int(np.argmax(M23))], max(M23)),
                 xy=(xs[int(np.argmax(M23))], max(M23)),
                 xytext=(xs[int(np.argmax(M23))] - 160, max(M23) - 1.6),
                 fontsize=9, color=C_RX,
                 arrowprops=dict(arrowstyle="->", color=C_RX, lw=1.2))
    k13 = [float(r["k13"]) for r in rows]
    k23 = [float(r["k23"]) for r in rows]
    ax2.plot(xs, k23, "^-", color=C_RX, lw=1.7, ms=5, label="k23 耦合系数（Rx<->Tx2）")
    ax2.plot(xs, k13, "v-", color=C_COPPER_D, lw=1.7, ms=5, label="k13 耦合系数（Rx<->Tx1）")
    ax2.set_xlabel("接收线圈位移 x (mm)")
    ax2.set_ylabel("耦合系数 k")
    ax2.legend(fontsize=9)
    ax2.grid(alpha=0.25, lw=0.5)

    txt = ("网格口径分布：" + "、".join(
        "%s %d 点" % (m, meshes.count(m)) for m in sorted(set(meshes))) +
        "\n自感实测：L11 ≈ %.2f μH，L22 ≈ %.2f μH，L33 ≈ %.2f μH（%d 点；L33 随位置波动约 1%%）"
        % (np.mean(L11), np.mean(L22), np.mean(L33), len(xs)))
    ax2.text(0.99, 0.06, txt, transform=ax2.transAxes, ha="right", va="bottom",
             fontsize=8.8, bbox=dict(fc="#FBF5E8", ec="#B7950B", alpha=0.95,
                                     boxstyle="round,pad=0.45"))
    fig.tight_layout()
    p = os.path.join(FIGDIR, "fig5_sweep_curve.png")
    fig.savefig(p, facecolor=C_BG); plt.close(fig)
    print("OK", p)


# ---------------------------------------------------------------- 图6 流程
def fig_flow():
    fig, ax = plt.subplots(figsize=(13.6, 9.4))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")

    def box(x, y, w, h, text, fc, ec, fs=9.2, bold=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.6",
                                    fc=fc, ec=ec, lw=1.5))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs,
                fontweight="bold" if bold else "normal", linespacing=1.45)

    def arrow(x1, y1, x2, y2, col="#555", ls="-", txt=None, dx=1.4):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>",
                                     mutation_scale=15, color=col, lw=1.6,
                                     linestyle=ls,
                                     connectionstyle="arc3,rad=0.0"))
        if txt:
            ax.text((x1 + x2) / 2 + dx, (y1 + y2) / 2, txt, fontsize=8.4, color=col,
                    va="center")

    ax.text(50, 97.5, "图 6  工艺步骤（建模 → 求解 → 采集）与动作关系流程图",
            ha="center", fontsize=13.5, fontweight="bold")

    # 左列：输入
    box(1, 80, 21, 12,
        "① 输入：7 个主变量\n"
        "Lc=184.2572 mm\n hole_ratio=0.3702\n tx_fill=0.6461 / rx_fill=0.5078\n"
        "tx_thick=5.8831 / rx_thick=6.8723 mm\n spacing_ratio g=0.3304",
        "#EAF2F8", C_AIR, 8.6)
    box(1, 63.5, 21, 12,
        "② 派生几何（wpt_contract.derived）\n"
        "Tx 条宽 19.383 mm / Rx 条宽 15.234 mm\n"
        "条长 221 mm（=1.2·Lc 取整）\n"
        "边沿间隙 tg 61 mm（=g·Lc 取整）\n"
        "中心距 245.26 mm，扫描跨度 429.39 mm",
        "#EAF2F8", C_AIR, 8.6)
    box(1, 47, 21, 12,
        "③ 线圈路径生成（coil_gen.make_path）\n"
        "768 点模板 → 环半径径向重映射\n"
        "h_out=93.403 / h_in=34.578 mm\n"
        "12 匝，直边最小净间隙 2.931 mm\n"
        "（≥1.5 mm → 走 OPT 网格口径）",
        "#EAF2F8", C_AIR, 8.6)
    box(1, 30.5, 21, 12,
        "④ 三线圈建模（rebuild_all）\n"
        "铜带扫掠：矩形截面 2.0×0.5 mm\n"
        "角部圆角，Corner 折弯\n"
        "引线 φ0.6 mm：Tx 先竖直再沿 −Y 出线；\n"
        "Rx 竖直向上到 z=+75\n"
        "Unite → 端面 → Assign Coil → Winding",
        "#FEF5E7", C_COPPER_D, 8.6)
    box(1, 14, 21, 12,
        "⑤ 摆位与铁氧体（set_tx_gap + build_ferrite）\n"
        "Tx1 中心 x=−123.629 / Tx2 x=+123.629\n"
        "Tx 铁氧体 16 条（z −35.88…−30）\n"
        "Rx 铁氧体 8 条（z +60…+66.87）\n"
        "Rx 引线处开 φ2 mm 通孔\n"
        "铜带分层：Tx1 z=+0.325 / Tx2 z=−0.325",
        "#FEF5E7", C_COPPER_D, 8.6)

    # 中间列：求解
    box(27, 80, 22, 12,
        "⑥ 空气域（ensure_region）\n"
        "固定盒 Region\n"
        "X ∈ [−420, +420] mm\n"
        "Y ∈ [−134.94, +161] mm\n"
        "Z ∈ [−45, +75] mm\n"
        "（−Y 面贴发射端子面、+Z 面贴接收端子面）",
        "#EAF2F8", C_AIR, 8.6)
    box(27, 63.5, 22, 12,
        "⑦ 材料与激励（工程预置）\n"
        "铜：σ=5.8×10⁷ S/m\n"
        "铁氧体：μr=1000，σ=0，各向同性\n"
        "Winding_Tx1 = 10 A\n Winding_Tx2 = 10 A\n"
        "Winding_Rx = 0 A（开路侧，只取互感）\n"
        "求解类型：Maxwell 3D Magnetostatic",
        "#EAF2F8", C_AIR, 8.6)
    box(27, 45.5, 22, 13,
        "⑧ 接收位置设置（set_rx_dx）\n"
        "每点：先移到 x+0.05 再移回 x\n"
        "→ 强制网格失效，逐点独立求解\n"
        "半扫 21 点：x = i·S/40，i=0…20\n"
        "（x = 0 … 214.696 mm，步长 10.735 mm）",
        "#FEF9E7", "#B7950B", 8.6)
    box(27, 28.5, 22, 12.5,
        "⑨ 网格与求解（solve_and_extract）\n"
        "OPT 口径：TAU Flex 柔性网格 + Region 粗化\n"
        "(Lc/5=36.85 mm) + PercentRefinement 10\n"
        "+ RelativeResidual 1e−5\n"
        "自适应：MaximumPasses 8 / PercentError 5%\n"
        "迭代求解器，8 核并行",
        "#FEF9E7", "#B7950B", 8.6)
    box(27, 11.5, 22, 12.5,
        "⑩ 后处理提取（get_solution_data）\n"
        "表达式 Lmatrix.L(Winding_i, Winding_j)\n"
        "→ 3×3 电感矩阵\n"
        "L11 / L22 / L33 / M12 / M13 / M23\n"
        "k13 = M13/√(L11·L33)，k23 = M23/√(L22·L33)\n"
        "解完即删场数据（控制磁盘占用）",
        "#FEF9E7", "#B7950B", 8.6)

    # 右列：输出
    box(54, 80, 21, 12,
        "(11) 逐点原始结果（真值来源）\n"
        "b1_raw_runK.csv，15 列\n"
        "case_id,i,x_mm,L11,L22,L33,M12,M13,M23,\n"
        "k13,k23,minutes,aedt_pid,ts,mesh\n"
        "断点续跑的唯一依据",
        "#EAFAF1", C_RX, 8.6)
    box(54, 63.5, 21, 12,
        "(12) 镜像展开 → 41 点曲线\n"
        "M1(x<0) = M2(−x)\n M2(x<0) = M1(−x)\n"
        "自检：镜像和口径 ≤2%，个体 ≤3%\n"
        "关键指标：M_sum = M1+M2 不受镜像影响",
        "#EAFAF1", C_RX, 8.6)
    box(54, 45.5, 21, 13,
        "(13) 契约四表（contract_merge）\n"
        "b1_cases.csv（每工况一行）\n"
        "b1_curves.csv（每工况 41 行）\n"
        "b1_selfcheck.csv（自检）\n"
        "b1_diag.csv（诊断，非契约）",
        "#EAFAF1", C_RX, 8.6)
    box(54, 28.5, 21, 12.5,
        "(14) 交付闸门（b1_deliver.py）\n"
        "口径合规 + 分片覆盖 + 缺口登记\n"
        "退出码 0=可交付 / 1=未就绪 / 2=校验失败\n"
        "由计划任务每 30 min 自动运行",
        "#EAFAF1", C_RX, 8.6)
    box(54, 11.5, 21, 12.5,
        "(15) 交付软件端\n"
        "目标量：M_sum（和口径）、M_pp（原边互感）、\n"
        "V_rx（接收铁氧体体积）等\n"
        "用途：代理模型 / 参数寻优",
        "#EAFAF1", C_RX, 8.6)

    # 竖箭头（左列）
    for y in (80, 63.5, 47, 30.5):
        arrow(11.5, y, 11.5, y - 2.5)
    # 左→中
    arrow(22.3, 36.5, 27, 34.5, txt="几何就绪", dx=-9.6)
    # 中列竖箭头
    for y in (80, 63.5, 45.5, 28.5):
        arrow(38, y, 38, y - 2.0)
    # 中→右
    arrow(49.3, 17.5, 54, 17.5)
    # 右列竖箭头
    for y in (80, 63.5, 45.5, 28.5):
        arrow(64.5, y, 64.5, y - 2.5)
    # 反馈回路
    arrow(75, 15, 79, 15, col="#B03A2E")
    ax.add_patch(FancyArrowPatch((79, 15), (79, 88), arrowstyle="-", color="#B03A2E",
                                 lw=1.5, linestyle="--"))
    ax.add_patch(FancyArrowPatch((79, 88), (38, 88), arrowstyle="-|>", color="#B03A2E",
                                 lw=1.5, linestyle="--", mutation_scale=15))
    ax.text(79.6, 55, "断点续跑 / 失败重试回路\n（看门狗 1500 s 几何、2400 s 求解超时；\n"
                      "网格崩溃则本工况整套回退 BASE 口径；\n"
                      "会话存活超 7 h 主动轮换）",
            fontsize=8.4, color="#B03A2E", rotation=90, va="center", ha="center")

    ax.text(0.5, 5.5, "注：①…⑤ 为「建模工艺步骤」；⑥⑦ 为「物理环境与激励设置」；"
                      "⑧⑨⑩ 为「逐点求解动作」；(11)…(15) 为「数据产出动作」。",
            fontsize=9, color="#444")
    fig.tight_layout()
    p = os.path.join(FIGDIR, "fig6_flow.png")
    fig.savefig(p, facecolor=C_BG); plt.close(fig)
    print("OK", p)


if __name__ == "__main__":
    os.makedirs(FIGDIR, exist_ok=True)
    fig_top()
    fig_section()
    fig_iso()
    fig_curve()
    fig_flow()
    print("全部完成 ->", FIGDIR)
