# -*- coding: utf-8 -*-
r"""单独重启一个采集实例（外科手术式，不动其余实例）。

背景：2026-09-20 16:41，run2 的 worker 在"保存工程之后、下一点开始之前"卡死
（worker 与 AEDT 30 秒 CPU 增量均为 0.00 秒，日志 4 小时零新增）。
其它实例正常，故**不能**用 guard 的 `--restart`（那会重启整批、拖慢其余实例）。

本脚本只是把 contract_launch.py 的单实例启动逻辑原样抄一遍。

⚠️ 2026-10-12 第二轮启动前修正：原版把 `B = "b1"`、`ROOT = HERE` **写死**，
而 guard 的外科恢复调用它时**只传实例号** —— 于是 b2 的外科恢复会拉起一个
`WPT_BATCH=b1` 的 worker：读 `b1_plan_shardK.csv`、写 `b1_raw_runK.csv` 与
`b1_worker_runK.log`。结果既救不活本实例（worker 起来就 FileNotFoundError 变 fatal），
又把另一批次的数据污染了。现在 batch/root/boxx/boxy 全部可由调用方传入。

用法： python _relaunch_one.py <K> [batch] [root] [boxx] [boxy]
"""
import os
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = r"C:\anaconda\python.exe"


def main():
    if len(sys.argv) < 2:
        raise SystemExit("用法: python _relaunch_one.py <K> [batch] [root] [boxx] [boxy]")
    k = int(sys.argv[1])
    B = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("WPT_BATCH", "b2")
    ROOT = (os.path.abspath(sys.argv[3]) if len(sys.argv) > 3
            else os.environ.get("WPT_ROOT", HERE))
    BOXX = sys.argv[4] if len(sys.argv) > 4 else "420"
    BOXY = sys.argv[5] if len(sys.argv) > 5 else "161"

    plan = os.path.join(ROOT, "%s_plan_shard%d.csv" % (B, k))
    if not os.path.exists(plan):
        raise SystemExit("找不到分片表: %s（batch/root 传错？）" % plan)

    # 与 contract_launch.py 的 env0 保持一致，并清掉会改变扫描/工况集合的变量
    e = dict(os.environ)
    e.update({"PYTHONIOENCODING": "utf-8", "WPT_BATCH": B, "WPT_ROOT": ROOT,
              "WPT_BOXX": BOXX, "WPT_BOXY": BOXY,
              # ⚠️ 2026-10-13：外科恢复由 guard 在计划任务（S4U / 会话 0）里发起，
              # 那里没有交互桌面 —— GUI 模式的 AEDT 起不来（实测失败 148.9 s，
              # 无界面 7.0 s 成功）。故这里默认置 1，保证会话无关。
              "WPT_NON_GRAPHICAL": os.environ.get("WPT_NON_GRAPHICAL", "1")})
    e.pop("WPT_XS", None)
    e.pop("WPT_CASES", None)
    e["WPT_RUN"] = str(k)
    e["WPT_PLAN"] = plan

    out = open(os.path.join(ROOT, "%s_stdout_%d.txt" % (B, k)), "a",
               encoding="utf-8", errors="replace")
    out.write("\n===== 单实例重启于 %s（_relaunch_one.py, batch=%s root=%s）=====\n"
              % (time.strftime("%Y-%m-%d %H:%M:%S"), B, ROOT))
    out.flush()
    p = subprocess.Popen([PY, os.path.join(HERE, "contract_worker.py")],
                         env=e, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT)
    print("已拉起实例 %d (batch=%s, pid=%d)" % (k, B, p.pid), flush=True)


if __name__ == "__main__":
    main()
