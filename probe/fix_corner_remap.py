# -*- coding: utf-8 -*-
"""拐角缺陷的修法验证（离线）。

现状：make_path 用逐点 s = max(|x|,|y|) 做径向重映射。
      拐角圆角处的 s 会掉到环半径以下（模板第1匝 26.45 vs 环 30），
      于是圆角各点的缩放系数与直边不同 -> 圆角被拉成径向尖刺（最大 98.7°）。

修法：把重映射坐标从「逐点 s」换成「该点所属**环**的半径」s_R = 沿路径的局部极大
      （窗口 win 覆盖一个圆角），圆角整体获得同一个缩放系数 -> 形状保持不变。
      参考参数下 k=1，修正后仍是**逐点恒等**（历史验证不受影响）。

本脚本对全批 256 工况比较：修正前后的最大转角、匝间隙、内外锚点、
以及相对现状的最大位移（判断改动幅度是否可接受）。
"""
import csv
import math
import sys

import numpy as np

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG          # noqa: E402

K_LC = CG.k_lc()
H_IN_REF, H_OUT_REF = 30.0, 83.6415


def path_current(LC, KR):
    return CG.make_path(LC, KR)[:, :2]


def ring_coord(P, win):
    """该点所属环的半径：沿路径对 s 做滑动局部极大（环绕不做，端点用边缘复制）。"""
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    n = len(s)
    idx = np.arange(n)[:, None] + np.arange(-win, win + 1)[None, :]
    idx = np.clip(idx, 0, n - 1)
    return s[idx].max(axis=1)


def path_fixed(LC, KR, win=12):
    P = path_current(LC, KR)
    s_R = ring_coord(P, win)
    h_out = LC * K_LC / 2.0
    h_in = KR * LC * K_LC / 2.0
    k = (h_out - h_in) / (H_OUT_REF - H_IN_REF)
    s_new = h_in + (s_R - H_IN_REF) * k
    lam = s_new / s_R
    return P * lam[:, None]


def metrics(P):
    v = np.diff(P, axis=0)
    ang = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    d = np.abs((np.diff(ang) + 180.0) % 360.0 - 180.0)
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    gap = float((s[64:] - s[:-64]).min()) - CG.WIDTH
    return float(d.max()), gap, float(s.max()), float(s.min())


def main():
    rows = list(csv.DictReader(open(r"C:\ansys maxwell2024\_work\b1_plan.csv",
                                    encoding="utf-8-sig")))
    print("=" * 108)
    print("参考点恒等性检查（LC=165, KR=0.358674 — 修正必须逐点不变）")
    P0 = path_current(165.0, 0.358674)
    for win in (8, 12, 16):
        P1 = path_fixed(165.0, 0.358674, win)
        print("  win=%2d  最大位移 %.3e mm   %s"
              % (win, np.abs(P1 - P0).max(),
                 "恒等 ✓" if np.abs(P1 - P0).max() < 1e-9 else "★非恒等"))
    print()
    print("窗口大小选择（全批 256 工况的最大转角分布）")
    for win in (6, 8, 10, 12, 16, 20):
        mx = []
        for r in rows:
            P = path_fixed(float(r["coil_size"]), float(r["hole_ratio"]), win)
            mx.append(metrics(P)[0])
        mx = np.array(mx)
        print("  win=%2d  最大转角: 中位 %.2f°  p90 %.2f°  最大 %.2f°  >15°的工况 %d/256"
              % (win, np.median(mx), np.percentile(mx, 90), mx.max(), int((mx > 15).sum())))
    print()
    win = 12
    print("修正前 vs 修正后（逐工况，win=%d）" % win)
    print("  %-9s %7s %7s | %8s %8s | %8s %8s | %8s"
          % ("case", "LC", "KR", "转角前", "转角后", "间隙前", "间隙后", "最大位移"))
    worst_shift = 0.0
    before, after = [], []
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        Pa = path_current(LC, KR)
        Pb = path_fixed(LC, KR, win)
        ma, mb = metrics(Pa), metrics(Pb)
        before.append(ma[0])
        after.append(mb[0])
        sh = float(np.abs(Pb - Pa).max())
        worst_shift = max(worst_shift, sh)
        if r["case_id"] in ("b1_0163", "b1_0169", "b1_0126", "b1_0213", "b1_0236",
                            "b1_0254", "b1_0003"):
            print("  %-9s %7.2f %7.4f | %8.2f %8.2f | %8.3f %8.3f | %8.3f mm"
                  % (r["case_id"], LC, KR, ma[0], mb[0], ma[1], mb[1], sh))
    before, after = np.array(before), np.array(after)
    print()
    print("全批统计：")
    print("  最大转角  修正前 中位 %.2f° / p90 %.2f° / max %.2f°  (>15°: %d/256)"
          % (np.median(before), np.percentile(before, 90), before.max(), int((before > 15).sum())))
    print("            修正后 中位 %.2f° / p90 %.2f° / max %.2f°  (>15°: %d/256)"
          % (np.median(after), np.percentile(after, 90), after.max(), int((after > 15).sum())))
    print("  相对现状最大位移 %.2f mm（线圈尺度 120~220mm）" % worst_shift)
    # 锚点与间隙一致性
    dmax_in = dmax_out = dmax_gap = 0.0
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        ma, mb = metrics(path_current(LC, KR)), metrics(path_fixed(LC, KR, win))
        dmax_in = max(dmax_in, abs(ma[3] - mb[3]))
        dmax_out = max(dmax_out, abs(ma[2] - mb[2]))
        dmax_gap = max(dmax_gap, abs(ma[1] - mb[1]))
    print("  内孔锚点变化 ≤ %.3f mm  外缘锚点变化 ≤ %.3f mm  匝间隙变化 ≤ %.3f mm"
          % (dmax_in, dmax_out, dmax_gap))


if __name__ == "__main__":
    main()
