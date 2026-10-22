# -*- coding: utf-8 -*-
"""b2（1920 工况）参数表 + 审计表生成（离线，不启动 AEDT）。

与第一轮 build_b1_plan.py 的区别（第一轮已知缺陷，b2 全部修掉）
--------------------------------------------------------------
1. 用户参数表先过 validate_b2_plan.validate()（列名/NaN/空值/case_id 唯一性与前缀/
   行数/7 维范围/几何盒）；**FAIL 直接退出，不产出任何文件**。
2. gap_min / use_opt / t_case_min **自己现算**（CG.path_dims + 冻结常数），
   不再抄 batch1_audit.csv（build_b1_plan.py:73-74 的做法）。
3. 空气域盒不再硬编码 330（build_b1_plan.py:29），而是 CLI --boxx（默认 420）；
   另外仍会算出"装下全部工况所需的最小盒半宽"供比对。
4. 排序加二级键：同档 t_case_min 内再按 sweep_span 降序（b1 只有两档耗时，
   1920 规模下只按 t_case_min 排等于没排）。
5. 验收点从 16 扩到 32（每实例 4 个）。

冻结口径（与 validate_b2_plan.py 同一份数值）
--------------------------------------------
空气域 X ±420 / Y [-134.94, 161] / Z [-45, 75]，MARGIN=40；PATH_MODE=ring；
闸门 OPT_MIN_GAP=1.5；半扫 21 点；t_case_min: OPT 105.4 / BASE 290.8（先验估计）。

输出（写到 --outdir）：
    <batch>_plan.csv          8 列（case_id + 7 维），32 个验收点在前
    <batch>_audit.csv         列与 batch1_audit.csv 逐字一致
    <batch>_region_check.csv  逐工况几何核查
    <batch>_plan_meta.json    n_cases/n_opt/n_base/box_x_required/box_x_suggest/
                              validation/order_head
"""
import argparse
import csv
import json
import math
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# _probe 目录里有一个同名旧版 coil_gen.py（无 k_lc/path_dims），
# 千万不要把 _probe 加进 sys.path，否则会遮蔽 C:\wpt 的正版。
# validate_b2_plan 与它同目录，靠 importlib 按文件路径加载即可。
sys.path.insert(0, r"C:\wpt")
import coil_gen as CG            # noqa: E402
import wpt_contract as WC        # noqa: E402

import importlib.util            # noqa: E402

_vb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_b2_plan.py")
_spec = importlib.util.spec_from_file_location("validate_b2_plan", _vb_path)
VB = importlib.util.module_from_spec(_spec)
sys.modules["validate_b2_plan"] = VB
_spec.loader.exec_module(VB)     # 该模块自己会做 coil_gen 防遮蔽自检

# ============================ 冻结口径常量 ============================
BOX_X = 420.0                  # 空气域固定盒 X 半宽（--boxx 默认）
BOX_Y = (-134.94, 161.0)
BOX_Z = (-45.0, 75.0)
MARGIN = 40.0
PATH_MODE_REQUIRED = "ring"
OPT_MIN_GAP = 1.5
N_HALF = 21
N_FULL = 41
T_POINT_OPT = 4.78             # 单点耗时（audit_batch1.py 的先验口径，非 b1 直接实测）
T_POINT_BASE = 13.61           # 同上
T_CASE_OPT = 105.4             # = 21*4.78+5（先验估计）—— 冻结常数，落在 audit 的 t_case_min 列
T_CASE_BASE = 290.8            # = 21*13.61+5（先验估计）
# ⚠️ 工期**唯一**可用常数：b1 生产口径实测单工况均值（含 BASE 工况与 8 实例争用）。
# 来源：b1 交付的 8 份 raw 逐点 minutes 求和 = 735 实例·小时 / 5370 点 / 251 完整工况
# -> 单点 8.22 min、单工况 172.4 min。用 T_CASE_OPT/BASE 估工期会低估约 1.64 倍。
T_CASE_MEASURED = 172.4
N_INST = 8

# ---- 验收点规则（b2：32 个 / 每实例 4 个）----
N_VALID = 32
N_BASE_HARD = 8                # gap_min 最小的 8 个（必走 BASE）
N_SPAN = 8                     # sweep_span 最大的补足

B1_AUDIT = r"C:\ansys maxwell2024\_work\batch1_audit.csv"
DIM_COLS = list(WC.MAIN_COLS)

