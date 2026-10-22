# -*- coding: utf-8 -*-
"""拟并入 C:\\wpt\\wpt_contract.py 的镜像自检补丁（双阈值版，2026-09-18 采纳）。

放置位置：`wpt_contract.py` 里现有的 `mirror_error()` 之后（原函数保留，便于对旧数据回溯）。

改动理由（必须与软件端同步，属文档 3.6 自检项 2 的口径调整）：
  Tx 分层（Tx1 z=+0.325 / Tx2 z=−0.325）+ Rx 单层（z=30）使"沿 x 镜像"不再严格成立，
  M1/M2 有 ~2.2% 固有非对称（dx=0 实测 M13=3.949 vs M23=4.039）。
  但 ① 半扫展开是**交换**（M1(−x):=M2(+x)、M2(−x):=M1(+x)），和守恒：
  和(+x)=7.9880 vs 和(−x)=8.0080 -> 0.25%；而四目标里 f2/f3 用的正是 M1+M2。
  因此：和口径仍卡 2%，个体口径放宽到 3%（只影响导出的 M1/M2/k13/k23 列）。

同时建议在各工况 x=0 处补 1 点，用 `asymmetry_at_center()` 量化该工况的非对称度并在数据里打标。
"""

MIRROR_TOL_SUM_PCT = 2.0    # 和口径 |Δ(M1+M2)| / 峰值（%）
MIRROR_TOL_IND_PCT = 3.0    # 个体口径 max|ΔM1|,|ΔM2| / 峰值（%）


def mirror_check(xs_full, M1_full, M2_full,
                 tol_sum=MIRROR_TOL_SUM_PCT, tol_ind=MIRROR_TOL_IND_PCT):
    """文档 3.6 自检项 2（双阈值版）：判定 ① 镜像半扫的前提是否成立。

    返回 dict：
      peak      峰值 |M|
      sum_pct   max|Δ(M1+M2)| / 峰值  (%)   —— 决定目标量（f2/f3）能否用 ①
      ind_pct   max|ΔM1|,|ΔM2| / 峰值 (%)   —— 只影响导出的 M1/M2/k 列
      pass_sum / pass_ind / pass            各自与总判定
      n_pairs   参与比对的镜像点对数
    """
    by_x = {}
    for x, a, b in zip(xs_full, M1_full, M2_full):
        by_x[round(float(x), 6)] = (float(a), float(b))
    peak = max([abs(v) for v in list(M1_full) + list(M2_full)] or [1.0]) or 1.0
    sum_pct = ind_pct = 0.0
    n = 0
    for x, (m1p, m2p) in by_x.items():
        peer = by_x.get(round(-x, 6))
        if not peer:
            continue
        n += 1
        m1n, m2n = peer
        ind_pct = max(ind_pct, max(abs(m1n - m2p), abs(m2n - m1p)) / peak * 100.0)
        sum_pct = max(sum_pct, abs((m1n + m2n) - (m1p + m2p)) / peak * 100.0)
    return {"peak": peak, "sum_pct": sum_pct, "ind_pct": ind_pct, "n_pairs": n,
            "tol_sum": tol_sum, "tol_ind": tol_ind,
            "pass_sum": bool(sum_pct <= tol_sum), "pass_ind": bool(ind_pct <= tol_ind),
            "pass": bool(sum_pct <= tol_sum and ind_pct <= tol_ind)}


def asymmetry_at_center(M1_center, M2_center):
    """x=0 处的固有非对称度（%）。"""
    pk = max(abs(M1_center), abs(M2_center)) or 1.0
    return abs(M1_center - M2_center) / pk * 100.0


def case_asymmetry_tag(case_id, xs, M1, M2):
    """每工况的固有非对称度打标（**零额外求解**）。

    x=0 本来就是半扫 21 点里的第 0 点（`sweep_positions_half`：x = i*S/40, i=0..20），
    所以直接从该行取 M1/M2 即可：
        asym_pct = |M1(x=0) - M2(x=0)| / max(|M1|,|M2|) * 100
    再把整条曲线的双阈值镜像自检一起带上，供入库前筛选。
    返回 dict（键即 batchN_selfcheck.csv 的列）。
    """
    by_x = {round(float(x), 6): (float(a), float(b)) for x, a, b in zip(xs, M1, M2)}
    c = by_x.get(0.0)
    mc = mirror_check(xs, M1, M2)
    return {"case_id": case_id,
            "x0_M1": c[0] if c else None,
            "x0_M2": c[1] if c else None,
            "asym_pct": round(asymmetry_at_center(c[0], c[1]), 4) if c else None,
            "mirror_sum_pct": round(mc["sum_pct"], 4),
            "mirror_ind_pct": round(mc["ind_pct"], 4),
            "mirror_pairs": mc["n_pairs"],
            "mirror_pass": mc["pass"]}


SELFCHECK_COLS = ["case_id", "x0_M1", "x0_M2", "asym_pct",
                  "mirror_sum_pct", "mirror_ind_pct", "mirror_pairs", "mirror_pass"]


def write_selfcheck(path, rows, append=True):
    """写入**独立**的自检表（不是契约 CSV，契约列名不得改动）。"""
    import csv
    import os as _os
    new = (not append) or (not _os.path.exists(path))
    with open(path, "a" if append else "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(SELFCHECK_COLS)
        for r in rows:
            w.writerow([r.get(c, "") for c in SELFCHECK_COLS])


if __name__ == "__main__":
    # 用 P1 实测回测：dx=±7.1095 的真值
    step = 7.109523250000001
    xs = [-step, step]
    M1 = [4.649, 3.261]      # dx=-step 与 +step 的 M13
    M2 = [3.359, 4.727]      # dx=-step 与 +step 的 M23
    r = mirror_check(xs, M1, M2)
    print("sum=%.3f%% ind=%.3f%% -> %s" % (r["sum_pct"], r["ind_pct"],
                                           "通过 ✓" if r["pass"] else "不通过 ✗"))
    print("dx=0 非对称度 = %.3f%%" % asymmetry_at_center(3.949, 4.039))
    # 半扫曲线（含 x=0）打标：这里用 P1 两点 + 参考点 x=0 的实测值拼一条最小曲线
    xs_s = [-step, 0.0, step]
    M1_s = [4.649, 3.949, 3.261]
    M2_s = [3.359, 4.039, 4.727]
    print("自检行:", case_asymmetry_tag("demo_case", xs_s, M1_s, M2_s))
