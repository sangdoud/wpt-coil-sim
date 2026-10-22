# -*- coding: utf-8 -*-
"""极限叠加队列：在「柔性网格 + ⑥」之上继续叠开关，逐个量耗时与偏差。

  SF0  flex + ⑥                      （本会话基线，约 6 分钟）
  SF1  flex + ⑥ + RelativeResidual=1e-5
  SF2  flex + ⑥ + PercentRefinement=10
  SF3  flex + ⑥ + 铜带定向网格（Length 1.0mm，指望初始网格更接近收敛、少走趟）
  SF4  flex + ⑥ + rres1e-5 + pref10   （若 SF1/SF2 都可用）

判据：耗时降幅（对标 A0 = 14.23 分钟）、电感偏差（对标 A0 的 L11=20.418 等）、有效性。
工程：Projecttonight_ref.aedt（干净参考工程，几何已在 dx=0）
"""
import json
import os
import re
import subprocess
import sys
import time
import traceback

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                               # noqa: E402
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import batch_sweep_lc as B                       # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

aedt_shim.patch_pyaedt_proc()

PROJ = os.path.join(WORK, "Projecttonight_ref.aedt")
RESDIR = os.path.join(WORK, "Projecttonight_ref.aedtresults", "WPT_G.results")
LOGF = os.path.join(WORK, "queueMax.log")
OUT = os.path.join(WORK, "queueMax.json")
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
A0 = dict(minutes=14.23, L11=20.418, L22=20.443, L33=24.844,
          M12=-2.250, M13=3.940, M23=4.028)
FLEX_SIX = dict(minutes=6.07, L11=20.501, L22=20.521, L33=24.893,
                M12=-2.247, M13=3.939, M23=4.028)     # S1 实测（另一会话）
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


B.kill_aedt = kill_aedt_ps


def stats_of(row):
    if not row:
        return None
    v = [float(x) for x in row.split(",")]
    return dict(L11=v[8], L22=v[9], L33=v[10], M12=v[11], M13=v[12], M23=v[13],
                k13=v[14], k23=v[15])


def validity(st):
    if not st:
        return False, "无结果行"
    if any(st[k] <= 0 for k in ("L11", "L22", "L33")):
        return False, "自感<=0"
    if st["M13"] == 0 or st["M23"] == 0:
        return False, "互感为 0"
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
    out, group, npass = {}, None, 0
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
    out["n_passes"] = npass
    out["initial_mesh_elapsed"] = (out.get("elapsed") or {}).get("Initial Meshing")
    out["adaptive_elapsed"] = (out.get("elapsed") or {}).get("Adaptive Meshing")
    return out


def clear_ops():
    for mo in list(m.mesh.meshoperations):
        try:
            mo.delete()
            log("  清网格操作 %s" % mo.name)
        except Exception as e:
            log("  清 %s 失败 %r" % (mo.name, e))


def flex_on():
    m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=True)


def six_on():
    try:
        op = m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                       maximum_length="%.4fmm" % (PT["LC"] / 5.0),
                                       maximum_elements=None, name="region_coarse")
        log("  ⑥: %s" % getattr(op, "name", op))
    except Exception as e:
        log("  !! ⑥ 失败 %r" % e)


def coil_len_mesh():
    try:
        op = m.mesh.assign_length_mesh(assignment=["Tx1", "Tx2", "Rx"], inside_selection=True,
                                       maximum_length="1.0mm", maximum_elements=None,
                                       name="coil_len")
        log("  铜带定向网格: %s" % getattr(op, "name", op))
    except Exception as e:
        log("  !! 铜带网格失败 %r" % e)


def set_rres(val):
    s = m.setups[0]
    s.props["RelativeResidual"] = val
    s.update()
    log("  RelativeResidual -> %s" % val)


def solve(tag):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, 8, 5.0
    csvp = os.path.join(WORK, "solve_qM_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, 0.05)
    B.set_rx_dx(m, 0.0)
    log(">>> [%s] 8 核 / 8 趟 / 5%% ..." % tag)
    t0 = time.time()
    st, r = B.run_stage("求解[%s]" % tag,
                        lambda: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                    PT["W"], PT["G"], 0.0, PT["mu"], PT["thk"]),
                        3600)
    dt = (time.time() - t0) / 60.0
    rows = [x.strip() for x in open(csvp)] if os.path.exists(csvp) else []
    row = rows[-1] if len(rows) > 1 else ""
    stt = stats_of(row)
    ok, why = validity(stt)
    prof = profile_now()
    log("    [%s] %s %.2f 分钟  初始网格=%s 自适应=%s 趟数=%s 有效=%s %s"
        % (tag, st, dt, prof.get("initial_mesh_elapsed"), prof.get("adaptive_elapsed"),
           prof.get("n_passes"), ok, why))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, stage=st, ok=bool(r), minutes=round(dt, 2), row=row,
                stats=stt, valid=ok, invalid_reason=why, profile=prof)


