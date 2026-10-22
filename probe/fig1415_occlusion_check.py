# -*- coding: utf-8 -*-
"""图 14 / 图 15 的第三类几何自检：**图例、注记框是否盖住了曲线/散点/标注线**。

前两个脚本只查"文字互相压字"与"文字出界"，查不出"图例压在曲线上"——
那类缺陷文字包围盒之间毫无交集，但看图就是糊在一起。
本脚本把每个可见图元（曲线、marker、扫描条、连线的顶点）换算成像素，
再与图例/注记框的包围盒求交，报出"图元点落在框内"的数量。
"""
import importlib.util

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

spec = importlib.util.spec_from_file_location(
    "f1415", r"C:\ansys maxwell2024\_probe\case_b1_0186_figs14_15.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

orig = plt.Figure.savefig


def artist_points(ax, r):
    """把该 axes 里所有可见曲线/marker/线段的顶点取成像素坐标数组。"""
    pts = []
    for ln in ax.get_lines():
        if not ln.get_visible():
            continue
        xy = ln.get_xydata()
        if len(xy) == 0:
            continue
        p = ax.transData.transform(xy)
        pts.append(p)
    for c in ax.collections:                      # fill_betweenx 之类的面
        for path in c.get_paths() or []:
            v = path.vertices
            if len(v):
                pts.append(ax.transData.transform(v))
    return np.vstack(pts) if pts else np.zeros((0, 2))


def check(fig, name):
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    print("\n### %s" % name)
    bad = 0
    for k, ax in enumerate(fig.axes):
        P = artist_points(ax, r)
        if len(P) == 0:
            continue
        boxes = []
        lg = ax.get_legend()
        if lg is not None:
            boxes.append(("图例", lg.get_window_extent(r)))
        for t in ax.texts:
            if t.get_text().strip() and t.get_bbox_patch() is not None:
                boxes.append(("注记框:" + t.get_text().split("\n")[0][:16],
                              t.get_bbox_patch().get_window_extent(r)))
        for tag, b in boxes:
            inside = ((P[:, 0] >= b.x0) & (P[:, 0] <= b.x1) &
                      (P[:, 1] >= b.y0) & (P[:, 1] <= b.y1))
            n = int(inside.sum())
            if n:
                bad += 1
                frac = n / len(P) * 100
                print("  !! axes%d [%s] 框 x[%.0f,%.0f] y[%.0f,%.0f] 内有 %d 个图元点"
                      "（占 %.1f%%）" % (k, tag, b.x0, b.x1, b.y0, b.y1, n, frac))
    if not bad:
        print("  ==> 无图例/注记框盖住曲线")
    else:
        print("  ==> %d 处遮挡" % bad)
    return bad


def spy(self, fname, **kw):
    check(self, str(fname))
    return orig(self, fname, **kw)


plt.Figure.savefig = spy
try:
    mod.fig_single_coil_top()
    mod.fig_mirror_half()
finally:
    plt.Figure.savefig = orig
