# -*- coding: utf-8 -*-
"""把 Tx1/Tx2/Rx 三个线圈的线宽（平面内宽度）从 3mm 改成 2mm。

做法（不动引线、不动路径）：
  1) 记录每个线圈的端子（名字/面/中心/面积/极性）
  2) 用一个大盒子把「旧铜带」所在的 z 层切掉 —— 切完对象里只剩引线
  3) 用原路径（768 点，从 .aedt 文本逐点提取）按新线宽重建铜带
  4) 与引线 Unite -> 端子被摧毁 -> 按位置重新找回端面并重建端子 + 挂回绕组
  5) 几何自检：铜带体积必须 = 路径长 x 线宽 x 厚（直线段扫掠，可精确预测）

自带 3mm 回归：同一条代码路径重建 3mm，体积必须回到原值附近
（差 = 被切掉的引线短桩：Tx 每个引线 0.25mm -> -0.1413，Rx 差 0）。

用法：
  python rebuild_width_pipeline.py                     # 几何 + 3mm 回归 + 2mm 重建，不存盘
  python rebuild_width_pipeline.py --apply             # 存盘
  python rebuild_width_pipeline.py --apply --solve     # 再做 A/B 双求解（基线点，各约 11 分钟）
"""

import json
import os
import sys
import time
import traceback

from ansys.aedt.core import Desktop, Maxwell3d

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, WORK)          # 生产脚本的工作区副本 batch_unit30_ws.py 放在这里
PROJ = os.path.join(WORK, "Projecttonight.aedt")
PATHS_JSON = os.path.join(WORK, "coil_paths.json")
LOGF = os.path.join(WORK, "rebuild_pipeline.log")
RESULT_JSON = os.path.join(WORK, "rebuild_result.json")
DESIGN = "WPT_G"

WIDTH_NEW = 2.0
WIDTH_OLD = 3.0
HEIGHT = 0.5

# ---- 3mm 原模型实测基准（来自 live_probe）----
V_OLD = {"Tx1": 7750.7989, "Tx2": 7750.9649, "Rx": 7723.2137}
PATH_LEN = 5131.9170
V_TRACE_3 = PATH_LEN * WIDTH_OLD * HEIGHT      # 7697.8755
V_TRACE_2 = PATH_LEN * WIDTH_NEW * HEIGHT      # 5131.9170
DV_TRACE = V_TRACE_3 - V_TRACE_2               # 2565.9585
# 切掉引线短桩造成的体积损失（回归时能看到）
STUB = {"Tx1": -0.1413, "Tx2": -0.1413, "Rx": 0.0}

# 切掉旧铜带用的 z 层 [origin_z, +size_z]
CUT = {
    "Tx1": (-1.0, 1.25),     # -1.00 .. +0.25   （铜带 z -0.25..+0.25，引线竖段从 -0.5 起）
    "Tx2": (-0.25, 1.25),    # -0.25 .. +1.00   （引线竖段到 +0.5）
    "Rx":  (0.0, 30.25),     #  0.00 .. 30.25   （铜带 z 29.75..30.25，引线从 30 往上）
}
COILS = ("Tx1", "Tx2", "Rx")

# 基线 A/B 点（与 9/15 报告一致）
PT = dict(W=10.0, G=20.0, dx=-150.0, tg=0.0, mu=1000.0, thk=10.0)
REF_3MM = dict(L11=19.956, L22=19.563, L33=24.046, M12=-1.063, M13=3.408,
               M23=-0.153, k13=0.15558, k23=-0.00707)

# 交付模型要恢复成的原始几何状态（live_probe 实测）
ORIG_GEOM = dict(W=20.0, G=10.0, tg=30.0, thk=10.0, dx=-140.0)

LOG_LINES = []


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    LOG_LINES.append(s)
    try:
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass


