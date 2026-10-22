# -*- coding: utf-8 -*-
"""按价值排序的验证队列（⑦ 之后的 P1/P2/P3）。

P1  ① 镜像半扫的对称性复验（当前几何！文档那份 0.9% 是旧几何量的）
      参考点 x=+7.1095 与 x=-7.1095 各解一次，检查
        max|M1(+x) - M2(-x)| / 峰值 <= 2%   （① 成立的前提）
P2  ② Region 随 Lc 缩放：修好"守门条件写反"的 bug 后，在 LC=120 小线圈上量效
      R0 = 沿用现区域（X±205）   R1 = ② 规则区域（X±162, Y<=132）
      比耗时 + 电感偏差（区域是物理量，偏差非零属正常，要看有多大）
P3  网格密度矩阵（回到参考点）：M0 基线 / M3 去掉自适应 / M1 全局初始网格粗化 / M2 M1+⑥

用法：python queue_verify.py p1|p2|p3|all
每一步都增量落盘到 queue_verify.json。
"""
import json
import os
import re
import subprocess
import sys
import time
import traceback

import numpy as np

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                               # noqa: E402
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import batch_sweep_lc as B                       # noqa: E402
import coil_gen as CG                            # noqa: E402
import wpt_contract as WC                        # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

aedt_shim.patch_pyaedt_proc()

PROJ = os.path.join(WORK, "Projecttonight_4ch.aedt")
RESDIR = os.path.join(WORK, "Projecttonight_4ch.aedtresults", "WPT_G.results")
TMPL_OLD = r"C:\wpt\coil_template_Rx.json"
LOGF = os.path.join(WORK, "queue_verify.log")
OUT = os.path.join(WORK, "queue_verify.json")
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
REGION_REF = {"x": (-205.0, 205.0), "y": (-134.94, 134.0), "z": (-45.0, 75.0)}
RES = {}


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    try:
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass


def dump():
    json.dump(RES, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)


def run_ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                          capture_output=True, text=True)


def kill_aedt_ps(wait_s=60):
    t0 = time.time()
    while time.time() - t0 < wait_s:
        run_ps("Get-Process -Name ansysedt,ansyscl -ErrorAction SilentlyContinue |"
               " Stop-Process -Force -ErrorAction SilentlyContinue")
        time.sleep(3)
        r = run_ps("@(Get-Process -Name ansysedt -ErrorAction SilentlyContinue).Count")
        if (r.stdout or "").strip() in ("0", ""):
            break


def clear_lock(proj):
    lk = proj + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
        log("  已删除陈旧锁 %s" % os.path.basename(lk))


B.kill_aedt = kill_aedt_ps


# ---------------------------------------------------------------- 通用工具
def stats_of(row):
    if not row:
        return None
    v = [float(x) for x in row.split(",")]
    return dict(L11=v[8], L22=v[9], L33=v[10], M12=v[11], M13=v[12], M23=v[13],
                k13=v[14], k23=v[15])


def m1m2_of(row):
    if not row:
        return None
    v = [float(x) for x in row.split(",")]
    return dict(M1=v[12], M2=v[13])          # M13 = Tx1-Rx = M1, M23 = Tx2-Rx = M2


def profile_now():
    fs = [f for f in os.listdir(RESDIR) if f.endswith(".profile")]
    if not fs:
        return {}
    f = max((os.path.join(RESDIR, x) for x in fs), key=os.path.getmtime)
    txt = open(f, encoding="utf-8", errors="replace").read().splitlines()
    out, group, npass = {"file": os.path.basename(f)}, None, 0
    tets, mem_max = [], 0
    for ln in txt:
        m = re.search(r"Name='([^']+)'", ln)
        if m:
            group = m.group(1)
            if re.match(r"Pass \d+", group):
                npass += 1
            continue
        m = re.search(r"I\(1, 'Elapsed Time', '([^']+)'\)", ln)
        if m and group:
            out.setdefault("elapsed", {})[group] = m.group(1)
            continue
        m = re.search(r"ProfileItem\('([^']*)', (\d+), 0, (\d+), 0, (\d+), 'I\((\d+), (.*)\)'", ln)
        if m:
            name, cpu, el, mem, n, args = m.groups()
            mem_max = max(mem_max, int(mem))
            tm = re.search(r"'Tetrahedra', (\d+)", args)
            if tm:
                tets.append(int(tm.group(1)))
                if name == "Mesh":
                    out["tets_raw"] = int(tm.group(1))
                elif name == "Coarsen":
                    out["tets_coarsened"] = int(tm.group(1))
    out["n_passes"] = npass
    out["tets_last"] = tets[-1] if tets else None
    out["mem_max_kb"] = mem_max or None
    out["initial_mesh_elapsed"] = (out.get("elapsed") or {}).get("Initial Meshing")
    return out


