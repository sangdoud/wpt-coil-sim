# -*- coding: utf-8 -*-
"""生成 b1_0186 案例新增的两张图（离线复算，不接触 AEDT）：

  fig14_single_coil_top.png   图 14  单个线圈俯视图（12 匝方螺旋，带完整参数标注）
  fig15_mirror_half_sweep.png 图 15  镜像半扫加速：41 点 → 只需算 21 点 + 双阈值判据

口径与图 2 ~ 图 13 完全一致：1:1 等比、真实几何、尺寸标注、图例、图题；
几何取自 _work\\case_figures\\geom_b1_0186.json（生产环境同一套离线几何代码复算）；
曲线取自 b1_raw_run0.csv 中 b1_0186 真实已解点，镜像展开用与生产 (12) 步完全相同的交换规则。
"""
import csv
import glob
import json
import os
import re

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import (Rectangle, Polygon, FancyArrowPatch, FancyBboxPatch,
                                Patch)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 130

FIGDIR = r"C:\ansys maxwell2024\_work\case_figures"
GEOM = os.path.join(FIGDIR, "geom_b1_0186.json")
RAW = r"C:\ansys maxwell2024\_work\b1\b1_raw_run0.csv"
CASE = "b1_0186"

# 文档《WPT案例图文说明_b1_0186_20260923.md》中的图号（改文档编号时只改这里）
FIG_NO_COIL = 14
FIG_NO_MIRROR = 15

C_COPPER = "#C87137"
C_COPPER_D = "#8C4A1E"
C_RX = "#1E8449"
C_RED = "#B03A2E"
C_DIM = "#1F4E79"
C_BG = "#FFFFFF"

G = json.load(open(GEOM, encoding="utf-8"))
P = np.array(G["path"], dtype=float)
C = G["coil"]
V = G["vars"]
D = G["derived"]
W = C["width"]
H = C["height"]


# ------------------------------------------------------------------ 工具
def rigid_offsets(Q, w):
    """把中心线 Q 按局部切线法向两侧各偏 w/2，返回 (outer, inner)。

    切向用 p[i+1]-p[i-1]（真实行进方向），法向取左手侧；因为是方形螺旋，
    行进方向在直边上恰好是 ±X/±Y，法向因此精确落在另一坐标轴上，不会产生斜切。
    """
    n = len(Q)
    T = np.zeros_like(Q)
    T[0] = Q[1] - Q[-1]
    T[-1] = Q[0] - Q[-2]
    T[1:-1] = Q[2:] - Q[:-2]
    N = np.c_[T[:, 1], -T[:, 0]]
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    return Q + N * (w / 2.0), Q - N * (w / 2.0)


def ribbon_polygon(Q, w):
    o, i = rigid_offsets(Q, w)
    return np.vstack([o, i[::-1]])


def ribbon_area(Q, w):
    o, i = rigid_offsets(Q, w)
    A = 0.0
    for k in range(len(Q) - 1):
        quad = np.array([o[k], o[k + 1], i[k + 1], i[k]])
        x, y = quad[:, 0], quad[:, 1]
        A += abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))) / 2.0
    return A


def read_case(x_from_csv=False):
    rows = [r for r in csv.DictReader(open(RAW, encoding="utf-8"))
            if r["case_id"] == CASE]
    rows.sort(key=lambda r: int(r["i"]))
    return rows


def anchored_box(fig, x, y, ha, va, s, **tkw):
    """在图上放一段文字，并按**实测包围盒**给它画一个对称留白的底色框。

    为什么不用 text(bbox=...)：当锚点是 ha="right" 时，matplotlib 的 bbox 补丁
    两侧留白并不对称（实测左 8 px、右仅 7 px），最长那行几乎顶到边框，
    看起来就像"字被框截断了"。这里改成自己量、自己画，四边留白一律 pad_px。
    """
    pad_px = 10.0
    fc = tkw.pop("bbox_fc", "#FFFFFF")
    ec = tkw.pop("bbox_ec", "#999999")
    al = tkw.pop("bbox_alpha", 0.95)
    t = fig.text(x, y, s, ha=ha, va=va, **tkw)
    return draw_box_around(fig, t, fc, ec, al, pad_px)


def draw_box_around(fig, t, fc="#FFFFFF", ec="#999999", alpha=0.95, pad_px=10.0):
    """给一段已定位的 fig.text 画底色框（量它当前的真实包围盒，四边等留白）。"""
    r = fig.canvas.get_renderer()
    h_px = fig.get_figheight() * fig.dpi
    w_px = fig.get_figwidth() * fig.dpi
    z = t.get_zorder() - 1
    fig.canvas.draw()
    b = t.get_window_extent(r)
    x0, y0 = (b.x0 - pad_px) / w_px, (b.y0 - pad_px) / h_px
    x1, y1 = (b.x1 + pad_px) / w_px, (b.y1 + pad_px) / h_px
    fig.patches.append(FancyBboxPatch(
        (x0, y0), x1 - x0, y1 - y0, transform=fig.transFigure,
        boxstyle="round,pad=0,rounding_size=0.006", zorder=z,
        fc=fc, ec=ec, alpha=alpha, mutation_aspect=1.0))
    return t


def place_legend_clear(ax, cands, pad_frac=0.02):
    """把图例放到"最空"的候选位置：先量各图元的像素点，选框中图元点最少的那个。

    为什么需要它：图例默认的 loc="best" 只看它自己认得的 artist，且常把框摆到
    曲线正上方；而"文字互压/出界"两个自检根本看不到这种遮挡（框与线没有文字交集）。
    这里直接数"落在候选框内的数据点个数"，取最小者，并可打印留档。
    """
    fig = ax.figure
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    pts = []
    for ln in ax.get_lines():
        xy = ln.get_xydata()
        if len(xy):
            pts.append(ax.transData.transform(xy))
    for c in ax.collections:
        for p in (c.get_paths() or []):
            if len(p.vertices):
                pts.append(ax.transData.transform(p.vertices))
    P = np.vstack(pts) if pts else np.zeros((0, 2))
    best, best_n, best_box = None, None, None
    for loc in cands:
        lg = ax.legend(loc=loc, framealpha=0.95)
        fig.canvas.draw()
        b = lg.get_window_extent(r)
        n = int(((P[:, 0] >= b.x0) & (P[:, 0] <= b.x1) &
                 (P[:, 1] >= b.y0) & (P[:, 1] <= b.y1)).sum()) if len(P) else 0
        if best_n is None or n < best_n:
            if best is not None:
                best.remove()
            best, best_n, best_box = lg, n, b
        else:
            lg.remove()
    fig.canvas.draw()
    print("   [图例] 选 %s：框内图元点 %d 个（候选 %s）"
          % (best._loc if hasattr(best, "_loc") else "?", best_n, cands))
    return best