def dump_json(obj):
    with open(RESULT_JSON, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def rename_obj(m, old, new):
    if old == new:
        return
    try:
        m.modeler[old].name = new
        log("    rename %s -> %s" % (old, new))
    except Exception as e:
        log("    !! rename %s -> %s 失败: %r" % (old, new, e))


# ---------------------------------------------------------------- 端子
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
        rec[b.name] = {"face": fid, "center": [round(v, 6) for v in c],
                       "area": round(a, 6), "polarity": pol}
    if len(rec) != 2:
        raise RuntimeError("%s 端子数 = %d，期望 2" % (coil, len(rec)))
    return rec


def compute_offset(pts, rec):
    """引线轴 x = 路径端点 x + Δ；用两个端子的 x 反解（两种配对取一致的那组）。"""
    xa = sorted(t["center"][0] for t in rec.values())
    e0, eN = pts[0][0], pts[-1][0]
    cands = []
    for pair in ((xa[0] - e0, xa[1] - eN), (xa[0] - eN, xa[1] - e0)):
        cands.append((abs(pair[0] - pair[1]), pair))
    cands.sort(key=lambda z: z[0])
    spread, (d1, d2) = cands[0]
    if spread > 0.01:
        raise RuntimeError("两个端子反解出的偏移不一致：d1=%.4f d2=%.4f" % (d1, d2))
    return (d1 + d2) / 2.0, spread


def terminal_face_at(m, coil, center, area):
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


# ---------------------------------------------------------------- 单线圈重建
def rebuild_coil(m, coil, pts, width):
    t0 = time.time()
    info = {"coil": coil, "width": width}
    rec = record_terminals(m, coil)
    info["terminals_before"] = rec
    v0 = m.modeler[coil].volume
    nf0 = len(m.modeler[coil].faces)
    info["before"] = {"volume": round(v0, 4), "faces": nf0,
                      "bbox": [round(v, 4) for v in m.modeler[coil].bounding_box]}
    log("  [%s] 改前 体积=%.4f 面=%d" % (coil, v0, nf0))

    dx, spread = compute_offset(pts, rec)
    info["offset_x"] = round(dx, 6)
    info["offset_spread"] = round(spread, 6)
    log("  [%s] 路径->当前偏移 dx=%.6f (两端子一致性 %.6f)" % (coil, dx, spread))

    # 1) 切掉旧铜带，只留引线
    z0, dz = CUT[coil]
    cut = m.modeler.create_box(origin=[-600.0, -600.0, z0], sizes=[1200.0, 1200.0, dz],
                               name="CUT_%s_%s" % (coil, str(width).replace(".", "p")))
    m.modeler.subtract(blank_list=[coil], tool_list=[cut.name], keep_originals=False)
    if cut.name in m.modeler.object_names:
        m.modeler.delete(cut.name)
    v_leads = m.modeler[coil].volume
    info["volume_leads_only"] = round(v_leads, 4)
    log("  [%s] 切掉铜带后只剩引线 体积=%.4f (预测 %.4f)"
        % (coil, v_leads, v0 - V_TRACE_3))

    # 2) 按新线宽重建铜带
    wstr = "%.4fmm" % width
    new_pts = [[p[0] + dx, p[1], p[2]] for p in pts]
    tr = m.modeler.create_polyline(points=new_pts,
                                   xsection_type="Rectangle",
                                   xsection_orient="Auto",
                                   xsection_width=wstr,
                                   xsection_topwidth=wstr,
                                   xsection_height="%.4fmm" % HEIGHT,
                                   xsection_num_seg=0,
                                   xsection_bend_type="Corner",
                                   name="TR_%s" % coil,
                                   material="copper")
    bbtr = tr.bounding_box
    vtr = tr.volume
    info["trace"] = {"volume": round(vtr, 4), "predicted": round(PATH_LEN * width * HEIGHT, 4),
                     "z_span": round(bbtr[5] - bbtr[2], 4),
                     "bbox": [round(v, 4) for v in bbtr]}
    log("  [%s] 新铜带 体积=%.4f (预测 %.4f, 差 %+.4f)  z 跨度=%.4f (应 %.4f)"
        % (coil, vtr, PATH_LEN * width * HEIGHT, vtr - PATH_LEN * width * HEIGHT,
           bbtr[5] - bbtr[2], HEIGHT))
    # 截面朝向断言：矩形 2x0.5 无论怎么摆面积都一样，所以必须卡 z 跨度，
    # 否则「线宽」可能被摆到 Z 向（那就变成改线厚了）。
    if abs((bbtr[5] - bbtr[2]) - HEIGHT) > 1e-3:
        raise RuntimeError("[%s] 新铜带 z 跨度 %.4f != %.4f，截面朝向不对"
                           % (coil, bbtr[5] - bbtr[2], HEIGHT))

    # 3) 合并
    res = m.modeler.unite([coil, tr.name])
    if res is None or res is False:
        raise RuntimeError("[%s] unite 失败" % coil)
    if isinstance(res, str):
        rename_obj(m, res, coil)
    if m.modeler[coil].material_name != "copper":
        m.modeler[coil].material_name = "copper"
    v1 = m.modeler[coil].volume
    expect = v_leads + PATH_LEN * width * HEIGHT
    info["after"] = {"volume": round(v1, 4), "faces": len(m.modeler[coil].faces),
                     "bbox": [round(v, 4) for v in m.modeler[coil].bounding_box],
                     "predicted": round(expect, 4)}
    log("  [%s] unite 后 体积=%.4f (预测 %.4f, 差 %+.4f) 面=%d"
        % (coil, v1, expect, v1 - expect, len(m.modeler[coil].faces)))

    # 4) 重建端子 + 挂回绕组
    for nm in list(rec.keys()):
        for b in list(m.boundaries):
            if b.name == nm:
                try:
                    b.delete()
                except Exception as e:
                    log("    删除旧端子 %s 失败: %r" % (nm, e))
    new_terms = []
    for nm, t in sorted(rec.items()):
        hits = terminal_face_at(m, coil, t["center"], t["area"])
        if not hits:
            raise RuntimeError("[%s] 找不到 %s 的新端面（原中心 %s 面积 %.6f）"
                               % (coil, nm, t["center"], t["area"]))
        log("    %-12s 端面候选 %s" % (nm, hits[:2]))
        b = m.assign_coil(assignment=[hits[0][1]], conductors_number=1,
                          polarity=t["polarity"], name=nm)
        if not b:
            raise RuntimeError("[%s] assign_coil(%s) 失败" % (coil, nm))
        new_terms.append(nm)
    wn = "Winding_" + coil
    if wn not in [b.name for b in m.boundaries]:
        raise RuntimeError("找不到绕组 %s" % wn)
    if not m.add_winding_coils(wn, sorted(new_terms)):
        raise RuntimeError("[%s] add_winding_coils 失败" % coil)
    info["terminals_after"] = sorted(new_terms)
    info["elapsed_s"] = round(time.time() - t0, 1)
    log("  [%s] 端子重建 + 挂回 %s (%.1fs)" % (coil, wn, info["elapsed_s"]))
    return info


def rebuild_all(m, paths, width):
    return {c: rebuild_coil(m, c, paths[c], width) for c in COILS}


def set_geometry(m, W, G, tg, thk, dx, B):
    """用生产脚本的几何函数把铁氧体/线圈摆到指定状态。"""
    B.set_rx_dx(m, 0.0)
    B.set_tx_gap(m, tg)
    nf = B.rebuild_ferrite(m, W, G, tg, thk)
    B.ensure_region(m, tg)
    B.set_rx_dx(m, dx)
    log("  几何设置 W=%.1f G=%.1f tg=%.0f thk=%.0f dx=%.0f -> %d 根铁氧体条"
        % (W, G, tg, thk, dx, nf))
    return nf


def snapshot(m):
    """当前所有对象的 bbox 快照（用于交付前和原始状态对比）。"""
    out = {}
    for n in m.modeler.object_names:
        try:
            bb = m.modeler[n].bounding_box
            out[n] = [round(v, 3) for v in bb]
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- 主流程
def main():
    apply_save = "--apply" in sys.argv
    do_solve = "--solve" in sys.argv
    log("=" * 78)
    log("线宽改造流水线  WIDTH_NEW=%.1fmm  WIDTH_OLD=%.1fmm  apply=%s solve=%s"
        % (WIDTH_NEW, WIDTH_OLD, apply_save, do_solve))

    with open(PATHS_JSON, encoding="utf-8") as f:
        paths = json.load(f)
    for c in COILS:
        assert len(paths[c]) == 768, (c, len(paths[c]))
    log("路径点: %s" % {c: len(paths[c]) for c in COILS})

    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=DESIGN)
    log("已打开 %s / %s" % (PROJ, m.design_name))

    # 复用生产脚本的几何函数 + 看门狗（gRPC 会静默挂死，必须带超时）
    import batch_unit30_ws as B
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "solve_points.log")
    B.PLAN_CSV = os.path.join(WORK, "combos_unused.csv")

    def stage(name, fn, timeout=None):
        st, val = B.run_stage(name, fn, timeout or B.STAGE_TIMEOUT)
        if st != "OK":
            raise RuntimeError("阶段 [%s] 失败: %s" % (name, st))
        return val

    result = {}

    # 0) 原始状态核对
    log("")
    log("=== 0. 原始状态核对 ===")
    base = {}
    for c in COILS:
        v = m.modeler[c].volume
        base[c] = {"volume": round(v, 4), "faces": len(m.modeler[c].faces),
                   "bbox": [round(x, 4) for x in m.modeler[c].bounding_box]}
        log("  %-4s 体积=%.4f (基准 %.4f, 差 %+.4f)  面=%d"
            % (c, v, V_OLD[c], v - V_OLD[c], len(m.modeler[c].faces)))
        if abs(v - V_OLD[c]) > 0.01:
            raise RuntimeError("%s 原始体积与基准不符，模型不是预期的那一版" % c)
    result["base"] = base
    result["orig_objects"] = snapshot(m)

    # 1) 3mm 回归
    log("")
    log("=== 1. 回归自检：同代码路径重建 3mm ===")
    reg = stage("回归重建3mm", lambda: rebuild_all(m, paths, WIDTH_OLD), 1800)
    result["regress_3mm"] = reg
    for c in COILS:
        dv = reg[c]["after"]["volume"] - V_OLD[c]
        dtr = reg[c]["trace"]["volume"] - V_TRACE_3
        # 判据1（严）：重建出来的铜带体积必须 = 路径长x3x0.5（直线段扫掠可精确预测）
        # 判据2（松）：总体积差 = 切掉的引线短桩(-0.1414) + 布尔核残差；残差量级
        #               与原模型自身 Tx1/Tx2 镜像差(0.166)同阶，取 0.6 上限
        log("  %-4s 重建3mm 体积=%.4f 与原模型差=%+.4f (短桩理论 %+.4f) 铜带体积差=%+.4f"
            % (c, reg[c]["after"]["volume"], dv, STUB[c], dtr))
        if abs(dtr) > 0.15:
            raise RuntimeError("%s 3mm 铜带体积不合格: %+.4f" % (c, dtr))
        if abs(dv - STUB[c]) > 0.6:
            raise RuntimeError("%s 3mm 回归不合格: %+.4f" % (c, dv))
    result["regress_ok"] = True

    # 2) 改成 2mm
    log("")
    log("=== 2. 重建 2mm ===")
    two = stage("重建2mm", lambda: rebuild_all(m, paths, WIDTH_NEW), 1800)
    result["rebuild_2mm"] = two
    for c in COILS:
        dtr = two[c]["trace"]["volume"] - V_TRACE_2
        # 同一代码路径的 3mm -> 2mm 体积差必须精确等于铜带体积差（不依赖原模型）
        d32 = reg[c]["after"]["volume"] - two[c]["after"]["volume"]
        log("  %-4s 铜带体积=%.4f (差 %+.4f)  3mm->2mm 总体积差=%+.4f (理论 %.4f, 差 %+.4f)"
            % (c, two[c]["trace"]["volume"], dtr, d32, DV_TRACE, d32 - DV_TRACE))
        if abs(dtr) > 0.15:
            raise RuntimeError("%s 2mm 铜带体积不合格: %+.4f" % (c, dtr))
        if abs(d32 - DV_TRACE) > 0.15:
            raise RuntimeError("%s 3mm->2mm 体积差不合格: %+.4f" % (c, d32))
        two[c]["delta_vs_3mm"] = round(d32, 4)
    sizes = {}
    for c in COILS:
        bb = m.modeler[c].bounding_box
        sizes[c] = {"x": round(bb[3] - bb[0], 4), "y": round(bb[4] - bb[1], 4),
                    "z": round(bb[5] - bb[2], 4)}
    result["new_sizes"] = sizes
    log("  改造后尺寸: %s" % sizes)
    log("  -> 发射线圈 X 外尺寸 %.3f（原 168.88）；建议批次脚本 COIL_SIZE = %.2f"
        % (sizes["Tx1"]["x"], sizes["Tx1"]["x"]))

    # 3) 端子/绕组复核
    log("")
    log("=== 3. 端子 / 绕组复核 ===")
    bnd = []
    for b in m.boundaries:
        if b.name.startswith("CT_") or b.name.startswith("Winding"):
            p = b.props
            log("  %-12s Faces=%-9s Winding=%-5s Cond=%-3s Out=%s"
                % (b.name, p.get("Faces"), p.get("Winding"), p.get("Conductor number"),
                   p.get("Point out of terminal")))
            if b.name.startswith("CT_"):
                bnd.append({"name": b.name, "faces": p.get("Faces"),
                            "winding": p.get("Winding"), "cond": p.get("Conductor number")})
    result["boundaries_after"] = bnd
    if len(bnd) != 6 or any(str(x["cond"]) != "1" for x in bnd):
        raise RuntimeError("端子数/Conductor 不对: %s" % bnd)

    # 4) A/B 双求解
    if do_solve:
        def run_point(tag):
            csvp = os.path.join(WORK, "solve_%s.csv" % tag)
            if os.path.exists(csvp):
                os.remove(csvp)
            B.OUT_CSV = csvp
            set_geometry(m, PT["W"], PT["G"], PT["tg"], PT["thk"], PT["dx"], B)
            log("")
            log("=== 求解 [%s] W=%.0f G=%.0f dx=%.0f tg=%.0f mu=%.0f thk=%.0f (%s) ==="
                % (tag, PT["W"], PT["G"], PT["dx"], PT["tg"], PT["mu"], PT["thk"], csvp))
            t0 = time.time()
            st, res = B.run_stage("求解[%s]" % tag,
                                  lambda: B.solve_and_extract(d, m, PT["W"], PT["G"], PT["dx"],
                                                              PT["tg"], PT["mu"], PT["thk"]),
                                  B.SOLVE_TIMEOUT)
            ok = (st == "OK" and bool(res))
            log("  [%s] 看门狗=%s 返回=%s，耗时 %.1f 分钟" % (tag, st, res, (time.time() - t0) / 60.0))
            rows = []
            if os.path.exists(csvp):
                with open(csvp) as f:
                    rows = [r.strip() for r in f if r.strip()]
            return {"ok": ok, "stage": st, "csv": rows,
                    "minutes": round((time.time() - t0) / 60.0, 2)}

        log("")
        log("########## A/B 双求解开始 ##########")
        result["solve_2mm"] = run_point("width2")     # 当前就是 2mm
        log("")
        log("--- 切到 3mm 做对照 ---")
        result["switch_3mm"] = stage("切回3mm", lambda: rebuild_all(m, paths, WIDTH_OLD), 1800)
        result["solve_3mm"] = run_point("width3")
        log("")
        log("--- 切回 2mm ---")
        result["switch_2mm"] = stage("切回2mm", lambda: rebuild_all(m, paths, WIDTH_NEW), 1800)
        log("########## A/B 双求解结束 ##########")

    # 5) 恢复原始几何状态
    log("")
    log("=== 5. 恢复原始几何状态（只留线宽这一处差异）===")
    stage("恢复原始几何", lambda: set_geometry(m, ORIG_GEOM["W"], ORIG_GEOM["G"], ORIG_GEOM["tg"],
                                              ORIG_GEOM["thk"], ORIG_GEOM["dx"], B), 1800)
    now = snapshot(m)
    result["final_objects"] = now
    diff = []
    for n in sorted(set(list(result["orig_objects"].keys()) + list(now.keys()))):
        a = result["orig_objects"].get(n)
        b = now.get(n)
        if a is None or b is None or max(abs(x - y) for x, y in zip(a, b)) > 0.05:
            diff.append((n, a, b))
    for n, a, b in diff:
        log("  几何差异 %-16s 原=%s 现=%s" % (n, a, b))
    result["noncoil_diff"] = [d[0] for d in diff]
    log("  除线圈外的几何差异: %s" % (result["noncoil_diff"] or "无"))

    if apply_save:
        log("")
        log("save_project -> %s" % m.save_project())
        result["saved"] = True
    else:
        log("")
        log("DRY-RUN：未存盘")
        result["saved"] = False

    dump_json(result)
    log("结果 JSON -> %s" % RESULT_JSON)
    log("流水线结束")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!! 失败：\n" + traceback.format_exc())
        dump_json({"error": traceback.format_exc(), "log": LOG_LINES})
        sys.exit(1)
