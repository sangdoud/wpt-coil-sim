# -*- coding: utf-8 -*-
"""
preflight_2025.py — AEDT 高版本(2025.x)可行性自检

用途：在装有 2025 版 Maxwell 的机器上，一次性验证本 WPT 参数化方案能否运行。
      把本文件 + batch_sweep_unit30.py + Projecttonightxu.aedt 放同一目录，然后：
          python preflight_2025.py
      末尾出现全 [PASS] 即代表可用；出现 [HANG] 就要看是哪一步（多半是非图形模式）。

设计要点（针对已知的坑）：
  1. 版本探测会校验**目录真实存在**——本机就有一条指向不存在路径的幽灵 2025.1 条目。
  2. 每个可能挂死的阶段都套**看门狗**：非图形模式下几何重建会静默挂死(CPU 0%、不报错)，
     超时即强杀 AEDT 并判 [HANG]，不会让你干等。
  3. GUI 与 non_graphical 两种模式都测几何重建——服务器/无桌面环境的关键风险点。
  4. 求解结果与本机 2024.1 的已知参考值自动对比，输出漂移百分比。
  5. 全程 **不保存工程**（SAVE_PROJECT=False），避免把主文件升级成新版格式。
"""
import os, sys, time, math, glob, re, csv, threading, traceback

# ================== 配置（换机器只改这一段） ==================
TARGET_VERSION = "2025.1"        # 目标 AEDT 版本；找不到会自动回退到检测到的最高可用版
PROJECT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Projecttonightxu.aedt")
DESIGN  = "WPT_G"
SAVE_PROJECT = False             # 绝不改成 True（新版保存会单向升级 .aedt）

STAGE_TIMEOUT = 360              # 几何等操作的单阶段看门狗(秒)
SOLVE_TIMEOUT = 1500             # 单点求解看门狗(秒)
CORES = 8
MAX_PASSES, PCT_ERROR, PCT_REFINEMENT = 8, 5, 5
TOL_PCT = 2.0                    # 结果漂移容差(%)，超过则提示核对

# 本机 2024.1 实测参考值（用于对比漂移），取自 sweep_all_unit30.csv（1705 点主数据集）
# 格式 (W,G,dx,tg): dict(L11=, M13=, k13=, k23=)
# 注意 CSV 列序： W,G,dx,tg,mu,L11,L22,L33,M12,M13,M23,k13,k23 —— M13 是第 10 列(index 9)
REF = {
    (15, 15,   0,  0): dict(L11=3999.701, M13=245.097, k13=0.06210, k23=0.06995),
    (20, 10,   0,  0): dict(L11=4327.477, M13=248.366, k13=0.05619, k23=0.06246),
    (18, 12,   0,  0): dict(L11=4213.112, M13=247.943, k13=0.05846, k23=0.06504),
    (20, 10,   0, 60): dict(L11=4317.720, M13=-58.759, k13=-0.01348, k23=-0.01409),
}
# 自检只跑前 2 个点即可判定可行性（每点 ~6-9 分钟）
TEST_POINTS = [(15, 15, 0, 0), (20, 10, 0, 0)]
# =============================================================

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = os.path.join(HERE, "preflight_report.txt")
RESULTS = []          # [(stage, status, detail)]
_t0 = time.time()

