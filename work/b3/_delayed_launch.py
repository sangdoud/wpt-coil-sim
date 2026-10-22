# -*- coding: utf-8 -*-
r"""延迟启动器：等环境静置后再整批拉起（供 b1_guard.py 的整批重启调用）。

背景（2026-09-24 实测）：guard 整批重启失败过两次，每次都全灭——
`Failed to start new AEDT gRPC session on port ... on machine 127.0.0.1`
（6/8 实例同时失败）。但**同样的环境，只要"杀完等几分钟"再起就 100% 成功**
（13:06 与 18:37 两次手工重启均一次成功，且此前都静置了 3~5 分钟）。

结论：不是环境坏了，而是 **AEDT 被强杀后有约 3~5 分钟的退出/清理窗口**，
窗口内新建会话必然失败。guard 原来的 `time.sleep(5)` 远不够。

本脚本把这段等待从 guard 里挪出来（避免 guard 阻塞 4 分钟），
由 guard 以 detached 方式拉起，等够时间再执行 contract_launch.py。

用法：python _delayed_launch.py <wait_seconds> <n> <batch> <root> <boxx>
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PY = r"C:\anaconda\python.exe"


def main():
    wait = float(sys.argv[1]) if len(sys.argv) > 1 else 240.0
    n = sys.argv[2] if len(sys.argv) > 2 else "8"
    batch = sys.argv[3] if len(sys.argv) > 3 else "b2"
    root = sys.argv[4] if len(sys.argv) > 4 else HERE
    boxx = sys.argv[5] if len(sys.argv) > 5 else "420"
    boxy = sys.argv[6] if len(sys.argv) > 6 else "161"

    logf = os.path.join(root, "%s_guard_launch.log" % batch)
    log = open(logf, "a", encoding="utf-8", errors="replace")

    def say(m):
        log.write("%s | %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), m))
        log.flush()

    say("延迟启动器：等待 %.0f 秒让 AEDT 彻底退出（强杀后有 3~5 min 清理窗口）" % wait)
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(5)
        # 提前结束等待：只要 AEDT 全家族都退净了，就不必等满
        try:
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "@(Get-Process -Name ansysedt,3dnms,G3dMesher,ansyscl "
                 "-ErrorAction SilentlyContinue).Count"],
                capture_output=True, text=True, timeout=30)
            left = int((r.stdout or "0").strip() or 0)
        except Exception:
            left = -1
        if left == 0 and time.time() - t0 > 150:
            say("已静置 %.0f 秒且 AEDT 全家族退净，提前结束等待" % (time.time() - t0))
            break
    say("开始整批拉起：n=%s batch=%s boxx=%s boxy=%s（AEDT 无界面模式）"
        % (n, batch, boxx, boxy))
    cmd = [PY, os.path.join(HERE, "contract_launch.py"), str(n),
           "--batch", batch, "--root", root, "--boxx", str(boxx),
           "--boxy", str(boxy), "--merge"]
    # ⚠️ 2026-10-13：本脚本由 guard 在计划任务（S4U / 会话 0）里拉起 —— **那里没有交互桌面**，
    # GUI 模式的 AEDT 起不来（实测 non_graphical=False 失败 148.9 s，
    # non_graphical=True 成功 7.0 s）。必须显式传无界面标志，否则"自动重启"等于什么都不做。
    env = dict(os.environ)
    env["WPT_NON_GRAPHICAL"] = "1"
    p = subprocess.Popen(cmd, cwd=HERE, stdout=log, stderr=subprocess.STDOUT, env=env)
    say("已拉起启动器 pid=%d" % p.pid)


if __name__ == "__main__":
    main()
