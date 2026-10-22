# -*- coding: utf-8 -*-
"""查清 .aedt 里有哪些 design，以及 12 处 Conductor number 各属于哪个 design。"""

import re

P = r"C:\wpt\Projecttonight.aedt"

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    lines = f.readlines()

print("总行数:", len(lines))

# 找 design 边界：$begin 'Xxx' 里 Xxx 在 Designs 段内
# 先定位 $begin 'Designs'
designs_start = None
for i, l in enumerate(lines):
    if l.strip() == "$begin 'Designs'":
        designs_start = i
        break
print("Designs 段起始行:", (designs_start + 1) if designs_start is not None else None)

# 收集 design 名与起始行
designs = []
if designs_start is not None:
    depth = 0
    for i in range(designs_start, len(lines)):
        s = lines[i].strip()
        m = re.match(r"^\$begin '([^']+)'$", s)
        if m:
            depth += 1
            if depth == 2:   # Designs 下的第一层
                designs.append((m.group(1), i))
        elif s.startswith("$end '"):
            depth -= 1
            if depth == 0:
                break

print()
print("=== 检测到的 design ===")
for name, ln in designs:
    print("  行%-8d %s" % (ln + 1, name))

# 找 12 处 Conductor number
print()
print("=== 12 处 'Conductor number'='12' 的位置 ===")
occ = []
for i, l in enumerate(lines):
    if "'Conductor number'='12'" in l:
        occ.append(i + 1)
        print("  行%-8d %s" % (i + 1, l.strip()))

# 归属判定
print()
print("=== 归属 ===")
for ln in occ:
    owner = None
    for name, dln in designs:
        if dln + 1 <= ln:
            owner = name
    print("  行%-8d -> design %s" % (ln, owner))

print()
print("=== 附近上下文（每处前后 3 行） ===")
for ln in occ[:4]:
    print("  --- 行 %d ---" % ln)
    for j in range(max(0, ln - 4), min(len(lines), ln + 2)):
        print("    %7d: %s" % (j + 1, lines[j].rstrip()))
