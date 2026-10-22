# -*- coding: utf-8 -*-
"""从 .aedt 提取 6 根引线 + 线圈对象的关键几何。"""

import re
import sys

P = sys.argv[1] if len(sys.argv) > 1 else r"C:\wpt\Projecttonight.aedt"
print("模型:", P)

with open(P, "r", encoding="utf-8", errors="surrogateescape") as f:
    lines = f.readlines()

# 找每个 GeometryPart 的 Name + 紧随的 CylinderParameters
parts = []
i = 0
while i < len(lines):
    s = lines[i].strip()
    m = re.match(r"^Name='([^']+)'$", s)
    if m:
        name = m.group(1)
        # 往后找 40 行内的 Cylinder / Box / Polyline 参数
        blk = lines[i:i + 45]
        joined = "".join(blk)
        if "CylinderParameters" in joined:
            def g(k):
                mm = re.search(k + r"='([^']*)'", joined)
                return mm.group(1) if mm else None
            parts.append(dict(kind="Cylinder", name=name,
                              x=g("XCenter"), y=g("YCenter"), z=g("ZCenter"),
                              r=g("Radius"), h=g("Height"), ax=g("WhichAxis")))
        elif "BoxParameters" in joined:
            def g2(k):
                mm = re.search(k + r"='([^']*)'", joined)
                return mm.group(1) if mm else None
            parts.append(dict(kind="Box", name=name,
                              x=g2("XPosition"), y=g2("YPosition"), z=g2("ZPosition"),
                              xs=g2("XSize"), ys=g2("YSize"), zs=g2("ZSize")))
    i += 1

print("=== 引线对象 ===")
print("  %-14s %10s %10s %10s %8s %8s %5s" % ("名称", "X", "Y", "Z底", "半径", "高度", "轴"))
leads = [p for p in parts if p["name"].startswith("lead_")]
for p in sorted(leads, key=lambda q: q["name"]):
    z0 = float(p["z"].replace("mm", ""))
    h = float(p["h"].replace("mm", ""))
    print("  %-14s %10s %10s %10s %8s %8s %5s   -> z: %.1f ~ %.1f"
          % (p["name"], p["x"], p["y"], p["z"], p["r"], p["h"], p["ax"], z0, z0 + h))

print()
print("=== 线圈对象（找几何类型） ===")
for nm in ("Tx1", "Tx2", "Rx", "Region"):
    hits = [p for p in parts if p["name"] == nm]
    if hits:
        for p in hits:
            print("  %-8s %s %s" % (nm, p["kind"], {k: v for k, v in p.items() if k not in ("kind", "name")}))
    else:
        print("  %-8s (未在 GeometryPart 里匹配到，可能是 Polyline 或 UnitOperation)" % nm)

print()
print("=== 铁氧体条数量 ===")
fer = [p for p in parts if p["name"].startswith("ferrite_")]
print("  共 %d 条" % len(fer))
for p in fer[:3]:
    print("   ", p)
if len(fer) > 3:
    print("    ...")

print()
print("=== 与引线相关的 Z 区间（对照铁氧体） ===")
ths = [p for p in parts if p["name"].startswith("ferrite_")]
if ths:
    zlo = min(float(p["z"].replace("mm", "")) for p in ths)
    zhi = max(float(p["z"].replace("mm", "")) + float(p["zs"].replace("mm", "")) for p in ths)
    print("  铁氧体 z 范围: %.1f ~ %.1f" % (zlo, zhi))
for p in sorted(leads, key=lambda q: q["name"]):
    z0 = float(p["z"].replace("mm", "")); h = float(p["h"].replace("mm", ""))
    print("  %-14s z %.1f ~ %.1f" % (p["name"], z0, z0 + h))
