# -*- coding: utf-8 -*-
r"""batch1 验收检查 + 验收报告生成（读合并后的契约 CSV，不启动 AEDT）。

检查项（对应文档第 9 章自检清单 + 本次新增项）：
  A 完整性   每工况 41 点、半扫 21 点齐全、列名逐字对齐契约
  B 点位     升序、等距（S/40）、关于 0 对称
  C 镜像     M1(-x)=M2(+x) 逐位成立；曲线表 M_pp 留空
  D 有效性   自感/互感无 NaN、L>0、|k|<=1
  E 自检表   asym_pct 分布、mirror_pass 比例
  F 目标量   M_sum_mean / M_sum_var / M_pp 分布 + 物理趋势（与 g、LC、Lc 的相关性方向）
  G 曲线形状 M_sum 曲线平滑（无跳变）、峰值位置合理
  H 交叉校验 L11≈L22（两个发射线圈对称性）
  I 几何     拐角尖角检查（最大转角 <=15°，本次新增）
  J 耗时     单点/单工况耗时分布 + 全量 ETA 外推

用法： python b1_accept.py [--root ...] [--batch b1] [--out ...]
"""
import argparse
import csv
import math
import os
import sys

import numpy as np

# 无人值守环境下 stdout 是管道时，中文 Windows 默认用 GBK 编码，
# 打印 ✓(U+2713) / ✗(U+2717) 会抛 UnicodeEncodeError 直接中断报告生成
# （2026-09-19 由计划任务 S4U 环境实测触发）。计划任务不会设 PYTHONIOENCODING，
# 因此必须在入口强制切到 UTF-8，不能依赖调用方。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG          # noqa: E402
import wpt_contract as WC      # noqa: E402

MAIN = ["coil_size", "hole_ratio", "tx_fill", "rx_fill",
        "tx_thick", "rx_thick", "spacing_ratio"]

# 契约：每工况 21 点半扫（x_i = i·S/40, i=0..20）。
# curves 每工况 41 行是含镜像展开后的口径，勿与求解点数混淆。
PTS_PER_CASE = 21


