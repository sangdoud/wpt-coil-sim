# -*- coding: utf-8 -*-
"""在 AEDT 里把 LC=120 / KR=0.5 的线圈真建出来，并导出视图。
不存盘（工作区副本保持参考模型，便于以后复算回归）。"""
import os
import sys
import time
import traceback

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, r"C:\wpt")
sys.path.insert(0, WORK)
import coil_gen as CG                     # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

PROJ = os.path.join(WORK, "Projecttonight.aedt")
LOGF = os.path.join(WORK, "build_lc120.log")
LC, KR = 120.0, 0.5
NOM = dict(W=15.0, G=15.0, tg=0.0, thk=10.0, dx=0.0)


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def shot(m, name, orient):
    p = os.path.join(WORK, name)
    try:
        m.post.export_model_picture(full_name=p, orientation=orient)
        log("  已导出 %s (%s)" % (p, orient))
        return p
    except Exception as e:
        log("  !! export_model_picture(%s) 失败: %r" % (orient, e))
        try:
            m.post.export_model_picture(p)
            log("  已导出(默认视角) %s" % p)
            return p
        except Exception as e2:
            log("  !! 兜底也失败: %r" % e2)
            return None


def main():
    log("=" * 66)
    log("在 AEDT 里建 LC=%.0f KR=%.1f 的线圈" % (LC, KR))
    d = CG.path_dims(LC, KR)
    log("几何摘要: %s" % d)
    dd = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design="WPT_G")
    log("已打开 %s" % m.design_name)

    B = None
    try:
        sys.path.insert(0, r"C:\wpt")
        import batch_sweep_lc as B   # noqa
        log("已 import batch_sweep_lc")
    except Exception as e:
        log("!! import batch_sweep_lc 失败: %r" % e)

    outer = CG.coil_outer(LC)
    B.set_rx_dx(m, 0.0)
    log("重建三个线圈 ...")
    res = CG.rebuild_all(m, LC, KR, log=log)
    for c, v in res.items():
        log("  %-4s 体积=%.2f 面=%d bbox=%s" % (c, v["volume_after"], v["faces"], v["bbox"]))
    rx_leads = CG.current_leads(m, "Rx")
    log("接收引线位置 = %s" % rx_leads)

    B.set_tx_gap(m, NOM["tg"], outer)
    nf = B.rebuild_ferrite(m, NOM["W"], NOM["G"], NOM["tg"], NOM["thk"], outer, rx_leads)
    B.ensure_region(m, NOM["tg"])
    log("铁氧体条数 = %d" % nf)
    for o in ("Tx1", "Tx2", "Rx", "Region"):
        bb = m.modeler[o].bounding_box
        log("  %-6s X[%8.2f,%8.2f] Y[%8.2f,%8.2f] Z[%7.2f,%6.2f]"
            % (o, bb[0], bb[3], bb[1], bb[4], bb[2], bb[5]))
    log("端子:")
    for b in m.boundaries:
        if b.name.startswith("CT_"):
            p = b.props
            log("  %-10s Faces=%-8s Cond=%-3s Out=%s" % (b.name, p.get("Faces"),
                                                         p.get("Conductor number"),
                                                         p.get("Point out of terminal")))
    try:
        m.modeler.fit_all()
    except Exception:
        pass
    shot(m, "lc120_coil_iso.png", "isometric")
    shot(m, "lc120_coil_top.png", "top")
    shot(m, "lc120_coil_front.png", "front")
    log("不存盘，结束")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!! 失败\n" + traceback.format_exc())
        sys.exit(1)