def wrap_to_width(fig, s, fontsize, max_px, **kw):
    """把整段文字按**实测像素宽度**折行（逐词贪心）。

    为什么需要：脚注/说明文字的字号与字数随数据变化，靠手写 "\\n" 断行一旦内容变长
    就会越出图幅或被相邻文字压住（本项目已为此返工多次）。这里用渲染器量宽度，
    按目标像素宽自动断行，与字号、字体无关。
    """
    r = fig.canvas.get_renderer()
    probe = fig.text(0, -1, "", fontsize=fontsize, **kw)
    # 先给"数值 + 单位"之间塞不换行空格，否则会在 0.5 与 mm 之间断开，
    # 渲染成 "0.5/mm" 这种读不通的样子（2026-09-26 实测）。单位只认常见那几个，
    # 免得把 "5 mm 闸门" 里 mm 后面的整段都黏住。
    s = re.sub(r"(?<=[0-9.])\s+(?=(?:mm|μm|°|k|A|V|μH|Hz|s)\b)", "\u00a0",
               s.replace("\n", " "))
    out, cur = [], ""
    for tok in s.split(" "):
        trial = (cur + " " + tok).strip()
        probe.set_text(trial)
        fig.canvas.draw()
        if probe.get_window_extent(r).width <= max_px or not cur:
            cur = trial
        else:
            out.append(cur)
            cur = tok
    if cur:
        out.append(cur)
    probe.remove()
    return "\n".join(out).replace("\u00a0", " ")


def stack_texts(fig, ax, items, x_frac, gap_px, fontsize=8.2, ha="left"):
    """把若干条文字在 axes 内**自上而下排成梯子**，每条都按实测包围盒保证间距。

    为什么需要：先前按数据坐标"差 5 个单位"摆两条标注，实际只有约 14 px、看着仍是叠的
    （2026-09-26 反复踩）。这里改为：逐条落位 → 画一次 → 量它真实包围盒 →
    与已放好的上一条比较，不够 gap_px 就整体下移，直到够为止，并保证不越出坐标区。
    """
    r = fig.canvas.get_renderer()
    fig.canvas.draw()
    ax_box = ax.get_window_extent(r)
    placed = []
    for it in items:
        t = ax.text(x_frac, it.get("y0", 0.4), it["s"], transform=ax.transAxes,
                    ha=ha, va="top", fontsize=fontsize, color=it.get("color", "#333"))
        for _ in range(60):
            fig.canvas.draw()
            b = t.get_window_extent(r)
            clash = None
            for pb in placed:
                if b.x0 < pb.x1 and b.x1 > pb.x0 and b.y1 > pb.y0 - gap_px:
                    clash = pb
            if clash is None and b.y0 >= ax_box.y0 + 1:
                break
            dy = 2.0 / (ax_box.height)          # 每次下移 2 px（换算成 axes 分数）
            t.set_position((t.get_position()[0], t.get_position()[1] - dy))
        placed.append(t.get_window_extent(r))
        print("   [(b) 梯子] %-14s 框 y[%.0f,%.0f]"
              % (it["s"], placed[-1].y0, placed[-1].y1))
    return placed


def stack_column(fig, items, x_px, y_top_px, gap_px=6, fontsize=7.6, width_px=232):
    """在**图坐标**的固定 x 处，把若干条文字自上而下排成一列。

    每条都：按 width_px 自动折行 → 量真实像素包围盒 → 与上一条留够 gap_px；
    越出下边界就停下并报出来。返回最后一条的底边 y（像素）。
    这样"文字排在图外"就有了确定性落位，不依赖任何手算间距。
    """
    r = fig.canvas.get_renderer()
    W_px = fig.get_figwidth() * fig.dpi
    H_px = fig.get_figheight() * fig.dpi
    y = y_top_px
    for it in items:
        s = wrap_to_width(fig, it["s"], fontsize, width_px, color=it.get("color", "#333"))
        t = fig.text(x_px / W_px, y / H_px, s, ha="left", va="top",
                     fontsize=fontsize, color=it.get("color", "#333"),
                     linespacing=1.35)
        fig.canvas.draw()
        b = t.get_window_extent(r)
        if b.y0 < 4 or b.x1 > W_px - 2:
            print("   [栏] 警告：'%s' 越界（x1=%.0f y0=%.0f）"
                  % (it["s"][:18], b.x1, b.y0))
        y = b.y0 - gap_px
    return y


def anchor_block(fig, objs, y, gap, edge="bottom"):
    """把一组 fig.text **整体平移**，使整块的下沿（或上沿）落到 y 处（留 gap 空隙）。

    关键：用**同一个位移量**平移整块，而不是让每行各自对齐 —— 后者会把行距压平。
    为什么需要它：右侧那栏文字的行数/字数随数据变化，靠手算 0.0xx 间距会反复压字
    （本项目为此返工过两次）；这里量渲染后的像素包围盒反推位移，一次到位。
    """
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    h = fig.get_figheight() * fig.dpi
    top = max(t.get_window_extent(r).y1 for t in objs) / h
    bot = min(t.get_window_extent(r).y0 for t in objs) / h
    delta = (y + gap - bot) if edge == "bottom" else (y - gap - top)
    for t in objs:
        t.set_y(t.get_position()[1] + delta)
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    bot2 = min(t.get_window_extent(r).y0 for t in objs) / h
    top2 = max(t.get_window_extent(r).y1 for t in objs) / h
    print("   [排版] %d 块，高 %.3f，平移 %+.4f -> 现占 y ∈ [%.4f, %.4f]（目标 %s=%.3f）"
          % (len(objs), top - bot, delta, bot2, top2, edge, y))
    return bot2, top2