def log(msg):
    line = "[%7.1fs] %s" % (time.time() - _t0, msg)
    print(line, flush=True)
    try:
        with open(REPORT, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass

def rec(stage, status, detail=""):
    RESULTS.append((stage, status, detail))
    tag = {"OK": "[PASS]", "HANG": "[HANG]", "ERR": "[FAIL]", "SKIP": "[SKIP]"}.get(status, "[????]")
    log("%s %s %s" % (tag, stage, ("— " + str(detail)[:160]) if detail else ""))

def kill_aedt():
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            try:
                if (p.info["name"] or "").lower().startswith("ansysedt"):
                    p.kill()
            except Exception:
                pass
    except Exception:
        os.system('taskkill /F /IM ansysedt.exe >nul 2>&1')
    time.sleep(3)
    for f in glob.glob(os.path.join(os.path.dirname(PROJECT), "*.lock")):
        try:
            os.remove(f)
        except Exception:
            pass

def run_stage(name, fn, timeout):
    """带看门狗执行 fn；挂死则返回 HANG 并强杀 AEDT"""
    box = {}
    def target():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e
            box["tb"] = traceback.format_exc()
    t = threading.Thread(target=target, daemon=True)
    t.start(); t.join(timeout)
    if t.is_alive():
        log("  !! %s 超过 %ds 未返回，判定挂死，强杀 AEDT" % (name, timeout))
        kill_aedt()
        return "HANG", None, None
    if "e" in box:
        return "ERR", box["e"], box["tb"]
    return "OK", box.get("v"), None

# ---------------------------------------------------------------- 阶段 0：环境探测
def stage_env():
    log("=" * 70)
    log("阶段 0：环境探测")
    ver_ok = True
    try:
        import importlib.metadata as md
        try:
            pv = md.version("pyaedt")
        except Exception:
            try:
                pv = md.version("ansys-aedt-core")
            except Exception:
                pv = None
        if pv is None:
            rec("环境: pyaedt 已安装", "ERR", "未检测到 pyaedt/ansys-aedt-core")
            log("    → 请先安装：pip install pyaedt==1.3.0   (或 pip install -U ansys-aedt-core)")
            return None, False
        log("  pyaedt 版本: %s" % pv)
        rec("环境: pyaedt 已安装", "OK", "v" + pv)
    except Exception as e:
        rec("环境: pyaedt 已安装", "ERR", repr(e)[:120])
        return None, False

    try:
        from ansys.aedt.core.internal.aedt_versions import aedt_versions
        installed = dict(aedt_versions.installed_versions)
    except Exception as e:
        rec("环境: 探测 AEDT 版本", "ERR", repr(e)[:120])
        return None, False

    log("  检测到的 AEDT 版本条目：")
    real = {}
    for v, p in sorted(installed.items()):
        ok = os.path.isdir(p)
        log("    %-8s %s   %s" % (v, p, "" if ok else "  <== 路径不存在，忽略"))
        if ok:
            real[v] = p
    if not real:
        rec("环境: 存在可用 AEDT 安装", "ERR", "所有版本条目路径都不存在")
        return None, False

    def key(v):
        try:
            a, b = v.split("."); return (int(a), int(b))
        except Exception:
            return (0, 0)

    chosen = None
    if TARGET_VERSION in real:
        chosen = TARGET_VERSION
        log("  选用目标版本 %s（目录存在）" % chosen)
    else:
        cands = [v for v in real if key(v) >= (2024, 1)]
        if cands:
            chosen = max(cands, key=key)
            log("  目标版本 %s 不可用，回退到最高可用版 %s" % (TARGET_VERSION, chosen))
        else:
            chosen = max(real, key=key)
            log("  !! 无 >=2024.1 的版本，回退到 %s（低于本机模型版本，可能打不开）" % chosen)
    rec("环境: 选定 AEDT 版本", "OK", "%s @ %s" % (chosen, real[chosen]))

    # 版本配对提示
    try:
        pv_tuple = tuple(int(x) for x in pv.split(".")[:2])
    except Exception:
        pv_tuple = (0, 0)
    cv = key(chosen)
    if pv_tuple < (1, 0) and cv >= (2024, 1):
        rec("环境: 版本配对", "ERR", "pyaedt %s 可能不支持 AEDT %s，建议升级到 1.3.0+" % (pv, chosen))
    else:
        rec("环境: 版本配对", "OK", "pyaedt %s 支持 AEDT %s" % (pv, chosen))

    if not os.path.exists(PROJECT):
        rec("环境: 工程文件存在", "ERR", "找不到 %s（需与本脚本同目录）" % os.path.basename(PROJECT))
        return chosen, False
    rec("环境: 工程文件存在", "OK", os.path.basename(PROJECT))
    return chosen, True

# ---------------------------------------------------------------- 阶段 1：GUI 会话
def stage_gui_session(version):
    log("-" * 70)
    log("阶段 1：启动 GUI 会话并打开工程")
    from ansys.aedt.core import Desktop, Maxwell3d
    state = {}
    def go():
        d = Desktop(version=version, new_desktop=True, non_graphical=False, close_on_exit=False)
        m = Maxwell3d(project=PROJECT, design=DESIGN)
        state["d"], state["m"] = d, m
        return m.solution_type
    st, v, tb = run_stage("GUI 会话+打开工程", go, STAGE_TIMEOUT)
    if st == "OK":
        rec("GUI: 启动会话并打开 WPT_G", "OK", "solution_type=%s" % v)
        if str(v).lower().replace("_", "") != "magnetostatic":
            rec("GUI: 求解类型校验", "ERR", "期望 Magnetostatic，实际 %s" % v)
    elif st == "HANG":
        rec("GUI: 启动会话并打开 WPT_G", "HANG", "GUI 会话也挂死")
    else:
        rec("GUI: 启动会话并打开 WPT_G", "ERR", repr(v)[:150] + ("\n" + (tb or "")[-400:] if tb else ""))
        log("    → 常见原因：license 无 Maxwell 授权 / 版本号写错 / 工程被占用")
    return state.get("d"), state.get("m")

# 几何重建（供 GUI / non_graphical 复用）
def _rebuild(m, W, G, tg):
    import batch_sweep_unit30 as B
    B.set_rx_dx(m, 0.0)
    B.set_tx_gap(m, tg)
    n = B.rebuild_ferrite(m, W, G, tg)
    B.ensure_region(m, tg)
    B.set_rx_dx(m, 0.0)
    return n

def stage_geometry(m, label):
    log("-" * 70)
    log("阶段：几何重建测试（%s）" % label)
    try:
        import batch_sweep_unit30 as B  # noqa
    except Exception as e:
        rec("%s: 导入 batch_sweep_unit30" % label, "ERR", repr(e)[:120])
        return False
    W, G, tg = 15, 15, 0
    st, v, tb = run_stage("%s 几何重建(W=15,G=15,tg=0)" % label, lambda: _rebuild(m, W, G, tg), STAGE_TIMEOUT)
    if st == "OK":
        rec("%s: 几何重建" % label, "OK", "重建 %s 条铁氧体" % v)
        return True
    if st == "HANG":
        rec("%s: 几何重建" % label, "HANG", "delete/rebuild 静默挂死——**此模式不可用于长跑**")
    else:
        rec("%s: 几何重建" % label, "ERR", repr(v)[:150])
    return False

# ---------------------------------------------------------------- 阶段：单点求解
def stage_solve(m, label):
    log("-" * 70)
    log("阶段：单点求解 + 提取，对比 2024.1 参考值（%s）" % label)
    import batch_sweep_unit30 as B
    results_dir = os.path.join(os.path.splitext(PROJECT)[0] + ".aedtresults", DESIGN + ".results")

    def latest_profile():
        try:
            ps = sorted(glob.glob(os.path.join(results_dir, "DV*.profile")), key=os.path.getmtime)
            return ps[-1] if ps else None
        except Exception:
            return None

    for (W, G, dx, tg) in TEST_POINTS:
        ref = REF.get((W, G, dx, tg))
        log("  → W=%d G=%d dx=%d tg=%d" % (W, G, dx, tg))
        try:
            B.set_rx_dx(m, 0.0); B.set_tx_gap(m, tg)
            B.rebuild_ferrite(m, W, G, tg); B.ensure_region(m, tg)
            B.set_rx_dx(m, dx)
        except Exception as e:
            rec("求解 W%d/dx%d/tg%d: 几何" % (W, dx, tg), "ERR", repr(e)[:150])
            continue
        try:
            s = m.setups[0]
            s.props["MaximumPasses"] = MAX_PASSES
            s.props["PercentError"] = PCT_ERROR
            s.props["PercentRefinement"] = PCT_REFINEMENT
            s.update()
        except Exception as e:
            log("    setup 参数设置告警: %r" % (repr(e)[:100],))

        base = latest_profile()
        def solve():
            try:
                m.odesktop.StopSimulations(True); time.sleep(2)
            except Exception:
                pass
            m.analyze(cores=CORES)
            return True
        st, _, _ = run_stage("求解 W%d/dx%d/tg%d" % (W, dx, tg), solve, SOLVE_TIMEOUT)
        if st == "HANG":
            rec("求解 W%d/dx%d/tg%d" % (W, dx, tg), "HANG", "求解超时被强杀")
            return False
        if st == "ERR":
            rec("求解 W%d/dx%d/tg%d" % (W, dx, tg), "ERR", "analyze 抛错")
            continue

        try:
            solved = m.setups[0].is_solved
        except Exception:
            solved = False
        if not solved:
            # 查 profile 是否验证错误
            msg = ""
            p = latest_profile()
            if p and p != base:
                try:
                    txt = open(p, encoding="utf-8", errors="replace").read()
                    if "Engine Detected Error" in txt:
                        msg = "; ".join(re.findall(r"I\(1, 0, \\?'([^']*intersect[^']*)'\\?\)", txt)) or "Engine Detected Error"
                except Exception:
                    pass
            rec("求解 W%d/dx%d/tg%d" % (W, dx, tg), "ERR", "未解出" + ("：" + msg if msg else "（引擎可能启动失败，换会话重试）"))
            continue

        try:
            w = ["Winding_Tx1", "Winding_Tx2", "Winding_Rx"]
            data = m.post.get_solution_data(
                expressions=["Lmatrix.L(%s,%s)" % (a, b) for a in w for b in w],
                setup_sweep_name="Setup1 : LastAdaptive")
            real, _ = data.full_matrix_real_imag
            def L(i, j):
                return real["Lmatrix.L(%s,%s)" % (w[i], w[j])][0][1] / 1000.0
            L11 = L(0, 0); L33 = L(2, 2)
            M13 = L(0, 2); k13 = M13 / math.sqrt(L11 * L33) if L11 > 0 and L33 > 0 else 0
            M23 = L(1, 2); k23 = M23 / math.sqrt(L(1, 1) * L33) if L33 > 0 else 0
        except Exception as e:
            rec("求解 W%d/dx%d/tg%d: 提取" % (W, dx, tg), "ERR", repr(e)[:150])
            continue

        if not ref:
            rec("求解 W%d/dx%d/tg%d" % (W, dx, tg), "OK", "L11=%.1f M13=%.2f k13=%.5f k23=%.5f（无参考值）" % (L11, M13, k13, k23))
            continue
        drifts = {}
        for k, got in (("L11", L11), ("M13", M13), ("k13", k13), ("k23", k23)):
            base_v = ref[k]
            drifts[k] = abs(got - base_v) / abs(base_v) * 100.0 if base_v else 0.0
        worst = max(drifts.values())
        detail = "k13=%.5f(参考%.5f, 差%.2f%%) k23=%.5f(差%.2f%%) L11=%.1f(差%.2f%%) M13=%.2f(差%.2f%%)" % (
            k13, ref["k13"], drifts["k13"], k23, drifts["k23"], L11, drifts["L11"], M13, drifts["M13"])
        if worst <= TOL_PCT:
            rec("求解 W%d/dx%d/tg%d 对比2024.1" % (W, dx, tg), "OK", detail)
        else:
            rec("求解 W%d/dx%d/tg%d 对比2024.1" % (W, dx, tg), "ERR", "漂移 %.2f%% 超容差 %.1f%%：%s" % (worst, TOL_PCT, detail))
    return True

# ---------------------------------------------------------------- 阶段：非图形模式
def stage_nongraphical(version):
    log("-" * 70)
    log("阶段：non_graphical 模式测试（服务器/无桌面场景的关键风险点）")
    kill_aedt()
    from ansys.aedt.core import Desktop, Maxwell3d
    state = {}
    def go():
        d = Desktop(version=version, new_desktop=True, non_graphical=True, close_on_exit=False)
        m = Maxwell3d(project=PROJECT, design=DESIGN)
        state["d"], state["m"] = d, m
        return m.solution_type
    st, v, tb = run_stage("non_graphical 启动会话", go, STAGE_TIMEOUT)
    if st != "OK":
        rec("non_graphical: 启动会话", "HANG" if st == "HANG" else "ERR",
            "此环境无法用无界面模式启动" if st == "HANG" else repr(v)[:150])
        return
    rec("non_graphical: 启动会话", "OK", "solution_type=%s" % v)
    ok = stage_geometry(state["m"], "non_graphical")
    if ok:
        rec("non_graphical: 结论", "OK", "无界面模式几何重建正常，可用于服务器长跑")
    else:
        rec("non_graphical: 结论", "ERR", "无界面模式几何重建异常 → 服务器需保留 GUI 会话(RDP)")

# ---------------------------------------------------------------- 仅环境检查（部署用，不起 AEDT、不跑仿真）
def env_only():
    """只做环境探测：pyaedt 是否装好、AEDT 版本条目是否真实存在、工程文件是否到位。
    全程不启动 AEDT、不求解、不写任何工程文件。用于服务器部署后的验收。"""
    version, ready = stage_env()
    log("=" * 70)
    log("环境检查汇总（--env-only，未启动 AEDT、未跑仿真）")
    n_ok = sum(1 for _, s, _ in RESULTS if s == "OK")
    n_err = sum(1 for _, s, _ in RESULTS if s == "ERR")
    for stage, s, detail in RESULTS:
        tag = {"OK": "PASS", "ERR": "FAIL"}.get(s, s)
        if s != "OK":
            log("  [%s] %s — %s" % (tag, stage, str(detail)[:200]))
    log("-" * 70)
    log("PASS=%d  FAIL=%d" % (n_ok, n_err))
    if n_err == 0 and version:
        log(">>> 环境就绪：AEDT %s 已就位，pyaedt 配对正常，工程文件存在。" % version)
        log(">>> 下一步（需人工确认后）才跑真仿真：python preflight_2025.py")
    else:
        log(">>> 环境未就绪：见上面 FAIL 项。常见：pyaedt 未装 / AEDT 路径是残留 / 工程文件缺失。")
    log("报告已写入：%s" % REPORT)


# ---------------------------------------------------------------- 主流程
def main():
    try:
        open(REPORT, "w", encoding="utf-8").close()
    except Exception:
        pass
    if "--env-only" in sys.argv:
        log("preflight_2025.py 启动 [仅环境检查模式]  |  目标版本=%s  |  工程=%s" % (TARGET_VERSION, PROJECT))
        env_only()
        return
    log("preflight_2025.py 启动  |  目标版本=%s  |  工程=%s" % (TARGET_VERSION, PROJECT))
    version, ready = stage_env()
    if version and ready:
        # ---- GUI 全流程 ----
        d, m = stage_gui_session(version)
        if m is not None:
            if stage_geometry(m, "GUI"):
                stage_solve(m, "GUI")
        try:
            if d is not None:
                d.close_desktop()
        except Exception:
            pass
        kill_aedt()
        # ---- 非图形模式 ----
        stage_nongraphical(version)
    kill_aedt()

    # ---- 汇总 ----
    log("=" * 70)
    log("自检汇总")
    n_ok = sum(1 for _, s, _ in RESULTS if s == "OK")
    n_hang = sum(1 for _, s, _ in RESULTS if s == "HANG")
    n_err = sum(1 for _, s, _ in RESULTS if s == "ERR")
    for stage, s, detail in RESULTS:
        tag = {"OK": "PASS", "HANG": "HANG", "ERR": "FAIL", "SKIP": "SKIP"}.get(s, "????")
        if s != "OK":
            log("  [%s] %s — %s" % (tag, stage, str(detail)[:200]))
    log("-" * 70)
    log("PASS=%d  HANG=%d  FAIL=%d" % (n_ok, n_hang, n_err))
    if n_hang == 0 and n_err == 0:
        log(">>> 全部通过：AEDT %s 可直接用于本方案长跑。记得把脚本 AEDT_VERSION 改成 %s。" % (version, version))
    elif n_hang:
        log(">>> 有 HANG：多半是非图形模式不兼容。服务器上请保留 GUI(RDP) 会话；否则改用批量调度。")
    else:
        log(">>> 有 FAIL：看上面每条原因（license / 版本配对 / 工程文件 / 提取接口）。")
    log("报告已写入：%s" % REPORT)

if __name__ == "__main__":
    main()
