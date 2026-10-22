# -*- coding: utf-8 -*-
"""b2（1920 工况）用户参数表**只读**校验器 —— 离线，不启动 AEDT，不写任何文件。

背景
----
第一轮 build_b1_plan.py（:73-74）对用户参数表没有任何校验，gap_min/use_opt/t_case_min
全是抄 batch1_audit.csv，空气域盒硬编码 BOX_X=330（:29）。
b2 共 1920 工况，必须**自己算**派生量并做完整校验，因此把校验独立成这个脚本，
build_b2_plan.py 直接 import 它复用（校验 FAIL -> 不产出任何文件）。

冻结口径（不可改，与 build_b2_plan.py 保持同一份常量）
----------------------------------------------------
* 空气域固定盒: X ±420 / Y [-134.94, 161] / Z [-45, 75]，留边 MARGIN=40
* 几何路径 PATH_MODE=ring（coil_gen.PATH_MODE 默认值）
* 网格闸门 OPT_MIN_GAP=1.5（gap_min >= 1.5 -> OPT，否则整套 BASE）
* 半扫 21 点（镜像展开 41）
* 单工况耗时先验常数: OPT t_case_min=105.4 / BASE t_case_min=290.8
  —— 非 b1 直接实测值，而是由 audit_batch1.py 的先验口径换算得到：
     点耗时 4.78 / 13.61 min（文档实测）+ 21 点 + 5 min 几何重建
     -> 21*4.78+5 = 105.38 -> 105.4；21*13.61+5 = 290.81 -> 290.8
* 几何公式照 build_b1_plan.py:48-53

退出码：全部通过 -> 0；任一 FAIL -> 1（CLI 下）。
"""
import argparse
import csv
import importlib
import math
import os
import re
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 注意：_probe 目录里有一个**同名旧版** coil_gen.py（无 k_lc/path_dims），
# 如果它先被 import 就会遮蔽 C:\wpt 的正版（实测 AttributeError: k_lc）。
# 因此这里先确保 C:\wpt 在搜索路径最前，再 import。
WPT_DIR = r"C:\wpt"
PROBE_DIR = os.path.dirname(os.path.abspath(__file__))
if WPT_DIR not in sys.path:
    sys.path.insert(0, WPT_DIR)
else:
    sys.path.remove(WPT_DIR)
    sys.path.insert(0, WPT_DIR)

import coil_gen as CG            # noqa: E402
import wpt_contract as WC        # noqa: E402

# 防遮蔽自检：万一拿到的是 _probe 下的旧版，强制按 C:\wpt 重新加载
if not (hasattr(CG, "k_lc") and hasattr(CG, "path_dims")
        and os.path.dirname(os.path.abspath(CG.__file__)) == WPT_DIR):
    for _m in ("coil_gen", "wpt_contract"):
        sys.modules.pop(_m, None)
    CG = importlib.import_module("coil_gen")
    WC = importlib.import_module("wpt_contract")
if os.path.dirname(os.path.abspath(CG.__file__)) != WPT_DIR:
    raise ImportError("coil_gen 解析到了 %s，不是 %s 下的正版（k_lc/path_dims 会缺失）"
                      % (CG.__file__, WPT_DIR))