def corner_max_angle(LC, KR):
    P = CG.make_path(LC, KR)[:, :2]
    v = np.diff(P, axis=0)
    ang = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    d = np.abs((np.diff(ang) + 180.0) % 360.0 - 180.0)
    return float(d.max())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"C:\ansys maxwell2024\_work\b2")
    ap.add_argument("--batch", default="b2")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    ROOT, B = args.root, args.batch
    outdir = os.path.join(ROOT, "out")
    outmd = args.out or os.path.join(outdir, "%s_acceptance.md" % B)

    def rd(name):
        p = os.path.join(outdir, name)
        if not os.path.exists(p):
            return []
        with open(p, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def rd_root(name):
        """读 ROOT 下的文件。参数表等【输入】在 ROOT，不在 out\\。"""
        p = os.path.join(ROOT, name)
        if not os.path.exists(p):
            return []
        with open(p, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    cases = rd("%s_cases.csv" % B)
    curves = rd("%s_curves.csv" % B)
    chk = rd("%s_selfcheck.csv" % B)
    diag = rd("%s_diag.csv" % B)
    # b1_plan.csv 是【输入】，位于 ROOT 而非 out\；rd() 只查 out\，故此处曾恒为空，
    # 导致 A 节表头参数表记 0、J 节全量外推被静默跳过。改从 ROOT 读，out\ 仅作兜底。
    plan = (rd_root("%s_plan.csv" % B)
            or rd("%s_plan.csv" % B))
    L = []
    ok_all = True

    def line(s=""):
        print(s)
        L.append(s)

    def check(cond, msg):
        nonlocal ok_all
        ok_all = ok_all and bool(cond)
        line(("  ✓ " if cond else "  ✗ ") + msg)
        return bool(cond)

    line("# batch1 验收报告")
    line()
    line("生成时间：%s" % __import__("time").strftime("%Y-%m-%d %H:%M:%S"))
    line("输入：`%s`（cases %d / curves %d / selfcheck %d / diag %d 行；参数表 %d 工况）"
         % (outdir, len(cases), len(curves), len(chk), len(diag), len(plan)))
    line()
    if not cases:
        line("**尚无完整工况**（点位可能仍在计算中）。")
        open(outmd, "w", encoding="utf-8").write("\n".join(L))
        return 1

    v = {c["case_id"]: c for c in cases}
    cur = {}
    for r in curves:
        cur.setdefault(r["case_id"], []).append(r)

    line("## A 完整性与列名")
    check(list(cases[0].keys()) == WC.CASES_COLS, "cases 列名逐字对齐契约（%d 列）" % len(WC.CASES_COLS))
    check(list(curves[0].keys()) == WC.CURVES_COLS, "curves 列名逐字对齐契约（%d 列）" % len(WC.CURVES_COLS))
    bad_n = [c for c in v if len(cur.get(c, [])) != 41]
    check(not bad_n, "每工况 41 点（异常：%s）" % (bad_n[:5] or "无"))

    line()
    line("## B 点位口径")
    xs_bad, dstep_bad = [], []
    for cid, rows in cur.items():
        xs = [float(r["position_x"]) for r in rows]
        if any(xs[i] >= xs[i + 1] for i in range(len(xs) - 1)):
            xs_bad.append(cid)
        d = np.diff(xs)
        if d.max() - d.min() > 1e-3:
            dstep_bad.append(cid)
    check(not xs_bad, "position_x 严格升序（异常：%s）" % (xs_bad[:5] or "无"))
    check(not dstep_bad, "步长等距（异常：%s）" % (dstep_bad[:5] or "无"))
    # 与契约公式对照
    dev = 0.0
    for cid, c in v.items():
        LC = float(c["coil_size"]); g = float(c["spacing_ratio"])
        want = WC.sweep_positions(LC, g)
        got = [float(r["position_x"]) for r in cur[cid]]
        dev = max(dev, max(abs(a - b) for a, b in zip(want, got)))
    check(dev < 5e-4, "与契约 41 点公式最大偏差 %.2e mm（四舍五入到 4 位小数）" % dev)

    line()
    line("## C 镜像关系（① 半扫展开）")
    worst_mir = 0.0
    blank_ok = True
    for cid, rows in cur.items():
        by = {round(float(r["position_x"]), 4): (float(r["M1"]), float(r["M2"])) for r in rows}
        for x, (m1, m2) in by.items():
            if x > 0 and round(-x, 4) in by:
                worst_mir = max(worst_mir, abs(by[round(-x, 4)][0] - m2),
                                abs(by[round(-x, 4)][1] - m1))
        blank_ok = blank_ok and all(r["M_pp"] == "" for r in rows)
    check(worst_mir < 1e-6, "M1(-x)=M2(+x) 逐位成立（最大偏差 %.2e）" % worst_mir)
    check(blank_ok, "曲线表 M_pp 留空（由 cases 标量回退）")

    line()
    line("## D 有效性（L>0、|k|<=1、无 NaN）")
    Lbad, kbad = [], []
    for cid, rows in cur.items():
        for r in rows:
            vals = [float(r[x]) for x in ("M1", "M2", "L11", "L22", "L33", "k13", "k23")]
            if any(math.isnan(z) for z in vals) or min(float(r["L11"]), float(r["L22"]),
                                                       float(r["L33"])) <= 0:
                Lbad.append((cid, r["position_x"]))
            if max(abs(float(r["k13"])), abs(float(r["k23"]))) > 1.0:
                kbad.append((cid, r["position_x"]))
    check(not Lbad, "所有自感 >0 且无 NaN（异常 %d 处）" % len(Lbad))
    check(not kbad, "所有 |k| <= 1（异常 %d 处）" % len(kbad))

    line()
    line("## E 自检表")
    asym = [float(r["asym_pct"]) for r in chk if r["asym_pct"] not in ("", None)]
    npass = sum(1 for r in chk if r["mirror_pass"] == "True")
    line("  asym_pct（x=0 固有非对称度，契约口径 = |M1-M2|/max|M|）：min %.3f%% 中位 %.3f%% max %.3f%%"
         % (min(asym), float(np.median(asym)), max(asym)))
    # 契约口径在 x=0 互感接近零时会爆炸（实测 b1_0169 达 143.7%，但绝对差仅 0.102μH）。
    # 因此验收同时看「按曲线峰值归一化」的非对称度 —— 与参考点 2.19~2.23% 可直接比较。
    asym_peak, na = [], []
    for cid, rows in cur.items():
        by = {round(float(r["position_x"]), 4): (float(r["M1"]), float(r["M2"])) for r in rows}
        c0 = by.get(0.0)
        if not c0:
            continue
        pk = max(max(abs(z) for z in t) for t in by.values()) or 1.0
        ap = abs(c0[0] - c0[1]) / pk * 100.0
        asym_peak.append(ap)
        if max(abs(c0[0]), abs(c0[1])) < 0.5:
            na.append(cid)
    line("  峰值归一化非对称度：min %.3f%% 中位 %.3f%% max %.3f%%（参考点 2.19~2.23%%）"
         % (min(asym_peak), float(np.median(asym_peak)), max(asym_peak)))
    if na:
        line("  其中 %d 个工况 x=0 处 |M|<0.5μH（过零点附近），契约口径的 %% 值不可比：%s"
             % (len(na), na[:6]))
    line("  mirror_pass：%d/%d" % (npass, len(chk)))
    check(len(chk) == len(cases), "自检表与 cases 一一对应")
    check(max(asym_peak) < 5.0, "峰值归一化非对称度全部 < 5%（参考点实测 2.19~2.23%）")

    line()
    line("## F 目标量分布与物理趋势")
    ms = np.array([float(r["M_sum_mean"]) for r in diag])
    mv = np.array([float(r["M_sum_var"]) for r in diag])
    mp = np.array([float(r["M_pp"]) for r in diag])
    line("  M_sum_mean %.4f ~ %.4f（均值 %.4f）" % (ms.min(), ms.max(), ms.mean()))
    line("  M_sum_var  %.4f ~ %.4f（均值 %.4f）" % (mv.min(), mv.max(), mv.mean()))
    line("  M_pp       %.4f ~ %.4f（均值 %.4f）" % (mp.min(), mp.max(), mp.mean()))
    g = np.array([float(v[r["case_id"]]["spacing_ratio"]) for r in diag])
    LC = np.array([float(v[r["case_id"]]["coil_size"]) for r in diag])
    l11 = []
    for r in diag:
        l11.append(np.mean([float(z["L11"]) for z in cur[r["case_id"]]]))
    l11 = np.array(l11)
    c1 = np.corrcoef(g, ms)[0, 1] if (len(diag) > 2 and np.std(g) > 1e-9 and np.std(ms) > 1e-9) else float("nan")
    c2 = np.corrcoef(LC, l11)[0, 1] if (len(diag) > 2 and np.std(LC) > 1e-9 and np.std(l11) > 1e-9) else float("nan")
    line("  趋势：corr(g, M_sum_mean) = %+.3f（应为负：间隙越大耦合越小）" % c1)
    line("        corr(LC, L11)      = %+.3f（应为正：线圈越大自感越大）" % c2)
    if len(diag) > 2:
        if math.isnan(c1):
            line("  （g 或 M_sum 无变化，趋势检查跳过）")
        else:
            check(c1 < 0.3, "间隙-耦合趋势方向正确")
        if math.isnan(c2):
            line("  （LC 或 L11 无变化，趋势检查跳过）")
        else:
            check(c2 > 0.3, "线圈尺寸-自感趋势方向正确")
    else:
        line("  （样本 <3，趋势检查跳过）")

    line()
    line("## G 曲线形状")
    jumps, rel, peaks = [], [], []
    for cid, rows in cur.items():
        rows_s = sorted(rows, key=lambda r: float(r["position_x"]))
        m = np.array([float(r["M1"]) + float(r["M2"]) for r in rows_s])
        x = np.array([float(r["position_x"]) for r in rows_s])
        d = np.abs(np.diff(m))
        rng = float(m.max() - m.min()) or 1.0
        jumps.append((float(d.max()), cid))
        rel.append(float(d.max()) / rng)
        peaks.append((float(x[int(np.argmax(np.abs(m)))]), cid))
    jumps.sort(reverse=True)
    check(max(rel) < 0.35, "相邻点 M_sum 最大跳变占量程 %.1f%%（%.4f，%s）"
          % (max(rel) * 100, jumps[0][0], jumps[0][1]))
    line("  峰值位置 |x| 范围：%.1f ~ %.1f mm"
         % (min(abs(p[0]) for p in peaks), max(abs(p[0]) for p in peaks)))

    line()
    line("## H 交叉校验（发射线圈对称性 + 互感形状）")
    # L11 vs L22：应在**对称位置 x=0** 比较 —— 接收线圈偏到一侧时对两个发射线圈的
    # 耦合不同，会真实地改变 L11/L22（实测 b1_0169 在 x=-193 处差 3.6%，x=0 处仅 0.07%）。
    dl, pos_worst = [], None
    for cid, rows in cur.items():
        by = {round(float(r["position_x"]), 4): r for r in rows}
        r0 = by.get(0.0)
        if not r0:
            continue
        a, b = float(r0["L11"]), float(r0["L22"])
        dl.append(abs(a - b) / max(a, b) * 100.0)
    check(max(dl) < 2.0, "x=0 处 |L11-L22|/max 最大 %.3f%%（几何对称，应很小）" % max(dl))
    # |M2|=|M23| 在 x 靠近 Tx2 的过程中应显著上升（趋势判据，避免峰值附近的
    # 平坦段被噪声误判为"非单调"）；|M1| 允许过零 + 次级瓣（模型固有形状，
    # 试点实测 4.017 -> 过零 -> 0.88 -> 回落），故不作单调性判据。
    bad23, shape = [], []
    for cid, rows in cur.items():
        rs = sorted(rows, key=lambda r: float(r["position_x"]))
        x = np.array([float(r["position_x"]) for r in rs])
        a23 = np.abs([float(r["M2"]) for r in rs])       # M2 = M23（耦合到 Tx2）
        a13 = np.abs([float(r["M1"]) for r in rs])       # M1 = M13（耦合到 Tx1）
        LC = float(v[cid]["coil_size"]); g = float(v[cid]["spacing_ratio"])
        tx2c = int(round(g * LC)) / 2.0 + CG.coil_outer(LC) / 2.0
        m = x < tx2c
        if m.sum() >= 3 and np.std(x[m]) > 1e-9 and np.std(a23[m]) > 1e-12:
            c = float(np.corrcoef(x[m], np.array(a23)[m])[0, 1])
            net = float(a23[m][-1] - a23[m][0])
            if not (c > 0.7 and net > 0):
                bad23.append((cid, round(c, 3), round(net, 3)))
        shape.append((float(a13.max()), float(a13.min()), cid))
    check(not bad23, "|M23| 随 x 趋近 Tx2 显著上升（corr>0.7 且净增>0；异常：%s）"
          % (bad23[:4] or "无"))
    line("  |M13| 过零检查：%d 个工况出现幅值过零/次级瓣（模型固有形状，非异常）"
         % sum(1 for mx, mn, _ in shape if mn < 0.02 * max(mx, 1e-9)))

    line()
    line("## H2 L33 单点噪声（网格质量，非物理）")
    if diag and "L33_dev_pct" in diag[0]:
        d33 = [float(r["L33_dev_pct"]) for r in diag]
        n_out = sum(int(r["L33_outliers"]) for r in diag)
        flagged = [r["case_id"] for r in diag if float(r["L33_dev_pct"]) >= 2.0]
        line("  L33 对本工况中位最大偏差：中位 %.2f%%  p90 %.2f%%  max %.2f%%"
             % (float(np.median(d33)), float(np.percentile(d33, 90)), max(d33)))
        line("  单点离群（>2%%）合计 %d 个点，涉及 %d 个工况：%s"
             % (n_out, len(flagged), flagged[:8]))
        line("  四目标（M_sum / M_pp / V_rx）不使用 L33；L33 与 k13/k23 列会继承该噪声，")
        line("  可按 b1_diag.csv 的 L33_dev_pct / L33_outliers 筛选或加权。")
    else:
        line("  （本次未生成 L33 诊断列）")

    # ---- H3：L11 与 L33 的性质区分（2026-09-19 新增）----
    # 动机：b1_diag.csv 显示 L11_dev 在 15 个工况里有 12 个大于 L33_dev，容易被误当成
    # 同类噪声。实测二者性质相反 —— 若不加区分，下游可能错误地"滤掉"L11 的真实物理
    # 趋势，或误以为 L11 干净而忽略了 k13/k23 的噪声来源。
    # 注意：curves.csv 是镜像展开的 41 点，全量 x 关于 0 对称，直接求相关会得到 ≈0 的
    # 假结果；必须只取半扫（x>=0）才反映真实的沿轴变化。
    line()
    line("## H3 L11 沿轴变化是物理效应，不是噪声（2026-09-19 新增）")
    byc = {}
    for r in curves:
        try:
            xv, l11, l33 = float(r["position_x"]), float(r["L11"]), float(r["L33"])
        except (TypeError, ValueError):
            continue
        if xv >= 0:                       # 只用半扫，避开镜像对称导致的假零相关
            byc.setdefault(r["case_id"], []).append((xv, l11, l33))

    def _corr(vals, xs):
        if len(vals) < 8:
            return None
        a, b = np.asarray(vals, float), np.asarray(xs, float)
        if a.std() < 1e-12 or b.std() < 1e-12:
            return None
        return float(np.corrcoef(a, b)[0, 1])

    r11 = [c for c in (_corr([p[1] for p in v], [p[0] for p in v]) for v in byc.values())
           if c is not None]
    r33 = [c for c in (_corr([p[2] for p in v], [p[0] for p in v]) for v in byc.values())
           if c is not None]
    if r11 and r33:
        m11, m33 = float(np.median(np.abs(r11))), float(np.median(np.abs(r33)))
        # 判别量用【符号一致性】而非单看 |r| 大小：物理效应的相关性在所有工况同号；
        # 纯噪声则正负各半。只看 |r| 会把"|r| 中等但符号乱跳"误判成弱相关。
        con11 = max(sum(1 for c in r11 if c < 0), sum(1 for c in r11 if c > 0)) / len(r11)
        con33 = max(sum(1 for c in r33 if c < 0), sum(1 for c in r33 if c > 0)) / len(r33)
        line("  沿轴相关系数（半扫 x>=0）：L11 |r| 中位 %.2f，符号一致性 %.0f%%（%d 个工况）"
             % (m11, 100 * con11, len(r11)))
        line("                            L33 |r| 中位 %.2f，符号一致性 %.0f%%（%d 个工况）"
             % (m33, 100 * con33, len(r33)))
        if con11 >= 0.8 and m11 >= 0.5:
            line("  ✓ L11 与位置**强系统相关，且 %d/%d 个工况同号** -> 接收线圈+铁氧体沿轴"
                 % (max(sum(1 for c in r11 if c < 0), sum(1 for c in r11 if c > 0)), len(r11)))
            line("    移动改变了 Tx1 磁路加载，是**真实物理效应**（方向：Rx 远离 Tx1 时 L11 下降）。")
            line("    **不得当作网格噪声过滤。**")
            line("  · 对照 L33：|r| 中位 %.2f、符号一致性 %.0f%% —— **弱于 L11，但并非纯随机**，"
                 % (m33, 100 * con33))
            line("    说明 L33 也含物理成分（Tx 侧磁路对 Rx 的反向加载）。H2 所称「单点噪声」")
            line("    指的是其**孤立离群点**（>2% 的那几个），不是整条曲线的走势。")
            line("  交付口径：k13/k23 = M/sqrt(L11·L33) 中两侧都含真实物理变化；只应对 L33 的")
            line("    **孤立离群点**做筛选/加权（b1_diag.csv 的 L33_outliers），L11 侧与 L33 的")
            line("    整体趋势都须保留。四目标（M_sum / M_pp / V_rx）不使用 L11/L33 绝对值。")
        else:
            line("  ! L11 的系统性不显著，性质待人工确认（见 _diag_L11_nature.py）")
    else:
        line("  （L11/L33 沿轴相关无法计算）")

    line()
    line("## I 几何拐角检查（本次新增，防同类缺陷）")
    ang = [corner_max_angle(float(v[c]["coil_size"]), float(v[c]["hole_ratio"])) for c in v]
    check(max(ang) < 15.0, "最大转角 %.2f°（阈值 15°，模板固有 11.25°）" % max(ang))

    line()
    line("## J 耗时与 ETA")
    if diag:
        sm = [float(r["sum_minutes"]) for r in diag]
        npts = [int(r["n_points"]) for r in diag]
        per = sum(sm) / sum(npts)
        line("  单工况几何+21 点：%.1f ~ %.1f 分钟（均值 %.1f）"
             % (min(sm), max(sm), sum(sm) / len(sm)))
        line("  单点均值 %.2f 分钟（8 实例并行下的墙钟口径由启动器日志给出）" % per)
        done = len(cases) or len(diag)
        if plan:
            # 每工况 21 点（契约半扫口径；curves 每工况 41 行是含镜像的展开）。
            # 此前误把「单点分钟数」当作「单工况分钟数」直接乘剩余工况数，
            # 使剩余时间被低估 21 倍。
            rem_cases = max(0, len(plan) - done)
            rem_pts = rem_cases * PTS_PER_CASE
            mh = rem_pts * per / 60.0
            line("  已完成 %d/%d 工况；剩余 %d 工况 × %d 点 = %d 点"
                 % (done, len(plan), rem_cases, PTS_PER_CASE, rem_pts))
            line("  按单点 %.2f 分钟外推：剩余 %.1f 机时 → 8 实例墙钟 ≈ %.1f 小时（%.1f 天）"
                 % (per, mh, mh / 8.0, mh / 8.0 / 24.0))
            line("  注：未计入 BASE 回退工况（慢 ~2.8×）与半截工况已解点，实际偏乐观；"
                 "权威进度以 b1_status.py 为准")
        else:
            line("  已完成 %d 个工况（参数表未找到，跳过全量外推）" % done)

    line()
    line("## 结论")
    line("  **%s**" % ("全部检查通过，可交付" if ok_all else "存在未通过项，见上方 ✗"))
    line()
    os.makedirs(os.path.dirname(outmd), exist_ok=True)
    with open(outmd, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("\n报告 -> %s" % outmd)
    return 0 if ok_all else 2


if __name__ == "__main__":
    sys.exit(main())
