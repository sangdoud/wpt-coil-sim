# -*- coding: utf-8 -*-
"""网格密度限制的对照矩阵（参考点，8 核，旧模板=现模型几何）。

四组，全部在本会话内背靠背跑（跨会话的历史数字不可比）：

  M3_noadapt      MaximumPasses=1（彻底去掉自适应，只剩初始网格）
  M0_base         8 趟/5%，原始网格设置（= 同会话基线）
  M1_slider2      全局初始网格滑块 = 2（Coarse），8 趟/5%
  M2_slider2_six  M1 + ⑥ Region 最大单元尺寸 = Lc/5

每组记录：耗时、自适应趟数、初始网格各阶段耗时、原始/粗化后单元数、峰值内存、电感。

顺序说明：M3 排在最前，这样滑块改动前后"原始设置"只被用到一次，不需要恢复；
滑块一旦改到 2，后面两组都在同一前提下对照。
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
LOGF = os.path.join(WORK, "matrix_meshlimit.log")
OUT = os.path.join(WORK, "matrix_meshlimit.json")
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
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


def stats_of(row):
    if not row:
        return None
    v = [float(x) for x in row.split(",")]
    return dict(L11=v[8], L22=v[9], L33=v[10], M12=v[11], M13=v[12], M23=v[13],
                k13=v[14], k23=v[15])


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
                t = int(tm.group(1))
                tets.append(t)
                if name == "Mesh":
                    out["tets_raw"] = t
                elif name == "Coarsen":
                    out["tets_coarsened"] = t
        m = re.search(r"ProfileFootnote\('I\(\d+, 1, 'Stop Time', '([^']+)'", ln)
        if m:
            out["stop"] = m.group(1)
    out["n_passes"] = npass
    out["tets_last"] = tets[-1] if tets else None
    out["mem_max_kb"] = mem_max or None
    out["initial_mesh_elapsed"] = (out.get("elapsed") or {}).get("Initial Meshing")
    out["adaptive_elapsed"] = (out.get("elapsed") or {}).get("Adaptive Meshing")
    return out


def set_region_op(on):
    try:
        if on:
            max_len = PT["LC"] / 5.0
            op = m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                           maximum_length="%.4fmm" % max_len,
                                           maximum_elements=None, name="region_coarse")
            return str(getattr(op, "name", op))
        for mo in list(m.mesh.meshoperations):
            mo.delete()
        return None
    except Exception as e:
        log("  !! 网格操作失败: %s" % repr(e))
        return "ERR:%r" % e


def solve(tag, passes, pct):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, passes, pct
    csvp = os.path.join(WORK, "solve_mx_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, 0.05)
    B.set_rx_dx(m, 0.0)
    log(">>> [%s] 8 核 / %d 趟 / %.1f%% ..." % (tag, passes, pct))
    t0 = time.time()
    st, r = B.run_stage("求解[%s]" % tag,
                        lambda: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                    PT["W"], PT["G"], 0.0, PT["mu"], PT["thk"]),
                        3600)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    row = rows[-1] if len(rows) > 1 else ""
    prof = profile_now()
    log("    [%s] %s  %.2f 分钟  趟数=%s  初始网格=%s (原始 %s -> 粗化 %s 单元)  峰值内存 %.2f GB"
        % (tag, st, dt, prof.get("n_passes"), prof.get("initial_mesh_elapsed"),
           prof.get("tets_raw"), prof.get("tets_coarsened"),
           (prof.get("mem_max_kb") or 0) / 1048576.0))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, stage=st, ok=bool(r), minutes=round(dt, 2),
                passes=passes, pct=pct, row=row, stats=stats_of(row), profile=prof)


def pct(a, b, keys=("L11", "L22", "L33", "M12", "M13", "M23")):
    if not a or not b:
        return None
    return {k: round(100.0 * (a[k] - b[k]) / abs(b[k]), 4) for k in keys}


def main():
    global d, m
    log("=" * 78)
    log("网格密度限制对照矩阵：M3(无自适应) / M0(基线) / M1(全局粗化) / M2(粗化+⑥)")
    kill_aedt_ps()
    clear_lock(PROJ)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "matrix_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s / %s" % (PROJ, m.design_name))
    RES["initial_mesh_settings"] = dict(m.mesh.initial_mesh_settings.props)
    log("初始网格设置: %s" % RES["initial_mesh_settings"].get("GlobalSurfApproximation"))
    # 恢复成基线几何：旧模板 + Rx 归零 + 铁氧体/区域
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
    B.ensure_region(m, tg)
    set_region_op(False)
    log("几何就绪（旧模板）：铁氧体 %d 条" % nf)
    dump()

    # ---- M3: 彻底去掉自适应 ----
    RES["M3_noadapt"] = solve("M3_noadapt", 1, 5.0)
    dump()

    # ---- M0: 同会话基线 ----
    RES["M0_base"] = solve("M0_base", 8, 5.0)
    dump()

    # ---- M1: 全局初始网格粗化（滑块 = 2）----
    log("")
    log("---- M1: 全局初始网格滑块 -> 2 (Coarse) ----")
    try:
        m.mesh.assign_initial_mesh_from_slider(level=2, method="Auto")
        RES["slider"] = dict(m.mesh.initial_mesh_settings.props.get("GlobalSurfApproximation") or {})
        log("  GlobalSurfApproximation = %s" % RES["slider"])
    except Exception as e:
        RES["slider_err"] = repr(e)
        log("  !! 设置滑块失败: %s" % repr(e))
    RES["M1_slider2"] = solve("M1_slider2", 8, 5.0)
    dump()

    # ---- M2: 滑块 2 + ⑥ ----
    log("")
    log("---- M2: 滑块 2 + ⑥ Region 最大单元尺寸 = Lc/5 ----")
    RES["region_op"] = set_region_op(True)
    log("  网格操作: %s" % RES["region_op"])
    RES["M2_slider2_six"] = solve("M2_slider2_six", 8, 5.0)
    dump()

    # ---- 汇总 ----
    b = RES["M0_base"]
    log("")
    log("=== 汇总（基线 M0 = %.2f 分钟）===" % b["minutes"])
    for k in ("M3_noadapt", "M1_slider2", "M2_slider2_six"):
        r = RES[k]
        d_ = pct(r["stats"], b["stats"])
        RES[k + "_vs_M0"] = dict(time_pct=round(100.0 * (r["minutes"] - b["minutes"]) / b["minutes"], 2),
                                 l_pct=d_)
        log("  %-16s %6.2f 分钟 (%+.1f%%)  趟数 %s  初始网格 %s  电感偏差 %s"
            % (k, r["minutes"], RES[k + "_vs_M0"]["time_pct"], r["profile"].get("n_passes"),
               r["profile"].get("initial_mesh_elapsed"), d_))
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