# ------------------------------------------------------------------ 图 14
def coil_metrics():
    """从 768 点路径核算图 14 要标注的全部尺寸（口径见返回值注释）。"""
    xmin, xmax = P[:, 0].min(), P[:, 0].max()
    ymin, ymax = P[:, 1].min(), P[:, 1].max()
    # 逐"匝"切分：12 匝 × 64 点；同向切片内相邻匝中心线间距 = 节距
    slices = {}
    for axis, name in ((0, "x"), (1, "y")):
        other = 1 - axis
        v = np.unique(np.round(P[np.abs(P[:, other]) < 0.6][:, axis], 4))
        slices[name] = v
    pxs = np.diff(slices["x"]); pxs = pxs[pxs < 20]
    pys = np.diff(slices["y"]); pys = pys[pys < 20]
    pitch = float(np.mean([pxs.mean(), pys.mean()]))
    # 对边中心线跨距（直边口径）
    straight = {}
    for name, v in slices.items():
        neg = v[v < 0]; pos = v[v > 0]
        straight[name] = pos[-1] - neg[0] + W      # 外侧那两条匝的中心线跨
    # 通过尺寸：(Lc, r_h) → h_out / h_in
    h_out = C["h_out"]
    return dict(xmin=xmin, xmax=xmax, ymin=ymin, ymax=ymax,
                env_x=xmax - xmin + W, env_y=ymax - ymin + W,
                pitch=pitch, gap=pitch - W,
                span_x=straight["x"], span_y=straight["y"],
                h_out=h_out, h_in=C["h_in"],
                cx=(xmin + xmax) / 2, cy=(ymin + ymax) / 2,
                r_out=max(abs(xmin), abs(xmax)))


