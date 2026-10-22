# -*- coding: utf-8 -*-
"""④ 生产化的第 2 步补丁：给 batch_sweep_lc.py 加
   (a) 环境变量参数化（WPT_RUN -> 独立工程副本 / 参数表分片 / 结果文件 / 日志）
   (b) PID 级 kill（多实例下原来的无差别 taskkill 会互杀）

备份到 _work\\backup_prod2_<时间戳>\\。
"""
import datetime
import os
import shutil

WPT = r"C:\wpt"
WORK = r"C:\ansys maxwell2024\_work"
BATCH = os.path.join(WPT, "batch_sweep_lc.py")
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BAK = os.path.join(WORK, "backup_prod2_%s" % TS)
LOG = []


def say(m=""):
    print(m, flush=True)
    LOG.append(str(m))


def main():
    say("=" * 70)
    txt = open(BATCH, encoding="utf-8").read()
    if "WPT_RUN" in txt:
        say("已含 WPT_RUN 支持，跳过")
        return
    shutil.copy2(BATCH, os.path.join(os.makedirs(BAK, exist_ok=True) or BAK,
                                     os.path.basename(BATCH)))
    say("备份 -> %s" % BAK)

    # ---- (a) 环境变量参数化：插到 kill_aedt 之前 ----
    anchor = 'def kill_aedt():'
    block = '''# ============ ④ 多实例：环境变量参数化（2026-09-18）============
# WPT_RUN=0..N-1 时，本进程只用自己那份工程副本、自己的参数表分片、自己的结果文件与日志。
# 不设 WPT_RUN（或为 -1）时行为与原来完全一致（单实例）。
RUN_ID = int(os.environ.get("WPT_RUN", "-1"))
_OWN_PID = [None]
if RUN_ID >= 0:
    PROJECT = os.path.join(BASE_DIR, "Projecttonight_run%d.aedt" % RUN_ID)
    PLAN_CSV = os.path.join(BASE_DIR, "combos_lc_shard%d.csv" % RUN_ID)
    OUT_CSV = os.path.join(BASE_DIR, "sweep_all_lc_run%d.csv" % RUN_ID)
    LOG_FILE = os.path.join(BASE_DIR, "batch_sweep_lc_run%d.log" % RUN_ID)

'''
    if anchor not in txt:
        say("!! 未找到 kill_aedt 锚点")
        return
    txt = txt.replace(anchor, block + anchor, 1)

    # ---- (b) PID 级 kill ----
    old_kill = '''def kill_aedt():
    """强杀残留的 AEDT 进程并清理锁文件。"""
    try:'''
    new_kill = '''def kill_aedt():
    """强杀残留的 AEDT 进程并清理锁文件。

    ④ 多实例模式（RUN_ID>=0）：**只杀自己那个 PID**，否则会互杀。
    """
    if RUN_ID >= 0:
        pid = AEDT_PROCESS_ID or _OWN_PID[0]
        if pid:
            try:
                import subprocess as _sp
                _sp.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                         "Stop-Process -Id %d -Force -ErrorAction SilentlyContinue" % int(pid)],
                        capture_output=True, text=True)
            except Exception:
                pass
        try:
            for f in glob.glob(os.path.join(BASE_DIR, "Projecttonight_run%d.aedt.lock" % RUN_ID)):
                os.remove(f)
        except Exception:
            pass
        time.sleep(3)
        return
    try:'''
    if old_kill not in txt:
        say("!! 未找到 kill_aedt 函数体锚点")
        return
    txt = txt.replace(old_kill, new_kill, 1)

    # ---- 会话打开后记录自己的 PID ----
    anchor2 = '''    d, m3d = open_session()
    if d is None:
        sys.exit(1)'''
    new2 = '''    d, m3d = open_session()
    if d is None:
        sys.exit(1)
    try:
        _OWN_PID[0] = d.aedt_process_id
        log("my AEDT pid=%s (run=%d)" % (_OWN_PID[0], RUN_ID))
    except Exception:
        pass'''
    if anchor2 not in txt:
        say("!! 未找到 open_session 锚点")
        return
    txt = txt.replace(anchor2, new2, 1)

    open(BATCH, "w", encoding="utf-8").write(txt)
    say("已写入参数化 + PID 级 kill")
    try:
        compile(open(BATCH, encoding="utf-8").read(), BATCH, "exec")
        say("语法 OK ✓")
    except SyntaxError as e:
        say("!! 语法错误: %s" % e)
    open(os.path.join(WORK, "apply_prod_patch2.log"), "w", encoding="utf-8").write(
        "\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
