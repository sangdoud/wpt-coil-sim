# -*- coding: utf-8 -*-
r"""契约 CSV 生成器：把各实例的逐点原始结果 b1_raw_runK.csv 汇总成契约三表 + 诊断表。

原始结果 -> 41 点曲线 -> 契约 CSV 的唯一入口（保证可重放、无半截数据）：
  out\b1_cases.csv       每工况一行（CASES_COLS 逐字对齐契约）
  out\b1_curves.csv      长表，每工况 41 行（CURVES_COLS 逐字对齐契约）
  out\b1_selfcheck.csv   独立自检表（SELFCHECK_COLS + 3 个有效性列）
  out\b1_diag.csv        额外诊断（目标量/耗时/口径），**不属于契约**

用法： python contract_merge.py [--batch b1] [--root ...] [--strict]
"""
import argparse
import csv
import glob
import json
import math
import os
import sys

import numpy as np

# stdout 为管道时中文 Windows 默认 GBK，打印 ✓/✗ 会抛 UnicodeEncodeError。
# 计划任务等无人值守环境不会设 PYTHONIOENCODING，故在入口强制切 UTF-8。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG            # noqa: E402  仅用于复算闸门口径 gap_min
import wpt_contract as WC        # noqa: E402

MAIN = ["coil_size", "hole_ratio", "tx_fill", "rx_fill",
        "tx_thick", "rx_thick", "spacing_ratio"]
CHECK_COLS = WC.SELFCHECK_COLS + ["equidistant", "k_ok", "L_positive"]


def load_plan(path):
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out[r["case_id"]] = {k: float(r[k]) for k in MAIN}
    return out


def load_raw(raws):
    raw = {}
    for p in raws:
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    raw.setdefault(r["case_id"], {})[int(r["i"])] = r
                except (KeyError, ValueError):
                    continue
    return raw


