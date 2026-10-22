# -*- coding: utf-8 -*-
"""按 (LC, KR) 参数化重建三个线圈（铜带 + 引线 + 端子 + 绕组）。

流程（每个线圈）：
  1. 记录现有端子的端面中心/面积/极性，记录当前 bbox 中心
  2. 删掉整个线圈对象（它包含铜带和引线）
  3. 用 coil_gen.make_path(LC, KR) 生成新路径 -> create_polyline(Rectangle 2x0.5)
  4. 在路径两端点重建引线：
       Tx1: 竖直 z=+0.25->+2.0，再沿 -Y 水平到 y=-134.94
       Tx2: 竖直 z=-0.25->-2.0，再沿 -Y 水平到 y=-134.94
       Rx : 竖直 z=30.25->75（穿铁氧体，孔由批次脚本开）
  5. unite -> 按位置找回端面 -> 重建端子 + 挂回绕组
  6. 复核：线圈尺寸 / 体积 / 端子

用法：
  python coil_param_rebuild.py --LC 167.2829 --KR 0.3587          # 参考点回归（应复现现模型）
  python coil_param_rebuild.py --LC 180 --KR 0.25 --apply         # 改并存盘
"""
import argparse
import json
import math
import os
import sys
import time
import traceback

import numpy as np
from ansys.aedt.core import Desktop, Maxwell3d

sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
from coil_gen import CENTER, H_IN_REF, H_OUT_REF, LC_REF, KR_REF, cheb, make_path  # noqa

WORK = r"C:\ansys maxwell2024\_work"
PROJ = os.path.join(WORK, "Projecttonight.aedt")
LOGF = os.path.join(WORK, "coil_param_rebuild.log")
RESULT = os.path.join(WORK, "coil_param_rebuild.json")
DESIGN = "WPT_G"

RAD = 0.3            # 引线半径
WIDTH = 2.0          # 线宽
HEIGHT = 0.5         # 线厚
Y_END = -134.940     # 发射引线水平段终点（= Region 的 -Y 面）
RX_ZTOP = 75.0       # 接收引线顶端（= Region 的 +Z 面）
VERT = 2.0           # 发射引线竖直段高度
RX_Z0 = 30.0         # 接收线圈平面

COILS = ("Tx1", "Tx2", "Rx")
LEAD_UP = {"Tx1": +1.0, "Tx2": -1.0}      # 竖直段方向
PLANE_Z = {"Tx1": 0.0, "Tx2": 0.0, "Rx": RX_Z0}

LOG = []


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    LOG.append(s)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def face_map(m, name):
    out = {}
    for f in m.modeler[name].faces:
        try:
            out[f.id] = (tuple(f.center), f.area)
        except Exception:
            pass
    return out


def record_terminals(m, coil):
    fm = face_map(m, coil)
    rec = {}
    for b in m.boundaries:
        if not b.name.startswith("CT_" + coil + "_"):
            continue
        p = b.props
        fid = (p.get("Faces") or [None])[0]
        c, a = fm.get(fid, (None, None))
        if c is None:
            raise RuntimeError("%s 找不到端子面 %s" % (b.name, fid))
        pol = "Negative" if p.get("Point out of terminal") in (True, "true") else "Positive"
        rec[b.name] = {"center": [float(v) for v in c], "area": float(a), "polarity": pol}
    if len(rec) != 2:
        raise RuntimeError("%s 端子数=%d" % (coil, len(rec)))
    return rec


