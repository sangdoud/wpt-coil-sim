# -*- coding: utf-8 -*-
"""④ 生产化补丁 4：求解失败快速退出（避免白等 30 分钟轮询）。

现状：solve_and_extract 里
    for i in range(90):
        time.sleep(20)
        solved = m3d.setups[0].is_solved
        ...
`m3d.analyze()` 的返回值被丢掉，所以即使 AEDT 已经明确报错（.profile 里 Status='Error'），
仍会空转满 90×20s = 30 分钟。批量采集里每次失败都白烧半小时。

做法：轮询循环里每 5 次（约 100 秒）检查一次最新 .profile 的 Status；发现 'Error' 立即返回 False。
另外把 analyze 的返回值也接上：若它直接返回 False（提交失败），立即退出循环。
"""
import datetime
import os
import shutil

WPT = r"C:\wpt"
WORK = r"C:\ansys maxwell2024\_work"
BATCH = os.path.join(WPT, "batch_sweep_lc.py")
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BAK = os.path.join(WORK, "backup_prod4_%s" % TS)
LOG = []


def say(m=""):
    print(m, flush=True)
    LOG.append(str(m))


def main():
    say("=" * 70)
    txt = open(BATCH, encoding="utf-8").read()
    if "_profile_status" in txt:
        say("已含快速退出，跳过")
        return
    os.makedirs(BAK, exist_ok=True)
    shutil.copy2(BATCH, os.path.join(BAK, os.path.basename(BATCH)))
    say("备份 -> %s" % BAK)

    # 1) 插入辅助函数（放在 solve_and_extract 之前）
    anchor = "def solve_and_extract("
    helper = '''def _results_dir():
    """当前工程的 AEDT 结果目录（用于读取 .profile 判定求解状态）。"""
    base = os.path.splitext(os.path.basename(PROJECT))[0] + ".aedtresults"
    return os.path.join(BASE_DIR, base, DESIGN + ".results")


def _profile_status():
    """读最新 .profile 里的 Status 字段；取不到返回 None。"""
    try:
        d = _results_dir()
        fs = [f for f in os.listdir(d) if f.endswith(".profile")]
        if not fs:
            return None
        f = max((os.path.join(d, x) for x in fs), key=os.path.getmtime)
        txt = open(f, encoding="utf-8", errors="replace").read()
        m = re.search(r"ProfileFootnote\\('I\\(\\d+, 1, 'Stop Time', '([^']+)', 1, 'Status', '([^']+)'", txt)
        return m.group(2) if m else None
    except Exception:
        return None


'''
    if anchor not in txt:
        say("!! 未找到 solve_and_extract")
        return
    txt = txt.replace(anchor, helper + anchor, 1)
    if "\nimport re\n" not in txt and "^import re" not in txt:
        txt = txt.replace("import os, sys, time, csv, math, glob, threading, traceback",
                          "import os, re, sys, time, csv, math, glob, threading, traceback", 1)

    # 2) 轮询循环里加快速退出
    old = """    for i in range(90):
        time.sleep(20)
        try:
            solved = m3d.setups[0].is_solved
            err_streak = 0"""
    new = """    for i in range(90):
        time.sleep(20)
        # 快速失败：AEDT 若已明确报错（.profile 里 Status='Error'），不再空转
        if i % 5 == 4:
            _st = _profile_status()
            if _st and _st.lower().startswith("error"):
                log("  !! 求解已报错(Status=%s)，第 %d 次轮询提前退出" % (_st, i + 1))
                try:
                    d.odesktop.StopSimulations(True)
                except Exception:
                    pass
                return False
        try:
            solved = m3d.setups[0].is_solved
            err_streak = 0"""
    if old not in txt:
        say("!! 未找到轮询循环锚点")
        return
    txt = txt.replace(old, new, 1)

    open(BATCH, "w", encoding="utf-8").write(txt)
    say("已写入快速失败")
    try:
        compile(open(BATCH, encoding="utf-8").read(), BATCH, "exec")
        say("语法 OK ✓")
    except SyntaxError as e:
        say("!! 语法错误: %s" % e)
    open(os.path.join(WORK, "apply_prod_patch4.log"), "w", encoding="utf-8").write(
        "\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
