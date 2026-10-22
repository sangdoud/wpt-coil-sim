# -*- coding: utf-8 -*-
"""程序化校验图 14 / 图 15 的排版：把所有文字取真实包围盒，检测重叠。

这是本项目"宁删不加"流程里用过的判据（图 7 曾用同法把重叠磨到 0 处）：
  - Text  -> get_window_extent(renderer)
  - 图例  -> get_window_extent(renderer)
  - 轴标题/轴标签 -> 也纳入
重叠面积占较小者面积 > 12% 即判为"压字"。
"""
import importlib.util
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "f1415", r"C:\ansys maxwell2024\_probe\case_b1_0186_figs14_15.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def boxes(fig):
    """返回 [(标签, 包围盒)]，只统计可见文字（空文字如 set_xlabel("") 跳过）。"""
    r = fig.canvas.get_renderer()
    out = []
    for ax in fig.axes:
        for t in ax.texts:
            if not t.get_text().strip():
                continue
            out.append((("ax" + str(fig.axes.index(ax)) + ":" +
                         t.get_text().replace("\n", "⏎")[:34]),
                        t.get_window_extent(r)))
        for t in (ax.title, ax.xaxis.label, ax.yaxis.label):
            if t.get_text().strip() and t.get_visible():
                out.append((("lbl:" + t.get_text().replace("\n", "⏎")[:34]),
                            t.get_window_extent(r)))
        # 刻度标签也要算进来：fig.text 压住"Tx1（上层）中心 x =…"这类刻度/轴文字，
        # 正是漏检过的一类（2026-09-24 由用户目视发现）。
        for t in list(ax.get_xticklabels()) + list(ax.get_yticklabels()):
            if t.get_text().strip() and t.get_visible():
                out.append(("tick:" + t.get_text()[:22], t.get_window_extent(r)))
        lg = ax.get_legend()
        if lg is not None:
            out.append(("legend@" + str(fig.axes.index(ax)),
                        lg.get_window_extent(r)))
    for lg in fig.legends:                     # figure 级合并图例
        out.append(("fig-legend", lg.get_window_extent(r)))
    for t in fig.texts:
        if t.get_text().strip():
            out.append(("fig:" + t.get_text().replace("\n", "⏎")[:34],
                        t.get_window_extent(r)))
    return out


def check(name, fn):
    orig = plt.Figure.savefig

    def spy(self, fname, **kw):
        self.canvas.draw()
        bs = boxes(self)
        n_bad = 0
        for i in range(len(bs)):
            for j in range(i + 1, len(bs)):
                (la, a), (lb, b) = bs[i], bs[j]
                x0, y0 = max(a.x0, b.x0), max(a.y0, b.y0)
                x1, y1 = min(a.x1, b.x1), min(a.y1, b.y1)
                if x1 <= x0 or y1 <= y0:
                    continue
                inter = (x1 - x0) * (y1 - y0)
                small = min(a.width * a.height, b.width * b.height)
                if small > 0 and inter / small > 0.12:
                    n_bad += 1
                    print("  !! 压字 %.0f%%  [%s]  ×  [%s]" %
                          (inter / small * 100, la, lb))
        print("=== %s：文字/图例对象 %d 个，重叠 %d 处 ===" % (name, len(bs), n_bad))
        return orig(self, fname, **kw)

    plt.Figure.savefig = spy
    try:
        fn()
    finally:
        plt.Figure.savefig = orig


if __name__ == "__main__":
    check("图 14 单个线圈俯视图", mod.fig_single_coil_top)
    check("图 15 镜像半扫加速", mod.fig_mirror_half)
