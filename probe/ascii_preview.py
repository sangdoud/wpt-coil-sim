# -*- coding: utf-8 -*-
"""把生成的 PNG 渲染成 ASCII 供无图像能力时校验版面。

用法: python ascii_preview.py <png> [cols] [rows]
颜色分类： 空白 / 浅灰(网格) / 深灰(铁氧体) / 橙(铜) / 绿(Rx) / 蓝(Region) / 黑(文字线)
"""
import sys

import numpy as np
from PIL import Image


def classify(px):
    r, g, b = int(px[0]), int(px[1]), int(px[2])
    mx, mn = max(r, g, b), min(r, g, b)
    sat = mx - mn
    lum = (r + g + b) / 3.0
    if sat < 24:
        if lum > 246:
            return ' '
        if lum > 205:
            return '.'
        if lum > 120:
            return ':'
        return '#'
    if r > g >= b and r - b > 40:
        return 'C' if r > 150 else 'c'      # 橙/铜
    if g >= r and g > b:
        return 'G'                          # 绿
    if b >= r and b >= g:
        return 'B'                          # 蓝
    return '*'


def main():
    p = sys.argv[1]
    cols = int(sys.argv[2]) if len(sys.argv) > 2 else 150
    rows = int(sys.argv[3]) if len(sys.argv) > 3 else 44
    im = Image.open(p).convert("RGB")
    W, H = im.size
    a = np.asarray(im).astype(np.int16)
    sat = a.max(axis=2) - a.min(axis=2)
    lum = a.mean(axis=2)
    ink = ((sat > 24) | (lum < 235)).mean() * 100
    print("=== %s  %dx%d  着墨 %.1f%% ===" % (p, W, H, ink))
    cw, ch = W / cols, H / rows
    for j in range(rows):
        line = ''
        for i in range(cols):
            y0, y1 = int(j * ch), max(int((j + 1) * ch), int(j * ch) + 1)
            x0, x1 = int(i * cw), max(int((i + 1) * cw), int(i * cw) + 1)
            blk = a[y0:y1, x0:x1]
            if blk.size == 0:
                line += ' '
                continue
            bs = blk.max(axis=2) - blk.min(axis=2)
            bl = blk.mean(axis=2)
            # 优先显示彩色，其次深色
            colmask = (bs > 24)
            if colmask.mean() > 0.18:
                px = blk[colmask].mean(axis=0)
                line += classify(px)
            elif (bl < 120).mean() > 0.06:
                line += '#'
            elif (bl < 205).mean() > 0.12:
                line += ':'
            elif (bl < 246).mean() > 0.06:
                line += '.'
            else:
                line += ' '
        print("%4d|%s" % (j * ch, line))
    print("图例: (空)白 . 浅灰 : 中灰 # 深色/文字 C 铜色 c 暗铜 G 绿 B 蓝 * 其他")


if __name__ == "__main__":
    main()