def make_leads(m, coil, ends, zplane):
    """在路径两端点建引线，返回对象名列表。ends=[(x,y), (x,y)]"""
    objs = []
    if coil in ("Tx1", "Tx2"):
        sgn = LEAD_UP[coil]
        zrun = sgn * VERT
        z0 = sgn * HEIGHT / 2.0          # 铜带表面
        for i, (px, py) in enumerate(ends):
            v = m.modeler.create_cylinder(orientation="Z", origin=[px, py, min(z0, zrun)],
                                          radius=RAD, height=abs(zrun - z0),
                                          name="LD_%s_%d_V" % (coil, i))
            hy0, hy1 = Y_END, py + RAD
            h = m.modeler.create_cylinder(orientation="Y", origin=[px, hy0, zrun],
                                          radius=RAD, height=(hy1 - hy0),
                                          name="LD_%s_%d_H" % (coil, i))
            objs += [v.name, h.name]
            log("    %s 引线%d: 竖直 z %.2f->%.2f @(%.3f,%.3f); 水平 y %.2f->%.2f"
                % (coil, i, min(z0, zrun), max(z0, zrun), px, py, hy0, hy1))
    else:
        for i, (px, py) in enumerate(ends):
            v = m.modeler.create_cylinder(orientation="Z", origin=[px, py, zplane + HEIGHT / 2.0],
                                          radius=RAD, height=RX_ZTOP - (zplane + HEIGHT / 2.0),
                                          name="LD_%s_%d_V" % (coil, i))
            objs.append(v.name)
            log("    %s 引线%d: 竖直 z %.2f->%.2f @(%.3f,%.3f)"
                % (coil, i, zplane + HEIGHT / 2.0, RX_ZTOP, px, py))
    return objs


def term_face_at(m, coil, center, area):
    hits = []
    for f in m.modeler[coil].faces:
        try:
            c, a = f.center, f.area
        except Exception:
            continue
        d = max(abs(c[0] - center[0]), abs(c[1] - center[1]), abs(c[2] - center[2]))
        if d < 0.05 and abs(a - area) < area * 0.30:
            hits.append((round(d, 6), f.id, tuple(round(v, 4) for v in c), round(a, 6)))
    hits.sort()
    return hits


