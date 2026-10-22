# -*- coding: utf-8 -*-
"""线圈参数化模块（LC x 内孔比 KR）—— 供 batch_sweep_unit30.py 调用。

参数定义
--------
LC  = 线圈**中心线外跨** = 2 x 最外匝中心线半径（不是外边缘尺寸！外边缘 = LC + 线宽）
KR  = 中心线内跨 / LC = 最内匝中心线半径 / 最外匝中心线半径
参考模型（2026-09-16 的 2mm 线宽版）：LC_REF=167.2829  KR_REF=0.3587
      （对应内孔中心线跨 60.0mm、外边缘 169.28mm）
匝间隙不单独给：由 (LC, KR, 12 匝) 自动算出 = (h_out-h_in)/12 匝，
      LC=120/KR=0.5 时最小净间隙 0.517mm（最紧的一格）。

实现
----
以参考模型的 768 点路径为模板做径向重映射：
     s(p)  = 切比雪夫半径 max(|dx|,|dy|)     （对平边精确等于环半径）
     s'(p) = h_in' + (s - h_in_ref) * (h_out' - h_in')/(h_out_ref - h_in_ref)
     p'    = 中心 + (p - 中心) * s'/s
* 参考参数下逐点恒等 -> 可精确复现现有模型
* 纯缩放无失真；改内孔比时一个圆角内缩放因子差 2~3%，形变 < 0.1mm
"""
import json
import math
import os
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "coil_template_Rx.json")

# ---- 线圈固定规格 ----
WIDTH = 2.0          # 线宽（平面内）
HEIGHT = 0.5         # 线厚（Z 向）
RAD = 0.3            # 引线半径
TURNS = 12
Y_END = -134.940     # 发射引线水平段终点（= Region 的 -Y 面，端子贴在这里）
RX_ZTOP = 75.0       # 接收引线顶端（= Region 的 +Z 面）
VERT = 2.0           # 发射引线竖直段高度
RX_Z0 = 30.0         # 接收线圈平面 z
LEAD_UP = {"Tx1": +1.0, "Tx2": -1.0}
# 层间隙：两层铜带之间的介质层厚度（mm）。0 = 板面相贴。
# 按实际结构取 0.15mm（4 层板 prepreg 典型厚度）。
# 注意：间隙太小时空气夹层是"薄壳"，网格反而更难做；实测 0 或 0.1 都可能卡住。
LAYER_GAP = 0.15
# 铜带所在平面（z）。两个发射线圈**分两层**，中间留 LAYER_GAP：
#   Tx1 铜带中心 z = +(0.5+gap)/2，Tx2 = -(0.5+gap)/2  -> 两层不相接触
# 这样两个发射线圈在 XOY 面投影重叠时铜带也不会互相穿插/相贴。
# 引线本来就一上一下，分层后依然不打架；Rx 仍然在 z=30 单层。
PLANE_Z = {"Tx1": +(HEIGHT + LAYER_GAP) / 2.0,
           "Tx2": -(HEIGHT + LAYER_GAP) / 2.0,
           "Rx": RX_Z0}
COILS = ("Tx1", "Tx2", "Rx")

