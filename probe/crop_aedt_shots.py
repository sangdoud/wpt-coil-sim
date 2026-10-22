# -*- coding: utf-8 -*-
"""从 AEDT 实况截图裁出"模型图"。

裁剪框的确定依据（可复现的判据，而非目测）：
  对三个不同工况（Lc=184.26 / 186.9 / 133.23 mm）的窗口图做逐像素差分。
  UI（菜单栏、功能区、左侧工程树）在三张图里逐像素相同 -> 差分≈0；
  模型随 Lc 改变而改变 -> 差分显著。
  实测差异区包围盒 = x[480,1800] y[380,1020]，据此加边距取
  BOX = (400, 330) - (2020, 1085)，覆盖全部模型且不含任何 UI 元素。

输出内容统计，供文档如实描述截图内容。
"""
import os
import sys

try:
    import numpy as np
    from PIL import Image
except ImportError as e:
    print("缺依赖:", e)
    sys.exit(1)

FIGDIR = r"C:\ansys maxwell2024\_work\case_figures"
BOX = (400, 330, 2020, 1085)          # 左, 上, 右, 下（原始 2062x1126 窗口图坐标）

JOBS = [
    ("live_run0_pid26084.png", "fig1a_live_run0_b1_0186.png",
     "run0 实例，当前工况 b1_0186（Lc = 184.26 mm）"),
    ("live_run1_pid32656.png", "fig1b_live_run1_b1_0167.png",
     "run1 实例，当前工况 b1_0167（Lc = 186.90 mm）"),
    ("live_run3_pid41368.png", "fig1c_live_run3_b1_0180.png",
     "run3 实例，当前工况 b1_0180（Lc = 133.23 mm）"),
]


def stats(img):
    a = np.asarray(img, dtype=np.int16)
    r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    sat = a.max(axis=2) - a.min(axis=2)
    lum = a.mean(axis=2)
    model = (sat > 25) | (lum < 205)
    copper = (r > g) & (g > b) & ((r - b) > 55) & (r > 110)
    white = (sat <= 12) & (lum > 245)
    n = model.size
    return (100.0 * model.sum() / n, 100.0 * copper.sum() / n,
            100.0 * white.sum() / n)


def main():
    for src, dst, label in JOBS:
        p = os.path.join(FIGDIR, src)
        if not os.path.exists(p):
            print("!! 缺文件", p)
            continue
        img = Image.open(p).convert("RGB").crop(BOX)
        f_model, f_copper, f_white = stats(img)
        out = os.path.join(FIGDIR, dst)
        img.save(out)
        print("%-30s -> %-32s %dx%d" % (src, dst, img.width, img.height))
        print("     几何/材料像素 %.1f%%（铜 %.1f%%）  空白背景 %.1f%%   |  %s"
              % (f_model, f_copper, f_white, label))
    return 0


if __name__ == "__main__":
    sys.exit(main())
