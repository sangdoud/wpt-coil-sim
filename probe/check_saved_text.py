# -*- coding: utf-8 -*-
"""文本核对改造后的 .aedt（只读）：三个线圈截面=2mm、单连通、全直线段、6 个端子挂上绕组。"""
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\ansys maxwell2024\_work\Projecttonight.aedt"

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    txt = f.read()
print("文件 %s  字符数 %d" % (P, len(txt)))

blocks = [m.start() for m in re.finditer(r"\$begin 'GeometryCore'", txt)]
print("GeometryCore 段数 = %d（最后一段 = 活动设计 WPT_G）" % len(blocks))
seg = txt[blocks[-1]:]
bseg = txt[txt.rfind("$begin 'BoundarySetup'"):]

ok = True
for nm in ("Tx1", "Tx2", "Rx"):
    i = seg.find("Name='%s'" % nm)
    if i < 0:
        print("  %-4s 未找到" % nm)
        ok = False
        continue
    blk = seg[i:i + 400000]
    w = re.search(r"XSectionWidth='([^']+)'", blk)
    tw = re.search(r"XSectionTopWidth='([^']+)'", blk)
    h = re.search(r"XSectionHeight='([^']+)'", blk)
    orient = re.search(r"XSectionOrient='([^']+)'", blk)
    bend = re.search(r"XSectionBendType='([^']+)'", blk)
    lumps = re.search(r"NumLumps=(\d+)", blk)
    faces = re.search(r"NumFaces=(\d+)", blk)
    s0 = blk.find("$begin 'PolylineSegments'")
    s1 = blk.find("$end 'PolylineSegments'", s0)
    nline = blk[s0:s1].count("SegmentType='Line'")
    nother = len(re.findall(r"SegmentType='(?!Line)", blk[s0:s1]))
    npt = blk.count("$begin 'PLPoint'")
    good = (w and w.group(1) == "2mm" and h and h.group(1) == "0.5mm"
            and lumps and lumps.group(1) == "1" and nline == 767 and nother == 0)
    ok = ok and bool(good)
    print("  %-4s width=%-5s top=%-5s height=%-6s orient=%-5s bend=%-7s "
          "NumLumps=%-3s NumFaces=%-5s 点数=%-4d Line段=%d 其它段=%d  %s"
          % (nm, w.group(1) if w else "?", tw.group(1) if tw else "?",
             h.group(1) if h else "?", orient.group(1) if orient else "?",
             bend.group(1) if bend else "?", lumps.group(1) if lumps else "?",
             faces.group(1) if faces else "?", npt, nline, nother,
             "OK" if good else "<== 不对"))

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