def fig_single_coil_top():
    m = coil_metrics()
    poly = ribbon_polygon(P, W)
    h_out, h_in, pitch = m["h_out"], m["h_in"], m["pitch"]
    print("[图14] 外轮廓 X=%.3f Y=%.3f（图 2 文档 187.351/185.895）"
          % (m["env_x"], m["env_y"]))
    print("[图14] 节距 p=%.5f  净间隙 p−w=%.5f  json gap_min=%.4f（差 %.4f）"
          % (pitch, m["gap"], C["gap_min"], m["gap"] - C["gap_min"]))
    print("[图14] 直边跨距 X=%.3f Y=%.3f（差 %.3f，来自路径模板非严格对称）"
          % (m["span_x"], m["span_y"], m["span_x"] - m["span_y"]))
    print("[图14] 2·h_out=%.4f  2·h_in=%.4f  铜带外缘 2·r_out=%.4f  "
          "模板中心偏移 (%+.3f, %+.3f)"
          % (2 * h_out, 2 * h_in, 2 * m["r_out"], m["cx"], m["cy"]))
    print("[图14] 铜带中部净面积 = %.2f mm²" % ribbon_area(P, W))

    # 版面：右栏两幅 1:1 放大图必须给足宽度，否则 set_aspect("equal") 会把显示范围
    # 强行放大，标注文字就会被挤出坐标区、压到 y 轴刻度上（2026-09-24 实测）。
    #   (b) 19 mm × 38 mm -> 需 0.165 × 0.530 in；(c) 12 mm × 12 mm -> 0.135 × 0.280 in
    # 版面（2026-09-26 第三版）：(b) 放大图的四条标注**全部移到图的右侧**，
    # 排成一条专用文字栏（x∈[0.630,0.722]），不再压在线圈图上。
    #   图 → 文字栏 → 参数表，三者 x 区间互不相交。
    fig = plt.figure(figsize=(19.0, 11.4))
    ax = fig.add_axes([0.038, 0.055, 0.292, 0.870])
    axd = fig.add_axes([0.412, 0.520, 0.140, 0.430])   # 详图 (b)
    axi = fig.add_axes([0.412, 0.300, 0.124, 0.180])   # 内孔拐角 (c)
    # 图 14 的脚注整块放在 (b)(c) 与参数表之间的空白带（.030 起会被 y 轴刻度压住）

    # ================= 主图：(a) 坐标区内一律不放文字 =================
    ax.add_patch(Polygon(poly, closed=True, fc=C_COPPER, ec=C_COPPER_D,
                         lw=0.35, alpha=0.95, zorder=3))
    ax.plot(P[:, 0], P[:, 1], color="#4A2408", lw=0.5, ls="--", alpha=0.5, zorder=4)
    for e in (P[0], P[-1]):                      # 引线端点只用空心圆标记，文字在栏外
        ax.plot([e[0]], [e[1]], marker="o", ms=5.5, mfc="#FFFFFF",
                mec=C_COPPER_D, mew=1.5, zorder=7)
    # 尺寸箭头与点线保留（它们是图形，不是文字）
    ax.annotate("", xy=(-m["r_out"], 118), xytext=(m["r_out"], 118),
                arrowprops=dict(arrowstyle="<->", color=C_COPPER_D, lw=1.3))
    for xs in (-m["r_out"], m["r_out"]):
        ax.plot([xs, xs], [-96, 100], color=C_COPPER_D, lw=0.8, ls=":", alpha=0.6,
                zorder=1)
    ax.annotate("", xy=(-h_out, -110), xytext=(h_out, -110),
                arrowprops=dict(arrowstyle="<->", color=C_DIM, lw=1.5))
    ax.annotate("", xy=(-h_in, 0), xytext=(h_in, 0),
                arrowprops=dict(arrowstyle="<->", color=C_RX, lw=1.4))
    for xs in (-h_in, h_in):
        ax.plot([xs, xs], [-70, 64], color=C_RX, lw=0.8, ls=":", alpha=0.55, zorder=1)
    ax.annotate("", xy=(96, -m["span_x"] / 2), xytext=(96, m["span_x"] / 2),
                arrowprops=dict(arrowstyle="<->", color="#5D6D7E", lw=1.2))
    ax.annotate("", xy=(-m["span_y"] / 2, 104), xytext=(m["span_y"] / 2, 104),
                arrowprops=dict(arrowstyle="<->", color="#5D6D7E", lw=1.2))
    ax.add_patch(Rectangle((34.0, -30), 62, 30, fill=False, ec="#7D3C98",
                           lw=1.4, zorder=8))
    ax.add_patch(Rectangle((-33.6, 28.0), 12, 12, fill=False, ec="#1E8449",
                           lw=1.4, zorder=8))

    ax.set_aspect("equal")
    ax.set_xlim(-150, 150)
    ax.set_ylim(-150, 148)
    ax.grid(alpha=0.20, lw=0.5)
    ax.set_xlabel("X (mm)", labelpad=2)
    ax.set_ylabel("Y (mm)")
    ax.set_title("图 %d(a) 单个线圈俯视图（1:1）" % FIG_NO_COIL, fontsize=11.5,
                 pad=6, loc="left")

    # ---- (a) 的全部标注：统一排到**坐标区之外的文字栏**，图内零文字 ----
    _Wpx = fig.get_figwidth() * fig.dpi
    _Hpx = fig.get_figheight() * fig.dpi
    stack_column(fig, [
        dict(s="【(a) 结构说明】铜带 w %.1f × t %.1f mm，%d 匝"
             % (W, H, C["turns"]), color="#333"),
        dict(s="路径中心线 768 点 / 767 段", color="#4A2408"),
        dict(s="空心圆 = 引线端点 P / N（φ0.6 mm）", color=C_COPPER_D),
        dict(s="外缘包络 X %.3f ／ Y %.3f mm" % (m["env_x"], m["env_y"]),
             color=C_COPPER_D),
        dict(s="中心线外跨 2·h_out %.4f mm" % (2 * h_out), color=C_DIM),
        dict(s="标称 Lc %.4f mm（h_out = Lc·K_LC/2）" % V["coil_size"], color=C_DIM),
        dict(s="内孔 2·h_in %.3f mm（r_h %.4f）" % (2 * h_in, V["hole_ratio"]),
             color=C_RX),
        dict(s="内孔净边 %.3f mm" % (2 * h_in - W), color=C_RX),
        dict(s="左/右直边跨距 %.3f mm" % m["span_x"], color="#5D6D7E"),
        dict(s="上/下直边跨距 %.3f mm" % m["span_y"], color="#5D6D7E"),
        dict(s="紫框 → 图 %d(b)；绿框 → 图 %d(c)" % (FIG_NO_COIL, FIG_NO_COIL),
             color="#7D3C98"),
    ], x_px=0.362 * _Wpx, y_top_px=0.915 * _Hpx, gap_px=7, fontsize=7.6,
        width_px=232)

    # ================= 详图 (b)：右直边 =================
    axd.add_patch(Polygon(poly, closed=True, fc=C_COPPER, ec=C_COPPER_D, lw=0.4))
    axd.plot(P[:, 0], P[:, 1], color="#4A2408", lw=0.6, ls="--", alpha=0.6)
    xr = [c for c in np.unique(np.round(P[(P[:, 0] > 0) & (np.abs(P[:, 1]) < 12)][:, 0], 4))]
    xr = xr[:4]
    # ---- (b) 的三条标注 ----
    # 2026-09-26 第二版：先前按"数据坐标差 5 个单位"摆位，实际只差约 14 px，看着仍是叠的。
    # 现在**不再手写数据坐标**：三条文字在扫描线右侧排成一条竖直梯子，
    # 每条落下前都量一次已渲染的包围盒，保证与上一条至少隔 gap_px（见 stack_texts）。
    box_p, box_g, box_w = [], [], []

    def _rec(store):
        def f(t):
            store.append(t)
        return f

    cands = [("节距 %.4f mm" % pitch, C_DIM, box_p),
             ("净间隙 %.4f mm" % m["gap"], C_RX, box_g),
             ("线宽 %.1f mm" % W, C_COPPER_D, box_w)]

    axd.annotate("", xy=(xr[0], -22), xytext=(xr[1], -22),
                 arrowprops=dict(arrowstyle="<->", color=C_DIM, lw=1.4))
    axd.annotate("", xy=(xr[1] + W / 2, 25.5), xytext=(xr[2] - W / 2, 25.5),
                 arrowprops=dict(arrowstyle="<->", color=C_RX, lw=1.4))
    axd.annotate("", xy=(xr[2] - W / 2, -12), xytext=(xr[2] + W / 2, -12),
                 arrowprops=dict(arrowstyle="<->", color=C_COPPER_D, lw=1.4))
    axd.set_aspect("equal")
    axd.set_xlim(34.0, 54.0)
    axd.set_ylim(-40, 40)
    # 三条数字标注 + 比例说明**全部排在图右侧的文字栏**（绘图区内不再留任何文字）：
    # 逐条量包围盒、保证与上一条至少 gap_px，且不越出坐标区（见 stack_texts）。
    stack_texts(fig, axd, [
        dict(s="1:1，x∈[35,51] mm", color="#777", y0=0.72),
        dict(s="节距 %.4f mm" % pitch, color=C_DIM, y0=0.72),
        dict(s="净间隙 %.4f mm" % m["gap"], color=C_RX, y0=0.72),
        dict(s="线宽 %.1f mm" % W, color=C_COPPER_D, y0=0.72),
    ], x_frac=1.03, gap_px=8.0, fontsize=8.2)
    axd.text(1.03, 0.30, "12 匝逐匝外移", fontsize=8.2, color="#333",
             transform=axd.transAxes, ha="left", va="top")
    # (b) 的说明**移到 (c) 下面**：这片区域从 (c) 下缘一直空到图幅底，宽度够排 2 行
    _Wpx, _Hpx = fig.get_figwidth() * fig.dpi, fig.get_figheight() * fig.dpi
    stack_column(fig, [
        dict(s="【(b)(c) 放大说明】节距 %.4f mm、净间隙 %.4f mm、线宽 %.1f mm；"
               % (pitch, m["gap"], W), color="#333"),
        dict(s="最小净间隙 %.4f mm（≥1.5 mm 闸门 → OPT 口径）。"
               % C["gap_min"], color="#333"),
        dict(s="(c)：内孔拐角为圆弧，x∈[−36,−24]、y∈[26,38] mm。", color="#666"),
    ], x_px=0.432 * _Wpx, y_top_px=0.285 * _Hpx, gap_px=6, fontsize=7.4,
        width_px=368)
    # 每条标注用一条细引线指回图上被量的位置；引线只走文字左侧那条空隙，不压文字
    for (xa, ya, col) in (((xr[0] + xr[1]) / 2, -22.0, C_DIM),
                          ((xr[1] + xr[2]) / 2, 25.5, C_RX),
                          (xr[2], -12.0, C_COPPER_D)):
        yfrac = axd.transAxes.inverted().transform(
            axd.transData.transform((xa, ya)))[1]
        axd.annotate("", xy=(xa, ya), xytext=(1.005, yfrac),
                     xycoords="data", textcoords="axes fraction",
                     arrowprops=dict(arrowstyle="-", color=col, lw=0.8,
                                     shrinkA=1, shrinkB=1, alpha=0.75))
    axd.annotate("", xy=(xr[1], 4.0), xytext=(1.005, 0.285),
                 xycoords="data", textcoords="axes fraction",
                 arrowprops=dict(arrowstyle="-", color="#888", lw=0.8, alpha=0.75))
    axd.grid(alpha=0.22, lw=0.5)
    axd.set_title("图 %d(b) 右直边匝间放大" % FIG_NO_COIL, fontsize=9.0, pad=5,
                  loc="left")
    # 两幅 1:1 放大图一律**不画刻度标签**：数值已由尺寸链与右侧参数表给出，
    # 而刻度标签会与相邻文字（参数表、脚注、另一格标题）互相压住
    # （2026-09-24 实测 7 处）。比例说明"1:1，x∈[35,51] mm"也已移到右侧文字栏。
    axd.tick_params(labelsize=7.5, labelbottom=False, labelleft=False)

    # ================= 详图 (c)：内孔四角 =================
    axi.add_patch(Polygon(poly, closed=True, fc=C_COPPER, ec=C_COPPER_D, lw=0.4))
    axi.plot(P[:, 0], P[:, 1], color="#4A2408", lw=0.6, ls="--", alpha=0.6)
    axi.set_aspect("equal")
    axi.set_xlim(-36.0, -24.0)
    axi.set_ylim(26.0, 38.0)
    axi.grid(alpha=0.22, lw=0.5)
    axi.set_title("图 %d(c) 内孔拐角" % FIG_NO_COIL, fontsize=6.6, pad=4,
                  loc="left")
    axi.tick_params(labelsize=7.2, labelbottom=False, labelleft=False)
    # (c) 坐标区内同样**不放任何文字**：说明统一排到 (c) 下方的文字栏（见下）

    # ---- 参数表（图幅右侧一栏 x ∈ [0.658, 0.985]） ----
    tab = [
        ("图 %d(b)(c) 局部 1:1 放大：节距 ／ 净间隙" % FIG_NO_COIL,
         "%.4f ／ %.4f mm" % (pitch, m["gap"])),
        ("", ""),
        ("输入参数（三个线圈共用）", ""),
        ("coil_size  Lc", "%.4f mm" % V["coil_size"]),
        ("hole_ratio  r_h", "%.4f" % V["hole_ratio"]),
        ("匝数 N / 铜带宽×厚", "%d 匝 ／ %.1f × %.1f mm" % (C["turns"], W, H)),
        ("路径离散", "768 点 / 767 段"),
        ("", ""),
        ("派生几何（实测）", ""),
        ("中心线外/内跨  2·h_out ／ 2·h_in", "%.3f ／ %.3f mm" % (2 * h_out, 2 * h_in)),
        ("铜带内孔净边", "%.3f mm" % (2 * h_in - W)),
        ("匝节距  p", "%.4f mm" % pitch),
        ("匝净间隙  p − w", "%.4f mm" % m["gap"]),
        ("最小净间隙  gap_min", "%.4f mm" % C["gap_min"]),
        ("直边跨距  X ／ Y", "%.3f ／ %.3f mm" % (m["span_x"], m["span_y"])),
        ("外缘包络  X ／ Y", "%.3f ／ %.3f mm" % (m["env_x"], m["env_y"])),
        ("", ""),
        ("三个线圈只差 z", ""),
        ("Tx1 / Tx2 铜带 z", "%+.3f ／ %+.3f mm" % (C["plane_z"]["Tx1"],
                                                   C["plane_z"]["Tx2"])),
        ("Rx 铜带 z", "%+.3f mm（悬高 30）" % C["plane_z"]["Rx"]),
        ("层间介质", "%.2f mm" % C["layer_gap"]),
    ]
    yleft, yright = 0.726, 0.995
    ys = 0.672
    objs = []
    for k, v in tab:
        if not k:
            ys -= 0.005
            continue
        if not v:
            objs.append(fig.text(yleft, ys, k, fontsize=8.2, fontweight="bold",
                                 color=C_DIM))
            ys -= 0.0215
            continue
        objs.append(fig.text(yleft, ys, k, fontsize=7.1, color="#222"))
        objs.append(fig.text(yright, ys, v, fontsize=7.1, color="#222", ha="right"))
        ys -= 0.0185
    anchor_block(fig, objs, 0.168, 0.0, "bottom")   # 表格实测对齐：下沿钉在 y=0.150
    # 说明性脚注**不再画在图上**：左栏主图下方那条空白带只有 ~3.6 mm 宽，
    # 任何成段文字都会压住 y 轴刻度或被图幅裁掉（2026-09-24 反复实测）。
    # 这些口径说明改写在文档 8.8 节 —— 图只保留数字，说明归文字。

    p = os.path.join(FIGDIR, "fig14_single_coil_top.png")
    fig.savefig(p, facecolor=C_BG)
    plt.close(fig)
    print("OK", p)


