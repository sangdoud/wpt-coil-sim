# -*- coding: utf-8 -*-
r"""batch1 进度巡检：从逐点原始结果汇总进度与实测 ETA（不启动 AEDT）。

用法： python b1_status.py [--root ...] [--plan ...]
"""
import argparse
import collections
import csv
import glob
import json
import os
import sys
import time

# stdout 为管道时中文 Windows 默认 GBK，中文报告在无人值守环境会乱码。
# 计划任务不会设 PYTHONIOENCODING，故在入口强制切 UTF-8（与其他脚本一致）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"C:\ansys maxwell2024\_work\b2")
    ap.add_argument("--batch", default="b2")
    ap.add_argument("--n", type=int, default=8, help="实例数（ETA 外推用；第一轮写死 8）")
    args = ap.parse_args()
    ROOT, B = args.root, args.batch
    plan = list(csv.DictReader(open(os.path.join(ROOT, "%s_plan.csv" % B), encoding="utf-8-sig")))
    want = {r["case_id"]: 21 for r in plan}
    total_pts = sum(want.values())

    raws = sorted(glob.glob(os.path.join(ROOT, "%s_raw_run*.csv" % B)))
    by_case = collections.defaultdict(set)
    per_run = collections.Counter()
    mins = []
    sessions = collections.Counter()
    for p in raws:
        run = os.path.basename(p).split("run")[-1].split(".")[0]
        with open(p, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                try:
                    i = int(r["i"])
                except (KeyError, ValueError):
                    continue
                by_case[r["case_id"]].add(i)
                per_run[run] += 1
                sessions[r.get("aedt_pid", "?")] += 1
                try:
                    mins.append(float(r["minutes"]))
                except (KeyError, ValueError):
                    pass

    done_pts = sum(len(v) for v in by_case.values())
    complete = [c for c, v in by_case.items() if len(v) >= 21]
    partial = {c: len(v) for c, v in by_case.items() if 0 < len(v) < 21}
    print("=" * 74)
    print("%s 进度  %s" % (B, time.strftime("%Y-%m-%d %H:%M:%S")))
    print("  工况: %d/%d 完成；点位: %d/%d (%.1f%%)"
          % (len(complete), len(plan), done_pts, total_pts, 100.0 * done_pts / total_pts))
    if partial:
        print("  半截工况 %d 个: %s" % (len(partial), sorted(partial.items())[:8]))
    if per_run:
        print("  各实例已解点数: %s" % dict(sorted(per_run.items(), key=lambda z: int(z[0]))))
    print("  AEDT 会话数: %d（会话切换会带来 ~1%% 网格差异，已按 aedt_pid 记录）" % len(sessions))
    if mins:
        m = sorted(mins)
        mean = sum(m) / len(m)
        print("  单点求解: 均值 %.2f min 中位 %.2f  p10 %.2f  p90 %.2f  (n=%d)"
              % (mean, m[len(m) // 2], m[int(0.1 * len(m))], m[int(0.9 * len(m)) - 1], len(m)))
        left = total_pts - done_pts
        print("  按已跑均值外推: 剩余 %.1f 机时 -> %d 实例墙钟 ≈ %.1f 小时 (%.1f 天)"
              % (left * mean / 60.0, args.n, left * mean / 60.0 / args.n,
                 left * mean / 60.0 / args.n / 24.0))
    # BASE 回退工况的进度（单点 ~13.6 min，是尾巴的主要来源）
    try:
        # ⚠️ 2026-10-12：原来写死 C:\ansys maxwell2024\_work\batch1_audit.csv，
        # 换批次后 b2 的 case_id 不在表里 → KeyError 被下面 except 吞掉 →
        # BASE 统计**静默消失**（看起来"没有 BASE 工况"，实际是读错了表）。
        audit = {r["case_id"]: r for r in csv.DictReader(
            open(os.path.join(ROOT, "%s_audit.csv" % B), encoding="utf-8"))}
        base = [c for c in plan if audit[c["case_id"]]["use_opt"] == "False"]
        bdone = [c["case_id"] for c in base if len(by_case.get(c["case_id"], ())) >= 21]
        print("  BASE 回退工况（慢 2.8×）: %d/%d 完成" % (len(bdone), len(base)))
    except Exception as e:
        print("  (BASE 统计跳过: %s)" % e)
    jsons = sorted(glob.glob(os.path.join(ROOT, "%s_worker_run*.json" % B)))
    bad = []
    for p in jsons:
        try:
            dd = json.load(open(p, encoding="utf-8-sig"))
        except Exception:
            continue
        if dd.get("fatal"):
            bad.append((os.path.basename(p), "FATAL"))
        for c in dd.get("cases", []):
            if c.get("status") in ("geom_failed", "partial"):
                bad.append((c["case_id"], c.get("status"), c.get("fail")))
    if bad:
        print("  !! 异常工况: %s" % bad[:10])

    # ---------- 失速检测（无人值守用）----------
    # 单点 OPT ~7 min / BASE ~20 min；几何 ~7-10 min。阈值取 90 min（与 b1_guard 一致、
    # 也与交接文档第 6 节的判据一致）；45 min 会在几何重建+网格+启动补偿时误报。
    now = time.time()
    print("-" * 74)
    print("  失速检测（阈值 90 min）:")
    stall = []
    for p in raws:
        run = os.path.basename(p).split("run")[-1].split(".")[0]
        # 与 b1_guard 同口径：取「raw 落盘」与「worker 日志写入」中较新者作为活跃度。
        # 只看 raw 会误报 —— 启动补偿期间合法地不写 raw，且几何+网格本身常超过 45 min。
        a_raw = now - os.path.getmtime(p)
        lg = os.path.join(ROOT, "%s_worker_run%s.log" % (B, run))
        a_log = (now - os.path.getmtime(lg)) if os.path.exists(lg) else a_raw
        age = min(a_raw, a_log) / 60.0
        flag = "OK " if age < 90 else "!! 疑似卡住"
        if age >= 90:
            stall.append(run)
        print("    run%-2s 最近活动 %6.1f 分钟前（%d 点） %s" % (run, age, per_run[run], flag))
    try:
        import subprocess as _sp

        def _count(cmd):
            return _sp.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True).stdout.strip()

        n = _count("(Get-Process -Name ansysedt -ErrorAction SilentlyContinue | "
                   "Measure-Object).Count")
        nw = _count("(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                    "Where-Object { $_.CommandLine -match 'contract_worker' } | "
                    "Measure-Object).Count")
        print("    AEDT 进程数: %s（期望 8）；worker 进程数: %s（期望 8）" % (n, nw))
        # ⚠️ 2026-10-12：7/8 个 AEDT 是**常见且正常**的——某个实例正在走
        # 「失败 → 重开会话 → 重试」那条路径（重开期间它会删掉自己的 .lock）。
        # 第一轮文档早就写明「AEDT 进程 7/8 = 某实例正在重启会话，属正常，勿动」，
        # 但本脚本原来一律报「worker 可能已退出」→ 吓人且误导。
        # 判据改为：只要 **worker 数还是 8**，缺 AEDT 就只是正在换会话。
        if nw.isdigit() and int(nw) >= 8:
            if n.isdigit() and int(n) < 8:
                print("    （AEDT %s/8：某实例正在重开会话，属正常流程；worker 8/8 都在）" % n)
        elif nw.isdigit() and int(nw) < 8:
            print("    !! worker 只剩 %s/8 —— 有实例真的退出了，查 b2_worker_run<K>.log" % nw)
        if n.isdigit() and int(n) < 8 and (not nw.isdigit() or int(nw) < 8):
            print("    !! AEDT 实例不足且 worker 也不足，优先排查")
    except Exception as e:
        print("    （进程查询失败: %r）" % e)
    if stall:
        print("    !! 失速实例: %s —— 查 b2_worker_run<K>.log 与 b2_stdout_<K>.txt" % stall)
    print("=" * 74)


if __name__ == "__main__":
    main()