# ============================ 冻结口径常量 ============================
BOX_X = 420.0                  # 空气域固定盒 X 半宽（b1 结论值，见 b1_plan_meta.json box_x_suggest）
BOX_Y = (-134.94, 161.0)       # 空气域固定盒 Y 范围
BOX_Z = (-45.0, 75.0)          # 空气域固定盒 Z 范围
MARGIN = 40.0                  # 固定盒留边（"区域不贴物体"口径）
PATH_MODE_REQUIRED = "ring"    # 冻结几何路径口径
OPT_MIN_GAP = 1.5              # 网格闸门：gap_min >= 1.5 -> OPT，否则整套 BASE
N_HALF = 21                    # 半扫点数（镜像展开 41）
N_FULL = 41
# 单工况耗时先验常数（来自 b1 实测两档）
T_CASE_OPT = 105.4             # 先验估计，非 b1 直接实测（= 21*4.78 + 5 几何重建）
T_CASE_BASE = 290.8            # 先验估计，非 b1 直接实测（= 21*13.61 + 5 几何重建）
T_POINT_OPT = 4.78             # 单点耗时（audit_batch1.py 口径）
T_POINT_BASE = 13.61
# ⚠️ 工期**唯一**可用常数：b1 生产口径实测单工况均值（含 BASE 工况与 8 实例争用）。
# 来源：b1 交付的 8 份 raw 逐点 minutes 求和 = 735 实例·小时 / 5370 点 / 251 完整工况
# -> 单点 8.22 min、单工况 172.4 min（交付文档口径 8.18 / 171.8，为 251 个完整工况的均值）。
# 上面的 105.4/290.8 只用于给工况排序，用它们估工期会低估约 1.64 倍。
T_CASE_MEASURED = 172.4
N_INST = 8                     # 并行实例数
HOURS_PER_DAY = 24.0           # 墙钟口径：8 实例 24h 滚动（与 audit_batch1.py 的 /N_INST/24.0 一致）
RANGE_TOL = 1e-6               # 范围比对容差（浮点存储误差）
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_b2_plan.py")

# 用户参数表列（除 case_id 外的 7 维）
DIM_COLS = list(WC.MAIN_COLS)
REQ_COLS = ["case_id"] + DIM_COLS


# ============================ 合法域解析 ============================
def parse_contract_domain(contract_path=r"C:\wpt\wpt_contract.py"):
    """从 wpt_contract.py 顶部注释读取 7 维合法域。

    契约文件第 11-13 行原文：
        coil_size(Lc) 120~220mm | hole_ratio(r_h) 0.2~0.5 | tx_fill 1/3~2/3
        rx_fill 1/3~2/3 | tx_thick 5~10mm | rx_thick 5~10mm | spacing_ratio(g) -0.5~+0.5
    解析不出来就返回 (None, 原因)，由调用方退回 WARN 口径（绝不凭空编造硬性范围）。
    """
    try:
        with open(contract_path, encoding="utf-8") as f:
            txt = f.read()
    except OSError as e:
        return None, "读取 %s 失败: %s" % (contract_path, e)

    dom = {}
    # 形态 A：名字 + 区间（120~220 / 1/3~2/3 / -0.5~+0.5）
    for name, lo, hi in re.findall(
            r"([a-z_]+)(?:\([^)]*\))?\s+(-?\d+(?:\.\d+)?(?:/\d+)?)\s*[~～]\s*\+?(-?\d+(?:\.\d+)?(?:/\d+)?)",
            txt):
        if name not in DIM_COLS or name in dom:
            continue
        dom[name] = (_eval_num(lo), _eval_num(hi))
    # 形态 B：区间 + 名字（如 "Lc 范围 120~220mm" 之类）
    for lo, hi, name in re.findall(
            r"(-?\d+(?:\.\d+)?(?:/\d+)?)\s*[~～]\s*\+?(-?\d+(?:\.\d+)?(?:/\d+)?)\s*mm?\s*[（(]?([a-z_]+)",
            txt):
        if name not in DIM_COLS or name in dom:
            continue
        dom[name] = (_eval_num(lo), _eval_num(hi))
    missing = [c for c in DIM_COLS if c not in dom]
    if missing:
        return None, "契约注释里没解析出这些维的区间: %s" % ", ".join(missing)
    return dom, ""


def _eval_num(s):
    """'2/3' -> 0.666...；'220' -> 220.0。"""
    if "/" in s:
        a, b = s.split("/")
        return float(a) / float(b)
    return float(s)


