# -*- coding: utf-8 -*-
"""⑦ PoC：跨位置网格复用（Apply Mesh / MeshLink）能不能用、能省多少。

场景（与生产扫描一致）：
  工程里已有 dx=0、旧模板、已收敛的 LastAdaptive 解（跟随实验 S4 留下的）。
  Rx 沿扫描方向走一档 dx = S/40 = 7.1096mm，然后：
     A) 套用上一位置的网格（setup MeshLink -> 本设计 LastAdaptive）再求解
     B) 不套用，按常规从零生成初始网格再求解
  两次几何完全相同，只有网格来源不同 -> 时间差 = ⑦ 的收益，电感差 = ⑦ 的精度代价。

判据：耗时降幅（期望 −30~50%）、电感偏差 <0.5%、.profile 里"初始网格"阶段是否被跳过。
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
LOGF = os.path.join(WORK, "poc7_meshreuse.log")
OUT = os.path.join(WORK, "poc7_meshreuse.json")
TMPL_OLD = r"C:\wpt\coil_template_Rx.json"
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
DX1 = PT["LC"] * (2.0 + PT["KX"]) / 40.0        # 一个扫描步长 = S/40
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
    """读最新 profile 的关键量：初始网格耗时/单元、趟数、停止时间。"""
    fs = [f for f in os.listdir(RESDIR) if f.endswith(".profile")]
    if not fs:
        return {}
    f = max((os.path.join(RESDIR, x) for x in fs), key=os.path.getmtime)
    txt = open(f, encoding="utf-8", errors="replace").read().splitlines()
    out = {"file": os.path.basename(f)}
    group = None
    npass = 0
    mesh_el = None
    for ln in txt:
        m = re.search(r"Name='([^']+)'", ln)
        if m:
            group = m.group(1)
            if re.match(r"Pass \d+", group):
                npass += 1
            continue
        m = re.search(r"I\(1, 'Elapsed Time', '([^']+)'\)", ln)
        if m and group == "Initial Meshing":
            mesh_el = m.group(1)
        m = re.search(r"ProfileItem\('Mesh', \d+, 0, (\d+), 0, \d+, 'I\(\d+, (.*)\)'", ln)
        if m:
            out["mesh_elapsed_s"] = int(m.group(1))
            tm = re.search(r"'Tetrahedra', (\d+)", m.group(2))
            if tm:
                out["mesh_tets"] = int(tm.group(1))
        m = re.search(r"ProfileFootnote\('I\(\d+, 1, 'Stop Time', '([^']+)'", ln)
        if m:
            out["stop"] = m.group(1)
    out["initial_mesh_elapsed"] = mesh_el
    out["n_passes"] = npass
    return out


def solve(tag, dx, passes=8, pct=5.0):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, passes, pct
    B.set_rx_dx(m, dx)
    csvp = os.path.join(WORK, "solve_poc7_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, dx + 0.05)          # 强制失效
    B.set_rx_dx(m, dx)
    log(">>> [%s] dx=%.4f  %d 趟 / %.1f%% ..." % (tag, dx, passes, pct))
    t0 = time.time()
    st, r = B.run_stage("求解[%s]" % tag,
                        lambda: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                    PT["W"], PT["G"], dx, PT["mu"], PT["thk"]),
                        3600)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    row = rows[-1] if len(rows) > 1 else ""
    prof = profile_now()
    log("    [%s] %s  %.2f 分钟  初始网格=%s (Mesh %ss, %s 单元)  趟数=%s"
        % (tag, st, dt, prof.get("initial_mesh_elapsed"), prof.get("mesh_elapsed_s"),
           prof.get("mesh_tets"), prof.get("n_passes")))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, dx=dx, stage=st, ok=bool(r), minutes=round(dt, 2),
                row=row, stats=stats_of(row), profile=prof)


def main():
    global d, m
    log("=" * 78)
    log("⑦ PoC：跨位置网格复用（dx=0 的网格 -> dx=+%.4fmm）" % DX1)
    kill_aedt_ps()
    clear_lock(PROJ)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "poc7_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s / %s" % (PROJ, m.design_name))
    log("已有解: %s" % m.existing_analysis_sweeps)
    B.set_rx_dx(m, 0.0)

    s = m.setups[0]
    RES["meshlink_before"] = dict(s.props.get("MeshLink"))
    log("MeshLink 初始: %s" % RES["meshlink_before"])

    # ---- A) 套用上一位置网格 ----
    log("")
    log("---- A. 加 MeshLink（源 = 本设计 dx=0 的 LastAdaptive）----")
    ok = None
    try:
        ok = s.add_mesh_link(design=B.DESIGN, solution="Setup1 : LastAdaptive",
                             project="This Project*", force_source_to_solve=False,
                             preserve_partner_solution=False, apply_mesh_operations=True)
        log("  add_mesh_link 返回 %s" % ok)
        RES["add_mesh_link"] = bool(ok)
        RES["meshlink_after"] = dict(s.props.get("MeshLink") or {})
        log("  MeshLink 现在: %s" % RES["meshlink_after"])
    except Exception as e:
        RES["add_mesh_link_err"] = repr(e)
        log("  !! add_mesh_link 失败: %s" % repr(e))
    dump()

    if ok:
        RES["A_reuse"] = solve("A_reuse", DX1)
        RES["A_cmp_prev"] = None
    else:
        log("  跳过 A（接口不可用）")

    # ---- B) 去掉 MeshLink，常规求解 ----
    log("")
    log("---- B. 去掉 MeshLink，同位置常规求解 ----")
    try:
        p = dict(s.props.get("MeshLink") or {})
        p["ImportMesh"] = False
        s.props["MeshLink"] = p
        s.update()
        RES["meshlink_removed"] = dict(s.props.get("MeshLink") or {})
        log("  MeshLink 现在: %s" % RES["meshlink_removed"])
    except Exception as e:
        RES["remove_meshlink_err"] = repr(e)
        log("  !! 去 MeshLink 失败: %s" % repr(e))
    dump()
    RES["B_noreuse"] = solve("B_noreuse", DX1)
    dump()

    a, b = RES.get("A_reuse"), RES.get("B_noreuse")
    if a and b and a.get("stats") and b.get("stats"):
        dev = {k: round(100.0 * (a["stats"][k] - b["stats"][k]) / abs(b["stats"][k]), 4)
               for k in ("L11", "L22", "L33", "M12", "M13", "M23")}
        RES["seven"] = dict(minutes_reuse=a["minutes"], minutes_noreuse=b["minutes"],
                            pct=round(100.0 * (b["minutes"] - a["minutes"]) / b["minutes"], 2),
                            l_dev_pct=dev,
                            worst_self=max(abs(dev["L11"]), abs(dev["L22"]), abs(dev["L33"])))
        log("")
        log("=== ⑦ 结果 ===")
        log("  耗时: 复用 %.2f 分钟 vs 不复用 %.2f 分钟 -> %+.2f%%"
            % (a["minutes"], b["minutes"], RES["seven"]["pct"]))
        log("  电感偏差(复用 vs 不复用): %s" % dev)
        log("  初始网格阶段: 复用=%s  不复用=%s"
            % (a["profile"].get("initial_mesh_elapsed"),
               b["profile"].get("initial_mesh_elapsed")))
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
