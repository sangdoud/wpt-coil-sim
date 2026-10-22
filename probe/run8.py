# -*- coding: utf-8 -*-
"""跑 8 实例并发并同步记录内存水位（判断是否在换页）。

用法：python run8.py            # T8F（8 实例 x 8 核）
      python run8.py T8F6       # 8 实例 x 6 核
每隔 20 秒记一次：可用物理内存、提交内存、ansysedt 进程数与占用、以及是否出现换页活动。
"""
import json
import os
import subprocess
import sys
import time

WORK = r"C:\ansys maxwell2024\_work"
PROBE = r"C:\ansys maxwell2024\_probe"
CFG = sys.argv[1] if len(sys.argv) > 1 else "T8F"
LOGF = os.path.join(WORK, "run8_mem.log")


def log(m):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def mem():
    try:
        o = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "$os=Get-CimInstance Win32_OperatingSystem;"
                            "$p=Get-Process -Name ansysedt -ErrorAction SilentlyContinue;"
                            "'{0}|{1}|{2}|{3}' -f [int]($os.FreePhysicalMemory/1024),"
                            "[int](($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/1024),"
                            "@($p).Count, [int](($p | Measure-Object WorkingSet64 -Sum).Sum/1MB)"],
                           capture_output=True, text=True)
        parts = (o.stdout or "").strip().split("|")
        return dict(free_mb=int(parts[0]), used_mb=int(parts[1]),
                    n_aedt=int(parts[2]), aedt_mb=int(parts[3]))
    except Exception as e:
        return dict(err=repr(e))


def main():
    log("=" * 70)
    log("启动 %s（8 实例并发）+ 内存监控" % CFG)
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.Popen([r"C:\anaconda\python.exe",
                          os.path.join(PROBE, "queue_p4_bisect.py"), CFG],
                         env=env, cwd=WORK,
                         stdout=open(os.path.join(WORK, "run8_stdout.txt"), "w"),
                         stderr=subprocess.STDOUT)
    log("  bisect 驱动 pid=%d" % p.pid)
    samples = []
    t0 = time.time()
    while p.poll() is None:
        m = mem()
        samples.append(dict(t=round(time.time() - t0, 1), **m))
        if len(samples) % 3 == 1:
            log("  内存: 可用 %s MB / 已用 %s MB / AEDT %s 个共 %s MB"
                % (m.get("free_mb"), m.get("used_mb"), m.get("n_aedt"), m.get("aedt_mb")))
        time.sleep(20)
    log("  驱动结束，退出码 %s，用时 %.1f 分钟" % (p.returncode, (time.time() - t0) / 60.0))
    if samples:
        frees = [s["free_mb"] for s in samples if "free_mb" in s]
        logs = [s.get("n_aedt", 0) for s in samples]
        if frees:
            log("  可用内存区间: %d ~ %d MB（最低 %d MB）" % (min(frees), max(frees), min(frees)))
        log("  并发 AEDT 峰值: %d 个" % (max(logs) if logs else 0))
    json.dump(samples, open(os.path.join(WORK, "run8_mem.json"), "w"), indent=2)
    # 打印结果
    try:
        d = json.load(open(os.path.join(WORK, "p4_bisect.json"), encoding="utf-8"))
        r = d.get(CFG, {})
        log("  %s: 墙钟 %s 分钟，%d 个实例，全部有效=%s"
            % (CFG, r.get("wall_minutes"), len(r.get("runs", [])), r.get("all_valid")))
        for x in r.get("runs", []):
            log("    实例 %s: %s 分钟 有效=%s" % (x["run"], x["minutes"], x["ok"]))
    except Exception as e:
        log("  读结果失败: %r" % e)


if __name__ == "__main__":
    main()