def main():
    global d, m
    log("#" * 78)
    log("极限叠加队列（工程 %s）" % os.path.basename(PROJ))
    kill_aedt_ps()
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "queueMax_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s  面数 %s" % (os.path.basename(PROJ),
                              {c: len(m.modeler[c].faces) for c in ("Tx1", "Tx2", "Rx")}))
    B.set_rx_dx(m, 0.0)
    clear_ops()

    # SF0: flex + ⑥
    log("")
    log("---- SF0: 柔性 + ⑥（本会话基线）----")
    flex_on(); six_on()
    RES["SF0_flex_six"] = solve("SF0_flex_six"); dump()

    # SF1: + rres 1e-5
    log("")
    log("---- SF1: 柔性 + ⑥ + RelativeResidual=1e-5 ----")
    set_rres("1e-05")
    RES["SF1_rres"] = solve("SF1_rres"); dump()
    set_rres("1e-06")

    # SF2: + pref10
    log("")
    log("---- SF2: 柔性 + ⑥ + PercentRefinement=10 ----")
    B.PCT_REFINEMENT = 10
    RES["SF2_pref10"] = solve("SF2_pref10"); dump()
    B.PCT_REFINEMENT = 5

    # SF3: + 铜带定向网格
    log("")
    log("---- SF3: 柔性 + ⑥ + 铜带 Length=1.0mm ----")
    coil_len_mesh()
    RES["SF3_coilmesh"] = solve("SF3_coilmesh"); dump()
    clear_ops(); flex_on(); six_on()

    # SF4: + rres + pref10
    log("")
    log("---- SF4: 柔性 + ⑥ + rres1e-5 + pref10 ----")
    set_rres("1e-05")
    B.PCT_REFINEMENT = 10
    RES["SF4_combo"] = solve("SF4_combo"); dump()
    set_rres("1e-06")
    B.PCT_REFINEMENT = 5

    # 汇总
    log("")
    log("=== 极限叠加汇总（对标 A0=%.2f 分钟 / 柔性+⑥=%.2f 分钟）==="
        % (A0["minutes"], FLEX_SIX["minutes"]))
    best = None
    for tag in ("SF0_flex_six", "SF1_rres", "SF2_pref10", "SF3_coilmesh", "SF4_combo"):
        r = RES.get(tag)
        if not r or not r["stats"]:
            log("  %-14s 无有效结果" % tag)
            continue
        d0 = pct(r["stats"], A0)
        r["vs_A0"] = dict(time_pct=round(100.0 * (r["minutes"] - A0["minutes"]) / A0["minutes"], 2),
                          l_pct=d0, worst=max(abs(v) for v in d0.values()))
        r["vs_flex_six"] = dict(
            time_pct=round(100.0 * (r["minutes"] - FLEX_SIX["minutes"]) / FLEX_SIX["minutes"], 2))
        ok = r["valid"] and r["vs_A0"]["worst"] <= 0.5
        log("  %-14s %5.2f 分钟 (%+6.2f%% vs A0, %+6.2f%% vs 柔性+⑥)  最坏偏差 %.3f%%  %s"
            % (tag, r["minutes"], r["vs_A0"]["time_pct"], r["vs_flex_six"]["time_pct"],
               r["vs_A0"]["worst"], "✅ 可用" if ok else "⚠️ 超门槛/无效"))
        if ok and (best is None or r["minutes"] < best[1]):
            best = (tag, r["minutes"], r["vs_A0"]["worst"])
    if best:
        RES["best"] = dict(tag=best[0], minutes=best[1], worst_pct=best[2])
        log("  => 最优组合: %s  %.2f 分钟  最坏偏差 %.3f%%" % best)
    dump()
    log("全部完成")
    try:
        kill_aedt_ps(wait_s=40)
        if os.path.exists(PROJ + ".lock"):
            os.remove(PROJ + ".lock")
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
