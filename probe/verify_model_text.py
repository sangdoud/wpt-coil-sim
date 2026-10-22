# -*- coding: utf-8 -*-
"""不打开 AEDT，直接从 .aedt 文本核对模型关键状态：
  - 6 个 CoilTerminal 的 Winding 链接 + Conductor number
  - Winding Group 的类型/电流
  - Region 的 padding
  - Tx1/Tx2/Rx 的 Z 范围（从 Polyline/圆柱 不易读，这里只报 Region 与端子面）
"""

import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\wpt\Projecttonight.aedt"
print("模型:", P)

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    txt = f.read()
print("大小: %d 字符" % len(txt))

i = txt.rfind("$begin 'BoundarySetup'")
seg = txt[i:]
print("权威 BoundarySetup 位于字符 %d" % i)

print("\n=== CoilTerminal ===")
ok = True
for nm in ("CT_Tx1_P", "CT_Tx1_N", "CT_Tx2_P", "CT_Tx2_N", "CT_Rx_P", "CT_Rx_N"):
    j = seg.find("$begin '%s'" % nm)
    if j < 0:
        print("  %-10s 未找到" % nm)
        ok = False
        continue
    blk = seg[j:j + 700]
    w = re.search(r"Winding=(-?\d+)", blk)
    c = re.search(r"'Conductor number'='([^']*)'", blk)
    fa = re.search(r"Faces\((\d+)\)", blk)
    pot = re.search(r"'Point out of terminal'=(\w+)", blk)
    wid = int(w.group(1)) if w else None
    cond = c.group(1) if c else "?"
    good = (wid is not None and wid > 0 and cond == "1")
    ok = ok and good
    print("  %-10s Faces=%-7s Winding=%-4s Conductor=%-3s PointOut=%-6s %s"
          % (nm, fa.group(1) if fa else "?", wid, cond,
             pot.group(1) if pot else "?", "OK" if good else "<== 有问题"))

print("\n=== Winding Group ===")
for nm in ("Winding_Tx1", "Winding_Tx2", "Winding_Rx"):
    j = seg.find("$begin '%s'" % nm)
    if j < 0:
        print("  %-12s 未找到" % nm)
        continue
    blk = seg[j:j + 700]
    t = re.search(r"Type='([^']*)'", blk)
    cu = re.search(r"Current='([^']*)'", blk)
    so = re.search(r"IsSolid=(\w+)", blk)
    print("  %-12s Type=%-8s Current=%-6s IsSolid=%s"
          % (nm, t.group(1) if t else "?", cu.group(1) if cu else "?", so.group(1) if so else "?"))

print("\n=== Region padding ===")
j = txt.rfind("$begin 'RegionParameters'")
blk = txt[j:j + 900]
for k in ("+X", "-X", "+Y", "-Y", "+Z", "-Z"):
    m = re.search(re.escape("'%sPadding'" % k) + r"='([^']*)'", blk)
    print("  %sPadding = %s" % (k, m.group(1) if m else "?"))

print("\n结果: %s" % ("全部正常" if ok else "!! 有问题"))
sys.exit(0 if ok else 1)
