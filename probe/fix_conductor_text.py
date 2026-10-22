# -*- coding: utf-8 -*-
"""把 .aedt 里 6 个线圈端子的 Conductor number 从 12 改成 1。

已在先前的对照实验里验证过这种做法是安全的（AEDT 能正常加载，L 精确缩小 144 倍）。
"""

import os
import sys

P = r"C:\wpt\Projecttonight.aedt"
OLD = "'Conductor number'='12'"
NEW = "'Conductor number'='1'"
EXPECT = 12

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    txt = f.read()

n_old = txt.count(OLD)
n_new_before = txt.count(NEW)
print("文件中 %r 出现 %d 次（预期 %d）" % (OLD, n_old, EXPECT))
print("文件中 %r 已出现 %d 次（预期 0）" % (NEW, n_new_before))

if n_old != EXPECT:
    print("!! 次数不符，停下")
    sys.exit(1)
if n_new_before != 0:
    print("!! 已有 '1' 存在，可能重复执行过，停下")
    sys.exit(1)

txt2 = txt.replace(OLD, NEW)

a, b = txt.splitlines(), txt2.splitlines()
diffs = [i + 1 for i, (x, y) in enumerate(zip(a, b)) if x != y]
print("差异行数 %d，行号: %s" % (len(diffs), diffs))
print("总行数一致: %s" % (len(a) == len(b)))

if len(a) != len(b) or len(diffs) != EXPECT:
    print("!! 差异异常，停下")
    sys.exit(1)

with open(P, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
    f.write(txt2)

print()
print("已改写 %d 处 Conductor number: 12 -> 1" % n_old)
print("新文件大小:", os.path.getsize(P))
