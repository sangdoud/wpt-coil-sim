# -*- coding: utf-8 -*-
r"""抽样仿真用：生成任意采样点的参数表 combos_lc.csv（拉丁超立方 LHS）。

用法：
  python make_sample_plan.py 300              # 300 个 LHS 样本（默认种子 20260916）
  python make_sample_plan.py 300 12345        # 指定随机种子
  python make_sample_plan.py --list my.csv    # 直接用你自己的 csv（第一行表头，8 列）

参数表列（顺序固定）：LC_mm, KR, KX, W_mm, G_mm, dx_mm, mu, thk_mm
  LC  120~220 mm        KR  0.2~0.5         KX  -0.5~+0.5（负=重叠）
  W   10~20 步长1（离散） G = 30-W          dx  -150~150 mm
  mu  1000（固定）       thk 5~10 步长1（离散）
生成后直接跑： python batch_sweep_lc.py
"""
import csv
import os
import sys

import numpy as np

OUT = r"C:\wpt\combos_lc.csv"
RANGES = dict(LC=(120.0, 220.0), KR=(0.2, 0.5), KX=(-0.5, 0.5),
              W=(10.0, 20.0), thk=(5.0, 10.0))
HEADER = ["LC_mm", "KR", "KX", "W_mm", "G_mm", "dx_mm", "mu", "thk_mm"]
# dx 不是独立变量：dx = S/40，S = Lc(2+KX) = 两个发射线圈阵列的总外宽
def dx_of(LC, KX):
    return LC * (2.0 + KX) / 40.0


def lhs(n, rng, keys):
    """拉丁超立方：每个维度分 n 层，各层内均匀取一点再打乱。"""
    cols = {}
    for k in keys:
        lo, hi = RANGES[k]
        u = (rng.permutation(n) + rng.random(n)) / n
        cols[k] = lo + u * (hi - lo)
    return cols


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--list":
        src = sys.argv[2]
        rows = list(csv.reader(open(src)))
        with open(OUT, "w", newline="") as f:
            csv.writer(f).writerows(rows)
        print("已复制 %s -> %s（%d 行）" % (src, OUT, len(rows) - 1))
        return

    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 20260916
    rng = np.random.default_rng(seed)
    keys = ["LC", "KR", "KX", "W", "thk"]
    c = lhs(n, rng, keys)
    # 离散维度取整
    c["W"] = np.round(c["W"]).astype(float)
    c["thk"] = np.round(c["thk"]).astype(float)
    rows = []
    for i in range(n):
        W = float(c["W"][i])
        LC = float(c["LC"][i])
        KX = float(c["KX"][i])
        rows.append([round(LC, 3), round(float(c["KR"][i]), 4),
                     round(KX, 4), W, round(30.0 - W, 1),
                     round(dx_of(LC, KX), 3), 1000.0, float(c["thk"][i])])
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(rows)
    print("已生成 %d 个 LHS 样本 -> %s (seed=%d)" % (n, OUT, seed))
    arr = np.array([[r[0], r[1], r[2], r[3], r[4], r[5], r[7]] for r in rows])
    print("各维范围检查(最小~最大): LC %.1f~%.1f  KR %.3f~%.3f  KX %+.3f~%+.3f  "
          "W %.0f~%.0f  G %.0f~%.0f  dx %.0f~%.0f  thk %.0f~%.0f"
          % (arr[:, 0].min(), arr[:, 0].max(), arr[:, 1].min(), arr[:, 1].max(),
             arr[:, 2].min(), arr[:, 2].max(), arr[:, 3].min(), arr[:, 3].max(),
             arr[:, 4].min(), arr[:, 4].max(), arr[:, 5].min(), arr[:, 5].max(),
             arr[:, 6].min(), arr[:, 6].max()))


if __name__ == "__main__":
    main()
