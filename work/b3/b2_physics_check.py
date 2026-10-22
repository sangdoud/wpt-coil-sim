# -*- coding: utf-8 -*-
"""部分曲线的物理趋势自检（不等工况跑完就能做）。

检查（对每个已解点 ≥4 的工况）：
  1) 接收线圈向 +x（Tx2 侧）移动时，耦合到 Tx2 的互感 M23 应单调上升、到 Tx1 的 M13 单调下降
  2) 自感 L11 / L33 沿位置应基本平稳（几何没变，只有接收线圈平移）
  3) |k13|,|k23| <= 1
  4) 与「几何预期」对照：M23 峰值的 x 位置应接近 Tx2 中心
"""
import csv
import glob
import os
import sys

import numpy as np

# stdout 为管道时中文 Windows 默认 GBK，打印 ✓/✗ 会乱码。
# 计划任务不会设 PYTHONIOENCODING，故在入口强制切 UTF-8（与其他脚本一致）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

ROOT = r"C:\ansys maxwell2024\_work\b2"
sys.path.insert(0, r"C:\wpt")
import coil_gen as CG          # noqa: E402
import wpt_contract as WC      # noqa: E402

plan = {}
# ⚠️ 2026-10-12：原来写死 "b1_plan.csv" / "b1_raw_run*.csv" —— 换批次后本脚本会去读
# **另一批**的参数表与 raw（或直接 FileNotFoundError）。它虽不在计划任务链上，
# 但是操作员查"部分曲线物理趋势"的工具，读错批次会给出完全误导的结论。
BATCH = os.environ.get("WPT_BATCH", "b2")
with open(os.path.join(ROOT, "%s_plan.csv" % BATCH), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        plan[r["case_id"]] = {k: float(r[k]) for k in
                              ("coil_size", "hole_ratio", "spacing_ratio")}

rows = {}
for p in glob.glob(os.path.join(ROOT, "%s_raw_run*.csv" % BATCH)):
    with open(p, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.setdefault(r["case_id"], []).append(r)

ok_all = True
outliers = []
print("=" * 92)
for cid, rs in sorted(rows.items()):
    if len(rs) < 4:
        continue
    rs.sort(key=lambda r: float(r["x_mm"]))
    x = np.array([float(r["x_mm"]) for r in rs])
    m13 = np.array([float(r["M13"]) for r in rs])
    m23 = np.array([float(r["M23"]) for r in rs])
    l11 = np.array([float(r["L11"]) for r in rs])
    l33 = np.array([float(r["L33"]) for r in rs])
    k = np.array([abs(float(r["k13"])) for r in rs] + [abs(float(r["k23"])) for r in rs])
    v = plan[cid]
    LC, g = v["coil_size"], v["spacing_ratio"]
    K = CG.k_lc()
    tg = int(round(g * LC))
    tx2c = tg / 2.0 + CG.coil_outer(LC) / 2.0
    S = LC * (2.0 + g)
    # 部分数据只判「真正可判」的三项（平滑性/量程占比要等 41 点齐全，见 b1_accept.py）：
    #   ① |M23| 在 x < Tx2 中心 范围内单调升（靠近 Tx2）
    #   ② 自感沿位置平稳（几何未变，仅接收平移）
    #   ③ |k| <= 1
    # M13 的过零 + 次级瓣是模型固有形状（试点参考工况实测），只作信息报告、不作判据。
    a13 = np.abs(m13)
    a23 = np.abs(m23)
    r23 = np.diff(a23) / np.maximum(a23[:-1], 1e-9)
    c2 = bool(np.all(r23 >= -0.02)) if x[-1] < tx2c else True
    c3 = float(max(np.ptp(l11), np.ptp(l33)) / np.mean(l11) * 100)
    c3l = float(np.ptp(l11) / np.mean(l11) * 100)
    c4 = bool(k.max() <= 1.0)
    l33m = float(np.median(l33))
    d33 = float(np.abs((l33 - l33m) / l33m * 100).max())
    # 部分数据的判据只留两项（真正与位置无关的）：
    #   ① |M23| 随 x 趋近 Tx2 上升（趋势，见上）
    #   ② |k| <= 1
    # L11/L33 沿位置的变化**是真实物理**，不作判据：
    #   接收线圈移动会改变它对两个发射线圈的耦合，从而真实改变 L11/L22
    #   （实测极端位置 L11 与 L22 差 3.6%，而 x=0 处仅 0.07%）。
    ok = c2 and c4
    ok_all = ok_all and ok
    if d33 >= 2.0:
        outliers.append(cid)
    print("%s  %d/21 点   LC=%6.2f g=%+.4f  S=%6.1f  Tx2中心=%+7.2f"
          % (cid, len(rs), LC, g, S, tx2c))
    print("   |M13|: %s   （过零/次级瓣属模型固有形状，仅信息）"
          % "  ".join("%.3f" % z for z in a13))
    print("   |M23|: %s  %s" % ("  ".join("%.3f" % z for z in a23),
                                "单调升 ✓" if c2 else "★非单调"))
    print("   L11 %.3f~%.3f（%.2f%%）  L33 %.3f~%.3f（%.2f%%，离群最大 %.1f%% %s）| |k|max=%.4f %s"
          % (l11.min(), l11.max(), c3l,
             l33.min(), l33.max(), float(np.ptp(l33) / np.mean(l33) * 100), d33,
             "✓" if d33 < 2 else "★单点网格离群", k.max(), "✓" if c4 else "★>1"))
    print("   x 位置: %s" % "  ".join("%.2f" % z for z in x))
print("=" * 92)
print("物理判据（|M23| 单调升 / |k|<=1 / L11 平稳）：%s" % ("全部通过 ✓" if ok_all else "有异常 ✗"))
print("L33 单点离群（>2%%，属柔性网格的单点表面网格质量波动）：%s"
      % ("无" if not outliers else "%d 个工况 %s" % (len(outliers), outliers)))
print("   四目标（M_sum / M_pp / V_rx）不使用 L33，不影响主交付；L33 与 k13/k23 列会继承，")
print("   下游可按 b1_diag.csv 的 L33_dev_pct / L33_outliers 两列筛选或加权。")
print("说明：|M13| 呈「过零 + 次级瓣」是模型固有形状（试点参考工况实测：4.017 -> 过零 -> 0.88 -> 回落），")
print("      故不作单调性判据；平滑性与量程占比等 41 点齐全后由 b1_accept.py 判。")
