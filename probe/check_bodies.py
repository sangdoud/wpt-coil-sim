# -*- coding: utf-8 -*-
"""体检：Tx1 / Tx2 是同一个线圈，体积/面数/包围盒应该一致。
若 Tx1 体积明显不同，说明之前 unite 把线圈弄坏了。"""

import sys

from ansys.aedt.core import Desktop, Maxwell3d

WPT = r"C:\wpt"
PROJ = sys.argv[1] if len(sys.argv) > 1 else r"C:\wpt\Projecttonight.aedt"
DESIGN = "WPT_G"


def log(m):
    print(m, flush=True)


d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=PROJ, design=DESIGN)
log("模型: %s   design=%s" % (PROJ, m.design_name))

log("")
log("%-6s %14s %8s %-12s %s" % ("对象", "体积(mm^3)", "面数", "材料", "bbox"))
for n in ("Tx1", "Tx2", "Rx"):
    try:
        o = m.modeler[n]
        bb = o.bounding_box
        log("%-6s %14.4f %8d %-12s X[%9.2f,%9.2f] Y[%9.2f,%9.2f] Z[%8.2f,%8.2f]"
            % (n, o.volume, len(o.faces), o.material_name,
               bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))
    except Exception as e:
        log("%-6s 读取失败: %r" % (n, e))

# 反查：Tx1 完全镜像后与 Tx2 是否重合？直接比关键指标
try:
    import math
    o1, o2 = m.modeler["Tx1"], m.modeler["Tx2"]
    b1, b2 = o1.bounding_box, o2.bounding_box
    log("")
    log("Tx1 X 跨度 %.4f  Y 跨度 %.4f  Z 跨度 %.4f" % (b1[3]-b1[0], b1[4]-b1[1], b1[5]-b1[2]))
    log("Tx2 X 跨度 %.4f  Y 跨度 %.4f  Z 跨度 %.4f" % (b2[3]-b2[0], b2[4]-b2[1], b2[5]-b2[2]))
    log("Tx1 中心 (%.4f, %.4f)   Tx2 中心 (%.4f, %.4f)"
        % ((b1[0]+b1[3])/2, (b1[1]+b1[4])/2, (b2[0]+b2[3])/2, (b2[1]+b2[4])/2))
    log("两中心之和 (应该是 2*对称轴): %.6f" % (((b1[0]+b1[3])/2 + (b2[0]+b2[3])/2)))
    log("两中心间距: X %.4f   Y %.4f" % (((b2[0]+b2[3])/2 - (b1[0]+b1[3])/2),
                                          ((b2[1]+b2[4])/2 - (b1[1]+b1[4])/2)))
except Exception as e:
    log("镜像比较失败: %r" % e)

try:
    v1 = m.modeler["Tx1"].volume
    v2 = m.modeler["Tx2"].volume
    log("")
    log("Tx1/Tx2 体积比 = %.6f  (同一线圈应该 = 1.000000)" % (v1 / v2))
    if abs(v1 / v2 - 1.0) > 1e-3:
        log("  !! 不一致，Tx1 可能被改坏了")
    else:
        log("  OK 一致")
except Exception as e:
    log("比较失败: %r" % e)

# 线圈本体（不含引线）应该 x 宽度 == y 高度
for n in ("Tx1", "Tx2"):
    bb = m.modeler[n].bounding_box
    log("%s 线圈本体宽度X=%.3f  高度Y=%.3f  厚度Z=%.3f"
        % (n, bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]))
