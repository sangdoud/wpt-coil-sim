# -*- coding: utf-8 -*-
"""判定实验：把 Region 的 -Y padding 设成 0，让区域 -Y 面正好落在端子面上，
看 "Illegal external terminal" 是否消失。

用已经建好该点几何(铁氧体已重建、Rx 已在 dx=-150)的测试模型，不重跑几何。
"""

import os
import shutil
import sys
import time

from ansys.aedt.core import Desktop, Maxwell3d

TEST = r"C:\wpt\_test_run"
SRC = os.path.join(TEST, "Projecttonight_leadsL.aedt")
PROJ = os.path.join(TEST, "Projecttonight_probeY.aedt")
DESIGN = "WPT_G"

PAD = ["50mm", "50mm", "50mm", "0mm", "0mm", "0mm"]   # +X -X +Y -Y +Z -Z
DRY = "--apply" not in sys.argv


def log(m):
    print(m, flush=True)


# 清掉旧的 probe 文件（可能有只读属性）
for n in ("Projecttonight_probeY.aedt", "Projecttonight_probeY.aedt.lock"):
    p = os.path.join(TEST, n)
    if os.path.exists(p):
        os.chmod(p, 0o666)
        os.remove(p)
for n in ("Projecttonight_probeY.aedtresults", "Projecttonight_probeY.pyaedt"):
    p = os.path.join(TEST, n)
    if os.path.isdir(p):
        shutil.rmtree(p, ignore_errors=True)

shutil.copyfile(SRC, PROJ)
os.chmod(PROJ, 0o666)
log("复制 %s -> %s (%d bytes)" % (os.path.basename(SRC), os.path.basename(PROJ),
                                  os.path.getsize(PROJ)))

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=PROJ, design=DESIGN)
log("design=%s" % m.design_name)

log("")
log("=== 改之前的 Region ===")
try:
    rbb = m.modeler["Region"].bounding_box
    log("  Region X[%.3f,%.3f] Y[%.3f,%.3f] Z[%.3f,%.3f]"
        % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5]))
except Exception as e:
    log("  读不到: %r" % e)
for n in ("Tx1", "Tx2", "Rx"):
    try:
        b = m.modeler[n].bounding_box
        log("  %-4s X[%9.2f,%9.2f] Y[%9.2f,%9.2f] Z[%8.2f,%8.2f]"
            % (n, b[0], b[3], b[1], b[4], b[2], b[5]))
    except Exception as e:
        log("  %s: %r" % (n, e))

log("")
log("=== 重建 Region, padding=%s ===" % PAD)
m.modeler.delete("Region")
time.sleep(1)
m.modeler.create_region(pad_value=PAD)
rbb = m.modeler["Region"].bounding_box
log("  Region X[%.3f,%.3f] Y[%.3f,%.3f] Z[%.3f,%.3f]"
    % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5]))

# 端子面 vs 区域面
log("")
log("=== 端子面位置 ===")
for b in m.boundaries:
    if not b.name.startswith("CT_"):
        continue
    fid = (b.props.get("Faces") or [None])[0]
    obj = None
    for cn in ("Tx1", "Tx2", "Rx"):
        try:
            for f in m.modeler[cn].faces:
                if f.id == fid:
                    obj = cn
                    c = f.center
                    log("  %-10s %s face=%s center=(%.4f, %.4f, %.4f) area=%.6f"
                        % (b.name, cn, fid, c[0], c[1], c[2], f.area))
                    break
        except Exception:
            pass
        if obj:
            break
    if not obj:
        log("  %-10s face=%s (没在 Tx1/Tx2/Rx 上找到)" % (b.name, fid))

if DRY:
    log("")
    log("DRY: 不求解。加 --apply 才求解。")
    sys.exit(0)

log("")
log("=== 求解 ===")
m.save_project()
t0 = time.time()
try:
    m.analyze(cores=8)
    log("  analyze 返回, 用时 %.0f 秒" % (time.time() - t0))
except Exception as e:
    log("  analyze 抛异常: %r" % repr(e))

w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
try:
    data = m.post.get_solution_data(
        expressions=["Lmatrix.L(%s,%s)" % (a, b) for a in w for b in w],
        setup_sweep_name="Setup1 : LastAdaptive")
    if data is None:
        log("  取不到解")
    else:
        for a in w:
            for b in w:
                try:
                    v = data.data_real("Lmatrix.L(%s,%s)" % (a, b))[0]
                    log("  L(%-11s,%-11s) = %12.6f nH" % (a, b, v))
                except Exception as e:
                    log("  L(%s,%s) 取不到: %r" % (a, b, e))
except Exception as e:
    log("  post 异常: %r" % repr(e))
