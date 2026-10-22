# -*- coding: utf-8 -*-
"""v3（相位）vs v4（模板自身环半径 + 仿射映射）对比，选更严谨的修法。

v4：
  R_est(p) = 模板上 s 的局部极大（窗口 ±win 点）——直边处等于环半径 R，
             圆角处取到相邻直边的 R（圆角下沉是局部凹陷，被极大值滤掉）
  f(p) = [h_in' + (R_est - h_in_ref)·k] / R_est      （k = (h_out'-h_in')/(h_out_ref-h_in_ref)）
  p' = 模板点 × f
性质：参考参数下 f ≡ 1（恒等）；直边处 s' = R_new 严格成立（无线性假设误差）；
      圆角获得与其相邻直边相同的 f -> 形状保持。
"""
import csv
import math
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
_d = np.abs((np.diff(_ang) + np.pi) % (2 * np.pi) - np.pi)
_th = np.concatenate([[0.0, 0.0], np.cumsum(_d)])
U = _th / _th[-1]


def path_v3(LC, KR):
    h_out, h_in = LC * K / 2.0, KR * LC * K / 2.0
    f = (h_in + U * (h_out - h_in)) / (HIN + U * (HOUT - HIN))
    return T * f[:, None]


def path_v4(LC, KR, win=10):
    h_out, h_in = LC * K / 2.0, KR * LC * K / 2.0
    idx = np.clip(np.arange(len(S))[:, None] + np.arange(-win, win + 1)[None, :],
                  0, len(S) - 1)
    r_est = S[idx].max(axis=1)
    k = (h_out - h_in) / (HOUT - HIN)
    f = (h_in + (r_est - HIN) * k) / r_est
    return T * f[:, None]


def stats(P):
    v = np.diff(P, axis=0)
    ang = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    d = np.abs((np.diff(ang) + 180.0) % 360.0 - 180.0)
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    g = s[64:] - s[:-64] - CG.WIDTH
    dd = np.abs(np.diff(np.unwrap(np.arctan2(np.diff(P[:, 0]), np.diff(P[:, 1])))))
    straight = np.concatenate([[True], dd < 0.005, [True]])
    R = s[0] if False else None
    return dict(kink=float(d.max()), gmin=float(g.min()), gmed=float(np.median(g)),
                gmax=float(g.max()), smin=float(s.min()), smax=float(s.max()),
                straight_s=(float(s[straight].min()), float(s[straight].max())))


def main():
    rows = list(csv.DictReader(open(r"C:\ansys maxwell2024\_work\b1_plan.csv",
                                    encoding="utf-8-sig")))
    print("=" * 104)
    P3 = path_v3(165.0, 30.0 / 83.6415)
    print("① 参考点恒等性：v3 %.3e mm   v4(win=10) %.3e mm"
          % (np.abs(P3 - T).max(), np.abs(path_v4(165.0, 30.0 / 83.6415) - T).max()))
    print("② v4 窗口扫描（全批最大转角）")
    for win in (6, 8, 10, 12, 16):
        mx = max(stats(path_v4(float(r["coil_size"]), float(r["hole_ratio"]), win))["kink"]
                 for r in rows)
        print("     win=%2d  最大转角 %.2f°" % (win, mx))
    win = 10
    print("③ 匝间隙均匀性（净间隙 min / 中位 / max，mm）")
    print("  %-9s %6s %6s | %-22s | %-22s | %-22s"
          % ("case", "LC", "KR", "legacy", "v3 相位", "v4 模板环半径"))
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        CG.PATH_MODE = "legacy"
        a = stats(CG.make_path(LC, KR)[:, :2])
        CG.PATH_MODE = "phase"
        b = stats(path_v3(LC, KR))
        c = stats(path_v4(LC, KR, win))
        if r["case_id"] in ("b1_0163", "b1_0169", "b1_0126", "b1_0213", "b1_0236",
                            "b1_0254", "b1_0003"):
            fmt = lambda z: "%6.3f %6.3f %6.3f" % (z["gmin"], z["gmed"], z["gmax"])
            print("  %-9s %6.1f %6.4f | %-22s | %-22s | %-22s"
                  % (r["case_id"], LC, KR, fmt(a), fmt(b), fmt(c)))
    print()
    print("④ 全批汇总")
    for name, fn in (("legacy", lambda LC, KR: CG.make_path(LC, KR)[:, :2].
                      __class__(CG.make_path(LC, KR)[:, :2]) if False else None),):
        pass
    for label, maker in (("legacy", None), ("v3", path_v3), ("v4", lambda LC, KR: path_v4(LC, KR, win))):
        ks, gmins, spreads = [], [], []
        for r in rows:
            LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
            if maker is None:
                CG.PATH_MODE = "legacy"
                P = CG.make_path(LC, KR)[:, :2]
            else:
                P = maker(LC, KR)
            z = stats(P)
            ks.append(z["kink"])
            gmins.append(z["gmin"])
            spreads.append(z["gmax"] - z["gmin"])
        ks = np.array(ks)
        print("  %-7s 最大转角 中位 %6.2f° max %6.2f° (>15°: %3d/256) | 最小间隙 %.3f mm | 间隙不均匀度 max %.3f mm"
              % (label, np.median(ks), ks.max(), int((ks > 15).sum()), min(gmins), max(spreads)))
    CG.PATH_MODE = "legacy"      # 恢复模块默认，避免影响后续
    print("=" * 104)


if __name__ == "__main__":
    main()
