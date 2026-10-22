# -*- coding: utf-8 -*-
"""定位线圈路径里的尖角（方向突变）：参数化径向重映射在极端 (LC, KR) 下是否产生折角。

对每个 (LC, KR)：
  1) 逐段计算方向变化（转角），列出最大的若干个
  2) 给出该处的坐标、切比雪夫半径、相邻段长度 -> 判断是"短段尖刺"还是"长段折角"
  3) 与参考点(原模型)对照，判断这是原模型固有、还是参数化引入的
"""
import math
import sys

import numpy as np

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG          # noqa: E402


def kinks(LC, KR, label, topn=8):
    P = CG.make_path(LC, KR)[:, :2]
    v = P[1:] - P[:-1]
    seg = np.linalg.norm(v, axis=1)
    ang = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    dang = np.abs((np.diff(ang) + 180.0) % 360.0 - 180.0)
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    order = np.argsort(-dang)
    print("=" * 116)
    print("%s  LC=%.4f KR=%.4f   （匝径向间距 %.3f mm，段数 %d）"
          % (label, LC, KR, (s[64] - s[0]), len(P) - 1))
    print("  转角统计: 中位 %.3f°  90分位 %.3f°  最大 %.3f°  |  >20°的段数 %d"
          % (np.median(dang), np.percentile(dang, 90), dang.max(), int((dang > 20).sum())))
    print("  最尖的 %d 处：" % topn)
    print("     idx   转角°     段长mm    x        y      切比雪夫半径  位置")
    for i in order[:topn]:
        j = int(i)
        pos = "拐角弧" if (j % 64) < 16 else "直边"
        print("    %5d %7.2f %9.3f %9.3f %9.3f %10.2f   %s(idx%%64=%d)"
              % (j, dang[j], seg[j], P[j, 0], P[j, 1], s[j], pos, j % 64))
    return dang


def main():
    kinks(165.0, 0.358674, "参考点(原模型，生产基准)")
    kinks(216.7738, 0.2294, "★屏幕上这个 (b1_0163)")
    kinks(219.9397, 0.3756, "本批 LC 最大")
    kinks(218.8542, 0.4997, "本批 孔比最大")
    kinks(120.1885, 0.2807, "本批 LC 最小")
    kinks(121.7205, 0.4823, "BASE 回退(最紧)")
    print("=" * 116)
    print("判定：若极端工况的最大转角远大于参考点，说明径向重映射在这些参数下")
    print("      把拐角附近的重映射点压成了尖角（视觉上就是『拐弯处变形』）。")


if __name__ == "__main__":
    main()
