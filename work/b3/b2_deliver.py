# -*- coding: utf-8 -*-
r"""batch1 终版交付闸门 + 打包。

解决两个问题：

1. **口径不可执行**。任务要求「口径不可改」，但此前没有任何环节校验跑出来的数据
   真的用了规定口径 —— 只能靠人工比对文档。本脚本把口径变成机器校验：从各实例
   落盘的 JSON 与启动日志里提取实跑口径，逐项对照常量，任一项不符即闸门失败。

2. **未跑完也能出"终版"**。contract_merge.py 只是汇总已完成工况，不阻止把
   15/256 的结果当成终版发出去。本脚本给出明确的 ready / not-ready 判据与退出码。

用法：
  python b2_deliver.py                 # 刷新交付物 + 全面校验 + 出就绪报告
  python b2_deliver.py --no-refresh    # 只校验，不重跑 merge/accept
  python b2_deliver.py --allow-partial # 允许未跑完也判为「可交付（部分）」

退出码：0 = 可交付；1 = 未就绪；2 = 口径或完整性校验失败
"""
import argparse
import collections
import csv
import glob
import json
import os
import re
import subprocess
import sys
import time

# stdout 为管道时中文 Windows 默认 GBK，打印 ✓/✗ 会抛 UnicodeEncodeError。
# 计划任务等无人值守环境不会设 PYTHONIOENCODING，故在入口强制切 UTF-8。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = r"C:\anaconda\python.exe"

# ---- 任务规定的口径（不可改；改这里等于改契约） ----
EXPECT = {
    "path_mode": "ring",
    "box_x": 420.0,
    "box_y_max": 161.0,
    "box_y_min": -134.94,
    "box_z": (-45.0, 75.0),
    "stage_timeout": 1500.0,
    "solve_timeout": 2400.0,
    "opt_min_gap": 1.5,
    "mesh_values": {"OPT", "BASE"},
    "n_points": 21,
}
N_CASES = 0     # 由 main() 按参数表行数（或 --n-cases）赋值；第一轮曾是写死的 256

# worker 启动日志行：
# 契约采集 worker 启动：plan=… BOX=X±420 Y[-134.94,161] Z[-45,75] 超时=几何1500s/求解2400s …
RE_BOOT = re.compile(
    r"BOX=X±(?P<bx>[\d.]+)\s+Y\[(?P<ymin>-?[\d.]+),(?P<ymax>-?[\d.]+)\]\s+"
    r"Z\[(?P<zmin>-?[\d.]+),(?P<zmax>-?[\d.]+)\]\s+"
    r"超时=几何(?P<st>\d+)s/求解(?P<sv>\d+)s")


class Report:
    def __init__(self, logf=None):
        self.lines = []
        self.fails = []          # 致命：口径 / 完整性
        self.warns = []
        self.logf = logf

    def line(self, s=""):
        print(s)
        self.lines.append(s)

    def flush_log(self, rc):
        """把整份报告追加到日志文件。

        计划任务不捕获 stdout，没有这一步自动运行时就不留任何痕迹。
        追加写 + 每次带时间戳，便于事后回溯「哪一次运行开始产出终版」。
        """
        if not self.logf:
            return
        try:
            d = os.path.dirname(self.logf)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(self.logf, "a", encoding="utf-8") as f:
                f.write("=" * 78 + "\n")
                f.write("运行 %s   退出码 %d（%s）\n"
                        % (time.strftime("%Y-%m-%d %H:%M:%S"), rc,
                           {0: "可交付", 1: "未就绪", 2: "校验失败"}.get(rc, "?")))
                f.write("\n".join(self.lines) + "\n")
        except OSError as e:
            print("（交付日志写入失败 %r）" % (e,))

    def check(self, cond, msg, fatal=True):
        mark = "✓" if cond else ("✗" if fatal else "!")
        self.line("  %s %s" % (mark, msg))
        if not cond:
            (self.fails if fatal else self.warns).append(msg)
        return bool(cond)