def objs_bbox(m3d):
    bb = None
    for o in m3d.modeler.object_names:
        if o == "Region":
            continue
        try:
            b = m3d.modeler[o].bounding_box
        except Exception:
            continue
        bb = list(b) if bb is None else [min(bb[0], b[0]), min(bb[1], b[1]), min(bb[2], b[2]),
                                         max(bb[3], b[3]), max(bb[4], b[4]), max(bb[5], b[5])]
    return bb


def create_region_to_box(m3d, box, log=print):
    """把 Region 重建成恰好 box 指定的盒子（正确版）：

    原始 ensure_region 的 padding 公式对 -X/-Y/-Z 侧符号写反（`目标-物体` 在物体位于盒内时
    必为负 -> 被 max(0,·) 夹成 0 -> 区域面贴在物体上），再加一句 `min(need)<0 就 return`
    的守门，导致它**从来没执行过**。这里按「物体到盒面的距离」正确算 padding。
    """
    bb = objs_bbox(m3d)
    if bb is None:
        return None
    out = (bb[0] < box["x"][0] - 1e-6 or bb[3] > box["x"][1] + 1e-6 or
           bb[1] < box["y"][0] - 1e-6 or bb[4] > box["y"][1] + 1e-6 or
           bb[2] < box["z"][0] - 1e-6 or bb[5] > box["z"][1] + 1e-6)
    if out:
        log("  !! 物体超出目标盒: bbox=%s box=%s" % (["%.2f" % v for v in bb], box))
        return None
    pad = [box["x"][1] - bb[3], bb[0] - box["x"][0],
           box["y"][1] - bb[4], bb[1] - box["y"][0],
           box["z"][1] - bb[5], bb[2] - box["z"][0]]
    PAD = ["%.4fmm" % max(0.0, v) for v in pad]
    try:
        m3d.modeler.delete("Region")
    except Exception:
        pass
    time.sleep(1)
    try:
        m3d.modeler.create_region(pad_value=PAD, pad_type="Absolute Offset")
    except Exception as e:
        log("  !! create_region 失败: %r" % e)
        return None
    rbb = m3d.modeler["Region"].bounding_box
    log("  Region 重建: X[%.2f,%.2f] Y[%.2f,%.2f] Z[%.2f,%.2f]  (pad=%s)"
        % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5], PAD))
    return rbb


def build_ref_geometry(LC, KR, KX, W, G, thk, log=print):
    CG.TEMPLATE = TMPL_OLD
    CG._ref = None
    CG._s_ref = None
    CG._load()
    B.set_rx_dx(m, 0.0)
    CG.rebuild_all(m, LC, KR, log=log)
    tg = KX * LC
    outer = CG.coil_outer(LC)
    rx_leads = CG.current_leads(m, "Rx")
    B.set_tx_gap(m, tg, outer)
    nf = B.rebuild_ferrite(m, W, G, tg, thk, outer, rx_leads)
    log("  铁氧体 %d 条  tg=%.2f  outer=%.4f" % (nf, tg, outer))
    return tg, outer


def solve(tag, dx, passes=8, pct=5.0, LC=None, KR=None, KX=None):
    LC = PT["LC"] if LC is None else LC
    KR = PT["KR"] if KR is None else KR
    KX = PT["KX"] if KX is None else KX
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, passes, pct
    csvp = os.path.join(WORK, "solve_q_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, dx + 0.05)
    B.set_rx_dx(m, dx)
    log(">>> [%s] dx=%.4f  %d 趟 / %.1f%% ..." % (tag, dx, passes, pct))
    t0 = time.time()
    st, r = B.run_stage("求解[%s]" % tag,
                        lambda: B.solve_and_extract(d, m, LC, KR, KX, PT["W"], PT["G"],
                                                    dx, PT["mu"], PT["thk"]),
                        3600)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    row = rows[-1] if len(rows) > 1 else ""
    prof = profile_now()
    log("    [%s] %s  %.2f 分钟  趟数=%s 初始网格=%s (%s->%s 单元) 峰值内存 %.2fGB"
        % (tag, st, dt, prof.get("n_passes"), prof.get("initial_mesh_elapsed"),
           prof.get("tets_raw"), prof.get("tets_coarsened"),
           (prof.get("mem_max_kb") or 0) / 1048576.0))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, dx=dx, stage=st, ok=bool(r), minutes=round(dt, 2),
                passes=passes, pct=pct, row=row, stats=stats_of(row),
                m1m2=m1m2_of(row), profile=prof)


