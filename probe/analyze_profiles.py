# -*- coding: utf-8 -*-
"""把 AEDT 各次求解的 .profile 汇总成一张表（ASCII 输出到文件）。

要回答两个问题：
  1) 每次求解的初始网格单元数/耗时、自适应趟数、每趟耗时 —— 用于解释耗时差异
  2) 换模板后重新求解时，初始网格是否被"继承"（若继承，同会话对照会被污染）
"""
import glob
import os
import re
import time

RES = r"C:\ansys maxwell2024\_work\Projecttonight_4ch.aedtresults\WPT_G.results"
OUT = r"C:\ansys maxwell2024\_work\profile_table.txt"

rows = []
for f in sorted(glob.glob(os.path.join(RES, "*.profile")), key=os.path.getmtime):
    txt = open(f, encoding="utf-8", errors="replace").read().splitlines()
    group = None
    elapsed = {}
    passes = []
    first_tets = None
    last_tets = None
    start = stop = None
    for ln in txt:
        m = re.search(r"Name='([^']+)'", ln)
        if m:
            group = m.group(1)
            if re.match(r"Pass \d+", group):
                passes.append([group, None])
            continue
        m = re.search(r"I\(1, 'Start Time', '([^']+)'\)", ln)
        if m and start is None:
            start = m.group(1)
        m = re.search(r"I\(1, 'Elapsed Time', '([^']+)'\)", ln)
        if m and group:
            elapsed[group] = m.group(1)
            continue
        m = re.search(r"ProfileItem\('([^']*)', (\d+), 0, (\d+), 0, (\d+), 'I\((\d+), (.*)\)'", ln)
        if m:
            name, cpu, el, mem, n, args = m.groups()
            tm = re.search(r"'Tetrahedra', (\d+)", args)
            t = int(tm.group(1)) if tm else None
            if t is not None and first_tets is None:
                first_tets = t
            if t is not None:
                last_tets = t
            if passes and name and name != "":
                passes[-1][1] = int(el)
            continue
        m = re.search(r"ProfileFootnote\('I\(\d+, 1, 'Stop Time', '([^']+)'", ln)
        if m:
            stop = m.group(1)
    rows.append(dict(file=os.path.basename(f),
                     mtime=time.strftime("%m-%d %H:%M:%S", time.localtime(os.path.getmtime(f))),
                     start=start, stop=stop,
                     init_el=elapsed.get("Initial Meshing"),
                     adapt_el=elapsed.get("Adaptive Meshing"),
                     mesh_s=None, coarsen_s=None,
                     first_tets=first_tets, last_tets=last_tets,
                     npass=len(passes), pass_s=[p[1] for p in passes]))
    # Mesh/Coarsen 明细
    for ln in txt:
        m = re.search(r"ProfileItem\('(Mesh|Coarsen)', (\d+), 0, (\d+)", ln)
        if m:
            if m.group(1) == "Mesh":
                rows[-1]["mesh_s"] = int(m.group(3))
            else:
                rows[-1]["coarsen_s"] = int(m.group(3))

lines = ["file | mtime | start | stop | initMesh_el | Mesh_s | Coarsen_s | tets_first | tets_last | npass | pass_el"]
for r in rows:
    lines.append("%s | %s | %s | %s | %s | %s | %s | %s | %s | %d | %s"
                 % (r["file"], r["mtime"], r["start"], r["stop"], r["init_el"],
                    r["mesh_s"], r["coarsen_s"], r["first_tets"], r["last_tets"],
                    r["npass"], r["pass_s"]))
open(OUT, "w", encoding="utf-8").write("\n".join(lines) + "\n")