# audit 表的期望表头（batch1_audit.csv 逐字一致）；读 b1 表失败时用它兜底
AUDIT_COLS_FALLBACK = [
    "case_id", "LC", "KR", "g", "tx_fill", "rx_fill", "tx_thick", "rx_thick",
    "tx_bar_w", "rx_bar_w", "ferrite_len", "edge_gap", "center_dist",
    "sweep_span", "step", "x_max", "n_bars_rx_est", "rx_volume_est",
    "gap_min", "use_opt", "t_point_min", "t_case_min",
]


def read_audit_header(path=B1_AUDIT):
    """读第一轮审计表表头（列顺序/含义必须逐字一致）。失败则返回兜底表头 + 原因。"""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            hdr = next(csv.reader(f))
        return [h.strip() for h in hdr], ""
    except (OSError, UnicodeDecodeError, csv.Error, StopIteration) as e:
        return list(AUDIT_COLS_FALLBACK), "读 %s 表头失败(%s)，用内置兜底表头" % (path, e)


def derived_audit(v, gap_min, use_opt):
    """由 7 维 + 现算 gap_min 得到一行 audit（口径照 audit_batch1.py:62-75）。

    注意 t_point_min / t_case_min 的口径（batch1_audit.csv 实测）：
        t_point_min = 单点耗时 4.78（OPT）/ 13.61（BASE）
        t_case_min  = 21 * t_point_min + 5.0（5 min 几何重建）= 105.4 / 290.8
    即冻结常数 105.4 / 290.8 对应的是 **t_case_min**，不是点耗时。
    """
    LC, KR, g = v["coil_size"], v["hole_ratio"], v["spacing_ratio"]
    d = WC.derived(LC, g, v["tx_fill"], v["rx_fill"], v["rx_thick"])
    S = LC * (2.0 + g)
    t_point = T_POINT_OPT if use_opt else T_POINT_BASE
    return dict(
        LC=LC, KR=KR, g=g,
        tx_fill=v["tx_fill"], rx_fill=v["rx_fill"],
        tx_thick=v["tx_thick"], rx_thick=v["rx_thick"],
        tx_bar_w=round(d["tx_bar_w"], 4), rx_bar_w=round(d["rx_bar_w"], 4),
        ferrite_len=d["ferrite_len"], edge_gap=d["edge_gap"],
        center_dist=round(d["center_dist"], 4), sweep_span=round(d["sweep_span"], 4),
        step=round(S / 40.0, 4), x_max=round(WC.sweep_positions_half(LC, g)[-1], 4),
        n_bars_rx_est=d["n_bars_rx"], rx_volume_est=round(d["rx_volume"], 1),
        gap_min=round(gap_min, 4), use_opt=bool(use_opt),
        t_point_min=t_point,
        # 21 点/工况 + 5 min 几何重建（先验估计口径，与 audit_batch1.py:75 完全一致）
        t_case_min=round(N_HALF * t_point + 5.0, 1),
    )


def region_check_row(cid, v, gap_min, use_opt, box_x):
    """逐工况几何核查（公式照 build_b1_plan.py:48-53，盒由 --boxx 给出）。"""
    K = CG.k_lc()
    LC, g = v["coil_size"], v["spacing_ratio"]
    S = LC * (2.0 + g)
    rx_half = LC * K / 2.0 + CG.WIDTH / 2.0
    need_x = max(S / 2.0 + rx_half, max(S / 2.0, LC / 2.0) + 15.0 + 10.0)
    y_half = round(1.2 * LC) / 2.0
    xs = WC.sweep_positions_half(LC, g)
    over = [(round(x, 3), round(abs(x) + rx_half, 2))
            for x in xs if abs(x) + rx_half > box_x + 1e-6]
    return dict(
        case_id=cid, LC=LC, g=g, S=round(S, 3), S_half=round(S / 2.0, 3),
        rx_half=round(rx_half, 3), need_x=round(need_x, 3),
        box_ok=not over, n_points_out=len(over),
        first_out_x=over[0][0] if over else "",
        max_reach=(round(max(o[1] for o in over), 2) if over
                   else round(max(abs(x) for x in xs) + rx_half, 2)),
        y_half=round(y_half, 2),
        y_ok=bool(y_half <= BOX_Y[1] + 1e-6 and -y_half >= BOX_Y[0] - 1e-6),
        sweep_span=round(S, 3), gap_min=round(gap_min, 4),
        use_opt=bool(use_opt),
        t_point_min=(T_POINT_OPT if use_opt else T_POINT_BASE),
        t_case_min=(T_CASE_OPT if use_opt else T_CASE_BASE))


