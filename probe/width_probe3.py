# -*- coding: utf-8 -*-
"""看活动设计(WPT_G)三个线圈 Polyline 的段类型分布 + 截面块原文。"""

import re
import sys
from collections import Counter

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\wpt\Projecttonight.aedt"

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    lines = f.readlines()

n = len(lines)
TARGET = {297717: "Tx1", 397567: "Tx2", 497229: "Rx"}

for ln0, nm in TARGET.items():
    i = ln0 - 1
    print("=" * 70)
    print("%s  Polyline@%d" % (nm, ln0))
    # 打印 op 头部
    for k in range(i, i + 8):
        print("   %d: %s" % (k + 1, lines[k].rstrip()))
    # 段统计
    segs = Counter()
    seg_len = Counter()
    j = i
    mode = None
    cur = None
    cnt = 0
    samples = []
    while j < n and lines[j].strip() != "$end 'Operation'":
        s = lines[j].strip()
        if s == "$begin 'PolylineSegments'":
            mode = "seg"
        elif s == "$end 'PolylineSegments'":
            mode = None
        elif mode == "seg":
            m = re.match(r"SegmentType='([^']+)'", s)
            if m:
                if cur is not None:
                    seg_len[cur] += 1
                cur = m.group(1)
                segs[m.group(1)] += 1
                cnt += 1
                if len(samples) < 4:
                    samples.append(" ".join(x.strip() for x in lines[j:j + 6]))
        j += 1
    print("   段类型: %s   (段数=%d)" % (dict(segs), cnt))
    for s in samples:
        print("   样例: %s" % s)
    # 截面块原文
    for k in range(i, j + 40):
        if lines[k].strip() == "$begin 'PolylineXSection'":
            print("   截面原文 (%d):" % (k + 1))
            while lines[k].strip() != "$end 'PolylineXSection'":
                print("      %s" % lines[k].rstrip())
                k += 1
            print("      %s" % lines[k].rstrip())
            break
    # 尾部参数
    for k in range(i, j):
        if "IsPolyline" in lines[k] or "KernelVersion" in lines[k] or "NumPoints" in lines[k]:
            print("   %d: %s" % (k + 1, lines[k].rstrip()))
