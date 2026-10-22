# -*- coding: utf-8 -*-
"""batch1_samples.csv 入库自检（离线，不启动 AEDT）。

做四件事：
  1) 范围/合法性检查（对照契约 3.1 的 7 个主变量范围）
  2) 逐工况派生几何（wpt_contract.derived）+ 匝间净间隙（coil_gen.path_dims）
  3) 提速闸门 OPT_MIN_GAP=1.5mm 判定 -> 标出会整套回退到 BASE 口径的工况
  4) 工期估算（按文档实测：OPT 4.78 min/点、BASE 13.61 min/点、21 点/工况 + 几何）

输出：_work\batch1_audit.csv / _work\batch1_audit.json
"""
import csv
import json
import os
import sys

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG            # noqa: E402
import wpt_contract as WC        # noqa: E402

SRC = r"C:\ansys maxwell2024\_work\batch1_samples.csv"
OUT_CSV = r"C:\ansys maxwell2024\_work\batch1_audit.csv"
OUT_JSON = r"C:\ansys maxwell2024\_work\batch1_audit.json"

# 契约 3.1 范围
RANGE = {
    "coil_size": (120.0, 220.0),
    "hole_ratio": (0.2, 0.5),
    "tx_fill": (1.0 / 3.0, 2.0 / 3.0),
    "rx_fill": (1.0 / 3.0, 2.0 / 3.0),
    "tx_thick": (5.0, 10.0),
    "rx_thick": (5.0, 10.0),
    "spacing_ratio": (-0.5, 0.5),
}
OPT_MIN_GAP = 1.5          # batch_sweep_lc.OPT_MIN_GAP
T_OPT, T_BASE = 4.78, 13.61   # min/点（文档实测，生产固定盒口径）
N_INST = 8


def main():
    with open(SRC, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    print("读入 %d 个工况" % len(rows))

    recs, viol = [], []
    for r in rows:
        cid = r["case_id"]
        v = {k: float(r[k]) for k in RANGE}
        bad = [k for k, (lo, hi) in RANGE.items()
               if not (lo - 1e-9 <= v[k] <= hi + 1e-9)]
        if bad:
            viol.append((cid, bad, {k: v[k] for k in bad}))

        LC, KR, g = v["coil_size"], v["hole_ratio"], v["spacing_ratio"]
        d = WC.derived(LC, g, v["tx_fill"], v["rx_fill"], v["rx_thick"])
        pd = CG.path_dims(LC, KR)
        gap = pd.get("gap_min")
        use_opt = (gap is None) or (gap >= OPT_MIN_GAP)
        S = LC * (2.0 + g)
        xs = WC.sweep_positions_half(LC, g)

        rec = dict(
            case_id=cid, LC=LC, KR=KR, g=g,
            tx_fill=v["tx_fill"], rx_fill=v["rx_fill"],
            tx_thick=v["tx_thick"], rx_thick=v["rx_thick"],
            tx_bar_w=round(d["tx_bar_w"], 4), rx_bar_w=round(d["rx_bar_w"], 4),
            ferrite_len=d["ferrite_len"], edge_gap=d["edge_gap"],
            center_dist=round(d["center_dist"], 4), sweep_span=round(d["sweep_span"], 4),
            step=round(S / 40.0, 4), x_max=round(xs[-1], 4),
            n_bars_rx_est=d["n_bars_rx"], rx_volume_est=round(d["rx_volume"], 1),
            gap_min=round(gap, 4) if gap is not None else None,
            use_opt=bool(use_opt),
            t_point_min=(T_OPT if use_opt else T_BASE),
        )
        rec["t_case_min"] = round(21 * rec["t_point_min"] + 5.0, 1)   # +5 min 几何重建
        recs.append(rec)

    # ---- 汇总 ----
    n = len(recs)
    n_opt = sum(1 for x in recs if x["use_opt"])
    n_base = n - n_opt
    single_h = sum(x["t_case_min"] for x in recs) / 60.0
    wall_days = single_h / N_INST / 24.0
    gaps = sorted(x["gap_min"] for x in recs if x["gap_min"] is not None)

    def q(p):
        if not gaps:
            return None
        i = min(len(gaps) - 1, max(0, int(round(p / 100.0 * (len(gaps) - 1)))))
        return gaps[i]

    summ = dict(
        n_cases=n, n_opt=n_opt, n_base_fallback=n_base,
        violated=viol,
        gap_min_min=gaps[0], gap_min_p05=q(5), gap_min_p25=q(25),
        gap_min_median=q(50), gap_min_max=gaps[-1],
        tx_bar_w=(min(x["tx_bar_w"] for x in recs), max(x["tx_bar_w"] for x in recs)),
        rx_bar_w=(min(x["rx_bar_w"] for x in recs), max(x["rx_bar_w"] for x in recs)),
        edge_gap=(min(x["edge_gap"] for x in recs), max(x["edge_gap"] for x in recs)),
        sweep_span=(min(x["sweep_span"] for x in recs), max(x["sweep_span"] for x in recs)),
        step=(min(x["step"] for x in recs), max(x["step"] for x in recs)),
        single_instance_hours=round(single_h, 1),
        wall_days_8inst=round(wall_days, 2),
        wall_days_8inst_if_all_opt=round(sum(21 * T_OPT + 5.0 for _ in recs) / 60.0 / N_INST / 24.0, 2),
    )

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(dict(summary=summ, cases=recs), f, ensure_ascii=False, indent=1)

    cols = list(recs[0].keys())
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(recs)

    # ---- 打印 ----
    print("=" * 78)
    print("范围违规: %d" % len(viol))
    for v in viol[:10]:
        print("   ", v)
    print("提速闸门(OPT_MIN_GAP=%.2f mm): OPT %d 个 / BASE 回退 %d 个 (%.1f%%)"
          % (OPT_MIN_GAP, n_opt, n_base, 100.0 * n_base / n))
    print("匝间净间隙 gap_min: min %.3f  p05 %.3f  中位 %.3f  max %.3f mm"
          % (summ["gap_min_min"], summ["gap_min_p05"], summ["gap_min_median"], summ["gap_min_max"]))
    print("发射条宽 tx_bar_w: %.2f ~ %.2f mm" % summ["tx_bar_w"])
    print("接收条宽 rx_bar_w: %.2f ~ %.2f mm" % summ["rx_bar_w"])
    print("边沿间隙 edge_gap(取整): %d ~ %d mm" % summ["edge_gap"])
    print("扫描跨度 sweep_span: %.1f ~ %.1f mm | 步长 %.2f ~ %.2f mm"
          % (summ["sweep_span"][0], summ["sweep_span"][1], summ["step"][0], summ["step"][1]))
    print("-" * 78)
    print("单实例总机时: %.0f 小时 (%.1f 天)" % (single_h, single_h / 24.0))
    print("8 实例墙钟  : %.1f 天   [全部走 OPT 的理论下限 %.1f 天]"
          % (wall_days, summ["wall_days_8inst_if_all_opt"]))
    print("=" * 78)

    low = sorted([x for x in recs if not x["use_opt"]], key=lambda z: z["gap_min"])[:15]
    if low:
        print("间隙最紧的 15 个工况（必然回退 BASE，单点 13.61 min）:")
        for x in low:
            print("   %s LC=%6.2f KR=%.4f gap=%.3f mm  -> %.0f min/工况"
                  % (x["case_id"], x["LC"], x["KR"], x["gap_min"], x["t_case_min"]))
    print("输出: %s\n      %s" % (OUT_CSV, OUT_JSON))


if __name__ == "__main__":
    main()
