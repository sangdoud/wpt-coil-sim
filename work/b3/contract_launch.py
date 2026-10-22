# -*- coding: utf-8 -*-
r"""契约口径采集启动器：N 实例并行（按**工况**分片，与生产 ④ 同策略）。

做四件事：
  1) 分片：b1_plan.csv 按行号交错切成 b1_plan_shardK.csv（整工况给一个实例）
  2) 副本：基础工程 -> Projecttonight_b1_runK.aedt，并**删除副本自己的 .aedtresults
     （继承源工程的已解状态会复用旧网格 -> 解得快但结果对不上，2026-09-18 实测踩过）
  3) 起 N 个 contract_worker.py（WPT_RUN=K），错峰 20 秒
  4) 结束后可选 --merge 生成契约 CSV

用法：
  python contract_launch.py 8                 # 8 实例
  python contract_launch.py 8 --merge         # 跑完并生成契约 CSV
  python contract_launch.py 8 --boxx 420      # 指定固定盒 X 半宽
环境变量 WPT_PY 可指定 python 解释器（默认 C:\anaconda\python.exe）。
"""
import argparse
import csv
import os
import shutil
import subprocess
import sys
import time

# stdout 被管道/文件捕获时中文 Windows 默认 GBK：中文日志会抛 UnicodeEncodeError 并以
# 退出码 1 结束，或（更坏）以 GBK 字节落进 UTF-8 日志文件造成混编乱码
# —— 第一轮的 b1_guard_launch.log 就是这个症状。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.environ.get("WPT_PY", r"C:\anaconda\python.exe")
DEFAULT_BASE = r"C:\ansys maxwell2024\_work\Projecttonight_ref.aedt"


def log(path, m):
    s = "%s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), m)
    print(s, flush=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def shard(plan, root, batch, n, logf):
    with open(plan, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    head, body = rows[0], rows[1:]
    counts = []
    for k in range(n):
        part = [r for i, r in enumerate(body) if i % n == k]
        p = os.path.join(root, "%s_plan_shard%d.csv" % (batch, k))
        with open(p, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(head)
            w.writerows(part)
        counts.append(len(part))
        log(logf, "  分片 %d: %d 个工况" % (k, len(part)))
    return counts


def prep(base, root, batch, k, logf):
    dst = os.path.join(root, "Projecttonight_%s_run%d.aedt" % (batch, k))
    if os.path.exists(dst):
        os.remove(dst)
    shutil.copy2(base, dst)
    for p in (dst + ".lock",):
        if os.path.exists(p):
            os.remove(p)
    rd = os.path.join(root, "Projecttonight_%s_run%d.aedtresults" % (batch, k))
    if os.path.isdir(rd):
        shutil.rmtree(rd, ignore_errors=True)
    log(logf, "  副本 %d 就绪: %s (%.1f MB, 已清结果目录)"
        % (k, os.path.basename(dst), os.path.getsize(dst) / 1048576.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("n", type=int, help="实例数")
    ap.add_argument("--batch", default="b2")
    ap.add_argument("--root", default=HERE)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--base", default=DEFAULT_BASE)
    ap.add_argument("--boxx", default="420")
    ap.add_argument("--boxy", default="161")
    ap.add_argument("--merge", action="store_true")
    ap.add_argument("--stagger", type=int, default=20)
    args = ap.parse_args()
    B, ROOT = args.batch, args.root
    plan = args.plan or os.path.join(ROOT, "%s_plan.csv" % B)
    logf = os.path.join(ROOT, "%s_launch.log" % B)
    os.makedirs(ROOT, exist_ok=True)

    log(logf, "=" * 74)
    log(logf, "契约采集启动：%d 实例，plan=%s，base=%s，BOX=X±%s Y≤%s"
        % (args.n, os.path.basename(plan), os.path.basename(args.base), args.boxx, args.boxy))
    if not os.path.exists(plan):
        raise SystemExit("找不到参数表: %s" % plan)
    if not os.path.exists(args.base):
        raise SystemExit("找不到基础工程: %s" % args.base)
    counts = shard(plan, ROOT, B, args.n, logf)
    for k in range(args.n):
        prep(args.base, ROOT, B, k, logf)

    env0 = dict(os.environ)
    # ⚠️ 2026-10-12：口径相关的环境变量必须**显式写死**，不能靠默认值兜。
    # 实测风险：PATH_MODE 取自环境变量（coil_gen.py 顶部），若机器上残留
    # WPT_PATH_MODE=legacy，整批几何会**静默**退回未修正的拐角重映射
    # （第一轮实测 214/256 工况受影响、电感偏 0.7~1.5%），事后只有交付闸门能抓到。
    env0.update({"PYTHONIOENCODING": "utf-8", "WPT_BATCH": B, "WPT_ROOT": ROOT,
                 "WPT_BOXX": str(args.boxx), "WPT_BOXY": str(args.boxy),
                 "WPT_PATH_MODE": "ring", "WPT_CLEAN": "point", "WPT_MESH_FALLBACK": "1"})
    # AEDT 会话模式：0=GUI（需要交互桌面）1=无界面（会话无关）。
    # ⚠️ 2026-10-13 实测：GUI 模式在计划任务（S4U/会话 0）里**起不来 AEDT**
    # （失败 148.9 s；无界面 7.0 s 成功）→ guard 的自动重启必须用无界面。
    # 这里显式落进 env0 并记进启动日志，便于事后审计。
    _nongui = os.environ.get("WPT_NON_GRAPHICAL", "0")
    env0["WPT_NON_GRAPHICAL"] = _nongui
    log(logf, "  AEDT 会话模式：%s"
        % ("无界面 non_graphical=True（可在会话 0 启动）" if _nongui == "1"
           else "GUI non_graphical=False（需要交互桌面；计划任务里起不来）"))
    env0.pop("WPT_XS", None)
    env0.pop("WPT_CASES", None)
    procs = []
    t0 = time.time()
    for k in range(args.n):
        e = dict(env0)
        e["WPT_RUN"] = str(k)
        e["WPT_PLAN"] = os.path.join(ROOT, "%s_plan_shard%d.csv" % (B, k))
        p = subprocess.Popen([PY, os.path.join(HERE, "contract_worker.py")],
                             env=e, cwd=ROOT,
                             stdout=open(os.path.join(ROOT, "%s_stdout_%d.txt" % (B, k)), "w"),
                             stderr=subprocess.STDOUT)
        procs.append(p)
        log(logf, "  启动实例 %d (pid=%d, %d 个工况)" % (k, p.pid, counts[k]))
        time.sleep(args.stagger)
    log(logf, "  %d 个实例已起，等待结束（Ctrl-C 不会杀子进程；结果已逐点落盘，重跑即续算）"
        % args.n)
    for k, p in enumerate(procs):
        p.wait()
        log(logf, "  实例 %d 退出码 %s" % (k, p.returncode))
    log(logf, "  全部结束，墙钟 %.1f 分钟" % ((time.time() - t0) / 60.0))
    if args.merge:
        subprocess.run([PY, os.path.join(HERE, "contract_merge.py"),
                        "--batch", B, "--root", ROOT], cwd=HERE)


if __name__ == "__main__":
    main()
