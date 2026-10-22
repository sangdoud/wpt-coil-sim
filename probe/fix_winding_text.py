# -*- coding: utf-8 -*-
"""直接改 .aedt 文本：把重建端子的 ParentBndID / Winding 从 -1 改成对应绕组 ID。

背景：pyAEDT 的 props+update() 没能真正建立端子->绕组 的父子关系，
     求解仍报 'Excitation CT_Tx2_P is not assigned to any winding.'
     而原模型的 .aedt 里这两个字段都是绕组 ID（如 ParentBndID=9, Winding=9）。
"""

import os
import re
import shutil

DST = r"C:\wpt\_test_run\Projecttonight_newlead.aedt"
BAK = r"C:\wpt\_test_run\Projecttonight_newlead_before_txtfix.aedt"

# 端子 -> 绕组 ID
WID = {"CT_Tx1_P": 9, "CT_Tx1_N": 9, "CT_Tx2_P": 12, "CT_Tx2_N": 12,
       "CT_Rx_P": 15, "CT_Rx_N": 15}

shutil.copyfile(DST, BAK)
print("备份 -> %s" % BAK)

with open(DST, "r", encoding="utf-8", errors="surrogateescape") as f:
    txt = f.read()

print()
print("=== 改前：6 个 CT_ 块的内容 ===")
changed = 0
for name, wid in WID.items():
    m = re.search(r"\$begin '%s'\n(.*?)\$end '%s'" % (re.escape(name), re.escape(name)), txt, re.S)
    if not m:
        print("  %-12s 找不到块！" % name)
        continue
    body = m.group(1)
    pb = re.search(r"ParentBndID=(-?\d+)", body)
    wd = re.search(r"Winding=(-?\d+)", body)
    print("  %-12s ParentBndID=%-4s Winding=%-4s  -> 应为 %d"
          % (name, pb.group(1) if pb else "?", wd.group(1) if wd else "?", wid))

# 逐个块替换
for name, wid in WID.items():
    pat = re.compile(r"(\$begin '%s'\n)(.*?)(\$end '%s')" % (re.escape(name), re.escape(name)), re.S)

    def fix(mo):
        global changed
        head, body, tail = mo.group(1), mo.group(2), mo.group(3)
        nb = re.sub(r"ParentBndID=-?\d+", "ParentBndID=%d" % wid, body)
        nb = re.sub(r"Winding=-?\d+", "Winding=%d" % wid, nb)
        if nb != body:
            changed += 1
        return head + nb + tail

    txt, n = pat.subn(fix, txt)
    if n == 0:
        print("  !! %s 未替换" % name)

with open(DST, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
    f.write(txt)

print()
print("已修改 %d 个端子块；文件大小 %d" % (changed, os.path.getsize(DST)))

print()
print("=== 改后核对 ===")
with open(DST, "r", encoding="utf-8", errors="surrogateescape") as f:
    txt2 = f.read()
for name, wid in WID.items():
    m = re.search(r"\$begin '%s'\n(.*?)\$end '%s'" % (re.escape(name), re.escape(name)), txt2, re.S)
    if not m:
        continue
    body = m.group(1)
    pb = re.search(r"ParentBndID=(-?\d+)", body)
    wd = re.search(r"Winding=(-?\d+)", body)
    good = pb and wd and pb.group(1) == str(wid) and wd.group(1) == str(wid)
    print("  %-12s ParentBndID=%-4s Winding=%-4s %s"
          % (name, pb.group(1) if pb else "?", wd.group(1) if wd else "?",
             "OK" if good else "<== 没对"))