_CENTER = (0.0, 0.0)
# Lc 口径：文档以「原模型 Lc=165」为基准。实测原模型路径的中心线外跨 = 167.2829mm，
# 因此取换算系数 K_LC = 167.2829/165，使 Lc=165 时**逐点复现原模型**（几何零改动）。
LC_REF_DOC = 165.0
# ============ 路径重映射口径（2026-09-19 拐角缺陷修正）============
# legacy：f = s'/s，s = 逐点 max(|x|,|y|)（切比雪夫半径）。
#   缺陷：拐角圆角处 s 掉到环半径以下（模板第 1 匝 26.45 vs 环 30），
#   圆角各点缩放系数与直边不同 -> 圆角被径向拉长、切向压扁成尖刺。
#   实测全批 256 工况中 214 个出现 >15° 假尖角，最坏 98.7°（KR≈0.20 档）。
# ring（现行）：以**环半径** R 为重映射坐标——
#   直边上 s 恒等于环半径 R；圆角点的 s 是下沉的假值，用两端直边点的 s 线性插值替代。
#   f = [h_in' + (R - h_in_ref)·k] / R，（k = (h_out'-h_in')/(h_out_ref-h_in_ref)）
#   性质：① 直边 s' = h_in' + (R-h_in_ref)k 严格成立 -> 匝间距口径不变
#         ② 圆角整体按环半径等比缩放 -> 形状保持，无尖刺
#         ③ 参考参数 (LC=165, KR=0.358674) 下 f ≡ 1 -> 与 legacy 逐点一致（历史验证不受影响）
#   修正后全批最大转角 ≤ 11.68°（= 模板固有 8 弦离散角 11.25° 量级），0/256 超 15°；
#   直边最小净间隙 0.680mm 与 legacy 完全一致。
PATH_MODE = os.environ.get("WPT_PATH_MODE", "ring")     # ring | legacy
FILLET_TURN_DEG = 0.05      # 段间转角超过该值即判为圆角点
_ref = None
_s_ref = None
_r_ref = None               # 环半径（圆角点已修正）
_h_in_ref = None
_h_out_ref = None


def _load():
    global _ref, _s_ref, _r_ref, _h_in_ref, _h_out_ref
    if _ref is not None:
        return
    _ref = np.array(json.load(open(TEMPLATE, encoding="utf-8")), dtype=float)
    if _ref.shape[1] == 2:
        _ref = np.hstack([_ref, np.zeros((len(_ref), 1))])
    cx, cy = _CENTER
    _s_ref = np.maximum(np.abs(_ref[:, 0] - cx), np.abs(_ref[:, 1] - cy))
    _h_in_ref = float(_s_ref[0])
    _h_out_ref = float(_s_ref.max())
    # 环半径：直边处 s 即环半径；圆角处 s 下沉，用两端直边点线性插值
    v = np.diff(_ref[:, :2], axis=0)
    ang = np.arctan2(v[:, 1], v[:, 0])
    turn = np.concatenate([[0.0],
                           np.abs((np.diff(ang) + np.pi) % (2.0 * np.pi) - np.pi),
                           [0.0]])
    fillet = turn > np.radians(FILLET_TURN_DEG)
    r = _s_ref.copy()
    n = len(r)
    i = 0
    while i < n:
        if fillet[i]:
            j = i
            while j < n and fillet[j]:
                j += 1
            a, b = max(i - 1, 0), min(j, n - 1)
            if b > a:
                r[i:j] = np.linspace(_s_ref[a], _s_ref[b], j - i)
            i = j
        else:
            i += 1
    _r_ref = r


def ref_params():
    """返回 (LC_REF, KR_REF) —— 文档口径：原模型 Lc=165。"""
    _load()
    return LC_REF_DOC, _h_in_ref / _h_out_ref


def k_lc():
    """Lc（文档口径）-> 实际中心线半径的换算系数。"""
    _load()
    return (2.0 * _h_out_ref) / LC_REF_DOC


def make_path(LC, KR):
    """按 (LC, KR) 生成 768 点路径（模板坐标系，中心在原点，z 沿用模板）。

    LC 用文档口径（原模型 = 165），内部乘 K_LC 换算成实际几何尺寸。
    重映射口径见文件头 PATH_MODE：phase（现行，拐角等比缩放）/ legacy（旧的逐点切比雪夫）。
    """
    _load()
    scale_lc = k_lc()
    h_out = LC * scale_lc / 2.0
    h_in = KR * LC * scale_lc / 2.0
    if h_in <= 0:
        raise ValueError("KR 太小，内孔半径 <= 0")
    if PATH_MODE == "legacy":
        k = (h_out - h_in) / (_h_out_ref - _h_in_ref)
        s2 = h_in + (_s_ref - _h_in_ref) * k
        f = s2 / _s_ref
    else:
        k = (h_out - h_in) / (_h_out_ref - _h_in_ref)
        r_new = h_in + (_r_ref - _h_in_ref) * k
        f = r_new / _r_ref
    cx, cy = _CENTER
    out = _ref.copy()
    out[:, 0] = cx + (_ref[:, 0] - cx) * f
    out[:, 1] = cy + (_ref[:, 1] - cy) * f
    return out


