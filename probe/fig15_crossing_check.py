# -*- coding: utf-8 -*-
"""图 15 第五类自检：**线条/图元是否从文字标签或图例框中间穿过**。

前四类自检（压字、出界、底色框、图例遮曲线）都基于"包围盒相交"，
查不出"一条线从标签正中间划过去"——线不是文字、也不进图例框，
但看图就是"标签被线劈开"。本脚本逐个绘图元单独渲染，与该图元相关的
文字标签求交，报出"线穿过了哪些标签"。
"""
import importlib.util

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Rectangle

spec = importlib.util.spec_from_file_location(
    "f1415", r"C:\ansys maxwell2024\_probe\case_b1_0186_figs14_15.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

orig = plt.Figure.savefig


def line_hits(ax, ln, box, r):
    """该 Line2D 的像素点里，有多少个落在 box 内。"""
    xy = ln.get_xydata()
    if len(xy) == 0:
        return 0
    P = ax.transData.transform(xy)
    return int(((P[:, 0] >= box.x0) & (P[:, 0] <= box.x1) &
                (P[:, 1] >= box.y0) & (P[:, 1] <= box.y1)).sum())


def check(fig, name):
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    print("\n### %s" % name)
    bad = 0
    for k, ax in enumerate(fig.axes):
        labels = []
        for t in ax.texts:
            if t.get_text().strip():
                labels.append((t.get_text().replace("\n", "⏎")[:26],
                               t.get_window_extent(r)))
        for t in (ax.title, ax.xaxis.label, ax.yaxis.label):
            if t.get_text().strip():
                labels.append(("轴文字:" + t.get_text().replace("\n", "⏎")[:22],
                               t.get_window_extent(r)))
        for ln in ax.get_lines():
            if not ln.get_visible():
                continue
            lab = str(ln.get_label())
            if lab.startswith("_"):
                lab = "线"
            for tag, box in labels:
                n = line_hits(ax, ln, box, r)
                if n >= 3:                     # ≥3 个顶点落在文字框内 = 穿过
                    bad += 1
                    print("  !! axes%d 线[%s] 有 %d 个点落在标签[%s]的框内"
                          % (k, lab[:20], n, tag))
    print("  ==> 线穿标签 %d 处" % bad)
    return bad


def spy(self, fname, **kw):
    check(self, str(fname))
    return orig(self, fname, **kw)


plt.Figure.savefig = spy
try:
    mod.fig_mirror_half()
finally:
    plt.Figure.savefig = orig
