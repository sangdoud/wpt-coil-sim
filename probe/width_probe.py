# -*- coding: utf-8 -*-
"""只读解析 Projecttonight.aedt：列出每个 GeometryPart 的名字 + 操作链 + 截面参数。
目的：确认 Tx1/Tx2/Rx 三个线圈实体当前的「线宽」定义在哪，改动影响面有多大。"""

import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\wpt\Projecttonight.aedt"

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    lines = f.readlines()

print("文件: %s  行数=%d" % (P, len(lines)))

# 找所有 GeometryPart 的区间
parts = []
for i, ln in enumerate(lines):
    if ln.strip() == "$begin 'GeometryPart'":
        parts.append(i)
print("GeometryPart 数: %d" % len(parts))

# 每个 part 的 Name（取 Attributes 里的 Name=）
def part_name(start):
    for k in range(start, min(start + 400, len(lines))):
        m = re.match(r"^\s*Name='([^']+)'\s*$", lines[k])
        if m:
            return m.group(1), k
    return "?", start

for idx, st in enumerate(parts):
    en = parts[idx + 1] if idx + 1 < len(parts) else len(lines)
    name, nline = part_name(st)
    ops = []
    for k in range(st, en):
        m = re.search(r"OperationType='([^']+)'", lines[k])
        if m:
            ops.append((m.group(1), k + 1))
    # 截面
    xs = None
    for k in range(st, en):
        if lines[k].strip() == "$begin 'PolylineXSection'":
            blk = {}
            j = k + 1
            while lines[j].strip() != "$end 'PolylineXSection'":
                if "=" in lines[j]:
                    a, b = lines[j].split("=", 1)
                    blk[a.strip()] = b.strip().strip("'")
                j += 1
            xs = blk
            break
    # 面/体
    nf = None
    for k in range(en - 1, st, -1):
        m = re.search(r"NumFaces=(\d+)", lines[k])
        if m:
            nf = int(m.group(1))
            break
    # 线点数
    npt = sum(1 for k in range(st, en) if lines[k].strip() == "$begin 'PLPoint'")
    print("")
    print("[%2d] %-12s 行%d-%d  面数=%s  线点数=%d" % (idx, name, st + 1, en, nf, npt))
    print("     操作: %s" % ", ".join("%s@%d" % (o, l) for o, l in ops))
    if xs:
        print("     截面: type=%s width=%s top=%s height=%s bend=%s"
              % (xs.get("XSectionType"), xs.get("XSectionWidth"),
                 xs.get("XSectionTopWidth"), xs.get("XSectionHeight"),
                 xs.get("XSectionBendType")))
    else:
        print("     截面: (无)")

# 所有 Polyline 操作的路径首尾点
print("")
print("=== 所有 Polyline 操作的路径首/尾点 ===")
for i, ln in enumerate(lines):
    if "OperationType='Polyline'" in ln:
        # 找所属 part
        owner = "?"
        for st in reversed(parts):
            if st < i:
                owner = part_name(st)[0]
                break
        pts = []
        k = i
        while k < len(lines) and lines[k].strip() != "$end 'Operation'":
            if lines[k].strip() == "$begin 'PLPoint'":
                x = lines[k + 1].split("'")[1]
                y = lines[k + 2].split("'")[1]
                z = lines[k + 3].split("'")[1]
                pts.append((x, y, z))
            k += 1
        if pts:
            print("  %-10s 行%-7d 点数=%-5d 首=%s 尾=%s"
                  % (owner, i + 1, len(pts), pts[0], pts[-1]))
