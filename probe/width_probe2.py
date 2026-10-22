# -*- coding: utf-8 -*-
"""解析 .aedt：设计名、各 part 的 Unite 工具件、所有 Cylinder 参数。
用来确认：活动设计是哪一个；Tx/Rx 引线的精确几何（半径/起点/高度）。"""

import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\wpt\Projecttonight.aedt"

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    lines = f.readlines()

n = len(lines)
print("行数 = %d" % n)

# ---- 设计名 ----
print("\n=== 设计块 (GeometryCore / design name) ===")
for i, ln in enumerate(lines):
    if ln.strip() == "$begin 'GeometryCore'":
        # 往前找 Name=
        nm = None
        for k in range(i, max(0, i - 60), -1):
            m = re.match(r"^\s*Name='([^']+)'\s*$", lines[k])
            if m:
                nm = m.group(1)
                break
        print("  行%-7d GeometryCore, 上方最近的 Name=%s" % (i + 1, nm))

print("\n=== 所有 Name= 出现的行（前 20）===")
cnt = 0
for i, ln in enumerate(lines):
    m = re.match(r"^\s*Name='([^']+)'\s*$", ln)
    if m and lines[i - 1].strip() in ("$begin 'Attributes'", "$begin 'DesignSettings'") or (m and "DesignName" in lines[i - 1]):
        pass
for i, ln in enumerate(lines):
    if "DesignName=" in ln:
        print("  行%-7d %s" % (i + 1, ln.strip()))
        cnt += 1
        if cnt > 20:
            break

# ---- 所有 Cylinder 操作 ----
print("\n=== 所有 Cylinder 操作 ===")
for i, ln in enumerate(lines):
    if "OperationType='Cylinder'" in ln:
        d = {}
        j = i
        while j < min(i + 400, n) and lines[j].strip() != "$end 'Operation'":
            for key in ("XCenter", "YCenter", "ZCenter", "Radius", "Height",
                        "WhichAxis", "XDim", "YDim", "ZDim", "Name="):
                if lines[j].strip().startswith(key):
                    d[lines[j].strip().split("=")[0]] = lines[j].strip().split("=", 1)[1].strip().strip("'")
            j += 1
        print("  行%-7d axis=%s c=(%s,%s,%s) r=%s h=%s" %
              (i + 1, d.get("WhichAxis"), d.get("XCenter"), d.get("YCenter"),
               d.get("ZCenter"), d.get("Radius"), d.get("Height")))

# ---- 各 part 的 Unite / Substract 工具件 ----
print("\n=== Unite / Substract 操作 ===")
for i, ln in enumerate(lines):
    m = re.search(r"OperationType='(Unite|Substract)'", ln)
    if m:
        blk = " ".join(x.strip() for x in lines[i:i + 12])
        mm = re.search(r"ToolParts\(([^)]*)\)", blk)
        bm = re.search(r"BlankPart=(\d+)", blk)
        print("  行%-7d %-9s Blank=%s Tool=(%s)" % (i + 1, m.group(1),
                                                   bm.group(1) if bm else "?", mm.group(1) if mm else ""))
