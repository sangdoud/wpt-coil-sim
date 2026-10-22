# -*- coding: utf-8 -*-
"""batch1 参数表整理 + 空气域包含性核查（离线，不启动 AEDT）。

发现：文档的生产固定盒 X±330 是为**旧生产扫描**（dx ≤ ±150）定的；
契约口径的接收扫描是 x ∈ [-S/2, +S/2]，S = Lc(2+g)（本批最大 528.6mm），
接收线圈自身半宽 = Lc*k_lc/2 + 1（k_lc ≈ 1.013836），
因此扫描到两端时接收线圈（及其铁氧体）会伸出固定盒 -> 解域被截断。

本脚本逐工况逐点位核查，并给出"能装下全部 256 工况×21 点"的固定盒半宽。

输出：_work\b1_region_check.csv / _work\b1_plan.csv / _work\b1_plan_meta.json
"""
import csv
import json
import math
import os
import sys

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG            # noqa: E402
import wpt_contract as WC        # noqa: E402

SRC = r"C:\ansys maxwell2024\_work\batch1_samples.csv"
AUDIT = r"C:\ansys maxwell2024\_work\batch1_audit.csv"
OUT_CHK = r"C:\ansys maxwell2024\_work\b1_region_check.csv"
OUT_PLAN = r"C:\ansys maxwell2024\_work\b1_plan.csv"
OUT_META = r"C:\ansys maxwell2024\_work\b1_plan_meta.json"

BOX_X = 330.0          # 文档现行生产固定盒 X 半宽
BOX_Y = (-134.94, 161.0)
BOX_Z = (-45.0, 75.0)
MARGIN = 40.0          # 固定盒留边（与"区域不贴物体"的一贯口径一致）


