# -*- coding: utf-8 -*-
"""⑦ 路线 B：另建 donor 设计做网格来源（路线 A「自链接」已被求解器拒绝）。

路线 A 结论：把 MeshLink 指向**本设计自己**的 LastAdaptive，属性层写入成功，
但 AEDT 求解层 11 秒即报 `Error in solving all setups (AnalyzeAll)` —— 自引用被拒。

路线 B（MeshLink 的设计用法：源 ≠ 目标）：
  1) 复制出 donor 设计 WPT_mesh（几何 = dx=0，并带上已收敛解；没带上就地解一次）
  2) 回到 WPT_G，把 Rx 挪到 dx=+7.1095（一个扫描步长）
  3) 加 MeshLink -> WPT_mesh : Setup1 : LastAdaptive，求解（A 组）
  4) 清掉 MeshLink，同位置常规求解（B 组，对照）
  判据：耗时降幅（A 比 B 快多少）、电感偏差、.profile 里"初始网格"阶段是否被跳过/变短。
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

PROJ = os.path.join(WORK, "Projecttonight_4ch.aedt")
RESDIR = os.path.join(WORK, "Projecttonight_4ch.aedtresults", "WPT_G.results")
LOGF = os.path.join(WORK, "poc7b_donor.log")
OUT = os.path.join(WORK, "poc7b_donor.json")
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
DX1 = PT["LC"] * (2.0 + PT["KX"]) / 40.0
DONOR = "WPT_mesh"
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
        m = re.search(r"ProfileItem\('Mesh', \d+, 0, (\d+), 0, \d+, 'I\(\d+, (.*)\)'", ln)
        if m:
            out["mesh_elapsed_s"] = int(m.group(1))
            tm = re.search(r"'Tetrahedra', (\d+)", m.group(2))
            if tm:
                out["mesh_tets"] = int(tm.group(1))
    out["n_passes"] = npass
    out["initial_mesh_elapsed"] = (out.get("elapsed") or {}).get("Initial Meshing")
    return out


def meshlink(design=None):
    """None -> 关；否则指向 design 的 LastAdaptive。"""
    s = m.setups[0]
    try:
        if design is None:
            p = dict(s.props.get("MeshLink") or {})
            p["ImportMesh"] = False
            s.props["MeshLink"] = p
            s.update()
        else:
            ok = s.add_mesh_link(design=design, solution="Setup1 : LastAdaptive",
                                 project="This Project*", force_source_to_solve=False,
                                 preserve_partner_solution=False, apply_mesh_operations=True)
            log("  add_mesh_link(%s) -> %s" % (design, ok))
        cur = dict(s.props.get("MeshLink") or {})
        log("  MeshLink = %s" % cur)
        return cur
    except Exception as e:
        log("  !! MeshLink 操作失败: %r" % e)
        return None


def solve(tag, dx, passes=8, pct=5.0):
    B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, passes, pct
    csvp = os.path.join(WORK, "solve_7b_%s.csv" % tag)
    if os.path.exists(csvp):
        os.remove(csvp)
    B.OUT_CSV = csvp
    B.set_rx_dx(m, dx + 0.05)
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
    stt = stats_of(row)
    # 有效性校验：M1/M2 那两组曾出现「Tx1 相关项全 0」（全局网格过粗把 0.3mm 端子面网格化掉了）
    valid, why = True, ""
    if not stt:
        valid, why = False, "无结果行"
    else:
        zeros = [k for k in ("L11", "L22", "L33") if not stt[k] or stt[k] <= 0]
        if zeros:
            valid, why = False, "自感为 0/负: %s" % zeros
        elif abs(stt["k13"]) > 1 or abs(stt["k23"]) > 1:
            valid, why = False, "|k|>1"
        elif stt["M13"] == 0 or stt["M23"] == 0:
            valid, why = False, "互感为 0（绕组可能未挂上）"
    log("    [%s] %s  %.2f 分钟  初始网格=%s (Mesh %ss %s 单元) 趟数=%s  有效性=%s %s"
        % (tag, st, dt, prof.get("initial_mesh_elapsed"), prof.get("mesh_elapsed_s"),
           prof.get("mesh_tets"), prof.get("n_passes"),
           "OK" if valid else "!! INVALID", why))
    log("    [%s] %s" % (tag, row))
    return dict(tag=tag, dx=dx, stage=st, ok=bool(r), minutes=round(dt, 2),
                row=row, stats=stt, valid=valid, invalid_reason=why, profile=prof)


def main():
    global d, m
    log("=" * 78)
    log("⑦ 路线 B：donor 设计网格链接（自链接已被拒）")
    kill_aedt_ps()
    clear_lock(PROJ)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "poc7b_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    log("已打开 %s / %s" % (m.design_name, PROJ))
    RES["designs_before"] = list(d.design_list())
    log("  已有设计: %s" % RES["designs_before"])
    meshlink(None)                      # 确保没有残留的 MeshLink
    B.set_rx_dx(m, 0.0)

    # ---- 把 P3 留下的网格改动恢复原状（否则 ⑦ 的对照全被污染）----
    log("  恢复网格设置：清网格操作 + 全局滑块回 5")
    try:
        for mo in list(m.mesh.meshoperations):
            log("    删除网格操作 %s" % mo.name)
            mo.delete()
    except Exception as e:
        log("    清网格操作失败: %r" % e)
    try:
        m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto")
        log("    滑块已设回 5（读回值可能是 pyaedt 缓存，以初始网格耗时为准）")
    except Exception as e:
        log("    设置滑块失败: %r" % e)

    # ---- donor 设计 ----
    if DONOR in d.design_list():
        log("  已存在旧 donor %s -> 先删掉重做" % DONOR)
        try:
            m.delete_design(DONOR)
        except Exception as e:
            log("  !! 删旧 donor 失败: %r" % e)
        RES["designs_after_del"] = list(d.design_list())
    if DONOR not in d.design_list():
        log("  复制设计 %s -> %s" % (B.DESIGN, DONOR))
        try:
            ok = m.duplicate_design(DONOR)
            log("  duplicate_design -> %s" % ok)
        except Exception as e:
            log("  !! 复制失败: %r" % e)
            RES["dup_err"] = repr(e)
    RES["designs_after"] = list(d.design_list())
    log("  设计列表: %s" % RES["designs_after"])

    # donor 是否自带解（复制可能不带解数据）
    donor_solved = False
    try:
        m.set_active_design(DONOR)
        sw = m.existing_analysis_sweeps
        try:
            donor_solved = bool(m.setups[0].is_solved)
        except Exception:
            donor_solved = bool(sw)
        log("  donor 解: sweeps=%s is_solved=%s" % (sw, donor_solved))
        RES["donor_solved_after_dup"] = donor_solved
    except Exception as e:
        log("  !! 切到 donor 失败: %r" % e)
        RES["donor_switch_err"] = repr(e)

    if not donor_solved:
        log("  donor 无解 -> 先解一次（8 核/8 趟/5%）")
        B.CORES, B.MAX_PASSES, B.PCT_ERROR = 8, 8, 5.0
        csvp = os.path.join(WORK, "solve_7b_donor.csv")
        if os.path.exists(csvp):
            os.remove(csvp)
        B.OUT_CSV = csvp
        B.set_rx_dx(m, 0.05)
        B.set_rx_dx(m, 0.0)
        t0 = time.time()
        st, r = B.run_stage("donor求解",
                            lambda: B.solve_and_extract(d, m, PT["LC"], PT["KR"], PT["KX"],
                                                        PT["W"], PT["G"], 0.0, PT["mu"], PT["thk"]),
                            3600)
        RES["donor_solve"] = dict(stage=st, ok=bool(r),
                                  minutes=round((time.time() - t0) / 60.0, 2))
        log("  donor 求解 %s %.2f 分钟" % (st, RES["donor_solve"]["minutes"]))
        dump()

    # ---- 回到目标设计 ----
    m.set_active_design(B.DESIGN)
    log("  已切回 %s" % m.design_name)

    # ---- A 组：套 donor 网格 ----
    log("")
    log("---- A. MeshLink -> %s : Setup1 : LastAdaptive ----" % DONOR)
    RES["meshlink_A"] = meshlink(DONOR)
    dump()
    RES["A_reuse"] = solve("A_donor", DX1)
    dump()

    # ---- B 组：清链接，同位置常规 ----
    log("")
    log("---- B. 清 MeshLink，同位置常规求解 ----")
    RES["meshlink_B"] = meshlink(None)
    dump()
    RES["B_noreuse"] = solve("B_plain", DX1)
    dump()

    a, b = RES["A_reuse"], RES["B_noreuse"]
    if a.get("stats") and b.get("stats"):
        dev = {k: round(100.0 * (a["stats"][k] - b["stats"][k]) / abs(b["stats"][k]), 4)
               for k in ("L11", "L22", "L33", "M12", "M13", "M23")}
        RES["seven_b"] = dict(minutes_reuse=a["minutes"], minutes_plain=b["minutes"],
                              pct=round(100.0 * (b["minutes"] - a["minutes"]) / b["minutes"], 2),
                              l_dev_pct=dev,
                              worst_self=max(abs(dev["L11"]), abs(dev["L22"]), abs(dev["L33"])))
        log("")
        log("=== ⑦ 路线 B 结果 ===")
        log("  耗时: 套 donor 网格 %.2f 分钟 vs 常规 %.2f 分钟 -> %+.2f%%"
            % (a["minutes"], b["minutes"], RES["seven_b"]["pct"]))
        log("  电感偏差: %s" % dev)
        log("  初始网格阶段: 套网格=%s  常规=%s"
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
