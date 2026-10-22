# -*- coding: utf-8 -*-
"""④ 多实例并行的驱动 + 量效。

做三件事：
  1) 准备 3 份独立工程副本（从参考工程拷贝）
  2) 同时起 3 个 worker（各 8 核），分别在各自副本上求解参考点同一点
  3) 量：3 点并发墙钟时间 vs 单点串行时间（14.32 分钟）-> 真实吞吐倍率；
         并比对三份结果是否一致（互相不干扰的旁证）

注意：本脚本**不**杀全局 ansysedt（多实例下那是互杀），只按 PID 收自己那份。
"""
import json
import os
import shutil
import subprocess
import sys
import time

WORK = r"C:\ansys maxwell2024\_work"
SRC = os.path.join(WORK, "Projecttonight_4ch.aedt")
OUT = os.path.join(WORK, "p4_parallel.json")
LOGF = os.path.join(WORK, "p4_parallel.log")
N = int(os.environ.get("WPT_N", "3"))
T_SINGLE = 14.32          # 同会话单点串行（S1，旧模板 8 核/8 趟/5%）


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def main():
    log("=" * 78)
    log("④ 多实例并行量效：%d 实例 x 8 核，同一点" % N)
    res = {"n_instances": N, "t_single_min": T_SINGLE}
    for i in range(N):
        dst = os.path.join(WORK, "Projecttonight_run%d.aedt" % i)
        shutil.copy2(SRC, dst)
        for lk in (dst + ".lock",):
            if os.path.exists(lk):
                os.remove(lk)
        log("  副本 %d -> %s (%.1f MB)" % (i, os.path.basename(dst),
                                          os.path.getsize(dst) / 1048576.0))
    # 清掉 worker 的旧产物
    for i in range(N):
        for f in ("p4_run%d.json" % i, "p4_run%d.log" % i, "solve_p4_run%d.csv" % i):
            p = os.path.join(WORK, f)
            if os.path.exists(p):
                os.remove(p)

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    procs = []
    t0 = time.time()
    for i in range(N):
        e = dict(env)
        e["WPT_RUN"] = str(i)
        e["WPT_DX"] = "0"
        p = subprocess.Popen([r"C:\anaconda\python.exe",
                              r"C:\ansys maxwell2024\_probe\worker_solve.py"],
                             env=e, cwd=WORK,
                             stdout=open(os.path.join(WORK, "p4_stdout_%d.txt" % i), "w"),
                             stderr=subprocess.STDOUT)
        procs.append(p)
        log("  启动 worker %d (pid=%d)" % (i, p.pid))
        time.sleep(20)                      # 错开启动，避免同时抢 license/端口
    log("  三个 worker 已起，等待...")
    for i, p in enumerate(procs):
        p.wait()
        log("  worker %d 退出码 %s" % (i, p.returncode))
    wall = (time.time() - t0) / 60.0
    res["wall_minutes"] = round(wall, 2)
    res["speedup_vs_single"] = round(N * T_SINGLE / wall, 2) if wall else None
    res["efficiency"] = round(res["speedup_vs_single"] / N * 100, 1) if res.get("speedup_vs_single") else None
    runs = []
    for i in range(N):
        p = os.path.join(WORK, "p4_run%d.json" % i)
        d = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {"run": i, "missing": True}
        if d.get("t_open") and d.get("t0"):
            d["open_overhead_min"] = round((d["t_open"] - d["t0"]) / 60.0, 2)
        if d.get("t_end") and d.get("t0"):
            d["end_to_end_min"] = round((d["t_end"] - d["t0"]) / 60.0, 2)
        runs.append(d)
        log("  run%d: 求解 %s 分钟 | 端到端 %s 分钟 | %s"
            % (i, d.get("solve_minutes"), d.get("end_to_end_min"), d.get("row", "")[:120]))
    res["runs"] = runs
    vals = [r.get("row", "").split(",") for r in runs if r.get("row")]
    if len(vals) >= 2:
        keys = ["L11", "L22", "L33", "M12", "M13", "M23"]
        spread = {}
        for j, k in enumerate(keys):
            xs = [float(v[8 + j]) for v in vals]
            spread[k] = round(100.0 * (max(xs) - min(xs)) / (abs(sum(xs) / len(xs)) or 1), 4)
        res["inter_instance_spread_pct"] = spread
        log("  三实例结果散布(%%): %s" % spread)
    log("")
    log("=== ④ 结论 ===  %d 点并发墙钟 %.2f 分钟；单点串行 %.2f 分钟 -> 吞吐 x%.2f（效率 %.0f%%）"
        % (N, wall, T_SINGLE, res.get("speedup_vs_single") or 0, res.get("efficiency") or 0))
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return res


if __name__ == "__main__":
    main()