def main():
    K = CG.k_lc()
    print("k_lc = %.6f（文档 Lc -> 实际中心线半跨的换算）" % K)

    audit = {r["case_id"]: r for r in csv.DictReader(open(AUDIT, encoding="utf-8"))}
    rows = list(csv.DictReader(open(SRC, encoding="utf-8-sig")))

    chk, worst = [], 0.0
    n_over_330_cases = 0
    n_over_330_points = 0
    n_points_total = 0
    for r in rows:
        cid = r["case_id"]
        LC = float(r["coil_size"]); g = float(r["spacing_ratio"])
        S = LC * (2.0 + g)
        rx_half = LC * K / 2.0 + CG.WIDTH / 2.0          # 接收线圈外缘半宽（含线宽）
        ferrite_half = max(S / 2.0, LC / 2.0)            # Tx 阵列跨度
        need_x = max(S / 2.0 + rx_half, ferrite_half + 15.0 + 10.0)
        y_half = int(round(1.2 * LC)) / 2.0
        xs = WC.sweep_positions_half(LC, g)
        over = []
        for x in xs:
            reach = abs(x) + rx_half
            if reach > BOX_X - 1e-6:
                over.append((round(x, 3), round(reach, 2)))
        n_points_total += len(xs)
        n_over_330_points += len(over)
        if over:
            n_over_330_cases += 1
        worst = max(worst, need_x)
        chk.append(dict(case_id=cid, LC=LC, g=g, S=round(S, 3), S_half=round(S / 2.0, 3),
                        rx_half=round(rx_half, 3), need_x=round(need_x, 3),
                        box330_ok=not over, n_points_out=len(over),
                        first_out_x=over[0][0] if over else "",
                        max_reach=round(max([o[1] for o in over]), 2) if over else round(
                            max(abs(x) for x in xs) + rx_half, 2),
                        y_half=round(y_half, 2),
                        y_ok=bool(y_half <= BOX_Y[1] - 1e-6 and -y_half >= BOX_Y[0] - 1e-6),
                        sweep_span=round(S, 3), gap_min=float(audit[cid]["gap_min"]),
                        use_opt=audit[cid]["use_opt"], t_case_min=float(audit[cid]["t_case_min"])))

    need_box_x = math.ceil((worst + MARGIN) / 10.0) * 10.0
    print("=" * 78)
    print("扫描跨度 S: 最大 %.1f mm（x 单向最远 ±%.1f）" % (max(c["S"] for c in chk),
                                                          max(c["S_half"] for c in chk)))
    print("接收线圈外缘半宽 rx_half: %.2f ~ %.2f mm" % (min(c["rx_half"] for c in chk),
                                                       max(c["rx_half"] for c in chk)))
    print("扫描到端点时接收线圈最远触及 |x| = %.1f mm" % worst)
    print("现行固定盒 X±%.0f -> 越界工况 %d/%d，越界点位 %d/%d (%.1f%%)"
          % (BOX_X, n_over_330_cases, len(chk), n_over_330_points, n_points_total,
             100.0 * n_over_330_points / n_points_total))
    print("要装下全部 256×21 点：X 半宽需 ≥ %.1f，取整留边 -> **X±%.0f**" % (worst, need_box_x))
    print("Y 检查: 全部 %s（铁氧体半长最大 %.1f ≤ %.1f）"
          % ("通过" if all(c["y_ok"] for c in chk) else "不通过",
             max(c["y_half"] for c in chk), BOX_Y[1]))
    print("=" * 78)

    # ---- 验收点选择（16 个：12 OPT + 4 BASE，覆盖各维极值 + 最大跨度）----
    base = sorted([c for c in chk if c["use_opt"] == "False"], key=lambda c: c["gap_min"])
    base_ids = [c["case_id"] for c in base[:4]]          # 间隙最紧的 4 个（必走 BASE 分支）

    # 12 个 OPT 极值点（覆盖 7 维两端 + 最大跨度）在前，4 个 BASE 回退点在后
    src = {r["case_id"]: r for r in rows}
    opt_pick = []
    oseen = set()

    def take_opt(cid, why):
        if cid and cid not in oseen and len(opt_pick) < 12:
            oseen.add(cid)
            opt_pick.append((cid, why))

    for k, why, rev in [("coil_size", "LC 最小", False), ("coil_size", "LC 最大", True),
                        ("hole_ratio", "孔比最小", False), ("hole_ratio", "孔比最大", True),
                        ("tx_fill", "tx_fill 最小", False), ("tx_fill", "tx_fill 最大", True),
                        ("rx_fill", "rx_fill 最小", False), ("rx_fill", "rx_fill 最大", True),
                        ("tx_thick", "tx_thick 最小", False), ("tx_thick", "tx_thick 最大", True),
                        ("rx_thick", "rx_thick 最小", False), ("rx_thick", "rx_thick 最大", True),
                        ("spacing_ratio", "g 最小", False), ("spacing_ratio", "g 最大", True)]:
        cand = [c for c in chk if c["use_opt"] == "True" and c["case_id"] not in oseen]
        if not cand:
            continue
        take_opt(sorted(cand, key=lambda c: float(src[c["case_id"]][k]), reverse=rev)[0]["case_id"], why)
    cand = [c for c in chk if c["use_opt"] == "True" and c["case_id"] not in oseen]
    if cand:
        take_opt(sorted(cand, key=lambda c: c["S"], reverse=True)[0]["case_id"], "跨度最大(OPT)")
    while len(opt_pick) < 12:                      # 去重后不足 12 个就按跨度补
        cand = [c for c in chk if c["use_opt"] == "True" and c["case_id"] not in oseen]
        if not cand:
            break
        take_opt(sorted(cand, key=lambda c: c["S"], reverse=True)[0]["case_id"], "补充(跨度)")

    pick = opt_pick + [(cid, "BASE 回退(最紧间隙)") for cid in base_ids[:4]]
    val_ids = [p[0] for p in pick]
    seen = set(val_ids)

    # ---- 排序：验收点在前（每实例 2 个），其余按单工况耗时降序（大件先跑，尾巴短）----
    rest = [c for c in chk if c["case_id"] not in seen]
    rest.sort(key=lambda c: -c["t_case_min"])
    order = val_ids + [c["case_id"] for c in rest]

    by_id = {r["case_id"]: r for r in rows}
    hdr = list(rows[0].keys())
    with open(OUT_PLAN, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(hdr)
        for cid in order:
            w.writerow([by_id[cid][h] for h in hdr])
    with open(OUT_CHK, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(chk[0].keys()))
        w.writeheader()
        w.writerows(chk)

    n_opt = sum(1 for c in chk if c["use_opt"] == "True")
    meta = dict(n_cases=len(chk), n_opt=n_opt, n_base=len(chk) - n_opt,
                box_x_doc=BOX_X, box_x_required=round(worst, 2), box_x_suggest=need_box_x,
                n_points_out_of_box330=n_over_330_points, n_points_total=n_points_total,
                n_cases_out_of_box330=n_over_330_cases,
                validation=[dict(case_id=c, why=w) for c, w in pick],
                order_head=order[:24])
    with open(OUT_META, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    print("验收点（16 个，已按实例交错：实例 k 拿第 k 与第 k+8 个）:")
    for i, (c, w) in enumerate(pick):
        m = src[c]
        print("  [run%d] %s  %-14s LC=%7.2f KR=%.4f tf=%.4f rf=%.4f tt=%.2f rt=%.2f g=%+.4f  %s min"
              % (i % 8, c, w, float(m["coil_size"]), float(m["hole_ratio"]),
                 float(m["tx_fill"]), float(m["rx_fill"]), float(m["tx_thick"]),
                 float(m["rx_thick"]), float(m["spacing_ratio"]),
                 audit[c]["t_case_min"]))
    print("\n参数表: %s（%d 行，验收点在前）" % (OUT_PLAN, len(order)))
    print("核查表: %s" % OUT_CHK)


if __name__ == "__main__":
    main()
