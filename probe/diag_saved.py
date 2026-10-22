# -*- coding: utf-8 -*-
"""诊断：存盘后的 .aedt 里每个 GeometryCore 属于哪个设计、线圈截面各是多少。"""
import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\ansys maxwell2024\_work\Projecttonight.aedt"
with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    txt = f.read()
print("字符数 %d" % len(txt))

blocks = [m.start() for m in re.finditer(r"\$begin 'GeometryCore'", txt)]
print("GeometryCore 段数 = %d" % len(blocks))

for bi, st in enumerate(blocks):
    en = blocks[bi + 1] if bi + 1 < len(blocks) else len(txt)
    seg = txt[st:en]
    # 设计名：向前找最近的 Name='xxx'
    head = txt[max(0, st - 200000):st]
    names = re.findall(r"Name='([^']+)'", head)
    dname = names[-1] if names else "?"
    # 也看看 DesignName
    print("")
    print("[%d] 偏移 %d..%d  长度 %d  上方最近 Name=%s" % (bi, st, en, len(seg), dname))
    for nm in ("Tx1", "Tx2", "Rx"):
        i = seg.find("Name='%s'" % nm)
        if i < 0:
            print("     %-4s 无" % nm)
            continue
        blk = seg[i:i + 400000]
        w = re.search(r"XSectionWidth='([^']+)'", blk)
        h = re.search(r"XSectionHeight='([^']+)'", blk)
        lumps = re.search(r"NumLumps=(\d+)", blk)
        faces = re.search(r"NumFaces=(\d+)", blk)
        npt = blk.count("$begin 'PLPoint'")
        print("     %-4s width=%-6s h=%-6s NumLumps=%-3s NumFaces=%-5s 点数=%d"
              % (nm, w.group(1) if w else "?", h.group(1) if h else "?",
                 lumps.group(1) if lumps else "?", faces.group(1) if faces else "?", npt))

# 所有 DesignName 出现位置
print("")
print("=== DesignName 出现处 ===")
for m in re.finditer(r"DesignName='([^']+)'", txt):
    print("  偏移 %d : %s" % (m.start(), m.group(1)))
