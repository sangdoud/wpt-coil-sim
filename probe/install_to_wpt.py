# -*- coding: utf-8 -*-
r"""把工作区改好的 2mm 模型装回生产目录，并同步批次脚本的 COIL_SIZE。

 1) 备份 C:\wpt 原模型 -> C:\wpt\backup\before_width2\
 2) 用工作区里改好的模型覆盖 C:\wpt\Projecttonight.aedt
 3) 把 batch_sweep_unit30.py 的 COIL_SIZE 改成改造后实测的线圈外尺寸
    （这样 tg 仍然 = 两个发射线圈之间的间隙，语义不变）
 4) 文本核对：每个线圈「最后一次 Unite」的工具件截面 = 2mm、最终 NumFaces/NumLumps、
    6 个端子且挂上绕组
"""
import hashlib
import json
import os
import re
import shutil
import sys
import time

WORK = r"C:\ansys maxwell2024\_work"
WPT = r"C:\wpt"
NEW = os.path.join(WORK, "Projecttonight.aedt")
OLD = os.path.join(WPT, "Projecttonight.aedt")
BK = os.path.join(WPT, "backup", "before_width2")
BATCH = os.path.join(WPT, "batch_sweep_unit30.py")
RESULT = os.path.join(WORK, "rebuild_result.json")

EXPECT_FACES = {"Tx1": "1548", "Tx2": "1548", "Rx": "1544"}


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def log(m):
    print("%s | %s" % (time.strftime("%H:%M:%S"), m), flush=True)


def verify(path):
    """文本核对，返回 (ok, 报告行列表)。"""
    out = []
    ok = True
    with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
        txt = f.read()
    core = [m.start() for m in re.finditer(r"\$begin 'GeometryCore'", txt)]
    seg = txt[core[-1]:]

    pat = re.compile(r"\$begin 'GeometryPart'\s*\n\s*\$begin 'Attributes'\s*\n\s*Name='([^']+)'")
    starts = [(m.start(), m.group(1)) for m in pat.finditer(seg)]
    starts.append((len(seg), None))
    info, id2part = {}, {}
    for i in range(len(starts) - 1):
        st, nm = starts[i]
        blk = seg[st:starts[i + 1][0]]
        xs = re.findall(r"XSectionWidth='([^']+)'", blk)
        nf = re.findall(r"NumFaces=(\d+)", blk)
        nl = re.findall(r"NumLumps=(\d+)", blk)
        info[nm] = dict(blk=blk, xs=xs, nf=nf[-1] if nf else "?",
                        nl=nl[-1] if nl else "?", off=st)
        for oid in re.findall(r"ParentPartID=(\d+)", blk):
            id2part.setdefault(oid, nm)
        for oid in re.findall(r"^\s*ID=(\d+)\s*$", blk, re.M):
            id2part.setdefault(oid, nm)

    for coil in ("Tx1", "Tx2", "Rx"):
        if coil not in info:
            out.append("  %-4s part 不存在" % coil)
            ok = False
            continue
        blk = info[coil]["blk"]
        un = list(re.finditer(r"OperationType='Unite'\s*\n\s*ID=(\d+)(.{0,600}?)ToolParts\(([^)]*)\)",
                              blk, re.S))
        tools = [t.strip() for t in un[-1].group(3).split(",") if t.strip()] if un else []
        tnames = [id2part.get(t, "?") for t in tools]
        txs = [info.get(n, {}).get("xs") for n in tnames]
        good = (len(tools) == 1 and txs[0] and txs[0][-1] == "2mm"
                and info[coil]["nf"] == EXPECT_FACES[coil] and info[coil]["nl"] == "1")
        ok = ok and good
        out.append("  %-4s 最后 Unite 工具件=%-12s 截面=%-6s 最终 NumFaces=%-5s NumLumps=%-3s %s"
                   % (coil, tnames[0] if tnames else "?", txs[0][-1] if txs and txs[0] else "?",
                      info[coil]["nf"], info[coil]["nl"], "OK" if good else "<== 不对"))
        # 路径段类型
        s0 = blk.find("$begin 'PolylineSegments'")
        s1 = blk.find("$end 'PolylineSegments'", s0)
        if s0 > 0:
            nl_line = blk[s0:s1].count("SegmentType='Line'")
            other = len(re.findall(r"SegmentType='(?!Line)", blk[s0:s1]))
            out.append("       原始路径段: Line=%d 其它=%d（应 767/0）" % (nl_line, other))
            ok = ok and nl_line == 767 and other == 0

    bseg = txt[txt.rfind("$begin 'BoundarySetup'"):]
    for nm in ("CT_Tx1_P", "CT_Tx1_N", "CT_Tx2_P", "CT_Tx2_N", "CT_Rx_P", "CT_Rx_N"):
        j = bseg.find("$begin '%s'" % nm)
        if j < 0:
            out.append("  端子 %-10s 未找到" % nm)
            ok = False
            continue
        blk = bseg[j:j + 700]
        w = re.search(r"Winding=(-?\d+)", blk)
        c = re.search(r"'Conductor number'='([^']*)'", blk)
        fa = re.search(r"Faces\((\d+)\)", blk)
        good = bool(w) and int(w.group(1)) > 0 and bool(c) and c.group(1) == "1"
        ok = ok and good
        out.append("  端子 %-10s Faces=%-6s Winding=%-4s Conductor=%-3s %s"
                   % (nm, fa.group(1) if fa else "?", w.group(1) if w else "?",
                      c.group(1) if c else "?", "OK" if good else "<== 不对"))
    return ok, out


