# -*- coding: utf-8 -*-
"""Tx1 / Tx2 激励引线改成 L 形：先竖直离开线圈一小段，再沿 XOY 面 -Y 直着出去。

  Tx1: 线圈端面(z=0) -> 竖直向上 VERT -> 沿 -Y 水平走到 y_end
  Tx2: 线圈端面(z=0) -> 竖直向下 VERT -> 沿 -Y 水平走到 y_end
  Rx : 不动（仍然竖直向上穿铁氧体，脚本开孔）

  线圈沿 X 排列(Tx1/Tx2 中心距 198.9mm)，引线沿 Y 出去正好垂直于排列方向，
  不会进入两个线圈的重叠区。

这样 Tx1 引线全程在 z=+2 附近、Tx2 全程在 z=-2 附近，
两个发射线圈在 XOY 面重叠时引线上下错开，互不相交。

对每个线圈:
  0. 记录端子面的 (x, y) 与极性，以及绕组名
  1. 用两个大盒子切掉 z<-0.3 / z>+0.3 的一切，只留线圈铜带本体
  2. 建 L 形引线（竖直圆柱 + 沿 X 的水平圆柱）
  3. unite -> 端子会被摧毁
  4. 在 x=x_end 的新端面上重建端子
  5. add_winding_coils 挂回绕组
  6. 复核，全部通过才存盘
"""

import os
import re
import shutil
import subprocess
import sys
import time

from ansys.aedt.core import Desktop, Maxwell3d

WPT = r"C:\wpt"
PROJ = os.path.join(WPT, "Projecttonight.aedt")
BK = os.path.join(WPT, "backup", "before_leads_bothdown")
DESIGN = "WPT_G"

VERT = 2.0          # 竖直段高度 mm
# 水平段终点 = 线圈中心 y - Y_OUT。
# 取 -134.94 (= 原模型 Region 的 -Y 面: 铁氧体/线圈最低 y=-84.94 再 pad 50mm)，
# 这样配 -YPadding=0 后区域 -Y 面正好落在端子面上，而空气域和原来完全一样。
Y_OUT = 133.815
RAD = 0.3
AREA = 3.14159265 * RAD * RAD

# Region padding: [+X, -X, +Y, -Y, +Z, -Z]
# 原模型是 [50,50,50,50,0,0]：±Z 为 0 是为了让端子面正好落在区域边界上
# （Maxwell 把线端端子当 external terminal，必须贴在区域边界上）。
# 现在端子面在 -Y 方向，所以改成 -Y padding=0；-Z 给 5mm 把底面补回原来的 -45。
PAD = ["50mm", "50mm", "50mm", "0mm", "0mm", "5mm"]

UP = {"Tx1": -1.0, "Tx2": -1.0}     # +1 向上, -1 向下
# 判别实验：Tx1 也改成向下（原来 +1 向上）。
# 目的：确认 L11 掉 14.5% 是不是由「引线在线圈上侧」造成的。
# 若 L11 回到 ~23.3，则上下交错可以改成「两根都向下、但下探深度不同」。

DRY = "--apply" not in sys.argv


def log(m):
    print(m, flush=True)


os.makedirs(BK, exist_ok=True)

# 先清干净：残留的 ansysedt 和 .lock 会让 pyAEDT 打不开工程
subprocess.run(["taskkill", "/F", "/IM", "ansysedt.exe"],
               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)
for _n in os.listdir(WPT):
    if _n.endswith(".lock"):
        try:
            os.remove(os.path.join(WPT, _n))
            log_early = "removed lock: " + _n
        except Exception:
            pass

shutil.copyfile(PROJ, os.path.join(BK, "Projecttonight.aedt"))
os.chmod(PROJ, 0o666)
log("已备份模型 -> %s" % BK)
log("参数: VERT=%.1f mm, Y_OUT=%.1f mm (线圈中心起算, 方向 -Y)" % (VERT, Y_OUT))
log("模式: %s" % ("DRY-RUN（不会存盘）" if DRY else "APPLY（会存盘）"))

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=PROJ, design=DESIGN)
log("design=%s solution=%s" % (m.design_name, m.solution_type))