def pct(a, b, keys=("L11", "L22", "L33", "M12", "M13", "M23")):
    if not a or not b:
        return None
    return {k: round(100.0 * (a[k] - b[k]) / abs(b[k]), 4) for k in keys}


# ---------------------------------------------------------------- P1
def phase1():
    log("")
    log("=" * 78)
    log("P1  ① 镜像半扫对称性复验（当前几何：换个引线 + Tx 分层）")
    STEP = PT["LC"] * (2.0 + PT["KX"]) / 40.0
    build_ref_geometry(PT["LC"], PT["KR"], PT["KX"], PT["W"], PT["G"], PT["thk"], log)
    create_region_to_box(m, REGION_REF, log)
    a = solve("P1_xpos", +STEP)
    b = solve("P1_xneg", -STEP)
    RES["P1_symmetry"] = dict(step=STEP, pos=a, neg=b)
    if a["m1m2"] and b["m1m2"]:
        pa, pb = a["m1m2"], b["m1m2"]
        pk = max(abs(pa["M1"]), abs(pa["M2"]), abs(pb["M1"]), abs(pb["M2"])) or 1.0
        e1 = abs(pa["M1"] - pb["M2"]) / pk          # M1(+x) vs M2(-x)
        e2 = abs(pa["M2"] - pb["M1"]) / pk          # M2(+x) vs M1(-x)
        RES["P1_symmetry"]["err_M1pos_vs_M2neg"] = round(100 * e1, 4)
        RES["P1_symmetry"]["err_M2pos_vs_M1neg"] = round(100 * e2, 4)
        RES["P1_symmetry"]["crit_pct"] = 2.0
        RES["P1_symmetry"]["pass"] = bool(max(e1, e2) * 100 <= 2.0)
        log("  M1(+x)=%.4f  M2(+x)=%.4f | M1(-x)=%.4f  M2(-x)=%.4f  (峰值 %.4f)"
            % (pa["M1"], pa["M2"], pb["M1"], pb["M2"], pk))
        log("  |M1(+x)-M2(-x)|/峰值 = %.3f%%   |M2(+x)-M1(-x)|/峰值 = %.3f%%"
            % (100 * e1, 100 * e2))
        log("  判据 <=2%%  ->  %s" % ("通过 ✓（① 的 −49%% 可兑现）"
                                      if RES["P1_symmetry"]["pass"] else "不通过 ✗"))
    dump()


# ---------------------------------------------------------------- P2
def phase2():
    log("")
    log("=" * 78)
    log("P2  ② Region 随 Lc 缩放量效（LC=120 小线圈）")
    LC, KR, KX = 120.0, 0.50, -0.3
    build_ref_geometry(LC, KR, KX, PT["W"], PT["G"], PT["thk"], log)
    create_region_to_box(m, REGION_REF, log)          # R0：沿用现区域口径
    r0 = solve("P2_R0_fixed", 0.0, LC=LC, KR=KR, KX=KX)
    box = WC.region_box(LC, KX)
    log("  ② 规则盒: X[%.2f,%.2f] Y[%.2f,%.2f] Z[%.2f,%.2f]"
        % (box["x"][0], box["x"][1], box["y"][0], box["y"][1], box["z"][0], box["z"][1]))
    create_region_to_box(m, box, log)                  # R1：② 缩放区域
    r1 = solve("P2_R1_scaled", 0.0, LC=LC, KR=KR, KX=KX)
    RES["P2_region"] = dict(LC=LC, KR=KR, R0=r0, R1=r1, box=box)
    if r0["stats"] and r1["stats"]:
        RES["P2_region"]["time_pct"] = round(
            100.0 * (r1["minutes"] - r0["minutes"]) / r0["minutes"], 2)
        RES["P2_region"]["l_pct"] = pct(r1["stats"], r0["stats"])
        log("  耗时: 固定区域 %.2f 分钟 -> ② 缩放 %.2f 分钟 (%+.2f%%)"
            % (r0["minutes"], r1["minutes"], RES["P2_region"]["time_pct"]))
        log("  电感偏差: %s" % RES["P2_region"]["l_pct"])
    dump()


