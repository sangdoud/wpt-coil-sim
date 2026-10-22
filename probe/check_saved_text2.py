# -*- coding: utf-8 -*-
"""核对存盘后的 .aedt（第二版）：
对活动设计 WPT_G 里的每个线圈 part，取「该 part 区间内最后一个 NumFaces/NumLumps」
（= 最终拓扑），并列出该 part 内出现的所有 XSectionWidth 值（按出现顺序）。"""
import re
import sys
from collections import Counter

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\ansys maxwell2024\_work\Projecttonight.aedt"
with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    txt = f.read()

core = [m.start() for m in re.finditer(r"\$begin 'GeometryCore'", txt)]
seg = txt[core[-1]:]
print("活动设计段(WPT_G) 字符数 = %d" % len(seg))

# 全段截面值统计
print("全段 XSectionWidth 统计: %s" % Counter(re.findall(r"XSectionWidth='([^']+)'", seg)))

parts = []
pat = re.compile(r"\$begin 'GeometryPart'\s*\n\s*\$begin 'Attributes'\s*\n\s*Name='([^']+)'")
for m in pat.finditer(seg):
    parts.append((m.start(), m.group(1)))
parts.append((len(seg), None))
print("GeometryPart 数 = %d" % (len(parts) - 1))

ok = True
for idx in range(len(parts) - 1):
    st, nm = parts[idx]
    en = parts[idx + 1][0]
    if nm not in ("Tx1", "Tx2", "Rx"):
        continue
    blk = seg[st:en]
    nf = re.findall(r"NumFaces=(\d+)", blk)
    nl = re.findall(r"NumLumps=(\d+)", blk)
    xs = re.findall(r"XSectionWidth='([^']+)'", blk)
    hs = re.findall(r"XSectionHeight='([^']+)'", blk)
    print("")
    print("part %-4s 字符长度=%-9d 最后一个 NumFaces=%s  NumLumps=%s"
          % (nm, len(blk), nf[-1] if nf else "?", nl[-1] if nl else "?"))
    print("        截面值序列: %s" % xs)
    print("        厚度值序列: %s" % hs)
    print("        操作序列: %s" % re.findall(r"OperationType='([^']+)'", blk)[-8:])
    good = (nf and nf[-1] in ("1548", "1544") and nl and nl[-1] == "1"
            and xs and xs[-1] == "2mm")
    ok = ok and bool(good)

# 端子
bseg = txt[txt.rfind("$begin 'BoundarySetup'"):]
print("")
for nm in ("CT_Tx1_P", "CT_Tx1_N", "CT_Tx2_P", "CT_Tx2_N", "CT_Rx_P", "CT_Rx_N"):
    j = bseg.find("$begin '%s'" % nm)
    if j < 0:
        print("  端子 %-10s 未找到" % nm)
        ok = False
        continue
    blk = bseg[j:j + 700]
    w = re.search(r"Winding=(-?\d+)", blk)
    c = re.search(r"'Conductor number'='([^']*)'", blk)
    fa = re.search(r"Faces\((\d+)\)", blk)
    good = bool(w) and int(w.group(1)) > 0 and bool(c) and c.group(1) == "1"
    ok = ok and good
    print("  端子 %-10s Faces=%-6s Winding=%-4s Conductor=%-3s %s"
          % (nm, fa.group(1) if fa else "?", w.group(1) if w else "?",
             c.group(1) if c else "?", "OK" if good else "<== 不对"))

print("")
print("总判定: %s" % ("全部通过" if ok else "!! 有项目不合格"))
sys.exit(0 if ok else 1)
