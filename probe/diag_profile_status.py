# -*- coding: utf-8 -*-
"""定位生产的「求解失败快速退出」为何没触发。

batch_sweep_lc._profile_status() 会在轮询中读最新 .profile 的 Status，
发现 'Error' 就提前退出。实测 run3/run5 的 profile 明确写着 Status='Error'，
但 worker 日志里没有对应的"提前退出"记录 —— 复现这个函数看它到底返回什么。
"""
import os
import re
import sys

sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                                  # noqa: E402,F401
sys.path.insert(0, r"C:\wpt")
import batch_sweep_lc as B                        # noqa: E402

ROOT = r"C:\ansys maxwell2024\_work\b1"
PAT = r"ProfileFootnote\('I\(\d+, 1, 'Stop Time', '([^']+)', 1, 'Status', '([^']+)'"

for k in (3, 5, 0, 1):
    B.BASE_DIR = ROOT
    B.PROJECT = os.path.join(ROOT, "Projecttonight_b1_run%d.aedt" % k)
    d = B._results_dir()
    print("run%d" % k)
    print("   _results_dir() = %s" % d)
    print("   目录存在 = %s" % os.path.isdir(d))
    if os.path.isdir(d):
        fs = [f for f in os.listdir(d) if f.endswith(".profile")]
        print("   该目录下 .profile 文件数 = %d" % len(fs))
        if fs:
            f = max((os.path.join(d, x) for x in fs), key=os.path.getmtime)
            txt = open(f, encoding="utf-8", errors="replace").read()
            m = re.search(PAT, txt)
            print("   最新 profile = %s" % os.path.basename(f))
            print("   正则匹配 Status = %r" % (m.group(2) if m else None))
        else:
            # 看看 profile 实际在哪
            hits = []
            for root, _dirs, files in os.walk(os.path.dirname(d)):
                for x in files:
                    if x.endswith(".profile"):
                        hits.append(os.path.join(root, x))
            print("   实际 profile 位置样例: %s" % hits[:3])
    print("   B._profile_status() = %r" % B._profile_status())
    print()
