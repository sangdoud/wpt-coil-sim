# -*- coding: utf-8 -*-
"""执行链：等 A 组收尾 -> 造干净工程 -> 柔性+⑥ 叠加 -> T1c -> T3c（必要时 T3c4）。

用法：python chain_p4.py   （后台跑，日志 _work/chain.log）
每一步的输出各自落到自己的日志里；本脚本只负责串行与判定。
"""
import json
import os
import subprocess
import sys
import time

WORK = r"C:\ansys maxwell2024\_work"
PY = r"C:\anaconda\python.exe"
PROBE = r"C:\ansys maxwell2024\_probe"
CHAIN_LOG = os.path.join(WORK, "chain.log")
QUEUEA_LOG = os.path.join(WORK, "queueA.log")
BISECT_JSON = os.path.join(WORK, "p4_bisect.json")


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    with open(CHAIN_LOG, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def run_ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                          capture_output=True, text=True)


def ansysedt_count():
    r = run_ps("@(Get-Process -Name ansysedt -ErrorAction SilentlyContinue).Count")
    try:
        return int((r.stdout or "0").strip() or 0)
    except Exception:
        return 0


def wait_a_group(max_min=90):
    """等 A 组队列跑完（日志出现"全部完成"且没有残留 AEDT 进程）。"""
    t0 = time.time()
    while (time.time() - t0) / 60.0 < max_min:
        txt = ""
        if os.path.exists(QUEUEA_LOG):
            txt = open(QUEUEA_LOG, encoding="utf-8", errors="replace").read()
        if "全部完成" in txt and ansysedt_count() == 0:
            log("A 组已收尾（等待 %.0f 分钟）" % ((time.time() - t0) / 60.0))
            return True
        time.sleep(20)
    log("!! 等待 A 组超时（%.0f 分钟）" % max_min)
    return False


def step(tag, script, args=(), env_extra=None, timeout_min=60):
    log("---- 步骤 %s : %s %s ----" % (tag, os.path.basename(script), " ".join(args)))
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    out = open(os.path.join(WORK, "chain_%s_stdout.txt" % tag), "w")
    t0 = time.time()
    p = subprocess.Popen([PY, script] + list(args), env=env, cwd=WORK,
                         stdout=out, stderr=subprocess.STDOUT)
    while p.poll() is None:
        if (time.time() - t0) / 60.0 > timeout_min:
            log("  步骤 %s 超时，强杀" % tag)
            p.kill()
            return False
        time.sleep(10)
    log("  步骤 %s 结束，退出码 %s，用时 %.1f 分钟"
        % (tag, p.returncode, (time.time() - t0) / 60.0))
    return p.returncode == 0


def t3c_valid():
    if not os.path.exists(BISECT_JSON):
        return False
    try:
        d = json.load(open(BISECT_JSON, encoding="utf-8"))
        return bool(d.get("T3C", {}).get("all_valid"))
    except Exception:
        return False


def p4_only():
    """只跑 ④ 的三步（跳过等 A 组/造工程/叠加试验）。"""
    log("=" * 78)
    log("仅跑 ④：T1C -> T3C ->（必要时）T3C4")
    step("T1C", os.path.join(PROBE, "queue_p4_bisect.py"), args=["T1C"], timeout_min=45)
    step("T3C", os.path.join(PROBE, "queue_p4_bisect.py"), args=["T3C"], timeout_min=45)
    if t3c_valid():
        log("T3C 通过：3 实例并发成立 ✓")
    else:
        log("T3C 未通过 -> 兜底 T3C4（3 实例 x 4 核）")
        step("T3C4", os.path.join(PROBE, "queue_p4_bisect.py"), args=["T3C4"], timeout_min=45)
    log("执行链结束")


def main():
    if len(sys.argv) > 1 and sys.argv[1].lower() in ("p4only", "p4"):
        p4_only()
        return
    log("=" * 78)
    log("执行链启动：等 A 组 -> 干净工程 -> 柔性+⑥ -> T1c -> T3c")
    if not wait_a_group():
        log("A 组未收尾，链中止")
        return
    ok = step("clean", os.path.join(PROBE, "make_clean_project.py"), timeout_min=25)
    if not ok or not os.path.exists(os.path.join(WORK, "Projecttonight_ref.aedt")):
        log("干净工程失败，链中止")
        return
    step("A2stack", os.path.join(PROBE, "queueA2_stack.py"), timeout_min=60)
    step("T1C", os.path.join(PROBE, "queue_p4_bisect.py"), args=["T1C"], timeout_min=45)
    step("T3C", os.path.join(PROBE, "queue_p4_bisect.py"), args=["T3C"], timeout_min=45)
    if t3c_valid():
        log("T3C 通过：3 实例并发成立 ✓")
    else:
        log("T3C 未通过 -> 兜底 T3C4（3 实例 x 4 核）")
        step("T3C4", os.path.join(PROBE, "queue_p4_bisect.py"), args=["T3C4"], timeout_min=45)
    log("执行链结束")


if __name__ == "__main__":
    main()