assert os.path.exists(NEW), NEW
with open(RESULT, encoding="utf-8") as f:
    res = json.load(f)
if res.get("error") or not res.get("saved"):
    print("!! 流水线结果是失败/未存盘状态，拒绝安装")
    sys.exit(1)

new_size = res["new_sizes"]["Tx1"]["x"]
log("改造后 Tx1 X 外尺寸 = %.4f mm（原 168.88）" % new_size)

log("")
log("=== 安装前先在副本上核对 ===")
ok0, lines = verify(NEW)
for l in lines:
    print(l)
if not ok0:
    print("!! 工作区副本核对不通过，拒绝安装")
    sys.exit(1)

os.makedirs(BK, exist_ok=True)
shutil.copy2(OLD, os.path.join(BK, "Projecttonight.aedt"))
shutil.copy2(BATCH, os.path.join(BK, "batch_sweep_unit30.py"))
old_md5 = md5(OLD)
log("")
log("已备份 -> %s" % BK)
log("原模型 md5 = %s  大小 %d bytes" % (old_md5, os.path.getsize(os.path.join(BK, "Projecttonight.aedt"))))

shutil.copy2(NEW, OLD)
os.chmod(OLD, 0o666)
new_md5 = md5(OLD)
log("新模型 md5 = %s  大小 %d bytes" % (new_md5, os.path.getsize(OLD)))

with open(BATCH, encoding="utf-8") as f:
    src = f.read()
m = re.search(r"^COIL_SIZE = ([0-9.]+)\s*(#.*)$", src, re.M)
if not m:
    log("!! 在 batch 脚本里找不到 COIL_SIZE 行")
    sys.exit(1)
old_val = m.group(1)
new_line = ("COIL_SIZE = %.2f          # 发射线圈外尺寸（WPT_G 实测；线宽 3mm->2mm 后 "
            "由 168.90 变 %.2f）" % (new_size, new_size))
with open(BATCH, "w", encoding="utf-8") as f:
    f.write(src[:m.start()] + new_line + src[m.end():])
log("batch_sweep_unit30.py: COIL_SIZE %s -> %.2f" % (old_val, new_size))

log("")
log("=== 安装后核对（读 C:\\wpt 上的正式模型）===")
ok1, lines1 = verify(OLD)
for l in lines1:
    print(l)

json.dump({"old_md5": old_md5, "new_md5": new_md5, "new_size_x": new_size,
           "coil_size_old": old_val, "verify_before": ok0, "verify_after": ok1},
          open(os.path.join(WORK, "install_result.json"), "w"), indent=2)
log("")
log("安装结果: %s" % ("成功" if ok1 else "!! 核对不通过"))
sys.exit(0 if ok1 else 1)
