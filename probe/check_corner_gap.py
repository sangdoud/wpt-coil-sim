# -*- coding: utf-8 -*-
"""拐角几何核查：径向重映射后，拐角处相邻匝的**真实（欧氏）**间隙是多少？

背景：coil_gen.make_path 用「切比雪夫半径径向重映射」把参考路径缩放到 (LC, KR)：
    s(p) = max(|dx|,|dy|)，s' = h_in' + (s - h_in_ref)·k，p' = 中心 + (p-中心)·s'/s
在**平边**上 s 恰好等于环半径，缩放是纯径向的 -> 匝间隙 = (h_out-h_in)/12 均匀；
但在**拐角圆弧**上 s 由较大的那个分量决定，各点的缩放系数不同 -> 拐角处的
匝与匝之间可能出现非径向偏移，真实间隙可能小于径向间隙。

本脚本对每个 (LC, KR)：
  1) 复算文档口径的 gap_min（径向）
  2) 逐点算 i 与 i+64（同角度、相邻匝）的欧氏距离 -> 拐角/平边分别统计
  3) 全网最小「点到非相邻线段」距离（真正的自交/夹紧检查）
  4) 报告最小值出现在模板索引的哪个位置（每匝 64 点 = 4 组「8 弧 + 8 直边」）
"""
import sys

import numpy as np

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG          # noqa: E402

WIDTH = CG.WIDTH
TURN = 64                      # 768 / 12


def analyse(LC, KR, label=""):
    P = CG.make_path(LC, KR)[:, :2]
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    radial = float((s[TURN:] - s[:-TURN]).min())
    d = np.linalg.norm(P[TURN:] - P[:-TURN], axis=1)
    n = len(d)
    # 模板结构：每匝 64 点 = 4 × (8 弧 + 8 直边)；弧在前 8 个
    idx = np.arange(n) % TURN
    arc = idx < 8
    euc_arc = float(d[arc].min())
    euc_str = float(d[~arc].min())
    # 真正的自交/夹紧检查：每个点到所有「非相邻」线段的距离
    A, B = P[:-1], P[1:]
    AB = B - A
    L2 = (AB ** 2).sum(axis=1)
    pts = P
    best, best_at = 1e9, None
    for k in range(0, len(pts), 1):
        p = pts[k]
        t = np.clip(((p - A) * AB).sum(axis=1) / np.maximum(L2, 1e-12), 0.0, 1.0)
        proj = A + t[:, None] * AB
        dist = np.linalg.norm(p - proj, axis=1)
        # 排除自身与同匝近邻（沿路径 index 差 < TURN 的段）
        seg_idx = np.arange(len(A))
        far = np.abs(seg_idx - k) >= TURN
        dist = np.where(far, dist, 1e9)
        j = int(np.argmin(dist))
        if dist[j] < best:
            best, best_at = float(dist[j]), (k, j)
    k, j = best_at if best_at else (0, 0)
    pos = "弧(拐角)" if (k % TURN) < 8 else "直边"
    print("%-22s LC=%7.2f KR=%.4f | 径向 gap=%6.3f | 欧氏 gap: 弧 %6.3f 直边 %6.3f | "
          "全网最小=%6.3f @idx%d(%s) 铜带净间隙=%6.3f mm"
          % (label, LC, KR, radial - WIDTH, euc_arc - WIDTH, euc_str - WIDTH,
             best - WIDTH, k, pos, best - WIDTH))
    return dict(LC=LC, KR=KR, radial=radial - WIDTH, arc=euc_arc - WIDTH,
                straight=euc_str - WIDTH, global_min=best - WIDTH, at=int(k))


def main():
    print("=" * 118)
    print("线圈拐角几何核查（铜带宽 %.1fmm；净间隙 = 中心线距离 - %.1f）" % (WIDTH, WIDTH))
    print("=" * 118)
    cases = [
        (165.0, 0.358674, "参考点(原模型)"),
        (216.7738, 0.2294, "★屏幕上这个(b1_0163)"),
        (120.1885, 0.2807, "本批 LC 最小"),
        (219.9397, 0.3756, "本批 LC 最大"),
        (218.8542, 0.4997, "本批 孔比最大"),
        (164.5777, 0.2006, "本批 孔比最小"),
        (130.903, 0.4975, "BASE 回退(紧)"),
        (121.7205, 0.4823, "BASE 回退(最紧)"),
    ]
    out = [analyse(LC, KR, lab) for LC, KR, lab in cases]
    print("=" * 118)
    print("结论：径向 gap 与实际欧氏 gap 的差 = %.3f mm（越大说明拐角被压得越厉害）"
          % max(abs(o["radial"] - o["arc"]) for o in out))
    print("      本批最小真实净间隙 = %.3f mm（对应 flex 闸门阈值 1.5mm：%s）"
          % (min(o["global_min"] for o in out),
             "仍高于阈值" if min(o["global_min"] for o in out) >= 1.5 else "★低于阈值"))


if __name__ == "__main__":
    main()