# ------------------------------------------------------------------ 图 15
def fig_mirror_half():
    rows = read_case()
    xs = np.array([float(r["x_mm"]) for r in rows])
    M13 = np.array([float(r["M13"]) for r in rows])
    M23 = np.array([float(r["M23"]) for r in rows])
    k13 = np.array([float(r["k13"]) for r in rows])
    k23 = np.array([float(r["k23"]) for r in rows])
    S = D["sweep_span"]
    n_full, n_half = D["n_points"], len(xs)

    # 与生产 (12) 步完全相同的镜像展开：M1(−x) := M2(+x)，M2(−x) := M1(+x)
    fx = np.concatenate([-xs[1:][::-1], xs])
    fM1 = np.concatenate([M23[1:][::-1], M13])
    fM2 = np.concatenate([M13[1:][::-1], M23])
    fk13 = np.concatenate([k23[1:][::-1], k13])
    fk23 = np.concatenate([k13[1:][::-1], k23])
    Msum = fM1 + fM2
    assert len(fx) == n_full, (len(fx), n_full)

    # 双阈值判据（与 selfcheck_mirror.py / patch_wpt_contract_mirror.py 同口径）
    pk = max(abs(v) for v in list(fM1) + list(fM2))
    P1 = {"step": 7.1095232,
          "M1p": 3.2610, "M2p": 4.7270, "M1n": 4.6490, "M2n": 3.3590}
    P1["peak"] = max(P1["M1p"], P1["M2p"], P1["M1n"], P1["M2n"])
    P1["ind"] = max(abs(P1["M1n"] - P1["M2p"]), abs(P1["M2n"] - P1["M1p"])) / P1["peak"] * 100
    sp, sn = P1["M1p"] + P1["M2p"], P1["M1n"] + P1["M2n"]
    P1["sum_peak"] = abs(sn - sp) / P1["peak"] * 100
    P1["sum_rel"] = abs(sn - sp) / abs(sp) * 100

    # 版面（图坐标，自下而上；各元素高度均已按实测像素核算）：
    #   收益核算框 0.134~0.245 ／ axb 0.228~0.373 ／ 合并图例 0.410~0.548
    #   ax2 0.580~0.695 ／ ax1 0.725~0.805 ／ axt 0.845~0.955
    fig = plt.figure(figsize=(13.6, 13.8))
    axt = fig.add_axes([0.075, 0.845, 0.855, 0.110])
    ax1 = fig.add_axes([0.075, 0.702, 0.855, 0.095])
    ax2 = fig.add_axes([0.075, 0.573, 0.855, 0.115])
    axb = fig.add_axes([0.075, 0.221, 0.855, 0.145])

    # ================= 上幅 =================
    Y_SOLVE, Y_MIRROR = 0.60, 0.34
    axt.axvline(0, color=C_RED, lw=1.8, ls="--", zorder=2)
    axt.text(0, 1.02, "镜像面  x = 0", color=C_RED, fontsize=9.6, ha="center",
             va="bottom", transform=axt.get_xaxis_transform())
    axt.fill_betweenx([-0.05, 1.0], 0, S / 2, color="#EAF7EF", zorder=0)
    axt.fill_betweenx([-0.05, 1.0], -S / 2, 0, color="#FDF3E7", zorder=0)
    axt.text(S / 4, 0.93, "仿真区（x ≥ 0）：%d 点" % n_half, color=C_RX,
             fontsize=11, ha="center", va="center", fontweight="bold")
    axt.text(-S / 4, 0.93, "镜像展开区（x < 0）：%d 点，零额外求解" % (n_full - n_half),
             color=C_COPPER_D, fontsize=11, ha="center", va="center", fontweight="bold")
    axt.plot([0, S / 2], [Y_SOLVE, Y_SOLVE], color=C_RX, lw=1.2, zorder=3)
    axt.plot(xs, [Y_SOLVE] * len(xs), "o", color=C_RX, ms=6, zorder=5)
    axt.plot([-S / 2, 0], [Y_MIRROR, Y_MIRROR], color=C_COPPER_D, lw=1.2, zorder=3)
    axt.plot(-xs[1:], [Y_MIRROR] * (len(xs) - 1), "o", mfc="none", mec=C_COPPER_D,
             mew=1.5, ms=6, zorder=5)
    for x in xs[1:]:
        axt.plot([-x, x], [Y_MIRROR, Y_SOLVE], color="#9AA0A6", lw=0.5,
                 ls=":", alpha=0.55, zorder=1)
    axt.text(S / 2 + 6, Y_SOLVE, "x = i·S/40，i = 0…%d\n步长 %.4f mm，半宽 ±%.3f mm"
             % (n_half - 1, xs[1] - xs[0], S / 2), fontsize=8.8, color=C_RX,
             va="center")
    axt.text(-S / 4, 0.50, "镜像展开点（由右半已解点交换得到）",
             color=C_COPPER_D, fontsize=9.2, ha="center", va="center")
    # Tx1/Tx2 示意
    for cx, col, lab in ((-D["center_dist"] / 2, C_COPPER_D, "Tx1（上层）"),
                         (D["center_dist"] / 2, C_COPPER, "Tx2（下层）")):
        axt.plot([cx - 93.7, cx + 93.7], [0.14, 0.14], color=col, lw=3.2,
                 solid_capstyle="butt", zorder=4)
        axt.text(cx, 0.055, "%s  中心 x = %+.3f" % (lab, cx), color=col,
                 fontsize=8.8, ha="center", va="top")
    # 中心距：尺寸箭头与文字分成两条独立元素 —— 文字必须落在"连线的稀疏高度"上，
    # 否则 20 条镜像连线会从文字中间穿过去（实测 y=0.255 处有 27 个连线点落在文字框内）。
    axt.annotate("", xy=(-D["center_dist"] / 2, 0.175), xytext=(D["center_dist"] / 2, 0.175),
                 arrowprops=dict(arrowstyle="<->", color="#555", lw=1.2))
    axt.text(0, 0.200, "两发射线圈中心距 %.2f mm（Tx1 z=+0.325 / Tx2 z=−0.325，"
                       "沿 x 镜像差一个 z 翻转 → 非严格镜像）" % D["center_dist"],
             fontsize=8.8, color="#555", ha="center", va="bottom")
    axt.set_xlim(-S / 2 - 78, S / 2 + 78)
    axt.set_ylim(-0.06, 1.0)
    axt.set_yticks([])
    axt.set_xlabel("接收线圈位移 x (mm)")
    axt.set_title("图 %d(a)  半扫 + 镜像展开的采样点关系" % FIG_NO_MIRROR + "：全扫 41 点 → 实测 21 点 + "
                  "镜像 20 点（采样点减少 %.1f%%）"
                  % ((1 - n_half / n_full) * 100), fontsize=12.2, pad=30)
    # 三个图例合并成**一块**，整块放到坐标区之外的空白带里（右侧）；
    # 判据是"框内图元点 = 0"且"不越出图幅"，由 fig1415_occlusion_check.py 复核。
    fig.legend(handles=[
        plt.Line2D([], [], marker="o", ls="-", color=C_RX, ms=6,
                   label="(a) 实测求解点（x ≥ 0）"),
        plt.Line2D([], [], marker="o", ls="", color=C_COPPER_D, ms=6, mfc="none",
                   label="(a) 镜像展开点（x < 0）"),
        Patch(fc="none", ec="none", label=""),
        plt.Line2D([], [], color=C_COPPER_D, lw=1.6, marker="o", ms=5,
                   label="(b1) M13（峰谷 %.3f μH）" % float(fM1.max() - fM1.min())),
        Patch(fc="none", ec="none", label=""),
        plt.Line2D([], [], color=C_RX, lw=1.6, marker="s", ms=5,
                   label="(b2) M23（峰值 %.3f μH）" % float(fM2.max())),
        plt.Line2D([], [], color="#7D3C98", lw=1.6,
                   label="(b2) M_sum = M13+M23"),
    ], loc="upper right", bbox_to_anchor=(0.998, 0.548), ncol=1, fontsize=8.4,
        framealpha=0.95, labelspacing=0.75, handlelength=2.0)

    # (a) 那一格不再单独放图例（其含义已并入上面这块合并图例）

    # ================= 中幅：为什么拆成两格 =================
    # M13 的整条峰谷只有 1.055 μH，而 M23 峰值 10.927 μH —— 同轴显示时 M13 会被压成
    # 贴着零线的一条直线（实测振幅仅占 9.7 %），曲线形状完全读不出来。
    # 因此把互感曲线拆成上下两格、各自一个纵轴（(b1) 只放 M13，(b2) 放 M23 与 M_sum）。
    half = fx >= -1e-9
    for ax_ in (ax1, ax2):
        ax_.axvline(0, color=C_RED, lw=1.2, ls="--", alpha=0.8)
        ax_.axhline(0, color="#888", lw=0.8)
        ax_.set_xlim(-S / 2 - 20, S / 2 + 20)
        ax_.grid(alpha=0.25, lw=0.5)

    ax1.plot(fx[~half], fM1[~half], "o", mfc="none", mec=C_COPPER_D, mew=1.5, ms=6,
             label="左半 = 镜像展开点（x < 0）")
    ax1.plot(fx[half], fM1[half], "o-", color=C_COPPER_D, lw=1.6, ms=5,
             label="右半 = 实测（x ≥ 0）")
    i13 = int(np.argmin(fM1[half]))          # 在右半（实测）里找最负点
    x13 = float(fx[half][i13])
    # 该格的空白区很小（曲线右半在 x>150 处回升到 0 附近），所以只放文字、不拉箭头：
    # 拉箭头就会从曲线/连线上穿过（实测该曲线有 6 个点落在标签框内）。
    # 数值本身写在文字里，位置已由颜色与文字自明。
    ax1.text(-232, 0.62, "M13 最负 %.3f μH @ x = ±%.3f mm" % (fM1[half][i13], x13),
             fontsize=8.6, color=C_COPPER_D, ha="left", va="center")
    ax1.set_ylabel("M13 (μH)", fontsize=8.6)
    ax1.set_title("图 %d(b1)  M13 = M(Tx1-Rx)：左半（x < 0）由右半已解点交换得到，"
                  "单独一个纵轴，峰谷 %.3f μH 才看得清"
                  % (FIG_NO_MIRROR, float(fM1.max() - fM1.min())),
                  fontsize=10.0, pad=4)
    # (b1)(b2) 的图例已并入上面那块合并图例（放在坐标区之外），此处不再单独放。
    # 同时把 (b1) 的 x 轴文字整体隐去：两格共用横轴，(b2) 的刻度与轴标题已足够，
    # 而 (b1) 的轴标题会与 (b2) 的标题在上下空隙里相撞（实测压字 63 %）。
    ax1.tick_params(labelsize=8, labelbottom=False)
    ax1.set_xlabel("")
    # 显式固定刻度：否则自动定位器会在两格之间留下上一轮状态的残留标签，
    # 那些标签不显示却仍参与包围盒，会报出"看不见的重叠"（2026-09-24 实测）。
    ax1.set_yticks([-1.0, 0.0])
    ax1.tick_params(axis="y", labelsize=7, pad=1)
    ax2.set_xticks([-200, -100, 0, 100, 200])
    ax2.set_yticks([0, 4, 8, 12])
    ax1.tick_params(labelbottom=False)          # 横轴刻度留给 (b2)，避免与标题挤

    ax2.plot(fx[~half], fM2[~half], "s", mfc="none", mec=C_RX, mew=1.5, ms=6,
             label="M23 左半 = 镜像展开点")
    ax2.plot(fx[half], fM2[half], "s-", color=C_RX, lw=1.6, ms=5,
             label="M23 右半 = 实测（x ≥ 0）")
    ax2.plot(fx, Msum, "-", color="#7D3C98", lw=1.4, alpha=0.9,
             label="M_sum = M13 + M23（和口径，交付目标量）")
    # (b2) 峰值标注：改用"独立文字 + 独立箭头"，放在曲线已落平的最右侧空白处。
    # 不用 annotate 是因为它的包围盒会把箭头也并进来（实测高 100+ px），
    # 于是"框内图元点"这类检查会误判、也无法精确控制遮挡。
    ipk = int(np.argmax(fM2))
    ax2.annotate("", xy=(fx[ipk], fM2[ipk]), xytext=(195, 1.6),
                 arrowprops=dict(arrowstyle="->", color=C_RX, lw=1.1))
    ax2.text(205, 0.5, "M23 峰值 %.3f μH @ x = ±%.3f mm" % (fM2[ipk], fx[ipk]),
             fontsize=8.6, color=C_RX, ha="right", va="bottom")
    ax2.set_xlabel("接收线圈位移 x (mm)", labelpad=0)
    ax2.set_ylabel("互感 (μH)", fontsize=8.6)
    ax2.set_title("图 %d(b2)  M23 与 M_sum：左半同为镜像展开点；曲线全部来自 %d 个真实解出的点，"
                  "无插值、无拟合" % (FIG_NO_MIRROR, n_half), fontsize=10.0, pad=4)
    # (b2) 的图例已并入合并图例（放在坐标区之外），此处不再单独放
    ax2.tick_params(labelsize=8)

    # ================= 下幅：双阈值判据 =================
    axb.axis("off")
    axb.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)
    axb.set_xticks([]); axb.set_yticks([])      # 双保险：axis("off") 后刻度标签仍会被计入包围盒
    axb.set_xlim(0, 1); axb.set_ylim(0, 1)
    axb.text(0.0, 0.97,
             "图 %d(c)  镜像正确性校验" % FIG_NO_MIRROR + " —— 双阈值判据（口径同 selfcheck_mirror.py / "
             "wpt_contract.mirror_check）",
             fontsize=10.6, fontweight="bold", va="top",
             bbox=dict(fc="#FFFFFF", ec="none", alpha=0.95, boxstyle="round,pad=0.15"))
    axb.text(0.0, 0.855,
             "为什么必须双阈值：Tx 分层（Tx1 z=+0.325、Tx2 z=−0.325）而 Rx 单层（z=+30），"
             "沿 x 镜像保持 z 不变，故 M1/M2 存在 ~2 % 的固有非对称；\n"
             "但半扫的展开是「交换」（M1(−x):=M2(+x)、M2(−x):=M1(+x)），「和」守恒 —— "
             "所以判据拆成两条：和口径 ≤ 2 %（决定目标量能否用半扫）、个体口径 ≤ 3 %"
             "（只影响导出列）。",
             fontsize=8.6, va="top", color="#333", linespacing=1.5)
    axb.text(0.0, 0.625,
             "峰值归一化：|M|_peak = %.4f μH（P1 参考点四个实测值取最大）" % P1["peak"],
             fontsize=8.6, va="top", color="#333")

    hdr = ["判据", "阈值", "P1 参考点双侧实测（x = ±%.4f mm）" % P1["step"],
           "判定"]
    colx = [0.0, 0.150, 0.245, 0.720]
    rows_t = [
        ["和口径", "≤ 2 %",
         "|Δ(M1+M2)| / 峰值：M1+M2 由 %+.4f → %+.4f，Δ = %.4f  →  %.3f %%"
         % (sp, sn, sn - sp, P1["sum_peak"]), "通过"],
        ["个体口径", "≤ 3 %",
         "max|ΔM1|,|ΔM2| / 峰值：%.4f vs %.4f；%.4f vs %.4f  →  %.3f %%"
         % (P1["M1p"], P1["M2n"], P1["M2p"], P1["M1n"], P1["ind"]), "通过"],
    ]
    yy = 0.485
    for i, cx in enumerate(colx):
        axb.text(cx, yy, hdr[i], fontsize=8.8, fontweight="bold",
                 color=C_DIM, va="center")
    axb.plot([0, 1], [yy - 0.038, yy - 0.038], color=C_DIM, lw=1.0)
    yy -= 0.088
    for r in rows_t:
        axb.text(colx[0], yy, r[0], fontsize=8.8, va="center")
        axb.text(colx[1], yy, r[1], fontsize=8.8, va="center")
        axb.text(colx[2], yy, r[2], fontsize=8.2, va="center")
        axb.text(colx[3], yy, r[3], fontsize=9.0, va="center", color=C_RX,
                 fontweight="bold")
        yy -= 0.082
    axb.text(0.0, yy + 0.008,
             "|M|_peak 口径下的相对量；和口径若按和值归一化则为 %.3f %%。"
             "同批 186 工况自检表 mirror_ind_pct ∈ [%.3f %%, %.3f %%]，全部 < 3 %%。"
             % (P1["sum_rel"], 0.1088, 2.8257),
             fontsize=8.5, va="top", color="#333")
    axb.text(0.0, 0.095,
             "注意：半扫曲线自身的「镜像误差」是构造性成立的（展开即交换，和口径必然 0.000 %%）"
             "—— 真正的镜像前提验证只能靠双侧实测，即上表 P1 参考点（x = ±7.1095 mm 各解一次）；\n"
             "每工况另用 x = 0 处的固有非对称度 asym_pct 打标（b1_0186：M13 = −0.082、"
             "M23 = +0.071 μH；该点在过零附近量级过小，其百分数口径不可比）。",
             fontsize=8.5, va="top", color="#333", linespacing=1.5)

    # ---- 收益标注（用 anchored_box：四边留白由实测包围盒决定，不再顶到边框）----
    n_solved = 0
    mins = 0.0
    for f in glob.glob(r"C:\ansys maxwell2024\_work\b1\b1_raw_run*.csv"):
        for r in csv.DictReader(open(f, encoding="utf-8")):
            n_solved += 1
            mins += float(r["minutes"])
    avg = mins / n_solved
    save_pts = 256 * 20
    benefit = fig.text(
        0.985, 0.245, "收益核算\n"
        "· 单工况：%d → %d 点（−%.1f %%）\n"
        "· 本工况实测机时 %.1f min\n"
        "· 全批 256 工况：%d → %d 点\n"
        "  共省 %d 点\n"
        "· 均值 %.2f min/点 × 8 实例并行\n"
        "  → 省 %.0f 机时 ≈ %.1f 天"
        % (n_full, n_half, (1 - n_half / n_full) * 100,
           sum(float(r["minutes"]) for r in rows),
           256 * n_full, 256 * n_half, save_pts, avg,
           save_pts * avg / 60, save_pts * avg / 60 / 8 / 24),
        ha="right", va="top", fontsize=8.2, color="#333", linespacing=1.5)
    assert benefit is not None
    draw_box_around(fig, benefit, "#FBF5E8", "#B7950B", 0.95, 10.0)

    p = os.path.join(FIGDIR, "fig15_mirror_half_sweep.png")
    fig.savefig(p, facecolor=C_BG)
    plt.close(fig)
    print("OK", p)
    print("[图15] 点数 full=%d half=%d  峰值|M|=%.4f" % (n_full, n_half, pk))
    print("[图15] P1 和口径峰值归一 %.3f%%（和值归一 %.3f%%）  个体口径 %.3f%%"
          % (P1["sum_peak"], P1["sum_rel"], P1["ind"]))
    print("[图15] b1_0186 已解点数 %d，机时 %.1f min，均值 %.2f min/点（全批 %d 点）"
          % (len(rows), sum(float(r["minutes"]) for r in rows),
             sum(float(r["minutes"]) for r in rows) / len(rows), n_solved))


if __name__ == "__main__":
    os.makedirs(FIGDIR, exist_ok=True)
    fig_single_coil_top()
    fig_mirror_half()
    print("全部完成 ->", FIGDIR)