# ---------------------------------------------------------------- P3
def phase3():
    log("")
    log("=" * 78)
    log("P3  网格密度矩阵（参考点，旧模板）")
    build_ref_geometry(PT["LC"], PT["KR"], PT["KX"], PT["W"], PT["G"], PT["thk"], log)
    create_region_to_box(m, REGION_REF, log)
    try:
        for mo in list(m.mesh.meshoperations):
            mo.delete()
    except Exception:
        pass
    RES["P3_slider_orig"] = dict(m.mesh.initial_mesh_settings.props.get("GlobalSurfApproximation") or {})
    RES["P3_M3_noadapt"] = solve("P3_M3_noadapt", 0.0, passes=1, pct=5.0)
    dump()
    RES["P3_M0_base"] = solve("P3_M0_base", 0.0, passes=8, pct=5.0)
    dump()
    log("---- 全局初始网格滑块 -> 2 (Coarse) ----")
    try:
        m.mesh.assign_initial_mesh_from_slider(level=2, method="Auto")
        RES["P3_slider_2"] = dict(m.mesh.initial_mesh_settings.props.get("GlobalSurfApproximation") or {})
        log("  = %s" % RES["P3_slider_2"])
    except Exception as e:
        RES["P3_slider_err"] = repr(e)
    RES["P3_M1_slider2"] = solve("P3_M1_slider2", 0.0, passes=8, pct=5.0)
    dump()
    log("---- 滑块 2 + ⑥ Region 最大单元尺寸 Lc/5 ----")
    try:
        op = m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                       maximum_length="%.4fmm" % (PT["LC"] / 5.0),
                                       maximum_elements=None, name="region_coarse")
        RES["P3_region_op"] = str(getattr(op, "name", op))
    except Exception as e:
        RES["P3_region_op_err"] = repr(e)
    RES["P3_M2_slider2_six"] = solve("P3_M2_slider2_six", 0.0, passes=8, pct=5.0)
    dump()
    b = RES["P3_M0_base"]
    log("")
    log("=== P3 汇总（基线 M0 = %.2f 分钟）===" % b["minutes"])
    for k in ("P3_M3_noadapt", "P3_M1_slider2", "P3_M2_slider2_six"):
        r = RES[k]
        d_ = pct(r["stats"], b["stats"])
        RES[k + "_vs_M0"] = dict(
            time_pct=round(100.0 * (r["minutes"] - b["minutes"]) / b["minutes"], 2), l_pct=d_)
        log("  %-18s %6.2f 分钟 (%+.1f%%)  趟数 %s  初始网格 %s  电感 %s"
            % (k, r["minutes"], RES[k + "_vs_M0"]["time_pct"], r["profile"].get("n_passes"),
               r["profile"].get("initial_mesh_elapsed"), d_))
    dump()


def clear_meshlink():
    """清掉 setup 上的 MeshLink（⑦ 自链接试验失败后留在工程里，不清会让后续求解全部 AnalyzeAll 失败）。"""
    try:
        s = m.setups[0]
        before = dict(s.props.get("MeshLink") or {})
        if before.get("ImportMesh"):
            p = dict(before)
            p["ImportMesh"] = False
            s.props["MeshLink"] = p
            s.update()
        after = dict(s.props.get("MeshLink") or {})
        log("  MeshLink: %s -> %s" % (before, after))
        return after
    except Exception as e:
        log("  !! 清 MeshLink 失败: %r" % e)
        return None


def main():
    global d, m
    which = (sys.argv[1] if len(sys.argv) > 1 else "all").lower()
    log("#" * 78)
    log("验证队列: %s" % which)
    if os.path.exists(OUT):
        try:
            RES.update(json.load(open(OUT, encoding="utf-8")))
            log("已载入既有结果 %d 项" % len(RES))
        except Exception:
            pass
    kill_aedt_ps()
    clear_lock(PROJ)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "queue_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s" % m.design_name)
    RES["meshlink_cleared"] = clear_meshlink()
    try:
        if which in ("p1", "all"):
            phase1()
        if which in ("p2", "all"):
            phase2()
        if which in ("p3", "all"):
            phase3()
    finally:
        dump()
        try:
            kill_aedt_ps(wait_s=40)
            clear_lock(PROJ)
        except Exception:
            pass
    log("队列完成")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!! 失败\n" + traceback.format_exc())
        RES["fatal"] = traceback.format_exc()
        try:
            dump()
        except Exception:
            pass
        sys.exit(1)
