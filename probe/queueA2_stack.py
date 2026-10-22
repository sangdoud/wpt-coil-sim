# -*- coding: utf-8 -*-
"""A2 叠加试验：柔性网格（A1，−39.6%）与 ⑥ 区域粗化（−9.8%）能否叠加。

 S0  flex ON，无 ⑥        -> 同会话对照
 S1  flex ON + ⑥ Region 最大单元尺寸 = Lc/5

两者都改网格、但作用点不同（柔性网格改的是网格器本身；⑥ 只给空气域加单元上限），
理论上可以叠加。判据：耗时降幅 + 电感偏差（对 A0 基线 14.23 分钟 / L11=20.418）。
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
import coil_gen as CG                            # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

aedt_shim.patch_pyaedt_proc()

PROJ = os.path.join(WORK, "Projecttonight_ref.aedt")   # 干净参考工程
RESDIR = os.path.join(WORK, "Projecttonight_ref.aedtresults", "WPT_G.results")
LOGF = os.path.join(WORK, "queueA2.log")
OUT = os.path.join(WORK, "queueA2.json")
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
A0 = dict(minutes=14.23, L11=20.418, L22=20.443, L33=24.844,
          M12=-2.250, M13=3.940, M23=4.028)          # A 组同会话基线
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
    return out


def solve(tag):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, 8, 5.0
    csvp = os.path.join(WORK, "solve_qA2_%s.csv" % tag)
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
    log("    [%s] %s %.2f 分钟  初始网格=%s 趟数=%s 有效性=%s %s"
        % (tag, st, dt, prof.get("initial_mesh_elapsed"), prof.get("n_passes"),
           "OK" if ok else "!!" + why, ""))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, stage=st, ok=bool(r), minutes=round(dt, 2), row=row,
                stats=stt, valid=ok, invalid_reason=why, profile=prof)


def main():
    global d, m
    log("#" * 78)
    log("A2：柔性网格 + ⑥ 叠加试验（工程 %s）" % os.path.basename(PROJ))
    kill_aedt_ps()
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "queueA2_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s" % os.path.basename(PROJ))
    # 几何已在干净工程里建好（dx=0），只需确认
    B.set_rx_dx(m, 0.0)
    log("  当前线圈面数: %s" % {c: len(m.modeler[c].faces) for c in ("Tx1", "Tx2", "Rx")})
    for mo in list(m.mesh.meshoperations):
        log("  清网格操作 %s" % mo.name)
        mo.delete()

    # S0：柔性网格 ON
    log("")
    log("---- S0: 柔性网格 ON（对照）----")
    m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=True)
    RES["S0_flex"] = solve("S0_flex")
    dump()

    # S1：柔性网格 + ⑥
    log("")
    log("---- S1: 柔性网格 ON + ⑥ Region 最大单元尺寸 = Lc/5 = %.4f mm ----" % (PT["LC"] / 5.0))
    try:
        op = m.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                       maximum_length="%.4fmm" % (PT["LC"] / 5.0),
                                       maximum_elements=None, name="region_coarse")
        RES["six_op"] = str(getattr(op, "name", op))
    except Exception as e:
        RES["six_op_err"] = repr(e)
        log("  !! %r" % e)
    RES["S1_flex_six"] = solve("S1_flex_six")
    dump()

    s0, s1 = RES["S0_flex"], RES["S1_flex_six"]
    log("")
    log("=== 叠加结果（A0 基线 %.2f 分钟 / L11=%.3f）===" % (A0["minutes"], A0["L11"]))
    for k, r in (("柔性", s0), ("柔性+⑥", s1)):
        if not r["stats"]:
            log("  %-8s 无有效结果" % k)
            continue
        d0 = pct(r["stats"], A0)
        r["vs_A0"] = dict(time_pct=round(100.0 * (r["minutes"] - A0["minutes"]) / A0["minutes"], 2),
                          l_pct=d0)
        log("  %-8s %6.2f 分钟 (%+6.2f%%)  偏差 %s  最坏 %.3f%%"
            % (k, r["minutes"], r["vs_A0"]["time_pct"], d0,
               max(abs(v) for v in d0.values())))
    if s0["stats"] and s1["stats"]:
        d1 = pct(s1["stats"], s0["stats"])
        RES["stack_vs_flex"] = d1
        log("  ⑥ 叠加在柔性网格之上：再 %+.2f%% 耗时，电感再偏 %s"
            % (100.0 * (s1["minutes"] - s0["minutes"]) / s0["minutes"], d1))
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
