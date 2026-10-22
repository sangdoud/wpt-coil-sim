# -*- coding: utf-8 -*-
"""B2：用多实例并行跑一条完整的半扫曲线（21 点），并离线验证"点位能否再砍"。

为什么要这条曲线：① 已把 41 点砍到 21 点（−49%）。曲线是光滑的，理论上 11~15 点也能定出
M_sum_mean / M_sum_var；但这必须用数据验证——拿 21 点当基准，比较 15/11/7 点算出的目标量误差。
没有这条曲线就没法验证，所以先用 ④ 的并行机制把曲线跑出来。

用法：WPT_N=3 python queue_b2_sweep.py
输出：_work\b2_curve.csv（case_id, position_x, M1, M2, L11, L33 ...）、
      _work\b2_points.json（点位裁剪的误差分析）
"""
import json
import math
import os
import shutil
import subprocess
import sys
import time

WORK = r"C:\ansys maxwell2024\_work"
SRC = os.path.join(WORK, "Projecttonight_4ch.aedt")
CURVE = os.path.join(WORK, "b2_curve.csv")
OUT = os.path.join(WORK, "b2_points.json")
LOGF = os.path.join(WORK, "b2_driver.log")
N = int(os.environ.get("WPT_N", "3"))
LC, KX = 167.2829, -0.3
S = LC * (2.0 + KX)
XS = [i * S / 40.0 for i in range(0, 21)]          # 半扫 21 点，与 sweep_positions_half 一致


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def shard(xs, k):
    """交错分片：保证每个实例拿到的位置在空间上分散（温度/负载更均衡）。"""
    return [xs[i::k] for i in range(k)]


def main():
    log("=" * 78)
    log("B2 半扫曲线并行采集：%d 点 / %d 实例" % (len(XS), N))
    log("  位置: %s" % ["%.2f" % x for x in XS])
    for i in range(N):
        dst = os.path.join(WORK, "Projecttonight_s%d.aedt" % i)
        shutil.copy2(SRC, dst)
        lk = dst + ".lock"
        if os.path.exists(lk):
            os.remove(lk)
    for i in range(N):
        for f in ("b2_run%d.json" % i, "b2_run%d.log" % i):
            p = os.path.join(WORK, f)
            if os.path.exists(p):
                os.remove(p)

    parts = shard(XS, N)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    procs = []
    t0 = time.time()
    for i, xs in enumerate(parts):
        e = dict(env)
        e["WPT_RUN"] = str(i)
        e["WPT_XS"] = ",".join("%.6f" % x for x in xs)
        p = subprocess.Popen([r"C:\anaconda\python.exe",
                              r"C:\ansys maxwell2024\_probe\worker_sweep.py"],
                             env=e, cwd=WORK,
                             stdout=open(os.path.join(WORK, "b2_stdout_%d.txt" % i), "w"),
                             stderr=subprocess.STDOUT)
        procs.append(p)
        log("  启动实例 %d：%d 个位置 %s" % (i, len(xs), ["%.1f" % x for x in xs]))
        time.sleep(20)
    for i, p in enumerate(procs):
        p.wait()
        log("  实例 %d 退出码 %s" % (i, p.returncode))
    wall = (time.time() - t0) / 60.0
    log("  三个实例全部结束，墙钟 %.1f 分钟" % wall)

    rows = {}
    for i in range(N):
        p = os.path.join(WORK, "b2_run%d.json" % i)
        if not os.path.exists(p):
            continue
        dd = json.load(open(p, encoding="utf-8"))
        for r in dd.get("rows", []):
            if r.get("row"):
                v = [float(z) for z in r["row"].split(",")]
                rows[round(r["x"], 6)] = dict(x=r["x"], minutes=r["minutes"],
                                              L11=v[8], L22=v[9], L33=v[10],
                                              M12=v[11], M1=v[12], M2=v[13],
                                              k13=v[14], k23=v[15])
    with open(CURVE, "w", encoding="utf-8") as f:
        f.write("position_x,M1,M2,M_sum,L11,L22,L33,M12,k13,k23,minutes\n")
        for x in sorted(rows):
            r = rows[x]
            f.write("%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.4f,%.5f,%.5f,%.2f\n"
                    % (r["x"], r["M1"], r["M2"], r["M1"] + r["M2"], r["L11"], r["L22"],
                       r["L33"], r["M12"], r["k13"], r["k23"], r["minutes"]))
    log("  曲线: %d/%d 点 -> %s" % (len(rows), len(XS), CURVE))

    # ---- 点位裁剪分析：目标量 M_sum_mean / M_sum_var / M_pp ----
    ana = {"wall_minutes": round(wall, 2), "n_full": len(rows)}
    if len(rows) >= 15:
        xs = sorted(rows)
        ms = [rows[x]["M1"] + rows[x]["M2"] for x in xs]
        m12 = [rows[x]["M12"] for x in xs]

        def stats(idx):
            v = [ms[i] for i in idx]
            n = len(v)
            mean = sum(v) / n
            var = sum((a - mean) ** 2 for a in v) / n
            return mean, var

        full = list(range(len(xs)))
        mean0, var0 = stats(full)
        mpp0 = sum(m12) / len(m12)
        ana["full"] = dict(n=len(xs), M_sum_mean=mean0, M_sum_var=var0, M_pp=mpp0)
        for n_keep in (15, 11, 9, 7):
            idx = [round(i * (len(xs) - 1) / (n_keep - 1)) for i in range(n_keep)]
            mean1, var1 = stats(idx)
            mpp1 = sum(m12[i] for i in idx) / len(idx)
            ana["keep_%d" % n_keep] = dict(
                n=n_keep, idx=idx,
                d_mean_pct=round(100 * (mean1 - mean0) / mean0, 4),
                d_var_pct=round(100 * (var1 - var0) / var0, 4) if var0 else None,
                d_mpp_pct=round(100 * (mpp1 - mpp0) / mpp0, 4) if mpp0 else None,
                d_minutes_pct=round(100 * (n_keep - len(xs)) / len(xs), 1))
            log("  取 %2d 点：M_sum_mean %+.4f%%  M_sum_var %+.4f%%  M_pp %+.4f%%  (点数 %+.1f%%)"
                % (n_keep, ana["keep_%d" % n_keep]["d_mean_pct"],
                   ana["keep_%d" % n_keep]["d_var_pct"] or 0,
                   ana["keep_%d" % n_keep]["d_mpp_pct"] or 0,
                   ana["keep_%d" % n_keep]["d_minutes_pct"]))
    json.dump(ana, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("  分析 -> %s" % OUT)


if __name__ == "__main__":
    main()