def read_csv(p):
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=HERE)
    ap.add_argument("--batch", default="b2")
    ap.add_argument("--no-refresh", action="store_true",
                    help="不重跑 contract_merge.py / b2_accept.py")
    ap.add_argument("--allow-partial", action="store_true",
                    help="未跑完也判为可交付（部分交付）")
    ap.add_argument("--log", default=None,
                    help="把整份报告追加写入该文件（计划任务无人值守时留痕用）")
    ap.add_argument("--n", type=int, default=8,
                    help="实例数（校验实例状态文件数量；第一轮写死 8）")
    ap.add_argument("--n-cases", type=int, default=None,
                    help="本批工况总数（默认取参数表行数；第一轮写死 256）")
    args = ap.parse_args()
    ROOT, B = args.root, args.batch
    OUT = os.path.join(ROOT, "out")
    R = Report(args.log)
    global N_CASES

    # ---------- 0. 刷新交付物 ----------
    if not args.no_refresh:
        R.line("## 0 刷新交付物")
        for script, extra in (("contract_merge.py", ["--batch", B, "--root", ROOT]),
                              ("b2_partial_export.py", ["--root", ROOT, "--batch", B]),
                              ("b2_accept.py", ["--root", ROOT, "--batch", B])):
            p = subprocess.run([PY, os.path.join(ROOT, script)] + extra,
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
            ok = p.returncode == 0
            R.check(ok, "%s 执行%s" % (script, "" if ok else "（rc=%d）" % p.returncode))
            if not ok:
                R.line("    " + (p.stderr or p.stdout or "")[-400:])
        R.line()

    plan = read_csv(os.path.join(ROOT, "%s_plan.csv" % B))
    raws = {os.path.basename(p): read_csv(p)
            for p in sorted(glob.glob(os.path.join(ROOT, "%s_raw_run*.csv" % B)))}
    # ⚠️ 2026-10-12：工况总数不能再写死（第一轮是 256）。b2 为 1920，
    # 写死会让 §1 的口径校验与 §5 的就绪判据全部失效。
    N_CASES = args.n_cases if args.n_cases else len(plan)

    # ---------- 1. 口径合规 ----------
    R.line("## 1 口径合规校验（任务规定，不可改）")
    R.check(len(plan) == N_CASES, "参数表 %d 个工况（期望 %d）" % (len(plan), N_CASES))

    jsons = sorted(glob.glob(os.path.join(ROOT, "%s_worker_run*.json" % B)))
    R.check(len(jsons) == args.n, "找到 %d 份实例状态文件（实际 %d）" % (args.n, len(jsons)))
    bad_mode = bad_box = bad_to = 0
    for p in jsons:
        # ⚠️ 2026-10-12：坏 JSON 不能让闸门直接 traceback（第一轮实测 worker 被强杀后
        # 会留下半截/被覆盖的 JSON）。解析失败 → 只报 WARN 并跳过该文件的口径字段。
        try:
            j = json.load(open(p, encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            R.line("    ! %s 解析失败（%r）—— 跳过其口径字段（raw 才是权威真值）"
                   % (os.path.basename(p), e))
            continue
        if j.get("path_mode") != EXPECT["path_mode"]:
            bad_mode += 1
            R.line("    ✗ %s path_mode=%r" % (os.path.basename(p), j.get("path_mode")))
        b = j.get("box") or {}
        if b.get("x") != EXPECT["box_x"] or b.get("y") != EXPECT["box_y_max"]:
            bad_box += 1
            R.line("    ✗ %s box=%r" % (os.path.basename(p), b))
        t = j.get("timeouts") or {}
        if t.get("stage") != EXPECT["stage_timeout"] or t.get("solve") != EXPECT["solve_timeout"]:
            bad_to += 1
            R.line("    ✗ %s timeouts=%r" % (os.path.basename(p), t))
    R.check(bad_mode == 0, "几何口径 PATH_MODE=%s（%d/8 实例不符）"
            % (EXPECT["path_mode"], bad_mode))
    R.check(bad_box == 0, "空气域盒 X±%.0f / Ymax %.0f（%d/8 不符）"
            % (EXPECT["box_x"], EXPECT["box_y_max"], bad_box))
    R.check(bad_to == 0, "超时 几何%.0fs / 求解%.0fs（%d/8 不符）"
            % (EXPECT["stage_timeout"], EXPECT["solve_timeout"], bad_to))

    # 启动日志里的完整盒（含 Ymin / Z）——JSON 里没记这两项
    boot_ok = boot_n = 0
    for p in sorted(glob.glob(os.path.join(ROOT, "%s_worker_run*.log" % B))):
        head = open(p, encoding="utf-8", errors="replace").read(4000)
        m = RE_BOOT.search(head)
        if not m:
            continue
        boot_n += 1
        g = m.groupdict()
        if (float(g["bx"]) == EXPECT["box_x"] and float(g["ymin"]) == EXPECT["box_y_min"]
                and float(g["ymax"]) == EXPECT["box_y_max"]
                and (float(g["zmin"]), float(g["zmax"])) == EXPECT["box_z"]
                and float(g["st"]) == EXPECT["stage_timeout"]
                and float(g["sv"]) == EXPECT["solve_timeout"]):
            boot_ok += 1
        else:
            R.line("    ✗ %s 启动口径: %s" % (os.path.basename(p), g))
    R.check(boot_n > 0 and boot_ok == boot_n,
            "启动日志完整盒 X±%.0f Y[%.2f,%.0f] Z[%.0f,%.0f]（%d/%d 相符）"
            % (EXPECT["box_x"], EXPECT["box_y_min"], EXPECT["box_y_max"],
               EXPECT["box_z"][0], EXPECT["box_z"][1], boot_ok, boot_n))

    # 逐点 mesh 口径
    mesh_of = collections.Counter()
    illegal = []
    dup = []
    seen = set()
    per_case = collections.defaultdict(set)
    for name, rows in raws.items():
        for r in rows:
            mv = (r.get("mesh") or "").strip()
            mesh_of[mv] += 1
            if mv not in EXPECT["mesh_values"]:
                illegal.append((name, r.get("case_id"), r.get("i"), mv))
            key = (r.get("case_id"), r.get("i"))
            if key in seen:
                dup.append(key)
            seen.add(key)
            per_case[r.get("case_id")].add(int(r["i"]) if r.get("i") else -1)
    R.check(not illegal, "所有原始点的 mesh 口径合法（非法 %d 处）" % len(illegal))
    if illegal:
        for x in illegal[:5]:
            R.line("    ✗ %s" % (x,))
    R.check(not dup, "无重复 (case_id, i)（重复 %d 处）" % len(dup))
    bad_i = [c for c, s in per_case.items() if any(i < 0 or i >= EXPECT["n_points"] for i in s)]
    R.check(not bad_i, "点位索引均落在 0..%d（越界工况 %d 个）"
            % (EXPECT["n_points"] - 1, len(bad_i)))
    R.line("    mesh 分布：%s（合计 %d 点）"
           % (", ".join("%s=%d" % (k, v) for k, v in sorted(mesh_of.items())), sum(mesh_of.values())))
    R.line("    OPT_MIN_GAP 闸门 = %.1f mm（worker 常量，见 b1_worker_*.log 的「阈值」字段）"
           % EXPECT["opt_min_gap"])
    R.line()

    # ---------- 缺口例外表 ----------
    # 经人工确认在规定口径（OPT 与 BASE）下确定性不可解、接受缺口的工况。
    # **只有列在这里的 final-partial 才不阻塞交付**；未列出的 partial 仍然是致命项 ——
    # 这样「已知且已接受的缺口」与「新出现的缺口」不会混为一谈，
    # 不会因为存在例外就放行任何新问题。
    exc_path = os.path.join(ROOT, "%s_partial_exceptions.json" % B)
    exceptions = {}
    if os.path.exists(exc_path):
        try:
            # ⚠️ 必须 utf-8-sig：PowerShell 的 `Set-Content -Encoding utf8`（PS 5.1）与
            # 记事本另存都会写 BOM，而 json.load(utf-8) 遇 BOM 直接抛 JSONDecodeError。
            # 2026-10-12 实测：BOM 会让这里判 FATAL，**把一份完全正常的交付挡住**
            # （而数据其实没问题），且报错信息与"缺口未登记"混在一起，极易误判。
            with open(exc_path, encoding="utf-8-sig") as f:
                exceptions = (json.load(f) or {}).get("cases") or {}
        except Exception as e:
            R.check(False, "缺口例外表解析失败：%r" % (e,))
    else:
        R.line("    （无缺口例外表 %s —— 任何缺点工况都会阻塞交付）"
               % os.path.basename(exc_path))

    # worker 的 final-partial 才是「跑完但仍缺点」。仅按点数 <21 判断会把**正在求解中**
    # 的工况也计成缺口，mid-batch 时产生大量误报，所以以 worker 落盘的状态为准。
    final_partial = {}
    for p in jsons:
        try:
            jj = json.load(open(p, encoding="utf-8-sig"))
        except Exception:
            continue
        for c in jj.get("cases", []):
            if isinstance(c, dict) and c.get("status") == "partial":
                final_partial[c["case_id"]] = sorted(c.get("fail") or [])

    # ---------- 2. 完整性 ----------
    R.line("## 2 完整性")
    plan_ids = [r["case_id"] for r in plan]
    plan_set = set(plan_ids)

    # 分片覆盖：参数表有 256 行不等于 256 个工况都会被求解 —— 真正决定跑哪些工况的是
    # 8 个分片文件。若某工况没进任何分片，它永远不会被求解，而批次照样会"跑完"，
    # 交付就会**静默缺 case**。这类缺口只靠参数表检查发现不了。
    shards = sorted(glob.glob(os.path.join(ROOT, "%s_plan_shard*.csv" % B)))
    cov = collections.Counter()
    for p in shards:
        for r in read_csv(p):
            cov[r.get("case_id")] += 1
    miss = [c for c in plan_ids if cov[c] == 0]
    dupc = [c for c in plan_ids if cov[c] > 1]
    stray_c = [c for c in cov if c not in plan_set]
    R.check(bool(shards) and not miss,
            "分片覆盖全部工况（%d 个分片，合计 %d 行，未分配 %d 个）"
            % (len(shards), sum(cov.values()), len(miss)))
    if miss:
        R.line("    ✗ 未分配工况：%s" % miss[:10])
    R.check(not dupc, "无工况被重复分配（重复 %d 个）" % len(dupc))
    R.check(not stray_c, "分片内无越界工况（越界 %d 个）" % len(stray_c))

    stray = sorted(set(per_case) - plan_set)
    R.check(not stray, "所有结果工况都在参数表内（越界 %d 个）" % len(stray))
    if stray:
        R.line("    ✗ %s" % stray[:10])

    n_pt = EXPECT["n_points"]
    complete = [c for c in plan_ids if len(per_case.get(c, ())) >= n_pt]
    partial = [(c, len(per_case.get(c, ()))) for c in plan_ids
               if 0 < len(per_case.get(c, ())) < n_pt]
    notstarted = [c for c in plan_ids if not per_case.get(c)]
    R.line("    完整 %d / %d；半截 %d；未开始 %d"
           % (len(complete), N_CASES, len(partial), len(notstarted)))
    if partial:
        R.line("    半截工况：%s" % ", ".join("%s(%d/%d)" % (c, n, n_pt) for c, n in partial[:12]))
    done_pts = sum(len(per_case.get(c, ())) for c in plan_ids)
    R.line("    点位 %d / %d (%.1f%%)" % (done_pts, N_CASES * n_pt,
                                        100.0 * done_pts / (N_CASES * n_pt)))

    known = {c: f for c, f in final_partial.items() if c in exceptions}
    unknown = {c: f for c, f in final_partial.items() if c not in exceptions}
    miss_pts = sum(len(f) for f in final_partial.values())
    R.line("    跑完但仍缺点（worker final-partial）：%d 个工况，%d 个点"
           % (len(final_partial), miss_pts))
    # ⚠️ 2026-10-12：这些明细必须**截断**。本脚本每 30 min 跑一次、整批 28 天 ≈ 1340 次，
    # 1920 组规模下"缺点工况"可能有数百个 → 每次打印数百行会让 deliver 日志涨到 GB 级。
    CAP = 20

    def _brief(d):
        items = sorted(d.items())
        s = ", ".join("%s 缺 i=%s" % (c, f) for c, f in items[:CAP])
        if len(items) > CAP:
            s += " …（共 %d 个，其余见 manifest/exceptions）" % len(items)
        return s

    if known:
        R.line("      已登记缺口：%s" % _brief(known))
    R.check(not unknown,
            "无未登记的缺口（未登记 %d 个%s）"
            % (len(unknown), ("：" + _brief(unknown)) if unknown else ""))
    R.line()

    # ---------- 3. 交付物一致性 ----------
    R.line("## 3 交付物与真值来源一致")
    cases = read_csv(os.path.join(OUT, "%s_cases.csv" % B))
    curves = read_csv(os.path.join(OUT, "%s_curves.csv" % B))
    diag = read_csv(os.path.join(OUT, "%s_diag.csv" % B))
    for nm, rows, want in (("cases", cases, len(complete)),
                           ("diag", diag, len(complete))):
        R.check(len(rows) == want, "%s.csv 行数 %d == 完整工况数 %d" % (nm, len(rows), want))
    n_curve = sum(1 for r in curves if r.get("position_x") not in ("", None))
    R.check(len(curves) >= len(complete) * (n_pt * 2 - 1),
            "curves.csv %d 行 ≥ 完整工况 × %d 点（镜像展开）" % (len(curves), n_pt * 2 - 1))
    R.check(len({r["case_id"] for r in cases}) == len(cases), "cases.csv 无重复工况")
    R.line()

    # ---------- 4. 分层组成（供误差预算） ----------
    R.line("## 4 网格口径分层组成（交付说明需按层给误差预算）")
    gate = collections.Counter(r.get("mesh_gate", "?") for r in diag)
    lay = collections.Counter(r.get("mesh", "?") for r in diag)
    mixed = sum(1 for r in diag if r.get("mesh_mixed") == "True")
    R.line("    diag.mesh_gate（整套口径）：%s"
           % ", ".join("%s=%d" % kv for kv in sorted(gate.items())))
    R.line("    diag.mesh（逐点汇总）：%s"
           % ", ".join("%s=%d" % kv for kv in sorted(lay.items())))
    R.line("    混合工况（同时含 OPT 与 BASE 点）：%d / %d" % (mixed, len(diag)))
    R.line("    全批 BASE 口径点占比：%.2f%%"
           % (100.0 * mesh_of.get("BASE", 0) / max(sum(mesh_of.values()), 1)))
    R.line()

    # ---------- 5. 判据 ----------
    # 就绪 = 无致命问题 且 每个工况要么完整、要么是**已登记并接受缺口**的工况。
    accounted = [c for c in plan_ids if c in complete or c in exceptions]
    ready = (not R.fails) and len(accounted) == N_CASES
    R.line("## 5 就绪判据")
    R.check(not R.fails, "无口径 / 完整性致命问题", fatal=False)
    if ready:
        if len(complete) == N_CASES:
            R.line("  ✓ %d/%d 工况全部完成 → **可出终版**" % (len(complete), N_CASES))
        else:
            R.line("  ✓ %d/%d 完整 + %d 个已登记缺口工况 = %d/%d 全部有交代 → **可出终版（带缺口）**"
                   % (len(complete), N_CASES, N_CASES - len(complete),
                      len(accounted), N_CASES))
            R.line("    缺口明细：%s"
                   % ", ".join("%s 缺 i=%s（%d 点）"
                               % (c, exceptions[c].get("missing_points"), len(final_partial.get(c, [])))
                               for c in sorted(exceptions) if c in final_partial))
            R.line("    **交付说明必须显式声明这些缺口**，不得按 256 个完整工况对外表述。")
    else:
        R.line("  ! %d/%d 工况完成，尚缺 %d 个 → **未就绪**"
               % (len(complete), N_CASES, N_CASES - len(complete)))
        R.line("    完成全部工况后再跑本脚本；若个别工况长期 partial，")
        R.line("    先确认是否属于规定口径下不可解 —— 是则登记进 %s，"
               % os.path.basename(exc_path))
        R.line("    否则跑 `b1_guard.py --restart` 让 worker 用 BASE 口径补齐缺点。")
    R.line()

    # ---------- 6. 清单 ----------
    # ⚠️ 2026-09-26 修正：known / miss_pts 原来都从 worker JSON 派生的 final_partial 算。
    # 但**整批重启会把 JSON 里 status="partial" 的记录重写清除**（实测：批次跑完后
    # final_partial 变成 0 个，而 raw 里仍实缺 6 个点），于是清单报出
    # `gaps_registered: []` / `points_missing: 0` —— 与本 policy 要求的「必须显式声明缺口」
    # 直接矛盾，会把带缺口交付伪装成 256 个完整工况。
    # 修正：以 **raw 反推的实际缺失点** 为权威（raw 是逐点落盘的、跨重启不会丢），
    # 只在取不到时退回 final_partial。已登记缺口按 exception 表 ∩ 参数表 计算。
    try:
        _have = collections.defaultdict(set)
        # ⚠️ raws 是 {文件名: 已解析行列表} 的**字典**（见上面 L143），不是路径列表。
        #    误当路径传给 read_csv() 会抛异常（被本 try 吞掉）→ _have 为空 →
        #    每个工况都被算成缺 21 点、points_missing=5376（2026-09-26 实测踩过）。
        for _rows in raws.values():
            for _r in _rows:
                try:
                    _have[_r.get("case_id")].add(int(_r.get("i")))
                except (TypeError, ValueError):
                    continue
        gap_truth = {}
        for _c in plan_ids:
            _miss = sorted(set(range(n_pt)) - _have.get(_c, set()))
            if _miss:
                gap_truth[_c] = _miss
        miss_pts = sum(len(v) for v in gap_truth.values())
        known = {c: gap_truth.get(c, []) for c in exceptions if c in plan_set}
    except Exception as e:
        R.line("    （缺口真值重建失败，退回 worker JSON 口径：%r）" % (e,))

    manifest = {
        "batch": B,
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "cases_complete": len(complete), "cases_total": N_CASES,
        "points_done": done_pts, "points_total": N_CASES * n_pt,
        # 缺口必须进清单：终版对外表述的依据，不能只写在报告正文里
        "cases_final_partial": {c: f for c, f in sorted(final_partial.items())},
        "gaps_registered": sorted(known),
        "gaps_registered_detail": {c: list(f) for c, f in sorted(known.items())},
        "gaps_unregistered": {c: f for c, f in sorted(unknown.items())},
        "points_missing": miss_pts,
        "missing_fraction_pct": round(100.0 * miss_pts / max(N_CASES * n_pt, 1), 4),
        "partial_cases_incomplete": {c: (n_pt - len(_have.get(c, set())))
                                     for c in plan_ids if len(_have.get(c, set())) < n_pt},
        "mesh_points": dict(mesh_of),
        "mesh_gate": dict(gate),
        "mixed_cases": mixed,
        "caliber": {k: (list(v) if isinstance(v, tuple) else
                        (sorted(v) if isinstance(v, set) else v))
                    for k, v in EXPECT.items()},
        "fatal_issues": R.fails,
        "ready": ready,
    }
    mf = os.path.join(OUT, "%s_manifest.json" % B)
    os.makedirs(OUT, exist_ok=True)
    with open(mf, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    R.line("清单 -> %s" % mf)

    rc = 2 if R.fails else (0 if (ready or args.allow_partial) else 1)
    R.line("退出码 %d（%s）" % (rc, {0: "可交付", 1: "未就绪", 2: "校验失败"}[rc]))
    R.flush_log(rc)
    return rc


if __name__ == "__main__":
    sys.exit(main())