def path_dims(LC, KR):
    """返回该参数下的几何摘要（不启动 AEDT）。"""
    P = make_path(LC, KR)
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    h_in, h_out = float(s[0]), float(s.max())
    P2 = np.roll(P[:, :2], -64, axis=0)
    d = np.hypot(P[:, 0] - P2[:, 0], P[:, 1] - P2[:, 1])
    return dict(h_in=h_in, h_out=h_out, outer=LC + WIDTH, hole=KR * LC - WIDTH,
                gap_min=float((s[64:] - s[:-64]).min() - WIDTH),
                neighbour_min=float(d.min()))


def coil_outer(LC):
    """线圈外边缘尺寸（批次脚本定位用）。"""
    return LC + WIDTH


# ------------------------------------------------------------------ AEDT 侧
def _face_map(m, name):
    out = {}
    for f in m.modeler[name].faces:
        try:
            out[f.id] = (tuple(f.center), f.area)
        except Exception:
            pass
    return out


def record_terminals(m, coil):
    fm = _face_map(m, coil)
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
        raise RuntimeError("%s 端子数=%d（应 2）" % (coil, len(rec)))
    return rec


def _make_leads(m, coil, ends, zplane):
    objs = []
    if coil in ("Tx1", "Tx2"):
        sgn = LEAD_UP[coil]
        zrun = sgn * VERT
        z0 = zplane + sgn * HEIGHT / 2.0     # 铜带外表面（分层后 Tx1=+0.50 / Tx2=-0.50）
        for i, (px, py) in enumerate(ends):
            v = m.modeler.create_cylinder(orientation="Z", origin=[px, py, min(z0, zrun)],
                                          radius=RAD, height=abs(zrun - z0),
                                          name="LD_%s_%d_V" % (coil, i))
            h = m.modeler.create_cylinder(orientation="Y", origin=[px, Y_END, zrun],
                                          radius=RAD, height=(py + RAD - Y_END),
                                          name="LD_%s_%d_H" % (coil, i))
            objs += [v.name, h.name]
    else:
        for i, (px, py) in enumerate(ends):
            v = m.modeler.create_cylinder(orientation="Z", origin=[px, py, zplane + HEIGHT / 2.0],
                                          radius=RAD, height=RX_ZTOP - (zplane + HEIGHT / 2.0),
                                          name="LD_%s_%d_V" % (coil, i))
            objs.append(v.name)
    return objs


def _term_face_at(m, coil, center, area):
    hits = []
    for f in m.modeler[coil].faces:
        try:
            c, a = f.center, f.area
        except Exception:
            continue
        d = max(abs(c[0] - center[0]), abs(c[1] - center[1]), abs(c[2] - center[2]))
        if d < 0.05 and abs(a - area) < area * 0.30:
            hits.append((round(d, 6), f.id))
    hits.sort()
    return hits


