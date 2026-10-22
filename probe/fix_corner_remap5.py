# -*- coding: utf-8 -*-
"""v5：环半径重映射（直边保持均匀间距 + 圆角等比缩放）。

思路：
  1) 模板上「直边点的 s」就是该环的真实环半径 R（直边上 s = max(|x|,|y|) = R 恒成立）
  2) 圆角点（局部转角大的点）的 s 是下沉的假值 -> 用其两端直边点的 s **线性插值**替代
  3) f(p) = [h_in' + (R(p) - h_in_ref)·k] / R(p)
结果：
  - 直边：s' = R_new = h_in' + (R-h_in_ref)k -> **匝间距严格等于 (h_out'-h_in')/12** ✓
  - 圆角：f 沿圆角缓慢变化（跟随环半径的自然增长）-> 形状保持，无尖刺 ✓
  - 参考参数下 f ≡ 1 -> 逐点恒等 ✓
"""
import csv
import sys

import numpy as np

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG          # noqa: E402

CG._load()
T = np.array(CG._ref, dtype=float)[:, :2]
S = np.maximum(np.abs(T[:, 0]), np.abs(T[:, 1]))
K = CG.k_lc()
HIN, HOUT = 30.0, float(S.max())

_v = np.diff(T, axis=0)
_ang = np.arctan2(_v[:, 1], _v[:, 0])
_D = np.abs((np.diff(_ang) + np.pi) % (2 * np.pi) - np.pi)      # 段间转角（766）
_TURN = np.concatenate([[0.0], _D, [0.0]])                       # 每点的局部转角
FILLET = _TURN > np.radians(0.05)                                # 圆角点判定


def ring_radius():
    """把圆角点的 s 用两端直边点的 s 线性插值替代，得到每点的真实环半径。"""
    R = S.copy()
    n = len(R)
    i = 0
    while i < n:
        if FILLET[i]:
            j = i
            while j < n and FILLET[j]:
                j += 1
            a, b = max(i - 1, 0), min(j, n - 1)          # 两端直边点
            if b > a:
                R[i:j] = np.linspace(S[a], S[b], j - i)
            i = j
        else:
            i += 1
    return R


R_REF = ring_radius()


def path_v5(LC, KR):
    h_out, h_in = LC * K / 2.0, KR * LC * K / 2.0
    k = (h_out - h_in) / (HOUT - HIN)
    R_new = h_in + (R_REF - HIN) * k
    f = R_new / R_REF
    return T * f[:, None]


def stats(P):
    v = np.diff(P, axis=0)
    ang = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    d = np.abs((np.diff(ang) + 180.0) % 360.0 - 180.0)
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    # 只在直边点上量匝间距（那里 s = 环半径）
    straight = ~FILLET
    g = (s[64:] - s[:-64])[straight[64:]] - CG.WIDTH
    return dict(kink=float(d.max()), gmin=float(g.min()), gmed=float(np.median(g)),
                gmax=float(g.max()), smin=float(s.min()), smax=float(s.max()))


def main():
    rows = list(csv.DictReader(open(r"C:\ansys maxwell2024\_work\b1_plan.csv",
                                    encoding="utf-8-sig")))
    print("=" * 104)
    print("① 恒等性：与模板最大差异 %.3e mm（参考参数 LC=165 KR=0.358674）"
          % np.abs(path_v5(165.0, 30.0 / 83.6415) - T).max())
    print("② 圆角点占比 %.1f%%（%d/%d）" % (100.0 * FILLET.mean(), FILLET.sum(), len(FILLET)))
    print("③ 逐工况（直边上的匝间距统计，mm）")
    print("  %-9s %7s %7s | %-26s | %-26s"
          % ("case", "LC", "KR", "legacy(min/med/max)", "v5(min/med/max)"))
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        CG.PATH_MODE = "legacy"
        a = stats(CG.make_path(LC, KR)[:, :2])
        b = stats(path_v5(LC, KR))
        if r["case_id"] in ("b1_0163", "b1_0169", "b1_0126", "b1_0213", "b1_0236",
                            "b1_0254", "b1_0003"):
            fmt = lambda z: "%6.3f %6.3f %6.3f" % (z["gmin"], z["gmed"], z["gmax"])
            print("  %-9s %7.1f %7.4f | %-26s | %-26s" % (r["case_id"], LC, KR, fmt(a), fmt(b)))
    # 全批
    ks, gmins, spreads, ks_l = [], [], [], []
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        CG.PATH_MODE = "legacy"
        za = stats(CG.make_path(LC, KR)[:, :2])
        zb = stats(path_v5(LC, KR))
        ks_l.append(za["kink"]); ks.append(zb["kink"])
        gmins.append(zb["gmin"]); spreads.append(zb["gmax"] - zb["gmin"])
    ks, ks_l = np.array(ks), np.array(ks_l)
    print()
    print("④ 全批 256 工况")
    print("  legacy: 最大转角 中位 %6.2f° max %6.2f° (>15°: %3d/256)"
          % (np.median(ks_l), ks_l.max(), int((ks_l > 15).sum())))
    print("  v5    : 最大转角 中位 %6.2f° max %6.2f° (>15°: %3d/256)"
          % (np.median(ks), ks.max(), int((ks > 15).sum())))
    print("         直边匝间距 最小 %.3f mm / 不均匀度 max %.4f mm（legacy 为 0）"
          % (min(gmins), max(spreads)))
    CG.PATH_MODE = "legacy"
    print("=" * 104)


if __name__ == "__main__":
    main()