def pick_validation(geom, vals, cids):
    """选 32 个验收点（14 维极值 + 8 最紧间隙(BASE) + 8 最大跨度），每实例 4 个。

    返回 [(index, reason), ...]，顺序即"实例交错"顺序：
    实例 k 依次拿 idx k, k+8, k+16, k+24。
    """
    picks = []
    seen = set()

    def add(i, why):
        if i is None or i in seen:
            return
        seen.add(i)
        picks.append((i, why))

    # (1) 7 维各取 min/max（14 个）
    for c in DIM_COLS:
        order = sorted(range(len(vals)), key=lambda i: vals[i][c])
        add(order[0], "%s 最小" % c)
        add(order[-1], "%s 最大" % c)
    n_ext = len(picks)

    # (2) gap_min 最小的 8 个（必走 BASE 分支）
    base_idx = sorted(range(len(vals)), key=lambda i: geom[i]["gap_min"])
    n_base_pick = 0
    for i in base_idx:
        if n_base_pick >= N_BASE_HARD:
            break
        if i in seen:
            continue
        add(i, "gap_min 最小(必走 BASE)")
        n_base_pick += 1

    # (3) sweep_span 最大补足到 32
    n_span_pick = 0
    for i in sorted(range(len(vals)), key=lambda i: -geom[i]["sweep_span"]):
        if len(picks) >= N_VALID:
            break
        if i in seen:
            continue
        add(i, "sweep_span 最大补足")
        n_span_pick += 1

    # 极端情况下（去重后不足 32）继续按耗时降序补足
    for i in sorted(range(len(vals)), key=lambda i: -geom[i]["t_case_min"]):
        if len(picks) >= N_VALID:
            break
        add(i, "补足(耗时降序)")

    picks = picks[:N_VALID]
    meta = dict(n_extremes=n_ext, n_base_pick=n_base_pick, n_span_pick=n_span_pick)
    return picks, meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="b2 参数表 + 审计表生成（含完整校验）")
    ap.add_argument("--src", required=True, help="用户参数表 CSV（7 维，可含 case_id）")
    ap.add_argument("--outdir", required=True, help="输出目录（自测请用临时目录）")
    ap.add_argument("--batch", default="b2", help="批次名（默认 b2）")
    ap.add_argument("--rows", type=int, default=1920, help="期望行数（默认 1920）")
    ap.add_argument("--boxx", type=float, default=BOX_X, help="空气域固定盒 X 半宽（默认 420）")
    ap.add_argument("--expect-path-mode", default=PATH_MODE_REQUIRED,
                    choices=["ring", "legacy"],
                    help="期望的线圈路径口径（默认 ring；仅 b1 对照标定时用 legacy）")
    ap.add_argument("--json", action="store_true", help="额外把 meta 打印到 stdout")
    ap.add_argument("--waive-box-margin", default=None, metavar="REASON",
                    help="显式豁免「+40mm 留边」不足（物体仍需在盒内）。必须写明实测证据；"
                         "会记入 plan_meta 的 box_margin_waiver 字段以便审计。")
    a = ap.parse_args(argv)

    print("#" * 84)
    print("# 步骤 1/5  import validate_b2_plan 做校验（FAIL 则退出，不产出任何文件）")
    print("#" * 84)
    rep = VB.validate(a.src, rows=a.rows, batch=a.batch, box_x=a.boxx,
                      expect_path_mode=a.expect_path_mode,
                      waive_box_margin=a.waive_box_margin)
    VB.print_report(rep)
    # 规格允许"源表没有 case_id 列 -> 按源表顺序分配 <batch>_0001 起"，
    # 这种情况校验只会给 WARN（检查 2/4）；其余 FAIL（7 维缺列/数值坏/行数不符/
    # 几何越界/case_id 重复或前缀错）一律退出，不产出任何文件。
    if not rep["passed"]:
        print("校验未通过（FAIL %d 项）-> 不产出任何文件，退出码 1" % rep["n_fail"])
        for c in rep["checks"]:
            if c["status"] == "FAIL":
                print("  FAIL %s：%s" % (c["title"], str(c["detail"]).splitlines()[0]))
        return 1
    if not rep.get("has_case_id", True):
        print("注意：源表没有 case_id 列 -> 按源表顺序分配 %s_0001 起" % a.batch)

    vals = [v for _c, v in rep["vals"]]
    src_ids = [c for c, _v in rep["vals"]]
    geom = rep["geom"]
    assert len(vals) == len(src_ids) == len(geom), "内部错位：vals/cids/geom 长度不一致"

    # ---------------- 步骤 2：case_id ----------------
    print("#" * 84)
    print("# 步骤 2/5  case_id 分配/保留")
    print("#" * 84)
    if src_ids and all(src_ids):
        cids = src_ids
        print("源表自带 case_id，原样保留（校验已确认唯一/非空/前缀 %s_）" % a.batch)
    else:
        cids = ["%s_%04d" % (a.batch, i + 1) for i in range(len(vals))]
        print("源表无 case_id -> 按源表顺序分配 %s_0001 ~ %s_%04d（共 %d 个）"
              % (a.batch, a.batch, len(vals), len(vals)))

    # ---------------- 步骤 3：audit 表 ----------------
    print("#" * 84)
    print("# 步骤 3/5  计算 audit 表（gap_min/use_opt/t_case_min 全部现算，不抄 b1）")
    print("#" * 84)
    hdr, hdr_warn = read_audit_header()
    if hdr_warn:
        print("WARN: %s" % hdr_warn)
    else:
        print("audit 列顺序取自 %s: %s" % (B1_AUDIT, ",".join(hdr)))
    audit_rows = []
    for cid, v, z in zip(cids, vals, geom):
        d = derived_audit(v, z["gap_min"], z["use_opt"])
        row = {"case_id": cid}
        row.update(d)
        audit_rows.append(row)
    need = [c for c in hdr if c not in audit_rows[0]] if audit_rows else []
    blank = [c for c in hdr if c in audit_rows[0]
             and any(r[c] in ("", None) for r in audit_rows)]
    if need:
        print("WARN: 表头里这些列本脚本算不出，将留空: %s" % ", ".join(need))
    if blank:
        print("WARN: 这些列存在空值: %s" % ", ".join(blank))

    # ---------------- 步骤 4：验收点 + 排序 ----------------
    print("#" * 84)
    print("# 步骤 4/5  选 %d 个验收点 + 排序（t_case_min 降序，同档再按 sweep_span 降序）"
          % N_VALID)
    print("#" * 84)
    picks, pmeta = pick_validation(geom, vals, cids)
    val_idx = [i for i, _ in picks]
    seen = set(val_idx)
    rest = [i for i in range(len(vals)) if i not in seen]
    rest.sort(key=lambda i: (-geom[i]["t_case_min"], -geom[i]["sweep_span"], cids[i]))
    order_idx = val_idx + rest
    if len(picks) < N_VALID:
        print("WARN: 去重后验收点只有 %d 个（< %d）" % (len(picks), N_VALID))
    print("验收点构成: 维极值 %d + 最紧间隙(BASE) %d + 最大跨度补足 %d = %d"
          % (pmeta["n_extremes"], pmeta["n_base_pick"], pmeta["n_span_pick"], len(picks)))

    # ---------------- 步骤 5：写文件 ----------------
    print("#" * 84)
    print("# 步骤 5/5  写输出")
    print("#" * 84)
    os.makedirs(a.outdir, exist_ok=True)
    p_plan = os.path.join(a.outdir, "%s_plan.csv" % a.batch)
    p_audit = os.path.join(a.outdir, "%s_audit.csv" % a.batch)
    p_chk = os.path.join(a.outdir, "%s_region_check.csv" % a.batch)
    p_meta = os.path.join(a.outdir, "%s_plan_meta.json" % a.batch)

    by_val = {i: v for i, v in enumerate(vals)}
    with open(p_plan, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["case_id"] + DIM_COLS)
        for i in order_idx:
            # %.10g 保留源表全部有效位（第一轮用 %g 只留 6 位有效数字，会把 4 位小数的
            # 源值截短，例如 148.1911 -> 148.191），同时不引入浮点噪声尾巴。
            w.writerow([cids[i]] + [("%.10g" % by_val[i][c]) for c in DIM_COLS])

    audit_by_id = {r["case_id"]: r for r in audit_rows}
    with open(p_audit, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=hdr)
        w.writeheader()
        w.writerows([{c: audit_by_id[cids[i]][c] for c in hdr} for i in order_idx])

    chk_rows = [region_check_row(cids[i], vals[i], geom[i]["gap_min"],
                                 geom[i]["use_opt"], a.boxx) for i in order_idx]
    with open(p_chk, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(chk_rows[0].keys()))
        w.writeheader()
        w.writerows(chk_rows)

    n_opt = sum(1 for z in geom if z["use_opt"])
    n_base = len(geom) - n_opt
    worst_margin = max(z["need_x_margin"] for z in geom)
    box_required = round(worst_margin, 2)
    box_suggest = math.ceil(worst_margin / 10.0) * 10.0
    tot_min = sum(z["t_case_min"] for z in geom)
    meta = dict(
        batch=a.batch, n_cases=len(geom), n_opt=n_opt, n_base=n_base,
        box_x=a.boxx, box_x_required=box_required, box_x_suggest=box_suggest,
        margin=MARGIN, path_mode=getattr(CG, "PATH_MODE", "?"),
        box_margin_waiver=rep["stats"].get("box_margin_waiver"),
        box_margin_waiver_cases=rep["stats"].get("box_margin_waiver_cases"),
        opt_min_gap=OPT_MIN_GAP, n_half=N_HALF, n_full=N_FULL,
        t_case_min_opt=T_CASE_OPT, t_case_min_base=T_CASE_BASE,
        timing_source="工期按 b1 生产实测单工况均值 %.1f min 估算；先验常数 4.78/13.61 min/点 "
                      "仅供工况排序参考（用于工期会低估约 1.64 倍）" % T_CASE_MEASURED,
        total_case_min=round(tot_min, 1),
        single_instance_hours=round(tot_min / 60.0, 1),
        wall_days_8inst=round(tot_min / 60.0 / 24.0 / N_INST, 2),
        wall_days_8inst_measured=round(len(geom) * T_CASE_MEASURED / 60.0 / 24.0 / N_INST, 2),
        n_points_out_of_box=sum(1 for c in chk_rows if not c["box_ok"]),
        y_ok=all(c["y_ok"] for c in chk_rows),
        validation=[dict(case_id=cids[i], why=w,
                         t_case_min=geom[i]["t_case_min"],
                         gap_min=round(geom[i]["gap_min"], 4),
                         sweep_span=round(geom[i]["sweep_span"], 4)) for i, w in picks],
        order_head=[cids[i] for i in order_idx[:max(40, N_VALID + 8)]],
        validate_summary=dict(ok=rep["n_ok"], warn=rep["n_warn"], fail=rep["n_fail"],
                              checks=[dict(status=c["status"], title=c["title"])
                                      for c in rep["checks"]]),
        audit_missing_cols=need, audit_blank_cols=blank,
        src=os.path.abspath(a.src),
    )
    with open(p_meta, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    # ---------------- 打印 ----------------
    print("-" * 84)
    print("几何核查: X 盒 ±%.0f（留边 %.0f）%s；全部工况最远触及 need_x+40 = %.3f mm，"
          "装下全部需盒半宽 ≥ %.3f -> 建议 X±%.0f；Y 盒 %s"
          % (a.boxx, MARGIN,
             "通过" if all(c["box_ok"] for c in chk_rows) else "**不通过**",
             worst_margin, box_required, box_suggest,
             "通过" if meta["y_ok"] else "**不通过**"))
    print("闸门分布: OPT %d (%.1f%%) / BASE %d (%.1f%%)"
          % (n_opt, 100.0 * n_opt / len(geom), n_base, 100.0 * n_base / len(geom)))
    print("工期预估: **%.2f 天**（%d 实例 24h 滚动，按 b1 生产实测 %.1f min/工况）；"
          "先验常数口径仅供排序参考 = %.2f 天"
          % (meta["wall_days_8inst_measured"], N_INST, T_CASE_MEASURED,
             meta["wall_days_8inst"]))
    print("          参考: 全 OPT 下限 %.2f 天；全 BASE 上限 %.2f 天（先验常数口径）"
          % (len(geom) * T_CASE_OPT / 60.0 / 24.0 / N_INST,
             len(geom) * T_CASE_BASE / 60.0 / 24.0 / N_INST))
    print("-" * 84)
    print("验收点 %d 个（按实例交错：实例 k 拿第 k / k+8 / k+16 / k+24 个）:" % len(picks))
    for n, (i, why) in enumerate(picks):
        v = vals[i]
        print("  [run%d] %s  %-24s LC=%7.2f KR=%.4f tf=%.4f rf=%.4f tt=%.2f rt=%.2f g=%+.4f"
              "  gap=%.4f span=%7.2f  t=%6.1f min"
              % (n % N_INST, cids[i], why, v["coil_size"], v["hole_ratio"], v["tx_fill"],
                 v["rx_fill"], v["tx_thick"], v["rx_thick"], v["spacing_ratio"],
                 geom[i]["gap_min"], geom[i]["sweep_span"], geom[i]["t_case_min"]))
    print("-" * 84)
    print("输出:")
    for p in (p_plan, p_audit, p_chk, p_meta):
        print("  %s" % p)
    print("plan 行数 %d（验收点 %d 在前）；audit 行数 %d" % (len(order_idx), len(picks), len(order_idx)))
    if a.json:
        print(json.dumps(meta, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