def b1_reference_domain(src=r"C:\ansys maxwell2024\_work\batch1_samples.csv"):
    """退回口径：b1 实测范围（只作参考，返回 None 表示读不到）。"""
    try:
        with open(src, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        return {c: (min(float(r[c]) for r in rows), max(float(r[c]) for r in rows))
                for c in DIM_COLS}
    except (OSError, UnicodeDecodeError, csv.Error, KeyError, ValueError):
        return None


def parse_float(s):
    """把单元格转 float；空串/非数字/NaN/Inf 一律返回 None。"""
    if s is None:
        return None
    t = s.strip()
    if t == "":
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return v


# ============================ 逐项检查 ============================
def _check(checks, status, title, detail=""):
    checks.append(dict(status=status, title=title, detail=detail))
    return status


def _percentile(sorted_vals, p):
    """线性插值分位（b1 用的是取整索引口径，这里 b2 用标准口径，只影响展示）。"""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * p / 100.0
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac


def validate(src, rows=1920, batch="b2", box_x=BOX_X, timing=True, verbose=False,
             expect_path_mode=PATH_MODE_REQUIRED, waive_box_margin=None):
    """执行全部校验。返回 report dict（不写任何文件）。

    waive_box_margin: 若给出非空字符串（豁免理由），则"物体仍在盒内、但 +MARGIN 留边不足"
    这一项从 FAIL 降为 WARN，理由记入 stats["box_margin_waiver"]。
    ⚠️ 只有拿到 **实测证据**（如 _probe\\ab_box_margin_20261012.py 的 A/B）才允许豁免；
    默认严格：不给理由就是 FAIL，批次不许启动。

    report = {passed, checks:[{status,title,detail}], n_ok/n_warn/n_fail,
              records:[{case_id, ...7 维...}], vals:[{case_id, 7 维 float}],
              geom:[{case_id, need_x, need_x_margin, y_half, gap_min, use_opt,
                     t_case_min, sweep_span}], stats:{...}}
    """
    checks = []
    rep = dict(passed=False, checks=checks, n_ok=0, n_warn=0, n_fail=0,
               records=[], vals=[], geom=[], stats={}, batch=batch,
               src=src, rows=rows, box_x=box_x,
               box_margin_waiver=waive_box_margin)

    # ---------- 检查 1：文件存在 / 可解析 / 非空 ----------
    if not os.path.isfile(src):
        _check(checks, "FAIL", "1 文件存在性", "找不到源表: %s" % src)
        return _finish(rep)
    raw = None
    for enc in ("utf-8-sig", "utf-8"):
        try:
            with open(src, encoding=enc, newline="") as f:
                raw = f.read()
            break
        except UnicodeDecodeError as e:
            last = e
        except OSError as e:
            _check(checks, "FAIL", "1 文件存在性", "读取失败: %s" % e)
            return _finish(rep)
    if raw is None:
        _check(checks, "FAIL", "1 文件存在性",
               "不是 UTF-8/带 BOM 的文本（utf-8-sig 解码失败: %s）" % last)
        return _finish(rep)
    if raw.strip() == "":
        _check(checks, "FAIL", "1 文件存在性", "文件为空（0 字节 / 全空白）")
        return _finish(rep)

    with open(src, encoding="utf-8-sig", newline="") as f:
        rd = csv.reader(f)
        try:
            table = [r for r in rd]
        except csv.Error as e:
            _check(checks, "FAIL", "1 文件存在性", "CSV 解析失败: %s" % e)
            return _finish(rep)
    table = [r for r in table if any(c.strip() != "" for c in r)]      # 丢空行
    if not table:
        _check(checks, "FAIL", "1 文件存在性", "文件里没有有效数据行")
        return _finish(rep)
    header = [c.strip().lstrip("\ufeff") for c in table[0]]
    body = table[1:]
    _check(checks, "OK", "1 文件存在性/解析/BOM",
           "%s（utf-8-sig 解码成功），表头 %d 列，数据 %d 行" % (src, len(header), len(body)))

    # ---------- 检查 2：列名 ----------
    # case_id 缺失不在这里判死：继续往下走，让行数/数值/几何/工期都拿到结论；
    # 相关状态由检查 4 给（WARN + "需由 build 脚本分配"）。
    # 7 维缺列则无法继续，直接退出。
    missing = [c for c in REQ_COLS if c not in header]
    miss_dims = [c for c in DIM_COLS if c not in header]
    extra = [c for c in header if c not in REQ_COLS]
    has_case_id = "case_id" in header
    if miss_dims:
        detail = "缺列: %s（7 维必需）" % ", ".join(miss_dims)
    elif not has_case_id:
        detail = "7 维齐全，但没有 case_id 列（需由 build 脚本按源表顺序分配）"
    else:
        detail = "必需列齐全（case_id + 7 维）"
    if extra:
        detail += "；多余列（仅提示，不影响判定）: %s" % ", ".join(extra)
    _check(checks, "FAIL" if miss_dims else ("OK" if has_case_id else "WARN"), "2 列名", detail)
    rep["has_case_id"] = has_case_id
    rep["missing_dims"] = miss_dims
    if miss_dims:
        return _finish(rep)

    idx = {c: header.index(c) for c in REQ_COLS if c in header}
    recs = []
    for r in body:
        rec = {c: (r[idx[c]] if idx[c] < len(r) else "") for c in DIM_COLS}
        # case_id 缺失时填 ''，后面的检查继续做（行数/数值/几何仍要给出结论）
        rec["case_id"] = (r[idx["case_id"]] if (has_case_id and idx["case_id"] < len(r)) else "")
        recs.append(rec)
    rep["records"] = recs

    # ---------- 检查 3：逐格 float() / NaN / Inf / 空 ----------
    # 注意：解析不过的行不进 vals（校验已 FAIL，build 会直接退出），
    # 所以 vals / geom 始终一一对应；case_id 用 (cid, vals) 二元组跟着走，避免错位。
    bad_cells = []
    vals = []
    for i, r in enumerate(recs, start=2):          # 行号从 2 起（1 是表头）
        v, ok = {}, True
        for c in DIM_COLS:
            x = parse_float(r[c])
            if x is None:
                ok = False
                if len(bad_cells) < 10:
                    why = "空值" if (r[c] or "").strip() == "" else "非数字(%r)" % r[c]
                    bad_cells.append("第 %d 行 列 %s: %s" % (i, c, why))
            v[c] = x
        if ok:
            vals.append((r["case_id"], v))
    if bad_cells:
        detail = "%d 个单元格无法转 float（最多列 10 条）: %s" % (len(bad_cells), " | ".join(bad_cells))
        _check(checks, "FAIL", "3 数值可解析性(NaN/Inf/空值)", detail)
    else:
        _check(checks, "OK", "3 数值可解析性(NaN/Inf/空值)",
               "全部 %d 行 x 7 维均可 float()，无 NaN/Inf/空值" % len(recs))
    rep["vals"] = vals

    # ---------- 检查 4：case_id 唯一/非空/前缀 ----------
    problems = []
    if has_case_id:
        ids = [(r["case_id"] or "").strip() for r in recs]
        empt = [i + 2 for i, x in enumerate(ids) if x == ""]
        dup = {}
        for x in ids:
            dup[x] = dup.get(x, 0) + 1
        dups = sorted([k for k, n in dup.items() if k != "" and n > 1])
        badpfx = sorted({x for x in ids if x and not x.startswith(batch + "_")})
        numeric = sorted({x for x in ids if x and re.fullmatch(r"\d+(\.\d+)?", x)})
        if empt:
            problems.append("空 case_id 共 %d 行（首个在源表第 %d 行）" % (len(empt), empt[0]))
        if dups:
            problems.append("case_id 重复 %d 个: %s" % (len(dups), ", ".join(dups[:10])))
        if badpfx:
            problems.append("前缀不是 %r 的 case_id %d 个: %s"
                            % (batch + "_", len(badpfx), ", ".join(badpfx[:10])))
        if numeric:
            problems.append("纯数字 case_id %d 个（如 %s）—— 需由 build 脚本分配 %s_NNNN"
                            % (len(numeric), ", ".join(numeric[:5]), batch))
        n_over = len(ids) - len(set(x for x in ids if x))
        if problems:
            _check(checks, "FAIL", "4 case_id 唯一性/前缀",
                   "；".join(problems) + "（唯一非空 %d/%d）" % (len(set(x for x in ids if x)), len(ids)))
        else:
            _check(checks, "OK", "4 case_id 唯一性/前缀",
                   "%d 个 case_id 全部唯一非空且以 %r 开头" % (len(ids), batch + "_"))
    else:
        _check(checks, "WARN", "4 case_id 唯一性/前缀",
               "源表没有 case_id 列 —— 需由 build 脚本按源表顺序分配 %s_0001 起"
               "（本项不算硬性失败，只是提示）" % batch)

    # ---------- 检查 5：行数 ----------
    n = len(recs)
    if n == rows:
        _check(checks, "OK", "5 行数", "实际 %d 行 == 期望 %d 行" % (n, rows))
    else:
        _check(checks, "FAIL", "5 行数", "实际 %d 行 != 期望 %d 行（差 %+d）" % (n, rows, n - rows))

    # ---------- 检查 6：7 维范围 ----------
    dom, why = parse_contract_domain()
    ref = None
    if dom is None:
        ref = b1_reference_domain()
        _check(checks, "WARN", "6 合法域读取",
               "从 wpt_contract.py 顶部注释读合法域失败（%s）；"
               "退回 b1 实测范围作**参考**，只给 WARN，不冒充硬性范围%s"
               % (why, "" if ref else "；b1 参考表也读不到"))
    else:
        _check(checks, "OK", "6 合法域读取", "已从 wpt_contract.py 顶部注释解析出 7 维合法域")
    if ref is not None:
        dom = ref                     # 参考域（WARN 口径）
        dom_is_hard = False
    else:
        dom_is_hard = (dom is not None)

    viol = []
    lines = []
    for c in DIM_COLS:
        arr = [v[c] for _cid, v in vals]
        if not arr:
            lines.append("  %-14s 无有效数据" % c)
            continue
        lo, hi = min(arr), max(arr)
        line = "  %-14s min %10.4f  max %10.4f  均值 %10.4f" % (
            c, lo, hi, statistics.fmean(arr))
        if dom and c in dom:
            dlo, dhi = dom[c]
            line += "  | 域 [%.4f, %.4f]%s" % (dlo, dhi, "" if dom_is_hard else " (参考)")
            out = [v for v in arr if not (dlo - RANGE_TOL <= v <= dhi + RANGE_TOL)]
            if out:
                viol.append((c, len(out), min(out), max(out)))
        lines.append(line)
    if viol:
        txt = "；".join("%s 越域 %d 个 (%.4f~%.4f)" % v for v in viol)
        _check(checks, "FAIL" if dom_is_hard else "WARN", "6 7 维范围",
               txt + "\n" + "\n".join(lines))
    else:
        _check(checks, "OK", "6 7 维范围",
               "全部落在域内" + ("" if dom_is_hard else "（参考域）") + "\n" + "\n".join(lines))

    # ---------- 检查 7：逐工况几何核查（X 盒 / Y 盒）----------
    geom = []
    K = CG.k_lc()
    for _cid, v in vals:
        LC, g = v["coil_size"], v["spacing_ratio"]
        S = LC * (2.0 + g)
        rx_half = LC * K / 2.0 + CG.WIDTH / 2.0
        ferrite_half = max(S / 2.0, LC / 2.0)
        need_x = max(S / 2.0 + rx_half, ferrite_half + 15.0 + 10.0)
        y_half = round(1.2 * LC) / 2.0
        gap = CG.path_dims(LC, v["hole_ratio"])["gap_min"]
        use_opt = bool(gap >= OPT_MIN_GAP)
        geom.append(dict(need_x=need_x, need_x_margin=need_x + MARGIN,
                         y_half=y_half, gap_min=gap, use_opt=use_opt,
                         sweep_span=S, t_case_min=(T_CASE_OPT if use_opt else T_CASE_BASE),
                         x_ok=bool(need_x + MARGIN <= box_x + 1e-6),
                         y_ok=bool(-y_half >= BOX_Y[0] - 1e-6 and y_half <= BOX_Y[1] + 1e-6)))
    rep["geom"] = geom
    worst = max(geom, key=lambda z: z["need_x_margin"]) if geom else None
    n_x_over = sum(1 for z in geom if not z["x_ok"])
    n_y_over = sum(1 for z in geom if not z["y_ok"])
    # 注意：X 盒里的物体是**接收线圈**（sweep 到端点时的外缘），need_x 就是它的最远触及
    n_pt_over = 0
    for _cid, v in vals:
        LC, g = v["coil_size"], v["spacing_ratio"]
        rx_half = LC * K / 2.0 + CG.WIDTH / 2.0
        for x in WC.sweep_positions_half(LC, g):
            if abs(x) + rx_half > box_x + 1e-6:
                n_pt_over += 1
    n_pt_total = len(vals) * N_HALF
    wi = max(range(len(geom)), key=lambda i: geom[i]["need_x_margin"]) if geom else -1
    wv = vals[wi][1] if wi >= 0 else {}
    if n_x_over or n_y_over:
        det = ("X 盒(±%.0f, 留边 %.0f) 越界 %d/%d 工况，半扫越界点位 %d/%d\n"
               "最坏工况: LC=%.4f hole_ratio=%.4f g=%.4f -> need_x+40 = %.3f mm（超盒 %.3f mm）\n"
               "Y 盒: %s（y_half 最大 %.2f vs 上限 %.2f，-y_half 最小 %.2f vs 下限 %.2f）"
               % (box_x, MARGIN, n_x_over, len(geom), n_pt_over, n_pt_total,
                  wv.get("coil_size", float("nan")), wv.get("hole_ratio", float("nan")),
                  wv.get("spacing_ratio", float("nan")),
                  worst["need_x_margin"], worst["need_x_margin"] - box_x,
                  "越界 %d 个工况" % n_y_over if n_y_over else "通过",
                  max(z["y_half"] for z in geom), BOX_Y[1],
                  min(z["y_half"] for z in geom), BOX_Y[0]))
        if n_y_over:
            # Y 越界是**物体真的出盒**，会让 ensure_region 直接失败 —— 不允许豁免
            _check(checks, "FAIL", "7 几何核查(X/Y 盒)", det)
        elif waive_box_margin:
            _check(checks, "WARN", "7 几何核查(X/Y 盒)",
                   det + "\n【已豁免】%s\n"
                         "（注意：豁免只针对「+%.0f mm 留边」这条自定准则；"
                         "上面显示的越界工况其**物体仍在盒内**，"
                         "ensure_region() 的硬判据不会触发。）" % (waive_box_margin, MARGIN))
            rep["stats"]["box_margin_waiver"] = waive_box_margin
            rep["stats"]["box_margin_waiver_cases"] = n_x_over
        else:
            _check(checks, "FAIL", "7 几何核查(X/Y 盒)",
                   det + "\n如已用 A/B 实测证明边界影响低于噪声，可用 "
                         "--waive-box-margin \"<理由与证据>\" 显式豁免（会记入 plan_meta）。")
    else:
        _check(checks, "OK", "7 几何核查(X/Y 盒)",
               "X 盒 ±%.0f（留边 %.0f）全部装下：%d 工况最远触及 need_x+40 = %.3f mm（余量 %.3f mm）；"
               "半扫 %d 点全部在内；Y 盒通过（y_half max %.2f ≤ %.2f，-y_half min ≥ %.2f）"
               % (box_x, MARGIN, len(geom), worst["need_x_margin"], box_x - worst["need_x_margin"],
                  n_pt_total, max(z["y_half"] for z in geom), BOX_Y[1], BOX_Y[0]))

    # ---------- 检查 8：gap_min 分布 / 闸门占比 / 工期 ----------
    gaps = sorted(z["gap_min"] for z in geom)
    n_opt = sum(1 for z in geom if z["use_opt"])
    n_base = len(geom) - n_opt
    tot_min = sum(z["t_case_min"] for z in geom)
    days8 = tot_min / 60.0 / HOURS_PER_DAY / N_INST
    days8_opt = N_HALF * 0 + len(geom) * T_CASE_OPT / 60.0 / HOURS_PER_DAY / N_INST
    # ⚠️ 工期预估值必须用 **b1 生产实测** 的单工况均值，**不能**用 4.78/13.61 那组先验常数：
    # 后者是单实例、旧几何、旧空气域（±205/±330）下测的；b1 的生产口径（独立双面铁氧体 +
    # 固定盒 ±420 + 8 实例争用）实测单点 8.22 min、单工况 172.4 min，是它的 **1.64 倍**。
    # 用先验常数会把 1920 组估成 ~21.7 天，而纯计算就要 ~28.7 天
    # （已用 b1 的 5370 点 raw 逐点重算核对：735 实例·小时 / 251 个完整工况）。
    # 先验常数仍保留，只用于**给工况排序**（相对成本），不用于工期。
    days8_meas = len(geom) * T_CASE_MEASURED / 60.0 / HOURS_PER_DAY / N_INST
    # ⚠️ 这里必须先把前面检查里写进 stats 的键取出来再整体赋值 —— 直接 `rep["stats"] = dict(...)`
    # 会把 box_margin_waiver 等**先前写入的键静默抹掉**（2026-10-12 实测踩到：豁免在检查 7 里
    # 明明报成 WARN，plan_meta 里却成了 null，因为被这一行覆盖了）。
    _wm = rep["stats"].get("box_margin_waiver")
    _wmc = rep["stats"].get("box_margin_waiver_cases")
    rep["stats"] = dict(
        n_cases=len(geom), n_opt=n_opt, n_base=n_base,
        gap_min_min=gaps[0] if gaps else None, gap_min_p05=_percentile(gaps, 5),
        gap_min_median=_percentile(gaps, 50), gap_min_max=gaps[-1] if gaps else None,
        gap_gate=OPT_MIN_GAP, t_case_opt=T_CASE_OPT, t_case_base=T_CASE_BASE,
        n_inst=N_INST, hours_per_day=HOURS_PER_DAY,
        total_case_min=tot_min, single_inst_hours=tot_min / 60.0,
        wall_days_8inst=days8, wall_days_8inst_all_opt=days8_opt,
        t_case_measured=T_CASE_MEASURED, wall_days_8inst_measured=days8_meas,
        n_x_over=n_x_over, n_y_over=n_y_over, n_points_out=n_pt_over,
        n_points_total=n_pt_total,
        worst_need_x_margin=worst["need_x_margin"] if worst else None,
        box_x=box_x, box_x_required=(worst["need_x_margin"] if worst else None),
        box_margin_waiver=_wm, box_margin_waiver_cases=_wmc,
        timing_source="工期按 b1 生产实测单工况均值 %.1f min 估算；另有先验常数口径（4.78/13.61 min/点）"
                      "仅供工况排序参考，不可用于工期（低估约 1.64 倍）" % T_CASE_MEASURED,
    )
    if gaps:
        _check(checks, "OK", "8 分布/闸门/工期",
               "gap_min min %.4f / p05 %.4f / 中位 %.4f / max %.4f mm；"
               "闸门 %.1f -> OPT %d (%.1f%%) / BASE %d (%.1f%%)；"
               "**工期 %.1f 天**（%d 实例 24h 滚动，按 b1 实测 %.1f min/工况）；"
               "先验常数口径仅供排序参考 = %.1f 天"
               % (gaps[0], _percentile(gaps, 5), _percentile(gaps, 50), gaps[-1],
                  OPT_MIN_GAP, n_opt, 100.0 * n_opt / len(geom), n_base,
                  100.0 * n_base / len(geom), days8_meas, N_INST, T_CASE_MEASURED,
                  days8))
    else:
        _check(checks, "FAIL", "8 分布/闸门/工期", "没有可用于统计的有效工况")

    # 冻结口径自检（PATH_MODE / 点数）
    # 注：--expect-path-mode 默认 ring（b2 生产口径）；只有做 b1 对照标定时才改成 legacy，
    # 且必须**同时**设环境变量 WPT_PATH_MODE=legacy（coil_gen 在 import 时就读它），
    # 否则这里会明确报 FAIL，避免"口径不一致却当成通过"。
    pm = getattr(CG, "PATH_MODE", "?")
    _check(checks, "OK" if pm == expect_path_mode else "FAIL", "9 冻结口径",
           "coil_gen.PATH_MODE=%s（要求 %s%s）；半扫点数 %d（镜像展开 %d）；k_lc=%.9f；WIDTH=%.1f"
           % (pm, expect_path_mode,
              "" if pm == expect_path_mode
              else "；想让 coil_gen 走别的口径必须在启动前设环境变量 WPT_PATH_MODE=legacy",
              len(WC.sweep_positions_half(150.0, 0.0)), N_FULL, K, CG.WIDTH))
    return _finish(rep)


def _finish(rep):
    rep["n_ok"] = sum(1 for c in rep["checks"] if c["status"] == "OK")
    rep["n_warn"] = sum(1 for c in rep["checks"] if c["status"] == "WARN")
    rep["n_fail"] = sum(1 for c in rep["checks"] if c["status"] == "FAIL")
    rep["passed"] = (rep["n_fail"] == 0)
    return rep


def print_report(rep):
    print("=" * 84)
    print("b2 参数表校验（只读）: %s" % rep["src"])
    print("批次 %s | 期望行数 %d | 空气域盒 X±%.0f (留边 %.0f) | PATH_MODE=%s (要求 %s) | 闸门 %.1f"
          % (rep["batch"], rep["rows"], rep["box_x"], MARGIN,
             getattr(CG, "PATH_MODE", "?"), PATH_MODE_REQUIRED, OPT_MIN_GAP))
    print("=" * 84)
    for c in rep["checks"]:
        print("[%s] %s" % (c["status"], c["title"]))
        for ln in str(c["detail"]).splitlines():
            print("      " + ln)
    st = rep["stats"]
    if st:
        print("-" * 84)
        print("汇总: OK %d / WARN %d / FAIL %d -> %s"
              % (rep["n_ok"], rep["n_warn"], rep["n_fail"],
                 "通过（退出码 0）" if rep["passed"] else "不通过（退出码 1）"))
        print("工期口径: %s" % st["timing_source"])
    else:
        print("-" * 84)
        print("汇总: OK %d / WARN %d / FAIL %d -> %s"
              % (rep["n_ok"], rep["n_warn"], rep["n_fail"],
                 "通过（退出码 0）" if rep["passed"] else "不通过（退出码 1）"))
    print("=" * 84)


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="b2（1920 工况）用户参数表只读校验器：列名/NaN/case_id/行数/7 维范围/几何盒/工期")
    ap.add_argument("--src", required=True, help="用户参数表 CSV")
    ap.add_argument("--rows", type=int, default=1920, help="期望行数（默认 1920）")
    ap.add_argument("--batch", default="b2", help="批次名（决定 case_id 前缀，默认 b2）")
    ap.add_argument("--boxx", type=float, default=BOX_X, help="空气域固定盒 X 半宽（默认 420）")
    ap.add_argument("--expect-path-mode", default=PATH_MODE_REQUIRED,
                    choices=["ring", "legacy"],
                    help="期望的线圈路径口径（默认 ring=冻结口径；仅 b1 对照标定时用 legacy）")
    ap.add_argument("--waive-box-margin", default=None, metavar="REASON",
                    help="显式豁免「+40mm 留边」不足（物体仍需在盒内）。"
                         "必须写明实测证据，例如 A/B 脚本的结果摘要。会记入 plan_meta 以便审计。")
    a = ap.parse_args(argv)

    rep = validate(a.src, rows=a.rows, batch=a.batch, box_x=a.boxx,
                   expect_path_mode=a.expect_path_mode,
                   waive_box_margin=a.waive_box_margin)
    print_report(rep)
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