# ---------------- 0. 记录端子 ----------------
log("")
log("=== 0. 记录 Tx1 / Tx2 端子 ===")
info = {}
for coil in ("Tx1", "Tx2"):
    fmap = {}
    for f in m.modeler[coil].faces:
        try:
            fmap[f.id] = (tuple(f.center), f.area)
        except Exception:
            pass
    bb = m.modeler[coil].bounding_box
    terms = {}
    for b in m.boundaries:
        if not b.name.startswith("CT_" + coil + "_"):
            continue
        fid = (b.props.get("Faces") or [None])[0]
        c, a = fmap.get(fid, (None, None))
        if c is None:
            log("  !! %s 找不到面 %s" % (b.name, fid))
            continue
        pol = "negative" if b.props.get("Point out of terminal") in (True, "true") else "positive"
        terms[b.name] = dict(x=c[0], y=c[1], z=c[2], polarity=pol)
        log("  %-12s center=(%.4f, %.4f, %.4f) area=%.6f 极性=%s"
            % (b.name, c[0], c[1], c[2], a, pol))
    info[coil] = dict(terms=terms, bbox=[round(v, 2) for v in bb])
    log("  %s bbox=%s" % (coil, info[coil]["bbox"]))

# ---------------- 1. 切成只剩线圈铜带 ----------------
log("")
log("=== 1. 切掉铜带以外的引线（z<-0.3 与 z>+0.3）===")
for coil in ("Tx1", "Tx2"):
    for tag, org, sz in (("LO", [-400.0, -400.0, -60.0], [800.0, 800.0, 59.7]),
                         ("HI", [-400.0, -400.0, 0.3], [800.0, 800.0, 60.0])):
        cut = m.modeler.create_box(origin=org, sizes=sz, name="CUT_%s_%s" % (coil, tag))
        m.modeler.subtract(blank_list=[coil], tool_list=[cut.name], keep_originals=False)
        if cut.name in m.modeler.object_names:
            m.modeler.delete(cut.name)
    bb = m.modeler[coil].bounding_box
    log("  %s -> X[%.2f,%.2f] Y[%.2f,%.2f] Z[%.2f,%.2f]"
        % (coil, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))
    # 线圈中心必须用「切掉引线之后」的 bbox 算，否则引线会把中心带偏
    info[coil]["cx"] = (bb[0] + bb[3]) / 2.0
    info[coil]["cy"] = (bb[1] + bb[4]) / 2.0
    log("     -> 线圈中心 (%.3f, %.3f)  半宽 %.2f x %.2f"
        % (info[coil]["cx"], info[coil]["cy"],
           (bb[3] - bb[0]) / 2.0, (bb[4] - bb[1]) / 2.0))

# 校验：记录到的端子 (x,y) 必须落在线圈轮廓内，否则说明读到了引线末端
log("")
log("=== 1.5 校验端子位置是否在线圈内 ===")
for coil in ("Tx1", "Tx2"):
    bb = m.modeler[coil].bounding_box
    for name, t in sorted(info[coil]["terms"].items()):
        inside = (bb[0] - 1.0 <= t["x"] <= bb[3] + 1.0 and
                  bb[1] - 1.0 <= t["y"] <= bb[4] + 1.0)
        log("  %-12s (%.3f, %.3f) 在线圈轮廓内: %s" % (name, t["x"], t["y"], inside))
        if not inside:
            log("  !! 端子不在线圈轮廓内 —— 多半是拿一个「引线已经改过」的模型在跑。")
            log("     请先用 backup\\before_leads_L\\Projecttonight.aedt 还原成原始引线模型再跑。")
            sys.exit(1)