def rebuild(m, coil, LC, KR):
    info = {"coil": coil}
    rec = record_terminals(m, coil)
    info["terminals_before"] = rec
    bb0 = m.modeler[coil].bounding_box
    cx0 = (bb0[0] + bb0[3]) / 2.0
    cy0 = (bb0[1] + bb0[4]) / 2.0
    v0 = m.modeler[coil].volume
    info["before"] = {"volume": round(v0, 4), "bbox": [round(v, 4) for v in bb0],
                      "center": [round(cx0, 4), round(cy0, 4)]}
    log("  [%s] 改前 体积=%.4f bbox中心=(%.3f, %.3f)" % (coil, v0, cx0, cy0))

    # 生成新路径（模板坐标），先建铜带，再量 bbox 把 x 中心对齐到原值
    P = make_path(LC, KR, WIDTH)
    z = PLANE_Z[coil]
    pts0 = [[float(p[0]), float(p[1]), z] for p in P]
    # 先删掉旧线圈（含引线），端子会一起消失，后面重建
    m.modeler.delete(coil)
    tr = m.modeler.create_polyline(points=pts0, xsection_type="Rectangle", xsection_orient="Auto",
                                   xsection_width="%.4fmm" % WIDTH, xsection_topwidth="%.4fmm" % WIDTH,
                                   xsection_height="%.4fmm" % HEIGHT, xsection_num_seg=0,
                                   xsection_bend_type="Corner", name="TR_%s_new" % coil,
                                   material="copper")
    bbt = tr.bounding_box
    dx_move = cx0 - (bbt[0] + bbt[3]) / 2.0
    if abs(dx_move) > 1e-9:
        m.modeler.move([tr.name], [dx_move, 0.0, 0.0])
        bbt = tr.bounding_box
    log("  [%s] 铜带 体积=%.4f z跨度=%.4f  x中心 %.3f -> %.3f (目标 %.3f)"
        % (coil, tr.volume, bbt[5] - bbt[2], (bbt[0] + bbt[3]) / 2.0 - dx_move,
           (bbt[0] + bbt[3]) / 2.0, cx0))
    pts = [[p[0] + dx_move, p[1], z] for p in pts0]
    ends = [(pts[0][0], pts[0][1]), (pts[-1][0], pts[-1][1])]
    log("  [%s] 路径端点 (%.3f,%.3f) / (%.3f,%.3f)  X跨度=%.2f Y跨度=%.2f"
        % (coil, ends[0][0], ends[0][1], ends[1][0], ends[1][1],
           max(p[0] for p in pts) - min(p[0] for p in pts),
           max(p[1] for p in pts) - min(p[1] for p in pts)))

    # 建引线并合并
    leads = make_leads(m, coil, ends, z)
    res = m.modeler.unite([tr.name] + leads)
    if res is None or res is False:
        raise RuntimeError("[%s] unite 失败" % coil)
    if isinstance(res, str) and res != coil:
        m.modeler[res].name = coil
    if m.modeler[coil].material_name != "copper":
        m.modeler[coil].material_name = "copper"
    bb1 = m.modeler[coil].bounding_box
    info["after"] = {"volume": round(m.modeler[coil].volume, 4),
                     "faces": len(m.modeler[coil].faces),
                     "bbox": [round(v, 4) for v in bb1],
                     "center": [round((bb1[0] + bb1[3]) / 2.0, 4), round((bb1[1] + bb1[4]) / 2.0, 4)]}
    log("  [%s] 合并后 体积=%.4f 面=%d bbox中心=(%.3f,%.3f)"
        % (coil, info["after"]["volume"], info["after"]["faces"],
           info["after"]["center"][0], info["after"]["center"][1]))

    # 端子
    for nm in list(rec.keys()):
        for b in list(m.boundaries):
            if b.name == nm:
                try:
                    b.delete()
                except Exception:
                    pass
    names = []
    for nm, t in sorted(rec.items()):
        hits = term_face_at(m, coil, t["center"], t["area"])
        if not hits:
            raise RuntimeError("[%s] 找不到 %s 的新端面（原 %s）" % (coil, nm, t["center"]))
        log("    %-12s 端面候选 %s" % (nm, hits[:2]))
        if not m.assign_coil(assignment=[hits[0][1]], conductors_number=1,
                             polarity=t["polarity"], name=nm):
            raise RuntimeError("[%s] assign_coil %s 失败" % (coil, nm))
        names.append(nm)
    wn = "Winding_" + coil
    if not m.add_winding_coils(wn, sorted(names)):
        raise RuntimeError("[%s] add_winding_coils 失败" % coil)
    info["terminals_after"] = sorted(names)
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--LC", type=float, required=True)
    ap.add_argument("--KR", type=float, required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    log("=" * 74)
    log("参数化重建  LC=%.4f mm  KR=%.4f  (参考 LC_REF=%.4f KR_REF=%.4f)  apply=%s"
        % (a.LC, a.KR, LC_REF, KR_REF, a.apply))

    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=DESIGN)
    log("已打开 %s / %s" % (PROJ, m.design_name))

    res = {"LC": a.LC, "KR": a.KR, "coils": {}}
    for c in COILS:
        res["coils"][c] = rebuild(m, c, a.LC, a.KR)

    log("")
    log("=== 端子/绕组复核 ===")
    bnd = []
    for b in m.boundaries:
        if b.name.startswith("CT_") or b.name.startswith("Winding"):
            p = b.props
            log("  %-12s Faces=%-9s Winding=%-5s Cond=%-3s Out=%s"
                % (b.name, p.get("Faces"), p.get("Winding"), p.get("Conductor number"),
                   p.get("Point out of terminal")))
            if b.name.startswith("CT_"):
                bnd.append(b.name)
    res["boundaries"] = bnd
    if len(bnd) != 6:
        raise RuntimeError("端子数 %d != 6" % len(bnd))

    if a.apply:
        log("save_project -> %s" % m.save_project())
        res["saved"] = True
    else:
        log("DRY-RUN：未存盘")
        res["saved"] = False
    json.dump(res, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("结果 -> %s" % RESULT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!! 失败\n" + traceback.format_exc())
        json.dump({"error": traceback.format_exc(), "log": LOG},
                  open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        sys.exit(1)
