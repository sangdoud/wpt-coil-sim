# -*- coding: utf-8 -*-
"""点位裁剪的离线验证：用旧数据集里已有的密集曲线，检验
「用 11/15/21 点算出的 M_sum_mean / M_sum_var / M_pp，与全点数结果差多少」。

为什么能做：`C:\\wpt\\sweep_all_unit30.csv` 是 (W,G,tx_gap,mu) 固定、dx 变化的扫描点表，
某些组合下有整条曲线。曲线光滑性由几何决定，旧几何（unit30、Lc≈165）与现在同族，
所以这里的结论对"点位能否再砍"有直接参考价值（正式上线前应再用当前几何的一条曲线复验）。

输出：_work/point_reduction.txt + .json
"""
import csv
import json
import math
import os
from collections import defaultdict

SRC = r"C:\wpt\sweep_all_unit30.csv"
OUT = r"C:\ansys maxwell2024\_work\point_reduction"
BUF = []


def say(*a):
    BUF.append(" ".join(str(x) for x in a))


rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
say("总行数 %d，列: %s" % (len(rows), list(rows[0].keys())))

groups = defaultdict(list)
for r in rows:
    key = (r.get("W_mm"), r.get("G_mm"), r.get("tx_gap_mm"), r.get("mu"))
    try:
        groups[key].append((float(r["dx_mm"]), float(r["M13_uH"]), float(r["M23_uH"]),
                            float(r["M12_uH"])))
    except Exception:
        continue

curves = {k: sorted(v) for k, v in groups.items() if len({p[0] for p in v}) >= 12}
say("含 >=12 个不同 dx 的参数组: %d" % len(curves))
lens = sorted({len({p[0] for p in v}) for v in curves.values()})
say("各曲线点数分布: %s" % lens[:12])


def objectives(pts):
    ms = [p[1] + p[2] for p in pts]
    n = len(ms)
    mean = sum(ms) / n
    var = sum((a - mean) ** 2 for a in ms) / n
    mpp = sum(p[3] for p in pts) / n
    return mean, var, mpp


res = []
for key, pts in sorted(curves.items(), key=lambda kv: -len(kv[1])):
    xs = sorted({p[0] for p in pts})
    dedup = []
    seen = set()
    for p in pts:
        if p[0] not in seen:
            seen.add(p[0])
            dedup.append(p)
    m0, v0, p0 = objectives(dedup)
    rec = dict(key=key, n=len(dedup), x_range=[min(xs), max(xs)],
               M_sum_mean=m0, M_sum_var=v0, M_pp=p0, subsets={})
    for k in (21, 15, 11, 9, 7):
        if k >= len(dedup):
            continue
        idx = [round(i * (len(dedup) - 1) / (k - 1)) for i in range(k)]
        sub = [dedup[i] for i in idx]
        m1, v1, p1 = objectives(sub)
        rec["subsets"][k] = dict(
            n=k,
            d_mean_pct=round(100 * (m1 - m0) / m0, 4) if m0 else None,
            d_var_pct=round(100 * (v1 - v0) / v0, 4) if v0 else None,
            d_mpp_pct=round(100 * (p1 - p0) / p0, 4) if p0 else None)
    res.append(rec)

say("")
say("=== 逐曲线结果（只列前 8 条最长的）===")
for rec in res[:8]:
    say("曲线 %s 点数=%d  dx∈[%.0f,%.0f]" % (rec["key"], rec["n"],
                                             rec["x_range"][0], rec["x_range"][1]))
    for k, d in sorted(rec["subsets"].items(), reverse=True):
        say("   取 %2d 点: D_mean %+.3f%%  D_var %+.3f%%  D_Mpp %+.3f%%"
            % (k, d["d_mean_pct"] or 0, d["d_var_pct"] or 0, d["d_mpp_pct"] or 0))

say("")
say("=== 汇总（所有曲线，取最坏）===")
summary = {}
for k in (21, 15, 11, 9, 7):
    vals = [(rec["subsets"][k]["d_mean_pct"], rec["subsets"][k]["d_var_pct"],
             rec["subsets"][k]["d_mpp_pct"]) for rec in res if k in rec["subsets"]]
    if not vals:
        continue
    worst = [max(abs(v[i]) for v in vals) for i in range(3)]
    med = [sorted(abs(v[i]) for v in vals)[len(vals) // 2] for i in range(3)]
    summary[k] = dict(n_curves=len(vals), worst_mean=worst[0], worst_var=worst[1],
                      worst_mpp=worst[2], med_mean=med[0], med_var=med[1], med_mpp=med[2])
    say("  取 %2d 点: 最坏 |D_mean| %.3f%%  |D_var| %.3f%%  |D_Mpp| %.3f%%   "
        "(中位 %.3f%% / %.3f%% / %.3f%%)"
        % (k, worst[0], worst[1], worst[2], med[0], med[1], med[2]))

open(OUT + ".txt", "w", encoding="utf-8").write("\n".join(BUF) + "\n")
json.dump(dict(curves=res, summary=summary), open(OUT + ".json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