def load_geom(jsons):
    """从 worker JSON 取实际铺设条数（契约 n_bars_rx = build_ferrite 回报值）。"""
    out = {}
    for p in jsons:
        try:
            dd = json.load(open(p, encoding="utf-8-sig"))
        except Exception:
            continue
        for c in dd.get("cases", []):
            if c.get("n_bars_rx"):
                out[c["case_id"]] = c
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", default="b2")
    ap.add_argument("--root", default=r"C:\ansys maxwell2024\_work\b2")
    ap.add_argument("--plan", default=None)
    args = ap.parse_args()
    B = args.batch
    ROOT = args.root
    plan_path = args.plan or os.path.join(ROOT, "%s_plan.csv" % B)
    outdir = os.path.join(ROOT, "out")
    os.makedirs(outdir, exist_ok=True)

    plan = load_plan(plan_path)
    raws = sorted(glob.glob(os.path.join(ROOT, "%s_raw_run*.csv" % B)))
    jsonf = sorted(glob.glob(os.path.join(ROOT, "%s_worker_run*.json" % B)))
    raw = load_raw(raws)
    geom = load_geom(jsonf)
    print("参数表 %d 个工况；原始结果文件 %d 个，覆盖 %d 个工况"
          % (len(plan), len(raws), len(raw)))

    cases_rows, curve_rows, chk_rows, diag = [], [], [], []
    n_partial = []
    for cid, v in plan.items():
        pts = raw.get(cid, {})
        xs_h = WC.sweep_positions_half(v["coil_size"], v["spacing_ratio"])
        if len(pts) < len(xs_h):
            n_partial.append((cid, len(pts)))
            continue
        d = WC.derived(v["coil_size"], v["spacing_ratio"], v["tx_fill"],
                       v["rx_fill"], v["rx_thick"])
        if cid in geom:                      # 用实际回报值覆盖估计值
            d["n_bars_rx"] = int(geom[cid]["n_bars_rx"])
            d["rx_volume"] = (d["n_bars_rx"] * d["rx_bar_w"] * v["rx_thick"]
                              * d["ferrite_len"])
        M1h = [float(pts[i]["M13"]) for i in range(len(xs_h))]
        M2h = [float(pts[i]["M23"]) for i in range(len(xs_h))]
        xr = [float(pts[i]["x_mm"]) for i in range(len(xs_h))]
        x_err = max(abs(a - b) for a, b in zip(xr, xs_h))
        xs_f, M1f, M2f = WC.expand_curve(xs_h, M1h, M2h)
        Msum = [a + b for a, b in zip(M1f, M2f)]
        msum_mean = sum(Msum) / len(Msum)
        msum_var = sum((z - msum_mean) ** 2 for z in Msum) / len(Msum)
        m12 = [float(pts[i]["M12"]) for i in range(len(xs_h))]
        mpp = WC.mpp_scalar(m12)

        tag = WC.case_asymmetry_tag(cid, xs_f, M1f, M2f)
        # 峰值归一化非对称度（2026-09-19 新增）：契约口径的 asym_pct = |M1-M2|/max|M|
        # 在 x=0 互感接近零时会爆炸（实测某工况 143.7%，但绝对差仅 0.102μH）。
        # 这里补一个按曲线峰值归一化的版本，与参考点 2.19~2.23% 可直接比较。
        peak_all = max(max(abs(v) for v in M1f), max(abs(v) for v in M2f)) or 1.0
        asym_peak = abs(M1f[len(xs_h) - 1] - M2f[len(xs_h) - 1]) / peak_all * 100.0
        k_all = [float(pts[i]["k13"]) for i in range(len(xs_h))] + \
                [float(pts[i]["k23"]) for i in range(len(xs_h))]
        L_all = [float(pts[i][c]) for i in range(len(xs_h)) for c in ("L11", "L22", "L33")]
        k_ok = all(abs(z) < 1.0 for z in k_all)
        L_ok = all(z > 0 for z in L_all)
        equi = bool(x_err < 1e-6 and len(xs_h) == 21)

        cases_rows.append(WC.build_case_row(cid, v, d, round(mpp, 4)))
        for i, x in enumerate(xs_f):
            src = min(range(len(xs_h)), key=lambda z: abs(xs_h[z] - abs(x)))
            r = pts[src]
            # M_pp 与位置无关（路径均值口径）-> 曲线表留空，由 cases 标量回退（契约 3.5）
            curve_rows.append({"case_id": cid, "position_x": round(x, 4),
                               "M1": M1f[i], "M2": M2f[i], "M_pp": "",
                               "L11": r["L11"], "L22": r["L22"], "L33": r["L33"],
                               "k13": r["k13"], "k23": r["k23"]})
        chk_rows.append(dict(tag, equidistant=equi, k_ok=k_ok, L_positive=L_ok))
        mins = [float(pts[i]["minutes"]) for i in range(len(xs_h))]
        # L33/L11 逐点离群诊断（2026-09-19）：每点独立重新网格化，偶发单点表面网格
        # 质量波动会让 L33 偏离本工况中位 2~6%（实测 2/25 点）。四目标不受影响，
        # 但导出的 L33 与 k13/k23 会继承 —— 这里只打标，不改数据，供下游筛选/加权。
        def dev_pct(key):
            v = np.array([float(pts[i][key]) for i in range(len(xs_h))])
            med = float(np.median(v)) or 1.0
            d = (v - med) / med * 100.0
            return float(np.abs(d).max()), int((np.abs(d) > 2.0).sum())
        d33, n33 = dev_pct("L33")
        d11, n11 = dev_pct("L11")
        # 网格口径标记（2026-09-19）：正常全 OPT；若该工况有点在 OPT 下解不出来、
        # 由补偿机制改用 BASE 补齐，则会出现 OPT+BASE 混合（单点差异约 0.25%）。
        # 另：闸门（gap_min<1.5mm）判定为 BASE 的工况，其点位在 raw 里早期被误标 OPT，
        # 这里按同一判据复算 gate 口径并合并 —— 保证交付表里的口径标记正确。
        meshes = sorted({(pts[i].get("mesh") or "OPT") for i in range(len(xs_h))})
        try:
            _gap = CG.path_dims(v["coil_size"], v["hole_ratio"]).get("gap_min")
        except Exception:
            _gap = None
        gate = "OPT" if (_gap is None or _gap >= 1.5) else "BASE"
        merged = sorted(set(meshes) | {gate})
        diag.append(dict(case_id=cid, M_sum_mean=round(msum_mean, 6),
                         mesh="+".join(merged), mesh_mixed=len(merged) > 1,
                         mesh_gate=gate, mesh_points="+".join(meshes),
                         gap_min=round(_gap, 3) if _gap is not None else "",
                         M_sum_var=round(msum_var, 6), M_pp=round(mpp, 6),
                         M_pp_min=round(min(m12), 4), M_pp_max=round(max(m12), 4),
                         M_sum_min=round(min(Msum), 6), M_sum_max=round(max(Msum), 6),
                         asym_pct=tag["asym_pct"], asym_peak_pct=round(asym_peak, 3), mirror_pass=tag["mirror_pass"],
                         k_ok=k_ok, L_positive=L_ok, equidistant=equi,
                         x_err_mm=round(x_err, 9), n_points=len(xs_h),
                         L33_dev_pct=round(d33, 2), L33_outliers=n33,
                         L11_dev_pct=round(d11, 2), L11_outliers=n11,
                         sum_minutes=round(sum(mins), 2), max_point_minutes=round(max(mins), 2),
                         n_sessions=len(set(pts[i]["aedt_pid"] for i in range(len(xs_h)))),
                         n_bars_rx=d["n_bars_rx"], tx_bar_w=round(d["tx_bar_w"], 3),
                         rx_bar_w=round(d["rx_bar_w"], 3), ferrite_len=d["ferrite_len"],
                         edge_gap=d["edge_gap"], sweep_span=round(d["sweep_span"], 3),
                         rx_volume=round(d["rx_volume"], 2)))

    def dump(path, cols, rows):
        with open(os.path.join(outdir, path), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in rows:
                w.writerow([r.get(c, "") for c in cols])
        print("  %-22s %d 行" % (path, len(rows)))

    dump("%s_cases.csv" % B, WC.CASES_COLS, cases_rows)
    dump("%s_curves.csv" % B, WC.CURVES_COLS, curve_rows)
    dump("%s_selfcheck.csv" % B, CHECK_COLS, chk_rows)
    dump("%s_diag.csv" % B, list(diag[0].keys()) if diag else [], diag)

    n = len(cases_rows)
    if n:
        print("-" * 78)
        print("完整工况 %d / 参数表 %d；未完成 %d 个" % (n, len(plan), len(n_partial)))
        if n_partial:
            print("  未完成: %s" % n_partial[:12])
        print("自检通过(镜像) %d/%d；|k|<1 %d/%d；自感>0 %d/%d；点位等距 %d/%d"
              % (sum(1 for r in chk_rows if r["mirror_pass"]), n,
                 sum(1 for r in chk_rows if r["k_ok"]), n,
                 sum(1 for r in chk_rows if r["L_positive"]), n,
                 sum(1 for r in chk_rows if r["equidistant"]), n))
        mv = [r["M_sum_mean"] for r in diag]
        vv = [r["M_sum_var"] for r in diag]
        pp = [r["M_pp"] for r in diag]
        print("M_sum_mean %.4f ~ %.4f (均值 %.4f)" % (min(mv), max(mv), sum(mv) / n))
        print("M_sum_var  %.4f ~ %.4f (均值 %.4f)" % (min(vv), max(vv), sum(vv) / n))
        print("M_pp       %.4f ~ %.4f (均值 %.4f)" % (min(pp), max(pp), sum(pp) / n))
        print("单点求解 %.2f ~ %.2f min（均值 %.2f）"
              % (min(r["max_point_minutes"] for r in diag),
                 max(r["max_point_minutes"] for r in diag),
                 sum(r["sum_minutes"] for r in diag) / sum(r["n_points"] for r in diag)))
    print("输出目录: %s" % outdir)


if __name__ == "__main__":
    main()