# ---------------- 2. 建 L 形引线 ----------------
log("")
log("=== 2. 建 L 形引线 ===")
newobjs = {}
for coil in ("Tx1", "Tx2"):
    sgn = UP[coil]
    zrun = sgn * VERT
    y_end = info[coil]["cy"] - Y_OUT
    objs = []
    for name, t in sorted(info[coil]["terms"].items()):
        x, y = t["x"], t["y"]
        # 竖直段：从线圈里 z=-0.5 一直到 z=zrun
        z0 = -0.5 if sgn > 0 else zrun
        h = (zrun + 0.5) if sgn > 0 else (0.5 - zrun)
        v = m.modeler.create_cylinder(orientation="Z", origin=[x, y, z0],
                                      radius=RAD, height=h, name="LD_%s_V" % name)
        # 水平段：沿 -Y，从 y_end 到 y+0.3（盖住竖直段轴线，保证连成一体）
        hy = m.modeler.create_cylinder(orientation="Y", origin=[x, y_end, zrun],
                                       radius=RAD, height=(y + RAD - y_end),
                                       name="LD_%s_H" % name)
        objs += [v.name, hy.name]
        log("  %-12s 竖直 z %.2f->%.2f @ (%.3f, %.3f);  水平 y %.3f->%.3f @ (x=%.3f, z=%.2f)"
            % (name, z0, z0 + h, x, y, y_end, y + RAD, x, zrun))
    newobjs[coil] = dict(objs=objs, y_end=y_end, zrun=zrun)

# ---------------- 3. unite ----------------
log("")
log("=== 3. unite（端子会被摧毁）===")
for coil in ("Tx1", "Tx2"):
    res = m.modeler.unite([coil] + newobjs[coil]["objs"])
    log("  %s unite -> %s" % (coil, res))
    if res and res != coil:
        m.modeler.rename(res, coil)
    bb = m.modeler[coil].bounding_box
    log("     bbox X[%.2f,%.2f] Y[%.2f,%.2f] Z[%.2f,%.2f]"
        % (bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

# ---------------- 4. 重建端子 ----------------
log("")
log("=== 4. 在 y=y_end 的新端面上重建端子 ===")
WNAMES = {}
newterms = {}
for coil in ("Tx1", "Tx2"):
    y_end = newobjs[coil]["y_end"]
    zrun = newobjs[coil]["zrun"]
    newterms[coil] = []
    for name, t in sorted(info[coil]["terms"].items()):
        hits = []
        for f in m.modeler[coil].faces:
            try:
                c = f.center
                a = f.area
            except Exception:
                continue
            if abs(c[1] - y_end) < 0.05 and abs(c[0] - t["x"]) < 0.05 \
               and abs(a - AREA) < AREA * 0.3:
                hits.append((abs(c[1] - y_end), f.id, tuple(round(v, 4) for v in c), round(a, 6)))
        hits.sort()
        if not hits:
            log("  !! %-12s 找不到 y=%.3f 的端面" % (name, y_end))
            log("     （y_end=%.3f, x=%.3f, z=%.3f, AREA=%.6f）" % (y_end, t["x"], zrun, AREA))
            continue
        log("  %-12s 候选: %s" % (name, hits[:3]))
        fid = hits[0][1]
        c = m.assign_coil(assignment=[fid], conductors_number=1,
                          polarity=t["polarity"], name=name)
        newterms[coil].append(name)
        log("       assign_coil -> %s" % ("OK" if c else "失败"))

# ---------------- 5. 挂回绕组 ----------------
log("")
log("=== 5. add_winding_coils 挂回绕组 ===")
for coil in ("Tx1", "Tx2"):
    wn = "Winding_" + coil
    WNAMES[coil] = wn
    w = [b.name for b in m.boundaries if b.name == wn]
    if not w:
        cand = [b.name for b in m.boundaries if b.name.startswith("Winding")]
        log("  !! 找不到 %s，现有: %s" % (wn, cand))
        continue
    try:
        r = m.add_winding_coils(wn, sorted(newterms[coil]))
        log("  add_winding_coils(%s, %s) -> %s" % (wn, sorted(newterms[coil]), r))
    except Exception as e:
        log("  !! add_winding_coils FAILED: %r" % e)

# ---------------- 5.5 重建 Region ----------------
log("")
log("=== 5.5 重建 Region, padding=%s (pad_type=Absolute Offset) ===" % PAD)
try:
    rbb = m.modeler["Region"].bounding_box
    log("  改前 Region X[%.3f,%.3f] Y[%.3f,%.3f] Z[%.3f,%.3f]"
        % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5]))
