# -*- coding: utf-8 -*-
"""核对第三版：解析活动设计所有 GeometryPart，把每个线圈「最后一次 Unite」的工具件
翻译成对应的 part，检查那个 part 的截面宽度是不是 2mm。

这是文本级的决定性证据：历史里虽然留着旧的 3mm 折线操作，
但最终合并进线圈实体的是最后一次 Unite 引用的那个工具件。
"""
import re
import sys
from collections import Counter

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\ansys maxwell2024\_work\Projecttonight.aedt"
with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    txt = f.read()

core = [m.start() for m in re.finditer(r"\$begin 'GeometryCore'", txt)]
seg = txt[core[-1]:]

pat = re.compile(r"\$begin 'GeometryPart'\s*\n\s*\$begin 'Attributes'\s*\n\s*Name='([^']+)'")
starts = [(m.start(), m.group(1)) for m in pat.finditer(seg)]
starts.append((len(seg), None))
print("GeometryPart 数 = %d" % (len(starts) - 1))

# op ID -> (part 名, 该 part 里的截面)
id2part = {}
part_info = {}
for i in range(len(starts) - 1):
    st, nm = starts[i]
    en = starts[i + 1][0]
    blk = seg[st:en]
    xs = re.findall(r"XSectionWidth='([^']+)'", blk)
    ops = re.findall(r"OperationType='([^']+)'", blk)
    ids = re.findall(r"^\s*ID=(\d+)\s*$", blk, re.M)
    part_info[nm] = dict(off=st, size=en - st, ops=ops, xs=xs, ids=ids)
    for oid in ids:
        id2part.setdefault(oid, nm)

print("")
print("=== 所有 part（按文件中出现顺序）===")
for nm, info in sorted(part_info.items(), key=lambda kv: kv[1]["off"]):
    if nm in ("Tx1", "Tx2", "Rx") or nm.startswith("TR_") or "CUT" in nm:
        print("  %-12s 偏移=%-9d 尺寸=%-9d 截面=%s 操作=%s"
              % (nm, info["off"], info["size"], info["xs"], info["ops"][:6]))

print("")
print("=== 每个线圈最后一次 Unite 引用的工具件 ===")
ok = True
for coil in ("Tx1", "Tx2", "Rx"):
    blk = seg[part_info[coil]["off"]:part_info[coil]["off"] + part_info[coil]["size"]]
    unites = list(re.finditer(r"OperationType='Unite'\s*\n\s*ID=(\d+)(.{0,600}?)ToolParts\(([^)]*)\)",
                              blk, re.S))
    if not unites:
        print("  %-4s 找不到 Unite" % coil)
        ok = False
        continue
    last = unites[-1]
    tools = [t.strip() for t in last.group(3).split(",") if t.strip()]
    print("  %-4s 最后一次 Unite 的工具件 id=%s" % (coil, tools))
    for t in tools:
        pn = id2part.get(t, "?")
        xs = part_info.get(pn, {}).get("xs")
        print("        id %-7s -> part %-12s 截面=%s" % (t, pn, xs))
        if pn == "?" or not xs or xs[-1] != "2mm":
            ok = False
print("")
print("总判定: %s" % ("最终合并进线圈的是 2mm 截面 ✓" if ok else "!! 不合格"))
sys.exit(0 if ok else 1)
