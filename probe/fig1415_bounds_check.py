# -*- coding: utf-8 -*-
"""逐个报告图 14 / 图 15 里每个文字对象的包围盒与图幅边界的关系。

判据：包围盒超出图幅（或超出其所属 axes 的绘图区）即为"被截断"。
上一版自检只查了"文字互相压字"，漏了"文字被图幅/axes 裁掉"这一类缺陷。
"""
import importlib.util

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

spec = importlib.util.spec_from_file_location(
    "f1415", r"C:\ansys maxwell2024\_probe\case_b1_0186_figs14_15.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

orig = plt.Figure.savefig


def spy(self, fname, **kw):
    self.canvas.draw()
    r = self.canvas.get_renderer()
    W, H = self.canvas.get_width_height()
    print("\n### %s  图幅 %dx%d px" % (fname, W, H))
    items = []
    for k, ax in enumerate(self.axes):
        for t in list(ax.texts) + [ax.title, ax.xaxis.label, ax.yaxis.label]:
            if t.get_text().strip():
                items.append(("ax%d" % k, t.get_text(), t.get_window_extent(r)))
        lg = ax.get_legend()
        if lg is not None:
            items.append(("ax%d-legend" % k, "<图例>", lg.get_window_extent(r)))
    for t in self.texts:
        if t.get_text().strip():
            items.append(("fig", t.get_text(), t.get_window_extent(r)))

    n_clip = 0
    for owner, txt, b in items:
        out = []
        if b.x0 < -0.5:
            out.append("左越界 %.0f px" % -b.x0)
        if b.x1 > W + 0.5:
            out.append("右越界 %.0f px" % (b.x1 - W))
        if b.y0 < -0.5:
            out.append("下越界 %.0f px" % -b.y0)
        if b.y1 > H + 0.5:
            out.append("上越界 %.0f px" % (b.y1 - H))
        if out:
            n_clip += 1
            print("  !! 出界 [%s] %-28s x[%.0f,%.0f] y[%.0f,%.0f]  %s"
                  % (owner, txt.replace("\n", "⏎")[:28], b.x0, b.x1, b.y0, b.y1,
                     "、".join(out)))
    # 打印底边附近（y0 < 30 px）的所有对象，便于人工核对
    print("  -- 贴近底边的对象（包围盒下沿 < 30 px）--")
    for owner, txt, b in sorted(items, key=lambda z: z[2].y0)[:6]:
        print("     [%s] %-28s y[%.0f,%.0f] x[%.0f,%.0f]"
              % (owner, txt.replace("\n", "⏎")[:28], b.y0, b.y1, b.x0, b.x1))
    print("  ==> 出界对象 %d 个" % n_clip)
    return orig(self, fname, **kw)


plt.Figure.savefig = spy
try:
    mod.fig_single_coil_top()
    mod.fig_mirror_half()
finally:
    plt.Figure.savefig = orig
