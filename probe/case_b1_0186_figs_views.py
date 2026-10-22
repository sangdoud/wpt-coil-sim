# -*- coding: utf-8 -*-
"""b1_0186 —— 更多"工程制图"风格的视角图（与 fig2_top_view 同一形式）。

产出：
  fig7_front_view_xz.png   正立面图（XZ 投影，非剖切，1:1）
  fig8_side_view_yz.png    侧立面图（YZ 投影，1:1）
  fig9_iso_true.png        三维轴测图（真实位置，Rx 铁氧体半透明）
  fig10_rx_positions.png   接收线圈三个位置的俯视对比（三联，含实测 M/k）
  fig11_detail_turn.png    匝间间距与拐角局部放大（两联，1:1）
  fig12_ferrite_detail.png 铁氧体铺条规则详图（两联，含尺寸链）
  fig13_exploded_iso.png   分层爆炸轴测图（层间距人为拉开，便于读层序）

全部离线复算，不接触 AEDT。
绘制约定：所有二维视图一律 1:1 等比（不做 Z 向夸张），
         图幅按数据宽高比自动确定，避免等比坐标下的大片留白；
         铜带仅 2 x 0.5 mm，在立面/剖面里按"加粗带"表示并明确标注。
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
from matplotlib.patches import Rectangle, Polygon

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
C_RX_D = "#145A32"
C_BG = "#FFFFFF"

G = json.load(open(GEOM, encoding="utf-8"))
P = np.array(G["path"], dtype=float)
CXV = G["place"]
CX = {c: CXV[c + "_cx"] for c in ("tx1", "tx2", "rx")}
PZ = {"tx1": G["coil"]["plane_z"]["Tx1"],
      "tx2": G["coil"]["plane_z"]["Tx2"],
      "rx": G["coil"]["plane_z"]["Rx"]}
W = G["coil"]["width"]
H = G["coil"]["height"]
D = G["derived"]
FR = G["ferrite"]
REG = G["region"]
YH = FR["y_half"]
ZTX = FR["z_tx"]
ZRX = FR["z_rx"]

PB_X = (P[:, 0].min(), P[:, 0].max())
PB_Y = (P[:, 1].min(), P[:, 1].max())
CW_X = PB_X[1] - PB_X[0] + W
CW_Y = PB_Y[1] - PB_Y[0] + W
PATH_CX = (PB_X[0] + PB_X[1]) / 2.0

ZH = 1.6      # 铜带在立面/剖面中的等效加粗厚度（真实 0.5 mm）


def placed(which):
    Q = P.copy()
    Q[:, 0] += CX[which] - PATH_CX
    return Q


def bbox(which):
    Q = placed(which)
    return (Q[:, 0].min() - W / 2, Q[:, 0].max() + W / 2,
            Q[:, 1].min() - W / 2, Q[:, 1].max() + W / 2)


def endpoints(which):
    Q = placed(which)
    return Q[0], Q[-1]


def ribbon(which):
    Q = placed(which)
    n = len(Q)
    L = np.zeros_like(Q); R = np.zeros_like(Q)
    for i in range(n):
        a = Q[max(i - 1, 0)]; b = Q[min(i + 1, n - 1)]
        t = b - a
        nt = np.array([t[1], -t[0]])
        ln = np.linalg.norm(nt)
        if ln < 1e-12:
            nt = np.array([1.0, 0.0]); ln = 1.0
        nt = nt / ln
        L[i] = Q[i] + (W / 2.0) * nt
        R[i] = Q[i] - (W / 2.0) * nt
    return np.vstack([L, R[::-1]])


def leads_3d(which):
    Q = placed(which)
    e0, e1 = Q[0], Q[-1]
    segs = []
    if which in ("tx1", "tx2"):
        sgn = 1.0 if which == "tx1" else -1.0
        zrun = sgn * CXV["vert"]
        z0 = PZ[which] + sgn * H / 2.0
        for (px, py) in (e0, e1):
            segs.append([(px, py, z0), (px, py, zrun), (px, CXV["y_end"], zrun)])
    else:
        for (px, py) in (e0, e1):
            segs.append([(px, py, PZ["rx"] + H / 2.0), (px, py, CXV["rx_ztop"])])
    return segs


def fit_fig(fig, ax, ncols=1, nrows=1, target_w=13.5, left=1.35, right=0.45,
            top=1.25, bottom=1.05, wgap=0.70, hgap=1.10):
    """按数据宽高比精确设定图幅与子图边距。

    等比坐标（set_aspect("equal")）下不能用 tight_layout —— 它会与固定纵横比冲突。
    这里直接由数据范围反算每个子图的物理尺寸，再据此 set_size_inches + subplots_adjust，
    既消除了留白，也保证 1:1 不变形。
    """
    x0, x1 = ax.get_xlim(); y0, y1 = ax.get_ylim()
    ar = abs(x1 - x0) / abs(y1 - y0)
    pw = (target_w - left - right - wgap * (ncols - 1)) / ncols
    ph = pw / ar
    fw = target_w
    fh = top + bottom + ph * nrows + hgap * (nrows - 1)
    fig.set_size_inches(fw, fh)
    fig.subplots_adjust(left=left / fw, right=1 - right / fw,
                        bottom=bottom / fh, top=1 - top / fh,
                        wspace=(wgap / pw) if ncols > 1 else 0.0,
                        hspace=(hgap / ph) if nrows > 1 else 0.0)
    return fw, fh


def _text_boxes(fig):
    """收集图内所有可见文本的显示坐标包围盒（含图例框）。"""
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    items = []
    for ax in fig.axes:
        for t in list(ax.texts) + [ax.title, ax.xaxis.label, ax.yaxis.label]:
            s = t.get_text().strip()
            if not s:
                continue
            try:
                items.append((s, t.get_window_extent(rend)))
            except Exception:
                pass
        lg = ax.get_legend()
        if lg is not None:
            items.append(("[图例]", lg.get_window_extent(rend)))
    for t in fig.texts:
        s = t.get_text().strip()
        if s:
            try:
                items.append((s, t.get_window_extent(rend)))
            except Exception:
                pass
    return items


def check_text_overlap(fig, name, min_frac=0.005, pad_px=4.0):
    """报告文本之间的重叠（用于替代人眼检查排版）。

    pad_px：把每个文本框向外扩张的像素数。matplotlib 的 get_window_extent 不含
    bbox 圆角框的内边距（round,pad≈0.3~0.4 em），故必须外扩，否则会漏判"看起来
    已经贴上"的情况。重叠面积占较小文本框面积超过 min_frac 即记为一条。
    """
    items = _text_boxes(fig)
    bad = []
    boxes = [(s, b.x0 - pad_px, b.y0 - pad_px, b.x1 + pad_px, b.y1 + pad_px)
             for s, b in items]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            _, ax0, ay0, ax1, ay1 = boxes[i]
            _, bx0, by0, bx1, by1 = boxes[j]
            ix = min(ax1, bx1) - max(ax0, bx0)
            iy = min(ay1, by1) - max(ay0, by0)
            if ix <= 0.5 or iy <= 0.5:
                continue
            sa = (ax1 - ax0) * (ay1 - ay0)
            sb = (bx1 - bx0) * (by1 - by0)
            frac = (ix * iy) / min(sa, sb)
            if frac > min_frac:
                bad.append((frac, boxes[i][0], boxes[j][0]))
    bad.sort(reverse=True)
    tag = "OK  " if not bad else "!!  "
    print("%s[%s] 文本重叠 %d 处" % (tag, name, len(bad)))
    for frac, s1, s2 in bad[:10]:
        print("      %4.1f%%  「%s」 ×  「%s」"
              % (frac * 100, s1.replace("\n", "⏎")[:34], s2.replace("\n", "⏎")[:34]))
    return bad


def save(fig, path):
    """先做文字重叠自检，再落盘。"""
    check_text_overlap(fig, os.path.basename(path))
    fig.savefig(path, facecolor=C_BG)
    plt.close(fig)


# ============================================================ 图 7 正立面
def fig_front():
    """正立面图（精简排版：宁删不加）。

    * 图内**不再给三条铜带和各铁氧体面加文字**——颜色由右侧图例识别，
      各层的 z 值直接写在图例条目里；
    * 图内只保留 4 条标高标签，彼此间隔 45 / 30 / 45 mm，
      远大于 9 pt 文字在该比例下的高度（约 10 mm），从根上杜绝压字；
    * 底部只留一行注记，放在图幅白边。
    """
    fig, ax = plt.subplots(figsize=(16.0, 5.0))
    ax.add_patch(Rectangle((REG["x"][0], REG["z"][0]),
                           REG["x"][1] - REG["x"][0], REG["z"][1] - REG["z"][0],
                           fill=False, ec=C_AIR, lw=1.8, ls="--"))

    for x in FR["tx_bar_x"]:
        ax.add_patch(Rectangle((x - D["tx_bar_w"] / 2, ZTX[0]), D["tx_bar_w"],
                               ZTX[1] - ZTX[0], fc=C_FERRITE, ec="#44525C", lw=0.6))
    for x in FR["rx_bar_x"]:
        ax.add_patch(Rectangle((x - D["rx_bar_w"] / 2, ZRX[0]), D["rx_bar_w"],
                               ZRX[1] - ZRX[0], fc=C_RX, ec=C_RX_D, lw=0.6, alpha=0.8))

    for which, col in (("tx1", C_COPPER_D), ("tx2", C_COPPER), ("rx", C_RX)):
        b = bbox(which)
        z = PZ[which]
        ax.add_patch(Rectangle((b[0], z - ZH / 2), b[1] - b[0], ZH,
                               fc=col, ec="none", zorder=6))

    for z, txt, col in (
            (75, "+75　空气域顶面 = Rx 引线顶端", C_RX),
            (30, "+30　接收平面（Rx 铜带）", C_RX),
            (0, "≈0　　发射铜带平面（Tx1 上层 / Tx2 下层）", C_COPPER_D),
            (-45, "−45　空气域底面", C_AIR)):
        ax.plot([-420, -400], [z, z], color=col, lw=1.1, ls=":", zorder=3)
        ax.text(-396, z, txt, color=col, fontsize=9, va="center", ha="left", zorder=9,
                bbox=dict(fc="white", ec="none", alpha=0.9, boxstyle="round,pad=0.16"))

    ax.set_aspect("equal")
    ax.set_xlim(-450, 450); ax.set_ylim(-58, 88)
    ax.set_xlabel("X (mm) —— 线圈排布方向 / 接收线圈平动方向")
    ax.set_ylabel("Z (mm) —— 层叠方向（1:1）")
    ax.set_title("图 7  WPT 磁耦合机构 正立面图（XZ 投影视图，工况 b1_0186，比例 1:1）\n"
                 "沿 −Y 方向看：发射铜带在 z≈0、其铁氧体在下 30 mm；接收铜带在 z=+30、其铁氧体在上 30 mm",
                 fontsize=12, pad=9)
    ax.grid(alpha=0.2, lw=0.5)

    hs = [plt.Line2D([], [], color=C_COPPER_D, lw=3.4, label="Tx1 铜带（上层，12 匝）z = +0.325"),
          plt.Line2D([], [], color=C_COPPER, lw=3.4, label="Tx2 铜带（下层，12 匝）z = −0.325"),
          plt.Line2D([], [], color=C_RX, lw=3.4, label="Rx 铜带（12 匝）z = +30.000"),
          plt.Line2D([], [], color=C_FERRITE, lw=7,
                     label="Tx 铁氧体 ×16：z ∈ [−35.88, −30.00]\n宽 19.383 ／ 节距 30 ／ 厚 5.883"),
          plt.Line2D([], [], color=C_RX, lw=7, alpha=0.55,
                     label="Rx 铁氧体 ×8：z ∈ [+60.00, +66.87]\n宽 15.234 ／ 节距 30 ／ 厚 6.872"),
          plt.Line2D([], [], color=C_AIR, ls="--", lw=1.5,
                     label="空气域 Region（固定盒）\nX ∈ [−420, +420]，Z ∈ [−45, +75]")]
    fig.legend(handles=hs, loc="center right", bbox_to_anchor=(0.995, 0.50),
               fontsize=9, framealpha=0.96, title="图例", title_fontsize=9.5,
               labelspacing=0.9)

    fit_fig(fig, ax, target_w=16.0, left=1.40, right=3.60, top=1.50, bottom=1.60)
    fig.text(0.38, 0.030,
             "投影视图（非剖切）：线圈在 XZ 面上投影为实心横带，看不到匝间间隙；"
             "铜带实际厚 0.5 mm，为可见已加粗到 %.1f mm 等效厚度。" % ZH,
             ha="center", va="bottom", fontsize=8.8, color="#666")
    p = os.path.join(FIGDIR, "fig7_front_view_xz.png")
    save(fig, p)
    print("OK", p)


# ============================================================ 图 8 侧立面
def fig_side():
    """侧立面图（精简排版：宁删不加）。

    删掉了原来贴在铜带右侧的两条说明、铁氧体条长的长句、以及两段引线长说明；
    改为：图内只留 3 个短标签 + 一个图例（图例里写全几何量），
    空气域参数与画面解读放图幅白边。
    """
    fig, ax = plt.subplots(figsize=(11.4, 6.2))
    ax.add_patch(Rectangle((REG["y"][0], REG["z"][0]),
                           REG["y"][1] - REG["y"][0], REG["z"][1] - REG["z"][0],
                           fill=False, ec=C_AIR, lw=1.8, ls="--"))

    ax.add_patch(Rectangle((-YH, ZTX[0]), 2 * YH, ZTX[1] - ZTX[0],
                           fc=C_FERRITE, ec="#44525C", lw=1.0))
    ax.add_patch(Rectangle((-YH, ZRX[0]), 2 * YH, ZRX[1] - ZRX[0],
                           fc=C_RX, ec=C_RX_D, lw=1.0, alpha=0.8))

    yb0, yb1 = PB_Y[0] - W / 2, PB_Y[1] + W / 2
    for z, col in ((PZ["tx2"], C_COPPER), (PZ["tx1"], C_COPPER_D), (PZ["rx"], C_RX)):
        ax.add_patch(Rectangle((yb0, z - ZH / 2), yb1 - yb0, ZH,
                               fc=col, ec="none", zorder=6))

    for which, col in (("tx1", C_COPPER_D), ("tx2", C_COPPER), ("rx", C_RX)):
        for seg in leads_3d(which):
            ax.plot([p[1] for p in seg], [p[2] for p in seg], color=col, lw=1.5, zorder=7)
    e0, e1 = endpoints("rx")
    for e in (e0, e1):
        ax.plot([e[1]], [CXV["rx_ztop"]], "o", ms=5, color=C_RX, zorder=8)

    # 尺寸链 + 3 个短标签
    ax.annotate("", xy=(-YH, -42), xytext=(YH, -42),
                arrowprops=dict(arrowstyle="<->", color="#44525C", lw=1.4))
    ax.text(0, -42, "221", color="#44525C", ha="center", va="center", fontsize=9.5,
            zorder=9, bbox=dict(fc="white", ec="none", alpha=0.9,
                                boxstyle="round,pad=0.18"))
    ax.annotate("", xy=(CXV["y_end"], ZTX[0] - 2), xytext=(CXV["y_end"], 6),
                arrowprops=dict(arrowstyle="<->", color=C_AIR, lw=1.3))
    ax.text(CXV["y_end"] + 8, -22, "发射端子面\n y = −134.94", color=C_AIR, fontsize=9,
            va="center", ha="left", zorder=9,
            bbox=dict(fc="white", ec=C_AIR, lw=0.8, alpha=0.92,
                      boxstyle="round,pad=0.24"))
    ax.text(0, 82, "Rx 端子  z = +75", color=C_RX, fontsize=9, va="center",
            ha="center", zorder=9,
            bbox=dict(fc="white", ec=C_RX, lw=0.8, alpha=0.92,
                      boxstyle="round,pad=0.24"))

    ax.set_aspect("equal")
    ax.set_xlim(-190, 210); ax.set_ylim(-56, 92)
    ax.set_xlabel("Y (mm) —— 引线出线方向（−Y 为出线侧）")
    ax.set_ylabel("Z (mm) —— 1:1")
    ax.set_title("图 8  WPT 磁耦合机构 侧立面图（YZ 投影视图，工况 b1_0186，比例 1:1）",
                 fontsize=12, pad=9)
    ax.grid(alpha=0.2, lw=0.5)

    hs = [plt.Line2D([], [], color=C_COPPER_D, lw=3.4, label="Tx1 铜带（下层）z = +0.325"),
          plt.Line2D([], [], color=C_COPPER, lw=3.4, label="Tx2 铜带            z = −0.325"),
          plt.Line2D([], [], color=C_RX, lw=3.4, label="Rx 铜带              z = +30.000"),
          plt.Line2D([], [], color=C_FERRITE, lw=7,
                     label="Tx 铁氧体 ×16（YZ 投影重叠成整板）"),
          plt.Line2D([], [], color=C_RX, lw=7, alpha=0.55,
                     label="Rx 铁氧体 ×8（YZ 投影重叠成整板）"),
          plt.Line2D([], [], color=C_AIR, ls="--", lw=1.5, label="空气域 Region")]
    ax.legend(handles=hs, loc="lower right", fontsize=8.6, framealpha=0.96)

    fit_fig(fig, ax, target_w=11.4, left=1.35, right=0.50, top=2.35, bottom=1.75)
    fig.text(0.5, 1 - 0.34 / fig.get_size_inches()[1],
             "空气域 Region（固定盒）：Y ∈ [−134.94, +161] mm，Z ∈ [−45, +75] mm"
             "　—— 其 −Y 面必须落在发射端子面 y = −134.94 上",
             ha="center", va="top", fontsize=9.2, color=C_AIR)
    fig.text(0.5, 0.030,
             "沿 +X 方向看：铁氧体条长（Y 向）221 mm；两发射线圈的引线沿 −Y 出线，是本视向外轮廓的决定者。",
             ha="center", va="bottom", fontsize=8.8, color="#666")
    p = os.path.join(FIGDIR, "fig8_side_view_yz.png")
    save(fig, p)
    print("OK", p)


# ============================================================ 轴测工具
AZ = math.radians(-60.0)
EL = math.radians(25.0)
_COSA, _SINA = math.cos(AZ), math.sin(AZ)
_COSE, _SINE = math.cos(EL), math.sin(EL)
DV = np.array([_COSE * _COSA, _COSE * _SINA, _SINE])


def prp(pts):
    a = np.asarray(pts, dtype=float)
    u = -a[:, 0] * _SINA + a[:, 1] * _COSA
    v = -a[:, 0] * _COSA * _SINE - a[:, 1] * _SINA * _SINE + a[:, 2] * _COSE
    return np.column_stack([u, v])


def draw_box(ax, x0, x1, y0, y1, z0, z1, fc, ec, alpha=1.0, lw=0.7, zorder=3):
    faces = {
        (1, 0, 0): ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], 0.78),
        (-1, 0, 0): ([(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)], 0.78),
        (0, 1, 0): ([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], 0.62),
        (0, -1, 0): ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], 0.62),
        (0, 0, 1): ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], 1.0),
        (0, 0, -1): ([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], 0.5),
    }
    for nrm, (vtx, sh) in faces.items():
        if float(np.dot(nrm, DV)) <= 0:
            continue
        s = prp(vtx)
        ax.add_patch(Polygon(s, closed=True, fc=fc, ec=ec, lw=lw, alpha=alpha,
                             zorder=zorder))


def iso_axes(ax, L=100):
    for vec, lab, col in (((L, 0, 0), "X", "#B03A2E"),
                          ((0, L, 0), "Y", "#1E8449"),
                          ((0, 0, L), "Z", "#2471A3")):
        a = prp([(0, 0, 0), vec])
        ax.annotate("", xy=a[1], xytext=a[0],
                    arrowprops=dict(arrowstyle="-|>", color=col, lw=1.6))
        ax.text(a[1][0], a[1][1], " " + lab, color=col, fontsize=12, fontweight="bold")


def draw_coil_iso(ax, which, col, dz=0.0, zorder=5):
    q = ribbon(which)
    t = np.column_stack([q, np.full(len(q), PZ[which] + H / 2 + dz)])
    b = np.column_stack([q, np.full(len(q), PZ[which] - H / 2 + dz)])
    ax.add_patch(Polygon(prp(np.vstack([t, b[::-1]])), closed=True,
                         fc="#7A3A14", ec="none", zorder=zorder - 1))
    ax.add_patch(Polygon(prp(t), closed=True, fc=col, ec="#5E2F12", lw=0.25,
                         zorder=zorder))


# ============================================================ 图 9 真实轴测
def fig_iso_true():
    fig, ax = plt.subplots(figsize=(13.4, 8.6))
    ax.set_aspect("equal"); ax.axis("off")

    for z in (REG["z"][0], REG["z"][1]):
        c = prp([(REG["x"][0], REG["y"][0], z), (REG["x"][1], REG["y"][0], z),
                 (REG["x"][1], REG["y"][1], z), (REG["x"][0], REG["y"][1], z),
                 (REG["x"][0], REG["y"][0], z)])
        ax.plot(c[:, 0], c[:, 1], color=C_AIR, ls="--", lw=1.0, alpha=0.75, zorder=1)
    for x, y in ((REG["x"][0], REG["y"][0]), (REG["x"][1], REG["y"][0]),
                 (REG["x"][1], REG["y"][1]), (REG["x"][0], REG["y"][1])):
        c = prp([(x, y, REG["z"][0]), (x, y, REG["z"][1])])
        ax.plot(c[:, 0], c[:, 1], color=C_AIR, ls="--", lw=0.9, alpha=0.6, zorder=1)

    for x in sorted(FR["tx_bar_x"], key=lambda v: -float(np.dot([v, 0, ZTX[0]], DV))):
        draw_box(ax, x - D["tx_bar_w"] / 2, x + D["tx_bar_w"] / 2, -YH, YH,
                 ZTX[0], ZTX[1], C_FERRITE, "#44525C", alpha=0.75, zorder=3)
    coils = sorted([("tx1", C_COPPER_D), ("tx2", C_COPPER), ("rx", C_RX)],
                   key=lambda t: -float(np.dot([CX[t[0]], 0, PZ[t[0]]], DV)))
    for which, col in coils:
        draw_coil_iso(ax, which, col, zorder=5)
    for x in sorted(FR["rx_bar_x"], key=lambda v: -float(np.dot([v, 0, ZRX[0]], DV))):
        draw_box(ax, x - D["rx_bar_w"] / 2, x + D["rx_bar_w"] / 2, -YH, YH,
                 ZRX[0], ZRX[1], C_RX, C_RX_D, alpha=0.48, zorder=8)
    for which, col in (("tx1", C_COPPER_D), ("tx2", C_COPPER), ("rx", C_RX)):
        for seg in leads_3d(which):
            c = prp(seg)
            ax.plot(c[:, 0], c[:, 1], color=col, lw=1.6, zorder=9)

    iso_axes(ax, 100)
    hs = [plt.Line2D([], [], color=C_COPPER_D, lw=3, label="Tx1 铜带 z=+0.325"),
          plt.Line2D([], [], color=C_COPPER, lw=3, label="Tx2 铜带 z=−0.325"),
          plt.Line2D([], [], color=C_RX, lw=3, label="Rx 铜带 z=+30.0"),
          plt.Line2D([], [], color=C_FERRITE, lw=7, label="Tx 铁氧体条 ×16（厚 5.883）"),
          plt.Line2D([], [], color=C_RX, lw=7, alpha=0.5, label="Rx 铁氧体条 ×8（厚 6.872）"),
          plt.Line2D([], [], color=C_AIR, ls="--", lw=1.4, label="空气域 Region")]
    ax.legend(handles=hs, loc="lower left", fontsize=9, framealpha=0.95)

    pts = []
    for X in (REG["x"][0], REG["x"][1]):
        for Y in (REG["y"][0], REG["y"][1]):
            for Z in (REG["z"][0], REG["z"][1]):
                pts.append(prp([(X, Y, Z)])[0])
    for w in ("tx1", "tx2", "rx"):
        pts.append(prp([(CX[w], PB_Y[0], -40)])[0])
        pts.append(prp([(CX[w], PB_Y[1], 30)])[0])
    bb = np.array(pts)
    ax.set_xlim(bb[:, 0].min() - 30, bb[:, 0].max() + 30)
    ax.set_ylim(bb[:, 1].min() - 30, bb[:, 1].max() + 30)

    fw, fh = fit_fig(fig, ax, target_w=14.6, left=0.55, right=0.55,
                     top=2.45, bottom=0.55, hgap=0.0)
    fig.text(0.5, 1 - 0.36 / fh, "图 9  WPT 磁耦合机构 三维轴测图（真实位置，未做展开）",
             ha="center", va="top", fontsize=13, fontweight="bold")
    fig.text(0.5, 1 - 0.92 / fh,
             "相机方位角 −60°、仰角 25°（自 +X/−Y/+Z 方向俯视）。灰块 = Tx 铁氧体 16 条；"
             "绿色半透明块 = Rx 铁氧体 8 条（真实位置在 Rx 铜带之上，做半透明以便看见下方铜带）；"
             "橙色带 = Tx1/Tx2/Rx 三片铜带。\n蓝色虚线 = 空气域 Region 的顶/底面与四条立柱（图中可见其远大于模型本体）；"
             "左下角为 X/Y/Z 轴指示。引线沿 −Y 出线并在 y = −134.94 形成端子排。",
             ha="center", va="top", fontsize=9.2, color="#444")
    p = os.path.join(FIGDIR, "fig9_iso_true.png")
    save(fig, p)
    print("OK", p)


# ============================================================ 图 10 接收位置
def read_case_rows(case="b1_0186"):
    rows = []
    with open(RAW0, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["case_id"] == case:
                rows.append(r)
    rows.sort(key=lambda r: float(r["x_mm"]))
    return rows


def fig_positions():
    rows = read_case_rows()
    if not rows:
        print("!! 无 b1_0186 已解数据"); return
    peak = max(rows, key=lambda r: float(r["M23"]))
    picks = [rows[0], peak, rows[-1]]
    labels = ["① 起始位置 x = 0（两发射线圈正中）",
              "② M23 峰值位置 x = %.3f mm" % float(peak["x_mm"]),
              "③ 最新已解位置 x = %.3f mm" % float(rows[-1]["x_mm"])]

    fig, axes = plt.subplots(1, 3, figsize=(16.2, 6.0))
    for ax, r, lab in zip(axes, picks, labels):
        x = float(r["x_mm"])
        ax.add_patch(Rectangle((REG["x"][0], REG["y"][0]),
                               REG["x"][1] - REG["x"][0], REG["y"][1] - REG["y"][0],
                               fill=False, ec=C_AIR, lw=1.2, ls="--", zorder=1))
        for xc in FR["tx_bar_x"]:
            ax.add_patch(Rectangle((xc - D["tx_bar_w"] / 2, -YH), D["tx_bar_w"], 2 * YH,
                                   fc=C_FERRITE, ec="none", alpha=0.40, zorder=2))
        for xc in FR["rx_bar_x"]:
            ax.add_patch(Rectangle((xc - D["rx_bar_w"] / 2 + x, -YH), D["rx_bar_w"],
                                   2 * YH, fc=C_RX, ec="none", alpha=0.32, zorder=2))
        for which, col in (("tx1", C_COPPER_D), ("tx2", C_COPPER)):
            Q = placed(which)
            ax.plot(Q[:, 0], Q[:, 1], color=col, lw=1.7, zorder=5)
        Qr = placed("rx")
        ax.plot(Qr[:, 0] + x, Qr[:, 1], color=C_RX, lw=2.0, zorder=7)
        for e in endpoints("rx"):
            ax.plot([e[0] + x], [e[1]], "o", ms=4, color=C_RX, zorder=8)
        for which, col in (("tx1", C_COPPER_D), ("tx2", C_COPPER)):
            for e in endpoints(which):
                ax.plot([e[0], e[0]], [CXV["y_end"], e[1]], color=col, lw=0.8, zorder=4)

        S = D["sweep_span"]
        ax.plot([-S / 2, S / 2], [172, 172], color="#B03A2E", lw=1.4)
        ax.plot([-S / 2, S / 2], [172, 172], "|", color="#B03A2E", ms=9, mew=1.6)
        ax.plot([x], [172], marker="v", ms=13, color="#B03A2E", zorder=9)
        # 扫描范围提示并入标题：图内只留箭头与位置标记，避免与标题压字
        ax.set_title("%s\nM13 = %s μH    M23 = %s μH    k23 = %s\n"
                     "红线段 = 全扫描范围 ±%.1f mm，▲ 为当前位置"
                     % (lab, r["M13"], r["M23"], r["k23"], S / 2), fontsize=10)
        ax.set_aspect("equal")
        ax.set_xlim(-265, 265); ax.set_ylim(-150, 192)
        ax.set_xlabel("X (mm)")
        ax.grid(alpha=0.2, lw=0.5)
    axes[0].set_ylabel("Y (mm)")
    fw, fh = fit_fig(fig, axes[0], ncols=3, target_w=16.4, top=1.95, bottom=1.10,
                     left=1.25, right=0.40, wgap=0.55)
    fig.text(0.5, 1 - 0.35 / fh,
             "图 10  接收线圈沿 X 平动的三个典型位置（俯视图对比）"
             "—— 接收线圈与其 8 条铁氧体同步平移，两发射线圈与 Tx 铁氧体静止",
             ha="center", va="top", fontsize=12.5)
    p = os.path.join(FIGDIR, "fig10_rx_positions.png")
    save(fig, p)
    print("OK", p)


# ============================================================ 图 11 匝间/拐角
def fig_turn_detail():
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13.0, 6.4))
    Qr = placed("rx")

    poly = ribbon("rx")
    a1.add_patch(Polygon(poly, closed=True, fc=C_COPPER, ec="#5E2F12", lw=0.6, zorder=3))
    a1.plot(Qr[:, 0], Qr[:, 1], color="#3E1F0C", lw=0.5, ls=":", zorder=4)
    a1.set_xlim(30, 100); a1.set_ylim(-36, 36)
    a1.set_aspect("equal"); a1.grid(alpha=0.25, lw=0.5)
    a1.set_title("(a) 直边匝间局部放大（Rx 线圈右直边，1:1）", fontsize=10.5)
    a1.set_xlabel("X (mm)"); a1.set_ylabel("Y (mm)")

    sel = Qr[(np.abs(Qr[:, 1]) < 3) & (Qr[:, 0] > 0)][:, 0]
    xs = []
    for v in sorted(sel):
        if not xs or v - xs[-1] > 0.3:
            xs.append(v)
    if len(xs) >= 2:
        pitch = (xs[-1] - xs[0]) / (len(xs) - 1)
        a1.annotate("", xy=(xs[0], 22), xytext=(xs[1], 22),
                    arrowprops=dict(arrowstyle="<->", color="#B03A2E", lw=1.3))
        a1.text((xs[0] + xs[1]) / 2, 24.5, "匝节距 %.3f mm" % pitch,
                color="#B03A2E", ha="center", va="bottom", fontsize=8.6)
        a1.annotate("", xy=(xs[0] + W / 2, -22), xytext=(xs[1] - W / 2, -22),
                    arrowprops=dict(arrowstyle="<->", color="#1E8449", lw=1.3))
        a1.text((xs[0] + xs[1]) / 2, -24.5,
                "净间隙 %.3f mm（= 节距 − 线宽 %.1f）" % (pitch - W, W),
                color="#1E8449", ha="center", va="top", fontsize=8.6)
    a1.text(0.025, 0.975,
            "共 12 匝（图中可见 12 条铜带），直边匝距均匀 %.3f mm\n"
            "直边最小净间隙 = %.3f mm；闸门阈值 1.5 mm → 本工况走 OPT 网格口径"
            % ((xs[-1] - xs[0]) / (len(xs) - 1) if len(xs) >= 2 else float("nan"),
               G["coil"]["gap_min"]),
            transform=a1.transAxes, va="top", ha="left", fontsize=9,
            bbox=dict(fc="#FEF9E7", ec="#B7950B", alpha=0.95, boxstyle="round,pad=0.35"))

    x0, y0 = PB_X[1] - 34, PB_Y[1] - 34
    a2.add_patch(Polygon(poly, closed=True, fc=C_COPPER, ec="#5E2F12", lw=0.6, zorder=3))
    a2.plot(Qr[:, 0], Qr[:, 1], color="#3E1F0C", lw=0.5, ls=":", zorder=4)
    a2.set_xlim(x0, PB_X[1] + 8); a2.set_ylim(y0, PB_Y[1] + 8)
    a2.set_aspect("equal"); a2.grid(alpha=0.25, lw=0.5)
    a2.set_title("(b) 外圈拐角局部放大（Rx 线圈右上角，1:1）", fontsize=10.5)
    a2.set_xlabel("X (mm)")
    a2.text(0.02, 0.97,
            "拐角为圆角（不是尖角）。路径在圆角处\n按**环半径**等比缩放，全批最大转角\n≤ 11.68°"
            "（模板固有 8 弦离散角 11.25°）",
            transform=a2.transAxes, va="top", fontsize=9,
            bbox=dict(fc="#EAF2F8", ec=C_AIR, alpha=0.95, boxstyle="round,pad=0.35"))

    fw, fh = fit_fig(fig, a1, ncols=2, target_w=13.6, top=1.85, bottom=1.15,
                     left=1.20, right=0.40, wgap=0.70)
    fig.text(0.5, 1 - 0.35 / fh,
             "图 11  铜带与匝间几何局部放大（工况 b1_0186，1:1）"
             "—— 铜带宽 %.1f mm、厚 %.1f mm，12 匝方螺旋，角部圆角" % (W, H),
             ha="center", va="top", fontsize=12.5)
    p = os.path.join(FIGDIR, "fig11_detail_turn.png")
    save(fig, p)
    print("OK", p)


# ============================================================ 图 12 铁氧体详图
def fig_ferrite():
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9.6, 9.4),
                                 gridspec_kw=dict(hspace=0.62))

    def bars(ax, xs, bw, fc, ec, txtcol, alpha=1.0, numcol="white"):
        for i, xc in enumerate(xs):
            ax.add_patch(Rectangle((xc - bw / 2, -YH), bw, 2 * YH,
                                   fc=fc, ec=ec, lw=0.8, alpha=alpha))
            ax.text(xc, 0, "%d" % (i + 1), ha="center", va="center",
                    fontsize=8, color=numcol)
        xa, xb = xs[0], xs[1]
        yb = -YH - 14
        ax.annotate("", xy=(xa, yb), xytext=(xb, yb),
                    arrowprops=dict(arrowstyle="<->", color="#B03A2E", lw=1.4))
        ax.text((xa + xb) / 2, yb - 3, "单元节距 30.000", color="#B03A2E",
                ha="center", va="top", fontsize=9)
        ax.annotate("", xy=(xa - bw / 2, yb), xytext=(xa + bw / 2, yb),
                    arrowprops=dict(arrowstyle="<->", color="#1E8449", lw=1.4))
        ax.text(xa, yb - 18, "条宽 %.3f" % bw, color="#1E8449",
                ha="center", va="top", fontsize=9)
        yc = YH + 14
        ax.annotate("", xy=(xa + bw / 2, yc), xytext=(xb - bw / 2, yc),
                    arrowprops=dict(arrowstyle="<->", color="#7D3C98", lw=1.4))
        ax.text((xa + xb) / 2, yc + 3, "条间气隙 %.3f" % (30 - bw), color="#7D3C98",
                ha="center", va="bottom", fontsize=9)
        ax.text(-244, 150, txtcol[0], ha="left", va="center", fontsize=9,
                color=txtcol[1],
                bbox=dict(fc=txtcol[2], ec=txtcol[1], alpha=0.95, boxstyle="round,pad=0.4"))
        ax.set_xlim(-250, 250); ax.set_ylim(-YH - 52, YH + 58)
        ax.set_aspect("equal"); ax.grid(alpha=0.2, lw=0.5)
        ax.set_ylabel("Y (mm)")

    bars(a1, FR["tx_bar_x"], D["tx_bar_w"], C_FERRITE, "#44525C",
         ("Tx 铁氧体 16 条（覆盖率 %.1f %%）\n条宽 19.383 ／ 气隙 10.617 ／ 条长 221"
          % (100 * D["tx_bar_w"] / 30.0), "#44525C", "#EEF2F5"), numcol="#22313A")
    a1.set_title("(a) Tx 侧铁氧体条阵 —— 16 条，条心 x 从 −225 到 +225（步距 30 mm）；"
                 "覆盖范围 −234.7 ~ +234.7 mm，盖住两发射线圈全宽", fontsize=10.5)

    bars(a2, FR["rx_bar_x"], D["rx_bar_w"], C_RX, C_RX_D,
         ("Rx 铁氧体 8 条（覆盖率 %.1f %%）\n条宽 15.234 ／ 气隙 14.766 ／ 条长 221"
          % (100 * D["rx_bar_w"] / 30.0), C_RX_D, "#EAF7EF"), alpha=0.85)
    a2.set_title("(b) Rx 侧铁氧体条阵 —— 8 条，条心 x 从 −105 到 +105（步距 30 mm）；"
                 "**x = 0 处没有条**（正中是一条气隙）", fontsize=10.5)
    a2.set_xlabel("X (mm)")

    fw, fh = fit_fig(fig, a1, nrows=2, target_w=10.4, top=1.85, bottom=1.15,
                     left=1.20, right=0.40, hgap=1.35)
    fig.text(0.5, 1 - 0.35 / fh,
             "图 12  铁氧体铺条规则详图（工况 b1_0186）"
             "—— 两侧独立：Tx 覆盖率 64.6 %，Rx 覆盖率 50.8 %；条长均由 1.2 × Lc 取整而来",
             ha="center", va="top", fontsize=12.5)
    p = os.path.join(FIGDIR, "fig12_ferrite_detail.png")
    save(fig, p)
    print("OK", p)


# ============================================================ 图 13 爆炸轴测
def fig_iso_exploded():
    fig, ax = plt.subplots(figsize=(13.4, 8.8))
    ax.set_aspect("equal"); ax.axis("off")
    GAP = 60.0

    def draw_layer(kind, z0, z1):
        if kind == "ferrite":
            for x in sorted(FR["tx_bar_x"], key=lambda v: -float(np.dot([v, 0, z0], DV))):
                draw_box(ax, x - D["tx_bar_w"] / 2, x + D["tx_bar_w"] / 2, -YH, YH,
                         z0, z1, C_FERRITE, "#44525C", alpha=0.95)
        elif kind == "rxf":
            for x in sorted(FR["rx_bar_x"], key=lambda v: -float(np.dot([v, 0, z0], DV))):
                draw_box(ax, x - D["rx_bar_w"] / 2, x + D["rx_bar_w"] / 2, -YH, YH,
                         z0, z1, C_RX, C_RX_D, alpha=0.85)
        else:
            col = {"tx1": C_COPPER_D, "tx2": C_COPPER, "rx": C_RX}[kind]
            q = ribbon(kind)
            t = np.column_stack([q, np.full(len(q), z0 + H / 2)])
            b = np.column_stack([q, np.full(len(q), z0 - H / 2)])
            ax.add_patch(Polygon(prp(np.vstack([t, b[::-1]])), closed=True,
                                 fc="#7A3A14", ec="none", zorder=4))
            ax.add_patch(Polygon(prp(t), closed=True, fc=col, ec="#5E2F12",
                                 lw=0.25, zorder=5))

    layers = [
        ("① Tx 铁氧体 16 条（厚 5.883，z ∈ [−35.88, −30]）", ZTX[0], ZTX[1], "ferrite", ZTX[1]),
        ("② Tx2 铜带（下层，z = −0.325）", PZ["tx2"] + GAP, PZ["tx2"] + GAP, "tx2", PZ["tx2"] + GAP),
        ("③ Tx1 铜带（上层，z = +0.325）", PZ["tx1"] + GAP * 2, PZ["tx1"] + GAP * 2, "tx1", PZ["tx1"] + GAP * 2),
        ("④ Rx 铜带（z = +30.00）", PZ["rx"] + GAP * 3, PZ["rx"] + GAP * 3, "rx", PZ["rx"] + GAP * 3),
        ("⑤ Rx 铁氧体 8 条（厚 6.872，z ∈ [+60, +66.87]）", ZRX[0] + GAP * 4, ZRX[1] + GAP * 4, "rxf", (ZRX[0] + ZRX[1]) / 2 + GAP * 4),
    ]
    for name, z0, z1, kind, labz in layers:
        draw_layer(kind, z0, z1)
    for x in (CX["tx1"], CX["tx2"], 0.0):
        c = prp([(x, 0, ZTX[0]), (x, 0, ZRX[1] + GAP * 4)])
        ax.plot(c[:, 0], c[:, 1], color="#999", ls=":", lw=1.0, zorder=2)

    cs = []
    for XW, zw0, zw1 in ((234.717, ZTX[0], ZTX[1]),
                         (112.617, ZRX[0] + GAP * 4, ZRX[1] + GAP * 4)):
        for X in (-XW, XW):
            for Y in (-YH, YH):
                for Z in (zw0, zw1):
                    cs.append((X, Y, Z))
    for kind, dz in (("tx1", GAP * 2), ("tx2", GAP), ("rx", GAP * 3)):
        hw = 93.675 if kind == "rx" else 217.304
        for X in (-hw, hw):
            for Y in (PB_Y[0] - W / 2, PB_Y[1] + W / 2):
                cs.append((X, Y, PZ[kind] + dz))
    for v in ((110, 0, 0), (0, 110, 0), (0, 0, 110)):
        cs.append(v)
    cs = prp(cs)
    x0, x1 = cs[:, 0].min() - 14, cs[:, 0].max() + 14
    y0, y1 = cs[:, 1].min() - 14, cs[:, 1].max() + 14
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1)

    # 显式布局：左侧绘图区 + 右侧层说明列（避免层标签被图幅裁掉）
    FW, PLOT_W = 15.4, 10.2
    ar = (x1 - x0) / (y1 - y0)
    plot_h = PLOT_W / ar
    top_in, bot_in = 2.35, 0.60
    FH = plot_h + top_in + bot_in
    fig.set_size_inches(FW, FH)
    ax.set_position([0.62 / FW, bot_in / FH, PLOT_W / FW, plot_h / FH])

    sw = [C_FERRITE, C_COPPER, C_COPPER_D, C_RX, C_RX]
    for i, ((name, _z0, _z1, _k, _lz)) in enumerate(layers):
        yy = 1 - (top_in + 0.30 + i * 0.40) / FH
        fig.text(10.95 / FW, yy, "■", color=sw[i], fontsize=13, va="center", ha="center")
        fig.text(11.20 / FW, yy, name, fontsize=9.6, va="center", ha="left", color="#333")

    iso_axes(ax, 110)
    fig.text(0.5, 1 - 0.36 / FH,
             "图 13  分层爆炸轴测图（层间 Z 向被人为拉开 %.0f mm，仅为看清层序）" % GAP,
             ha="center", va="top", fontsize=13, fontweight="bold")
    fig.text(0.5, 1 - 0.92 / FH,
             "自下而上五层，对应右侧清单 ①~⑤。③ Tx1 与 ② Tx2 在真实模型中只隔 0.15 mm 介质，"
             "④ Rx 铜带真实悬高 30 mm —— 本图把它们拉开只为看清层次归属。\n"
             "灰色竖向点线为 Tx1 中心 / Tx2 中心 / Rx 中心（x = 0）三条对齐基准。"
             "真实装配位置请对照图 4、图 7、图 9。",
             ha="center", va="top", fontsize=9.2, color="#444")
    p = os.path.join(FIGDIR, "fig13_exploded_iso.png")
    save(fig, p)
    print("OK", p)


if __name__ == "__main__":
    os.makedirs(FIGDIR, exist_ok=True)
    print("铜带外轮廓 X=%.3f  Y=%.3f" % (CW_X, CW_Y))
    for w in ("tx1", "tx2", "rx"):
        b = bbox(w)
        print("%s 铜带 bbox: x[%.3f, %.3f] y[%.3f, %.3f]" % (w, b[0], b[1], b[2], b[3]))
    e0, e1 = endpoints("rx")
    print("Rx 引线端点: (%.3f, %.3f) 与 (%.3f, %.3f)" % (e0[0], e0[1], e1[0], e1[1]))
    fig_front()
    fig_side()
    fig_iso_true()
    fig_positions()
    fig_turn_detail()
    fig_ferrite()
    fig_iso_exploded()
    print("全部完成 ->", FIGDIR)
