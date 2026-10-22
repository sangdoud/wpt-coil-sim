# -*- coding: utf-8 -*-
"""A 组：单个求解开关的逐个实测（参考点，8 核/8 趟/5%，旧模板=现模型几何）。

每组都给：耗时、Δ耗时 vs 同会话基线、电感偏差（L11/L22/L33/M12/M13/M23）、
自适应趟数、初始网格耗时、结果有效性。

  A0_base      基线：滑块 5 / Auto / flex 关 / PercentRefinement 5 / RelativeResidual 原值
  A1_flex      UseFlexMeshingForTAUvolumeMesh = True（柔性网格，面向薄层结构）
  A2_classic   MeshMethod = AnsoftClassic
  A3_pref15    PercentRefinement = 15（每趟多加密，可能少走趟）
  A4_rres1e5   RelativeResidual = 1e-5（迭代求解容差放宽）

注意：所有对比都在**同一会话内**做（跨会话的历史数字不可比，前面已吃过一次亏）。
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
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

aedt_shim.patch_pyaedt_proc()

PROJ = os.path.join(WORK, "Projecttonight_4ch.aedt")
RESDIR = os.path.join(WORK, "Projecttonight_4ch.aedtresults", "WPT_G.results")
TMPL_OLD = r"C:\wpt\coil_template_Rx.json"
LOGF = os.path.join(WORK, "queueA.log")
OUT = os.path.join(WORK, "queueA.json")
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
REGION_REF = {"x": (-205.0, 205.0), "y": (-134.94, 134.0), "z": (-45.0, 75.0)}
RES = {}

STEPS = [
    ("A0_base",    dict(flex=False, method="Auto",           level=5, pref=5,  rres=None,   desc="基线")),
    ("A1_flex",    dict(flex=True,  method="Auto",           level=5, pref=5,  rres=None,   desc="柔性网格 ON")),
    ("A2_classic", dict(flex=False, method="AnsoftClassic",  level=5, pref=5,  rres=None,   desc="经典网格器")),
    ("A3_pref15",  dict(flex=False, method="Auto",           level=5, pref=15, rres=None,   desc="PercentRefinement=15")),
    ("A4_rres1e5", dict(flex=False, method="Auto",           level=5, pref=5,  rres="1e-05", desc="RelativeResidual=1e-5")),
]


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


B.kill_aedt = kill_aedt_ps


# ------------------------------------------------------------------ 工具
def stats_of(row):
    if not row:
        return None
    v = [float(x) for x in row.split(",")]
    return dict(L11=v[8], L22=v[9], L33=v[10], M12=v[11], M13=v[12], M23=v[13],
                k13=v[14], k23=v[15])


def validity(st):
    if not st:
        return False, "无结果行"
    z = [k for k in ("L11", "L22", "L33") if st[k] <= 0]
    if z:
        return False, "自感<=0: %s" % z
    if st["M13"] == 0 or st["M23"] == 0:
        return False, "互感为 0（绕组可能未挂上）"
    if abs(st["k13"]) > 1 or abs(st["k23"]) > 1:
        return False, "|k|>1"
    return True, ""


def pct(a, b, keys=("L11", "L22", "L33", "M12", "M13", "M23")):
    if not a or not b:
        return None
    return {k: round(100.0 * (a[k] - b[k]) / abs(b[k]), 4) for k in keys}


def profile_now():
    fs = [f for f in os.listdir(RESDIR) if f.endswith(".profile")]
    if not fs:
        return {}
    f = max((os.path.join(RESDIR, x) for x in fs), key=os.path.getmtime)
    txt = open(f, encoding="utf-8", errors="replace").read().splitlines()
    out, group, npass, tets, mem_max = {}, None, 0, [], 0
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
    out["adaptive_elapsed"] = (out.get("elapsed") or {}).get("Adaptive Meshing")
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


def create_region_to_box(m3d, box):
    bb = objs_bbox(m3d)
    if bb is None:
        return None
    pad = [box["x"][1] - bb[3], bb[0] - box["x"][0],
           box["y"][1] - bb[4], bb[1] - box["y"][0],
           box["z"][1] - bb[5], bb[2] - box["z"][0]]
    if any(v < -1e-6 for v in pad):
        log("  !! 物体超出目标盒 pad=%s" % pad)
        return None
    try:
        m3d.modeler.delete("Region")
    except Exception:
        pass
    time.sleep(1)
    m3d.modeler.create_region(pad_value=["%.4fmm" % max(0.0, v) for v in pad],
                              pad_type="Absolute Offset")
    rbb = m3d.modeler["Region"].bounding_box
    log("  Region: X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]"
        % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5]))
    return rbb


def set_mesh(flex, method, level):
    m.mesh.assign_initial_mesh_from_slider(level=level, method=method, flex_mesh=flex)
    p = dict(m.mesh.initial_mesh_settings.props)
    log("  网格设置: flex=%s method=%s level=%d  (读回 GlobalSurfApproximation=%s)"
        % (flex, method, level, p.get("GlobalSurfApproximation")))
    return p


def set_rres(val):
    s = m.setups[0]
    if val is None:
        return dict(s.props).get("RelativeResidual")
    s.props["RelativeResidual"] = val
    s.update()
    got = dict(s.props).get("RelativeResidual")
    log("  RelativeResidual -> %s (读回 %s)" % (val, got))
    return got


def solve(tag, passes=8, pct_=5.0):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, passes, pct_
    csvp = os.path.join(WORK, "solve_qA_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, 0.05)
    B.set_rx_dx(m, 0.0)
    log(">>> [%s] 8 核 / %d 趟 / %.1f%% ..." % (tag, passes, pct_))
    t0 = time.time()
    st, r = B.run_stage("求解[%s]" % tag,
                        lambda: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                    PT["W"], PT["G"], 0.0, PT["mu"], PT["thk"]),
                        3600)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    row = rows[-1] if len(rows) > 1 else ""
    prof = profile_now()
    stt = stats_of(row)
    ok, why = validity(stt)
    log("    [%s] %s %.2f 分钟  初始网格=%s 趟数=%s  有效性=%s %s"
        % (tag, st, dt, prof.get("initial_mesh_elapsed"), prof.get("n_passes"),
           "OK" if ok else "!! INVALID", why))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, stage=st, ok=bool(r), minutes=round(dt, 2), row=row,
                stats=stt, valid=ok, invalid_reason=why, profile=prof)


def main():
    global d, m
    log("#" * 78)
    log("A 组：求解开关逐个实测")
    kill_aedt_ps()
    clear_lock(PROJ)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "queueA_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s" % m.design_name)

    # 清残留：MeshLink / 网格操作 / donor 设计
    try:
        s = m.setups[0]
        p = dict(s.props.get("MeshLink") or {})
        if p.get("ImportMesh"):
            p["ImportMesh"] = False
            s.props["MeshLink"] = p
            s.update()
            log("  清掉残留 MeshLink")
    except Exception as e:
        log("  MeshLink 清理: %r" % e)
    for mo in list(m.mesh.meshoperations):
        log("  删除网格操作 %s" % mo.name)
        mo.delete()
    try:
        if "WPT_mesh" in d.design_list():
            m.delete_design("WPT_mesh")
            log("  删除 donor 设计 WPT_mesh")
    except Exception as e:
        log("  donor 删除: %r" % e)

    # 基线几何
    CG.TEMPLATE = TMPL_OLD
    CG._ref = None
    CG._s_ref = None
    CG._load()
    B.set_rx_dx(m, 0.0)
    CG.rebuild_all(m, PT["LC"], PT["KR"], log=log)
    tg = PT["KX"] * PT["LC"]
    outer = CG.coil_outer(PT["LC"])
    rx_leads = CG.current_leads(m, "Rx")
    B.set_tx_gap(m, tg, outer)
    nf = B.rebuild_ferrite(m, PT["W"], PT["G"], tg, PT["thk"], outer, rx_leads)
    create_region_to_box(m, REGION_REF)
    log("几何就绪：铁氧体 %d 条" % nf)
    RES["setup_props_orig"] = {k: v for k, v in dict(m.setups[0].props).items()
                              if k in ("MaximumPasses", "PercentError", "PercentRefinement",
                                       "RelativeResidual", "UseIterativeSolver",
                                       "SolveMatrixAtLast", "MinimumConvergedPasses")}
    log("  原始 setup: %s" % RES["setup_props_orig"])
    dump()

    for tag, cfg in STEPS:
        log("")
        log("---- %s : %s ----" % (tag, cfg["desc"]))
        try:
            set_mesh(cfg["flex"], cfg["method"], cfg["level"])
        except Exception as e:
            log("  !! 网格设置失败: %r" % e)
        B.PCT_REFINEMENT = cfg["pref"]
        if cfg["rres"] is not None:
            set_rres(cfg["rres"])
        else:
            cur = set_rres(None)
            log("  RelativeResidual 保持 %s" % cur)
        RES[tag] = solve(tag)
        RES[tag]["cfg"] = cfg
        dump()

    # 汇总
    base = RES["A0_base"]
    log("")
    log("=== A 组汇总（基线 A0 = %.2f 分钟，L11=%.3f）===" % (base["minutes"], base["stats"]["L11"]))
    for tag, cfg in STEPS[1:]:
        r = RES[tag]
        if not r["stats"]:
            log("  %-12s  %6.2f 分钟  无有效结果" % (tag, r["minutes"]))
            continue
        d_ = pct(r["stats"], base["stats"])
        r["vs_base"] = dict(time_pct=round(100.0 * (r["minutes"] - base["minutes"]) / base["minutes"], 2),
                            l_pct=d_, valid=r["valid"])
        worst = max(abs(v) for v in d_.values())
        log("  %-12s %6.2f 分钟 (%+6.2f%%)  偏差 max %.3f%%  [%s]  %s"
            % (tag, r["minutes"], r["vs_base"]["time_pct"], worst,
               "有效" if r["valid"] else "无效:" + r["invalid_reason"], d_))
    dump()
    log("全部完成")
    try:
        kill_aedt_ps(wait_s=40)
        clear_lock(PROJ)
    except Exception:
        pass


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
