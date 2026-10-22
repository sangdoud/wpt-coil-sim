# -*- coding: utf-8 -*-
"""④ 并发失败的二分解（三个实例求解都 Status='Error' -> NaN）。

待排除的三种假设：
  H1 工程副本本身有问题（源工程现在含 donor 设计 WPT_mesh 等）-> 单实例用副本也会失败
  H2 并发实例数超限（license/HPC 座位）-> 2 实例能过、3 实例不过
  H3 并发总核数超限（HPC core token）-> 3 实例但每个 4 核能过

用法：python queue_p4_bisect.py T1|T2|T3
  T1 = 1 实例 × 8 核（副本）
  T2 = 2 实例 × 8 核
  T3 = 3 实例 × 4 核
每个配置结束打印：各实例耗时、结果是否有效（NaN/0 检查）、并发墙钟。
"""
import json
import math
import os
import shutil
import subprocess
import sys
import time

WORK = r"C:\ansys maxwell2024\_work"
SRC = os.environ.get("WPT_SRC", os.path.join(WORK, "Projecttonight_ref.aedt"))
LOGF = os.path.join(WORK, "p4_bisect.log")
OUT = os.path.join(WORK, "p4_bisect.json")

CONFIGS = {
    "T1":   dict(n=1, cores=8, desc="1 实例 x 8 核（副本）"),
    "T2":   dict(n=2, cores=8, desc="2 实例 x 8 核"),
    "T3":   dict(n=3, cores=4, desc="3 实例 x 4 核"),
    "T1C":  dict(n=1, cores=8, desc="1 实例 x 8 核（干净参考工程的副本）"),
    "T3C":  dict(n=3, cores=8, desc="3 实例 x 8 核（干净参考工程的副本）"),
    "T3C4": dict(n=3, cores=4, desc="3 实例 x 4 核（干净参考工程的副本）"),
    # 生产配置（柔性网格 + ⑥）下的实例扩展
    "T3F":  dict(n=3, cores=8, flex=1, six=1, desc="3 实例 x 8 核（柔性+⑥，生产配置）"),
    "T5F":  dict(n=5, cores=8, flex=1, six=1, desc="5 实例 x 8 核（柔性+⑥，生产配置）"),
    "T6F":  dict(n=6, cores=8, flex=1, six=1, desc="6 实例 x 8 核（柔性+⑥，生产配置）"),
    "T6F4": dict(n=6, cores=4, flex=1, six=1, desc="6 实例 x 4 核（柔性+⑥，生产配置）"),
    "T8F":  dict(n=8, cores=8, flex=1, six=1, desc="8 实例 x 8 核（柔性+⑥，生产配置）"),
    "T8F6": dict(n=8, cores=6, flex=1, six=1, desc="8 实例 x 6 核（柔性+⑥，生产配置）"),
    "T7F":  dict(n=7, cores=8, flex=1, six=1, desc="7 实例 x 8 核（柔性+⑥，生产配置）"),
}


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def valid_row(row):
    if not row:
        return False, "无结果行"
    v = row.split(",")
    if len(v) < 16:
        return False, "列数不足"
    try:
        L = [float(v[8]), float(v[9]), float(v[10])]
        M = [float(v[11]), float(v[12]), float(v[13])]
    except Exception:
        return False, "解析失败"
    if any(math.isnan(x) for x in L + M):
        return False, "含 NaN"
    if any(x <= 0 for x in L):
        return False, "自感<=0"
    if M[1] == 0 or M[2] == 0:
        return False, "互感为 0"
    return True, ""


def run_config(tag):
    cfg = CONFIGS[tag]
    n, cores = cfg["n"], cfg["cores"]
    log("=" * 78)
    log("%s : %s" % (tag, cfg["desc"]))
    res = dict(tag=tag, n=n, cores=cores, desc=cfg["desc"])
    for i in range(n):
        dst = os.path.join(WORK, "Projecttonight_b%d.aedt" % i)
        shutil.copy2(SRC, dst)
        lk = dst + ".lock"
        if os.path.exists(lk):
            os.remove(lk)
        # 关键：把副本自己的结果目录删掉。否则副本会继承源工程的"已解状态"，
        # AEDT 可能复用旧自适应网格 -> 解得更快但结果对不上（T1C 就出现了 L33 +2.2%）。
        rd = os.path.join(WORK, "Projecttonight_b%d.aedtresults" % i)
        if os.path.isdir(rd):
            shutil.rmtree(rd, ignore_errors=True)
            log("  清掉副本 %d 的结果目录（避免继承旧解）" % i)
    for i in range(n):
        for f in ("b_run%d.json" % i, "b_run%d.log" % i):
            p = os.path.join(WORK, f)
            if os.path.exists(p):
                os.remove(p)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["WPT_CORES"] = str(cores)
    env["WPT_FLEX"] = str(cfg.get("flex", 0))
    env["WPT_SIX"] = str(cfg.get("six", 0))
    procs = []
    t0 = time.time()
    for i in range(n):
        e = dict(env)
        e["WPT_RUN"] = str(i)
        # worker_solve.py 用 WPT_PROJ_SUFFIX 决定副本名，见下（默认 run%d）
        e["WPT_SUFFIX"] = "b%d" % i
        e["WPT_DX"] = "0"
        p = subprocess.Popen([r"C:\anaconda\python.exe",
                              r"C:\ansys maxwell2024\_probe\worker_ab.py"],
                             env=e, cwd=WORK,
                             stdout=open(os.path.join(WORK, "b_stdout_%d.txt" % i), "w"),
                             stderr=subprocess.STDOUT)
        procs.append(p)
        log("  启动实例 %d (%d 核)" % (i, cores))
        time.sleep(20)
    for i, p in enumerate(procs):
        p.wait()
        log("  实例 %d 退出码 %s" % (i, p.returncode))
    wall = (time.time() - t0) / 60.0
    res["wall_minutes"] = round(wall, 2)
    runs = []
    ok_all = True
    for i in range(n):
        p = os.path.join(WORK, "b_run%d.json" % i)
        dd = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"run": i, "missing": True}
        ok, why = valid_row(dd.get("row", ""))
        ok_all = ok_all and ok
        runs.append(dict(run=i, minutes=dd.get("solve_minutes"), ok=ok, why=why,
                         row=dd.get("row", "")))
        log("  实例 %d: %.2f 分钟  有效=%s %s" % (i, dd.get("solve_minutes"), ok, why))
    res["runs"] = runs
    res["all_valid"] = ok_all
    log("  => 墙钟 %.1f 分钟，%s" % (wall, "全部有效 ✓" if ok_all else "存在无效结果 ✗"))
    return res


def main():
    tag = (sys.argv[1] if len(sys.argv) > 1 else "T1").upper()
    if tag not in CONFIGS:
        print("用法: python queue_p4_bisect.py T1|T2|T3")
        return
    all_res = {}
    if os.path.exists(OUT):
        try:
            all_res = json.load(open(OUT, encoding="utf-8"))
        except Exception:
            pass
    all_res[tag] = run_config(tag)
    json.dump(all_res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