except Exception as e:
    log("  改前读不到 Region: %r" % e)
try:
    m.modeler.delete("Region")
    time.sleep(1)
    m.modeler.create_region(pad_value=PAD, pad_type="Absolute Offset")
    rbb = m.modeler["Region"].bounding_box
    log("  改后 Region X[%.3f,%.3f] Y[%.3f,%.3f] Z[%.3f,%.3f]"
        % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5]))
except Exception as e:
    log("  !! Region 重建失败: %r" % e)
    sys.exit(1)

# ---------------- 6. 复核 ----------------
log("")
log("=== 6. 复核（几何 / 边界清单）===")
for b in m.boundaries:
    if not b.name.startswith("CT_"):
        continue
    w = b.props.get("Winding")
    flag = ""
    if str(w) in ("None", "-1", "null"):
        flag = "   (新建边界，props 缓存未刷新，以第 7 步文本核对为准)"
    log("  %-12s Faces=%-9s Conductor=%-3s Winding=%-5s%s"
        % (b.name, b.props.get("Faces"), b.props.get("Conductor number"), w, flag))
for n in ("Tx1", "Tx2", "Rx"):
    bb = m.modeler[n].bounding_box
    log("  %-5s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%8.2f,%8.2f]"
        % (n, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))

nterms = sum(len(v) for v in newterms.values())
log("")
log("端子重建数: %d / 4" % nterms)
log("注: 刚建的边界，props 里 Winding 读出来是 None（pyAEDT 缓存未刷新）。")
log("    上一次同类编辑存盘后，.aedt 文本里其实是 Winding=9（已挂上），")
log("    所以这里不拿 props 当判据 —— 改成存盘后直接查 .aedt 文本。")
if DRY:
    log("DRY-RUN：不存盘。确认无误后加 --apply 重跑。")
    sys.exit(0)
if nterms != 4:
    log("!! 端子不足 4 个，拒绝存盘")
    sys.exit(1)

log("save_project -> %s" % m.save_project())

# ---------------- 7. 存盘后用文本核对绕组链接 ----------------
log("")
log("=== 7. 核对 .aedt 文本（权威段 = 最后一个 BoundarySetup）===")
with open(PROJ, "r", encoding="utf-8", errors="surrogateescape") as f:
    txt = f.read()
idx = txt.rfind("$begin 'BoundarySetup'")
seg = txt[idx:]
log("  权威 BoundarySetup 位于字符 %d / %d" % (idx, len(txt)))

allgood = True
for nm in ("CT_Tx1_P", "CT_Tx1_N", "CT_Tx2_P", "CT_Tx2_N", "CT_Rx_P", "CT_Rx_N"):
    j = seg.find("$begin '%s'" % nm)
    if j < 0:
        log("  %-10s 未找到" % nm)
        allgood = False
        continue
    blk = seg[j:j + 700]
    w = re.search(r"Winding=(-?\d+)", blk)
    c = re.search(r"'Conductor number'='([^']*)'", blk)
    fa = re.search(r"Faces\((\d+)\)", blk)
    wid = int(w.group(1)) if w else None
    cond = c.group(1) if c else "?"
    okw = (wid is not None and wid > 0)
    okc = (cond == "1")
    if not (okw and okc):
        allgood = False
    log("  %-10s Faces=%-6s Winding=%-4s Conductor=%-3s %s%s"
        % (nm, fa.group(1) if fa else "?", wid, cond,
           "" if okw else "  <== 没挂上绕组", "" if okc else "  <== Conductor 不是 1"))

log("")
if allgood:
    log("*** 全部 6 个端子的绕组链接 + Conductor=1 都正确 ***")
else:
    log("!! 有问题，从备份回滚")
    shutil.copyfile(os.path.join(BK, "Projecttonight.aedt"), PROJ)
    log("   已回滚 -> %s" % PROJ)
    sys.exit(1)
