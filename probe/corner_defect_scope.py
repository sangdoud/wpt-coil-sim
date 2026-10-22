# -*- coding: utf-8 -*-
"""拐角缺陷的成因分析与全批影响面。

1) 打印模板路径的切比雪夫半径分布 -> 看清「直边恒定 / 圆弧变化」的结构
2) 对每个点算重映射的缩放系数 σ = s'/s -> 直边与圆弧的 σ 差异就是尖角的来源
3) 全批 256 工况：统计最大转角、超 20°/40° 的段数
"""
import csv
import math
import sys

import numpy as np

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG          # noqa: E402

TURN = 64


def structure(LC, KR):
    P = CG.make_path(LC, KR)[:, :2]
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    return P, s


def main():
    print("=" * 112)
    print("① 模板结构（参考参数 LC=165 KR=0.358674，逐点切比雪夫半径 s）")
    P, s = structure(165.0, 0.358674)
    print("  前 40 点 s: %s" % " ".join("%.1f" % z for z in s[:40]))
    print("  第 1 匝 s 的唯一值: %s" % np.unique(np.round(s[:64], 3)))
    print("  前 8 匝每匝 s 的范围: %s"
          % ["%.2f~%.2f" % (s[t * TURN:(t + 1) * TURN].min(), s[t * TURN:(t + 1) * TURN].max())
             for t in range(8)])
    print()
    print("② 缩放系数 σ = (s'-s)/s 在直边 / 圆弧上的差异（LC=216.77 KR=0.2294）")
    P2, s2 = structure(216.7738, 0.2294)
    K = CG.k_lc()
    h_in2, h_out2 = 0.2294 * 216.7738 * K / 2, 216.7738 * K / 2
    h_in_r, h_out_r = 30.0, 83.6415
    k = (h_out2 - h_in2) / (h_out_r - h_in_r)
    s_new = h_in2 + (s - h_in_r) * k
    sigma = s_new / s
    idx = np.arange(len(s)) % TURN
    print("  直边 σ = %.4f ~ %.4f ；圆弧 σ = %.4f ~ %.4f  -> 差异 %.2f%%"
          % (sigma[idx >= 16].min(), sigma[idx >= 16].max(),
             sigma[idx < 16].min(), sigma[idx < 16].max(),
             (sigma[idx < 16].max() / sigma[idx >= 16].min() - 1) * 100))
    print("  模板圆弧处 s 变化幅度: 第1匝 %.3f mm（半径 %.2f~%.2f）"
          % (s[:16].max() - s[:16].min(), s[:16].min(), s[:16].max()))
    print()
    print("③ 全批 256 工况的拐角尖角统计")
    rows = list(csv.DictReader(open(r"C:\ansys maxwell2024\_work\b1_plan.csv",
                                    encoding="utf-8-sig")))
    bad = []
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        P3 = CG.make_path(LC, KR)[:, :2]
        v = np.diff(P3, axis=0)
        ang = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
        d = np.abs((np.diff(ang) + 180) % 360 - 180)
        # 模板固有：拐角 8 弦 -> 每段 11.25°；超过 15° 即视为被挤压
        bad.append((r["case_id"], LC, KR, float(d.max()), int((d > 15).sum()),
                    int((d > 40).sum())))
    mx = [b[3] for b in bad]
    n15 = sum(1 for b in bad if b[3] > 15)
    n40 = sum(1 for b in bad if b[3] > 40)
    n60 = sum(1 for b in bad if b[3] > 60)
    print("  最大转角: 中位 %.2f°  p90 %.2f°  最大 %.2f°" %
          (np.median(mx), np.percentile(mx, 90), max(mx)))
    print("  超过 15° 的工况 %d/256；超过 40° 的 %d/256；超过 60° 的 %d/256"
          % (n15, n40, n60))
    bad.sort(key=lambda z: -z[3])
    print("  最严重的 10 个:")
    for cid, LC, KR, m, a, b in bad[:10]:
        print("    %s LC=%7.2f KR=%.4f 最大转角 %6.2f°   >15°段 %3d  >40°段 %3d"
              % (cid, LC, KR, m, a, b))
    print("  最轻的 5 个:")
    for cid, LC, KR, m, a, b in bad[-5:]:
        print("    %s LC=%7.2f KR=%.4f 最大转角 %6.2f°" % (cid, LC, KR, m))
    print("=" * 112)
    print("判读：模板固有的拐角离散角 = %.2f°（8 弦拟合 90°）。"
          % (90.0 / 8))
    print("      超过它的部分全部是径向重映射挤出来的假尖角。")


if __name__ == "__main__":
    main()