def rebuild_coil(m, coil, LC, KR, keep_x_center=None, log=print):
    """按 (LC, KR) 重建一个线圈（铜带 + 引线 + 端子 + 绕组）。返回摘要 dict。

    keep_x_center: 线圈 bbox 的 x 中心要落到的位置（None = 保持当前）。
    """
    rec = record_terminals(m, coil)
    bb0 = m.modeler[coil].bounding_box
    cx0 = keep_x_center if keep_x_center is not None else (bb0[0] + bb0[3]) / 2.0
    v0 = m.modeler[coil].volume

    P = make_path(LC, KR)
    z = PLANE_Z[coil]
    pts0 = [[float(p[0]), float(p[1]), z] for p in P]
    m.modeler.delete(coil)
    tr = m.modeler.create_polyline(points=pts0, xsection_type="Rectangle", xsection_orient="Auto",
                                   xsection_width="%.4fmm" % WIDTH,
                                   xsection_topwidth="%.4fmm" % WIDTH,
                                   xsection_height="%.4fmm" % HEIGHT,
                                   xsection_num_seg=0, xsection_bend_type="Corner",
                                   name="TR_%s_new" % coil, material="copper")
    bbt = tr.bounding_box
    dx = cx0 - (bbt[0] + bbt[3]) / 2.0
    if abs(dx) > 1e-9:
        m.modeler.move([tr.name], [dx, 0.0, 0.0])
    pts = [[p[0] + dx, p[1], z] for p in pts0]
    ends = [(pts[0][0], pts[0][1]), (pts[-1][0], pts[-1][1])]
    leads = _make_leads(m, coil, ends, z)
    res = m.modeler.unite([tr.name] + leads)
    if res is None or res is False:
        raise RuntimeError("[%s] unite 失败" % coil)
    if isinstance(res, str) and res != coil:
        m.modeler[res].name = coil
    if m.modeler[coil].material_name != "copper":
        m.modeler[coil].material_name = "copper"
    for nm in list(rec.keys()):
        for b in list(m.boundaries):
            if b.name == nm:
                try:
                    b.delete()
                except Exception:
                    pass
    names = []
    # 改 LC/KR 后引线端点会移动，所以端面要按**新端点位置**去找；
    # 旧端子与新端点按 x 升序一一配对（两个端点 x 相差 ~50mm，不会有歧义），
    # 这样 P/N 极性跟随路径的内/外端保持不变。
    zrun = LEAD_UP[coil] * VERT if coil in ("Tx1", "Tx2") else RX_ZTOP
    old_sorted = sorted(rec.items(), key=lambda kv: kv[1]["center"][0])
    new_sorted = sorted(ends, key=lambda e: e[0])
    for (nm, t), (px, py) in zip(old_sorted, new_sorted):
        if coil in ("Tx1", "Tx2"):
            target = [px, Y_END, zrun]
        else:
            target = [px, py, RX_ZTOP]
        hits = _term_face_at(m, coil, target, t["area"])
        if not hits:
            hits = _term_face_at(m, coil, t["center"], t["area"])   # 兜底：按原位找
        if not hits:
            raise RuntimeError("[%s] 找不到 %s 的新端面（新端点 %s）" % (coil, nm, target))
        if not m.assign_coil(assignment=[hits[0][1]], conductors_number=1,
                             polarity=t["polarity"], name=nm):
            raise RuntimeError("[%s] assign_coil %s 失败" % (coil, nm))
        names.append(nm)
    if not m.add_winding_coils("Winding_" + coil, sorted(names)):
        raise RuntimeError("[%s] add_winding_coils 失败" % coil)

    bb1 = m.modeler[coil].bounding_box
    return dict(volume_before=round(v0, 4), volume_after=round(m.modeler[coil].volume, 4),
                faces=len(m.modeler[coil].faces),
                bbox=[round(v, 4) for v in bb1], ends=ends)


def rebuild_all(m, LC, KR, log=print):
    """三个线圈一起重建；返回 {coil: 摘要}。"""
    out = {}
    for c in COILS:
        out[c] = rebuild_coil(m, c, LC, KR, log=log)
        log("  线圈 %-4s LC=%.2f KR=%.3f -> 体积 %.2f 面 %d"
            % (c, LC, KR, out[c]["volume_after"], out[c]["faces"]))
    return out


def current_leads(m, coil):
    """从端子面中心反查当前两个引线的 (x, y)（模型绝对坐标）。"""
    out = []
    for b in m.boundaries:
        if not b.name.startswith("CT_" + coil + "_"):
            continue
        p = b.props
        fid = (p.get("Faces") or [None])[0]
        for f in m.modeler[coil].faces:
            if f.id == fid:
                c = f.center
                out.append((round(c[0], 4), round(c[1], 4)))
    return sorted(out)
