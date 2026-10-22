# -*- coding: utf-8 -*-
"""镜像自检（双阈值版）—— 2026-09-18 采纳。

背景：4-chord/分层改造后，Tx1 在 z=+0.325、Tx2 在 z=−0.325，而 Rx 在 z=30 单层。
"沿 x 镜像"保持 z 不变，所以上层 Tx1 与下层 Tx2 并不是彼此的镜像（差一个 z 翻转），
M1/M2 因此有 ~2.2% 的固有非对称：
    dx=0      : M13=3.949  M23=4.039   （相对差 2.23%）
    dx=±7.1095: 3.2610/4.7270 vs 4.6490/3.3590  （镜像误差 2.073% / 1.650%）

但 ① 镜像半扫展开做的是**交换**（M1(−x):=M2(+x)、M2(−x):=M1(+x)），**和守恒**：
    和(+x)=7.9880   和(−x)=8.0080   ->  误差仅 0.25%
而《改动方案》四目标里 f2/f3 用的正是 M1+M2 的均值/方差（f1=M12 与镜像无关）。

于是判据改成双阈值：
    和口径   |Δ(M1+M2)| / 峰值  <= 2%     （决定目标量能不能用 ①）
    个体口径 max|ΔM1|,|ΔM2| / 峰值 <= 3%  （放宽，仅影响导出的 M1/M2/k13/k23 列）
归一化沿用文档原口径：除以峰值 |M|。

自测：python selfcheck_mirror.py   （用 P1 的实测点）
"""
import json
import os

TOL_SUM = 2.0      # %
TOL_IND = 3.0      # %


def mirror_check(xs, M1, M2, tol_sum=TOL_SUM, tol_ind=TOL_IND):
    """返回双阈值镜像自检结果 dict。

    xs/M1/M2: 等长的完整曲线（已由半扫展开或直接测得）。
    """
    by_x = {}
    for x, a, b in zip(xs, M1, M2):
        by_x[round(float(x), 6)] = (float(a), float(b))
    peak = max([abs(v) for v in list(M1) + list(M2)] or [1.0]) or 1.0
    worst = {"ind": 0.0, "ind_at": None, "sum": 0.0, "sum_at": None,
             "sum_rel": 0.0, "n_pairs": 0}
    for x, (m1p, m2p) in sorted(by_x.items()):
        peer = by_x.get(round(-x, 6))
        if not peer:
            continue
        m1n, m2n = peer
        worst["n_pairs"] += 1
        ind = max(abs(m1n - m2p), abs(m2n - m1p)) / peak * 100.0
        s_p, s_n = m1p + m2p, m1n + m2n
        sm = abs(s_n - s_p) / peak * 100.0
        sm_rel = abs(s_n - s_p) / (abs(s_p) or 1.0) * 100.0
        if ind > worst["ind"]:
            worst["ind"], worst["ind_at"] = ind, x
        if sm > worst["sum"]:
            worst["sum"], worst["sum_at"] = sm, x
        worst["sum_rel"] = max(worst["sum_rel"], sm_rel)
    worst["peak"] = peak
    worst["tol_sum"] = tol_sum
    worst["tol_ind"] = tol_ind
    worst["pass_sum"] = bool(worst["sum"] <= tol_sum)
    worst["pass_ind"] = bool(worst["ind"] <= tol_ind)
    worst["pass"] = bool(worst["pass_sum"] and worst["pass_ind"])
    return worst


def report(r):
    lines = []
    lines.append("配对点数 %d  峰值|M| %.4f" % (r["n_pairs"], r["peak"]))
    lines.append("  和口径   max|Δ(M1+M2)|/峰值 = %.3f%%  (判据 <=%.0f%%)  -> %s"
                 % (r["sum"], r["tol_sum"], "通过 ✓" if r["pass_sum"] else "不通过 ✗"))
    lines.append("  个体口径 max|ΔM1|,|ΔM2|/峰值 = %.3f%%  (判据 <=%.0f%%)  -> %s"
                 % (r["ind"], r["tol_ind"], "通过 ✓" if r["pass_ind"] else "不通过 ✗"))
    lines.append("  总和判定: %s   (和口径按和值归一化时 %.3f%%)"
                 % ("通过 ✓" if r["pass"] else "不通过 ✗", r["sum_rel"]))
    return "\n".join(lines)


def _selftest():
    """P1 实测两点（dx=±7.1095）走一遍半扫展开逻辑。"""
    step = 7.109523250000001
    xp = {"L11": 20.403, "M1": 3.261, "M2": 4.727}
    xn = {"L11": 20.417, "M1": 4.649, "M2": 3.359}
    # 半扫只算 x>=0：x=+step 得 (M1=3.261, M2=4.727)，展开给 x=-step -> (4.727, 3.261)
    xs = [-step, step]
    M1 = [xp["M2"], xp["M1"]]
    M2 = [xp["M1"], xp["M2"]]
    r_self = mirror_check(xs, M1, M2)          # 自洽（必然全过）
    # 与真实求解值比：真值 x=-step 是 (4.649, 3.359)
    M1_true = [xn["M1"], xp["M1"]]
    M2_true = [xn["M2"], xp["M2"]]
    r = mirror_check(xs, M1_true, M2_true)
    print("=== 用 ① 真实前提检验（真值 vs 镜像展开值）===")
    print("镜像展开: x=-%.4f -> M1=%.4f M2=%.4f" % (step, M1[0], M2[0]))
    print("求解真值: x=-%.4f -> M1=%.4f M2=%.4f" % (step, M1_true[0], M2_true[0]))
    print(report(r))
    print("")
    print("=== 自洽性检查（展开值自身的镜像误差，应≈0）===")
    print(report(r_self))
    out = r"C:\ansys maxwell2024\_work\mirror_check_selftest.json"
    json.dump({"measured_pairs": r, "self_consistent": r_self}, open(out, "w"),
              ensure_ascii=False, indent=2)
    print("\n-> %s" % out)


if __name__ == "__main__":
    _selftest()
