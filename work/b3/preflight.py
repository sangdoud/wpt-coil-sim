# -*- coding: utf-8 -*-
r"""批次启动前自检（通用；第二轮 b2 起使用）。

设计原则 —— 全部来自 batch1 的血泪教训（《批量仿真故障总结与经验_20260926.md》）：
  1) 只用**可观测证据**做判据，不用"代码看起来对"的静态假设
     （教训：两道防线必须分别验证会触发）；
  2) **不做宽泛 except 吞异常** —— 取不到的证据一律显式报 FAIL/WARN 并带上原因
     （教训：宽泛 except 会把"我修错了"伪装成"没数据"）；
  3) 只读：本脚本不修改、不创建、不删除任何文件；
  4) 退出码：0=无 FAIL（可有 WARN）/ 1=存在 FAIL / 2=脚本自身异常。

用法：
  python preflight.py --root "C:\ansys maxwell2024\_work\b2" --batch b2 --plan "C:\ansys maxwell2024\_work\b2\b2_plan.csv"

不传 --plan 时默认取 <root>\<batch>_plan.csv；参数表不存在时该项报 FAIL 但其余照检。
"""
import argparse
import csv
import ctypes
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = r"C:\anaconda\python.exe"
WPT_DIR = r"C:\wpt"
BASE_PROJECT = r"C:\ansys maxwell2024\_work\Projecttonight_ref.aedt"

# ---- 冻结口径（不可随批次变化；改了就是换口径，跨批数据不可比）----
BOX_X = 420.0
BOX_Y = (-134.94, 161.0)
N_PTS = 21                     # 半扫点数（镜像展开成 41 点曲线）
OPT_MIN_GAP = 1.5
STAGE_TIMEOUT = 1500
SOLVE_TIMEOUT = 2400
MAIN_COLS = ["coil_size", "hole_ratio", "tx_fill", "rx_fill",
             "tx_thick", "rx_thick", "spacing_ratio"]

R = []


def rep(level, item, detail=""):
    R.append((level, item, detail))
    print("[%-4s] %s%s" % (level, item, ("\n         " + detail) if detail else ""), flush=True)


def ok(item, detail=""):
    rep("OK", item, detail)


def warn(item, detail=""):
    rep("WARN", item, detail)


def fail(item, detail=""):
    rep("FAIL", item, detail)


def sh(cmd, timeout=120):
    """执行 PowerShell 片段（只用 ASCII 输出，避开编码坑）。"""
    p = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                       capture_output=True, text=True, timeout=timeout)
    return (p.stdout or "").strip()


def read_text(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def mem_info():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = MS()
    st.dwLength = ctypes.sizeof(MS)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
        raise OSError("GlobalMemoryStatusEx 失败")
    g = float(2 ** 30)
    return (st.ullTotalPhys / g, st.ullAvailPhys / g,
            st.ullTotalPageFile / g, st.ullAvailPageFile / g)


def section(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78, flush=True)


def batch_running(root, batch):
    """批次是否正在运行：本批次的 contract_worker 进程存在，或 raw 在 30 min 内还在长。

    用于把"启动前语义"的检查（AEDT 必须清零、目录必须是空的）与"运行期语义"区分开，
    否则批次一跑起来，巡检就会挂满无意义的 FAIL，把真问题淹没。
    """
    try:
        n = sh("(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
               "Where-Object { $_.CommandLine -like '*%s*' } | Measure-Object).Count"
               % os.path.join(os.path.abspath(root), "contract_worker.py"))
        if int(str(n).strip() or 0) > 0:
            return True
    except (TypeError, ValueError, OSError):
        pass
    try:
        raws = glob.glob(os.path.join(root, "%s_raw_run*.csv" % batch))
        if raws and (time.time() - max(os.path.getmtime(p) for p in raws)) < 1800:
            return True
    except OSError:
        pass
    return False


# --------------------------------------------------------------------- A 环境
def check_env(args):
    section("A 环境与资源")

    n_fam = sh("@(Get-Process -Name ansysedt,3dnms,G3dMesher,ansyscl "
               "-ErrorAction SilentlyContinue).Count")
    try:
        n_fam = int(n_fam or 0)
    except ValueError:
        n_fam = -1
    # ⚠️ 2026-10-12：A1 原本是**启动前**语义（AEDT 必须清零）。批次跑起来之后它必然 FAIL，
    # 于是运行期每次巡检都挂一个醒目的 FAIL，把真正的问题淹没掉。故先判断批次是否在运行：
    # 在运行 -> AEDT 家族进程多是**正常**；未运行 -> 才按"启动前必须清零"判 FAIL。
    _running = batch_running(args.root, args.batch)
    if _running:
        ok("A1 批次**运行中**：AEDT 家族进程 %s 个属正常（启动前才要求清零）" % n_fam)
    elif n_fam == 0:
        ok("A1 无 AEDT 家族残留进程")
    elif n_fam < 0:
        fail("A1 无法确认 AEDT 进程数（PowerShell 查询失败）")
    else:
        fail("A1 存在 %d 个 AEDT 家族进程" % n_fam,
             "启动前必须清零。强杀后 AEDT 有 3~5 分钟静默窗口，窗口内新建会话"
             "必然失败（实测整批重启 8/8 全灭）。等 AEDT 全家族退净 ≥4 min 再启动。")

    try:
        du = shutil.disk_usage("C:\\")
        dfree = du.free / 2 ** 30
    except OSError as e:
        dfree = None
        fail("A2 磁盘余量取不到", repr(e))
    if dfree is not None:
        if dfree < 40:
            fail("A2 C: 可用 %.1f GB（<40 GB 报警线）" % dfree,
                 "页面文件是求解器提交内存的最后兜底：磁盘长不动 -> 提交分配失败 -> "
                 "求解器 OOM 死，症状与 3dnms 崩溃混淆。")
        elif dfree < 60:
            warn("A2 C: 可用 %.1f GB（40~60 GB，建议先清到 >60 GB）" % dfree)
        else:
            ok("A2 C: 可用 %.1f GB" % dfree)

    try:
        mt, ma, cl, ca = mem_info()
        pct = 100.0 * (cl - ca) / cl if cl else 0.0
        detail = "总 %.1f / 可用 %.1f GB；提交 %.1f/%.1f GB (%.1f%%)" % (mt, ma, cl - ca, cl, pct)
        if ma < 2:
            fail("A3 可用物理内存 %.1f GB（<2 GB）" % ma, detail)
        elif mt < 30 or ma < 8:
            warn("A3 内存偏紧", detail)
        else:
            ok("A3 内存 %s" % detail)
        if pct >= 88:
            fail("A4 提交量 %.1f%% ≥ 88%%（内存耗尽自救线）" % pct, detail)
        elif pct >= 75:
            warn("A4 提交量 %.1f%%（健康区间 53~75%%）" % pct, detail)
        else:
            ok("A4 提交量 %.1f%%" % pct)
    except (OSError, ValueError) as e:
        fail("A3/A4 内存信息取不到", repr(e))

    # 3dnms 崩溃取证：近 24 h 转储文件数（基线 ≈2 次/h，报警线 4 次/h）
    dumps, seen_dir = [], False
    for d in [os.path.join(os.environ.get("LOCALAPPDATA", ""), "CrashDumps"),
              r"C:\Windows\System32\config\systemprofile\AppData\Local\CrashDumps"]:
        if d and os.path.isdir(d):
            seen_dir = True
            dumps += glob.glob(os.path.join(d, "*.dmp"))
    now = time.time()
    fresh = [p for p in dumps if now - os.path.getmtime(p) < 86400]
    if seen_dir and len(fresh) <= 96:
        ok("A5 近 24 h 3dnms 崩溃转储 %d 份（基线 ≈2 次/h，报警线 4 次/h）" % len(fresh))
    elif seen_dir:
        warn("A5 近 24 h 崩溃转储 %d 份（>4 次/h）" % len(fresh),
             "崩溃是点失败主因；磁盘触底/内存压力会推高崩溃率，先看 A2/A3/A4 是否越线。")
    else:
        # 兜底取证：从 guard 日志读「网格器：近 24 h 崩溃 N 次」
        gl = os.path.join(args.root, "%s_guard.log" % args.batch)
        n24 = None
        if os.path.exists(gl):
            with open(gl, "r", encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-400:]
            for line in reversed(tail):
                m = re.search(r"近 24 h\s+(\d+)\s*次", line)
                if m:
                    n24 = int(m.group(1))
                    break
        if n24 is None:
            warn("A5 崩溃转储目录不存在，且 guard 日志里也读不到崩溃计数",
                 "崩溃率是点失败的主因（91% 的崩溃 45 min 内引发点失败）；"
                 "批次运行后用 guard 日志的「网格器」行跟踪。")
        elif n24 > 96:
            warn("A5 guard 日志：近 24 h 网格器崩溃 %d 次（>4 次/h）" % n24)
        else:
            ok("A5 guard 日志：近 24 h 网格器崩溃 %d 次" % n24)


# --------------------------------------------------------------------- B 代码
def check_code(args):
    section("B 代码与口径冻结（batch1 修复是否仍在位）")

    src = read_text(os.path.join(WPT_DIR, "batch_sweep_lc.py"))
    if src is None:
        fail("B1 找不到 %s\\batch_sweep_lc.py" % WPT_DIR, "worker 依赖它，必须存在")
    else:
        probes = [
            (r"CPU_STALL_SECS\s*=\s*360", "CPU_STALL_SECS=360（僵死探针）"),
            (r"SESSION_DEAD_POLLS\s*=\s*12", "SESSION_DEAD_POLLS=12（gRPC 断连判死）"),
            (r"for\s+\w+\s+in\s+range\(180\)", "轮询上限 range(180)（BASE 单点可达 41 min）"),
            (r"def\s+_aedt_cpu_seconds", "_aedt_cpu_seconds（OS 级 CPU 探针）"),
            (r"def\s+_aedt_pid_of", "_aedt_pid_of"),
        ]
        miss = [d for pat, d in probes if not re.search(pat, src)]
        if miss:
            fail("B1 batch_sweep_lc.py 僵死探针不完整", "缺失：" + "、".join(miss)
                 + "\n         这批修复必须重启 worker 才生效（用启动时间比对确认）。")
        else:
            ok("B1 batch_sweep_lc.py 僵死探针齐备（会话僵死不再白停数小时）")

        probes2 = [
            (r"^FLEX_MESH\s*=\s*True", "FLEX_MESH=True"),
            (r"REGION_MAX_LEN_DIV\s*=\s*5\.0", "REGION_MAX_LEN_DIV=5.0"),
            (r"PCT_REFINEMENT\s*=\s*10", "PCT_REFINEMENT=10"),
            (r'RELATIVE_RESIDUAL\s*=\s*"1e-05"', "RELATIVE_RESIDUAL=1e-05"),
        ]
        miss2 = [d for pat, d in probes2 if not re.search(pat, src, re.M)]
        if miss2:
            fail("B2 batch_sweep_lc.py OPT 口径常量不符", "异常项：" + "、".join(miss2))
        else:
            ok("B2 batch_sweep_lc.py OPT 口径常量（柔性+⑥+pref10+rres1e-5）")

    try:
        sys.path.insert(0, WPT_DIR)
        import coil_gen as CG
        pm = getattr(CG, "PATH_MODE", None)
        if pm == "ring":
            ok("B3 coil_gen.PATH_MODE=ring（拐角重映射修正版）")
        else:
            fail("B3 coil_gen.PATH_MODE=%r（应为 ring）" % pm,
                 "legacy 会让全批角部几何变成尖刺（实测电感偏 0.7~1.5%%，端点失败）")
    except Exception as e:                       # noqa: BLE001 —— 显式报出原因，不吞
        fail("B3 coil_gen 导入失败（无法确认 PATH_MODE）", repr(e))

    w = read_text(os.path.join(args.root, "contract_worker.py"))
    if w is None:
        fail("B4 找不到 %s\\contract_worker.py" % args.root)
    else:
        probes3 = [
            (r'WPT_STAGE_TIMEOUT",\s*"1500"', "STAGE_TIMEOUT 默认 1500 s"),
            (r'WPT_SOLVE_TIMEOUT",\s*"2400"', "SOLVE_TIMEOUT 默认 2400 s"),
            (r'WPT_CLEAN",\s*"point"', "WPT_CLEAN=point（逐点清场数据）"),
            (r'WPT_MESH_FALLBACK",\s*"1"', "WPT_MESH_FALLBACK=1（逐点 BASE 回退）"),
            (r'WPT_SESSION_MAX_H",\s*"7"', "WPT_SESSION_MAX_H=7（会话轮换）"),
            (r"OPT_MIN_GAP\s*=\s*True,\s*5\.0,\s*1\.5",
             "OPT 口径三元组 = (柔性, ⑥, 闸门 1.5 mm)"),
        ]
        miss3 = [d for pat, d in probes3 if not re.search(pat, w)]
        if miss3:
            fail("B4 contract_worker.py 口径/超时不符", "异常项：" + "、".join(miss3))
        else:
            ok("B4 contract_worker.py 超时/清理/回退/闸门常量一致")

    g = read_text(os.path.join(args.root, "%s_guard.py" % args.batch))
    if g is None:
        fail("B5 找不到 %s\\%s_guard.py" % (args.root, args.batch))
    else:
        probes4 = [
            (r"LAUNCH_GRACE_MIN\s*=\s*20\.0", "LAUNCH_GRACE_MIN=20（防重启互相残杀）"),
            (r"RELAUNCH_CONFIRMED_MIN\s*=\s*25\.0", "RELAUNCH_CONFIRMED_MIN=25（僵死快速通道）"),
            (r"ansysedt,3dnms,G3dMesher,ansyscl", "杀进程覆盖全家族 4 个进程名"),
            (r"_delayed_launch\.py", "整批重启走 _delayed_launch.py（杀完等 240 s）"),
            (r"批次已全部完工", "全部完工判据（2026-10-12 修：不再对已完工批次每 30 min 重启）"),
            (r"registered_gaps", "例外表已登记缺口计入完工判据"),
            (r"relaunch_one\(", "逐实例外科恢复 relaunch_one"),
            (r"_delayed_launch\|_relaunch_one", "重启时把延迟启动器/外科恢复进程一起杀掉"),
            (r"n_worker_known", "worker 计数取不到时不判死亡（防 PowerShell 抖动误杀健康批次）"),
            (r"CommandLine -like", "进程计数/杀进程按本批次脚本目录过滤（防跨批次互杀）"),
        ]
        miss4 = [d for pat, d in probes4 if not re.search(pat, g)]
        if miss4:
            fail("B5 %s_guard.py 关键修复缺失" % args.batch, "缺失：" + "、".join(miss4))
        else:
            ok("B5 %s_guard.py 关键修复齐备（外科恢复/延迟重启/完工判据/跨批次隔离）"
               % args.batch)

    raw_probe = {
        "%s_deliver.py" % args.batch: [r"raw", r"points_missing", r"gaps_registered",
                                       r"N_CASES"],
        "%s_partial_export.py" % args.batch: [r"raw"],
    }
    bad = []
    for fn, pats in raw_probe.items():
        t = read_text(os.path.join(args.root, fn))
        if t is None:
            bad.append("%s 缺失" % fn)
            continue
        for p in pats:
            if not re.search(p, t):
                bad.append("%s 无 %r" % (fn, p))
    if bad:
        warn("B6 清单/旁路导出的 raw 反推无法确认", "；".join(bad))
    else:
        ok("B6 交付链路含 raw 反推（缺口不依赖跨重启丢失的 worker JSON 状态）")

    # 只查会被计划任务/管道调用的生产脚本（测试脚本不在此列）
    BB = args.batch
    prod = ["%s_guard.py" % BB, "%s_status.py" % BB, "%s_deliver.py" % BB,
            "%s_accept.py" % BB, "%s_clean.py" % BB, "%s_physics_check.py" % BB,
            "%s_partial_export.py" % BB, "contract_merge.py",
            "contract_launch.py", "contract_worker.py", "%s_disk.py" % BB,
            "_delayed_launch.py", "_relaunch_one.py"]
    nohard = []
    for fn in prod:
        t = read_text(os.path.join(args.root, fn))
        if t is None:
            continue
        if "reconfigure(encoding" not in t and "print(" in t:
            nohard.append(fn)
    if nohard:
        warn("B7 有生产脚本缺 UTF-8 入口加固（管道/计划任务下会 UnicodeEncodeError）",
             "、".join(nohard) + "\n         已知教训：guard 曾在 stdout 被管道捕获时"
             "必崩在最后一行 ✓ 上（退出码 1 但日志已写、重启已执行，极易误判）。")
    else:
        ok("B7 生产脚本均有 UTF-8 入口加固")

    # ⚠️ 判据要写成"默认值 != 本批次名"，不能写成"默认值 == b1"
    # （写成字面 b1 后，把脚本复制成 b2 时连这条检查自己都会被一起替换掉 —— 已踩过）。
    stale = []
    for fn in sorted(glob.glob(os.path.join(args.root, "*.py"))):
        bn = os.path.basename(fn)
        if bn.startswith("test_") or bn == "preflight.py":
            continue
        t = read_text(fn) or ""
        # 只看 --batch 的默认值（不能对所有 default="..." 一律比对：
        # --boxx 420 / --boxy 161 这类数值默认值不是批次名，会误报）
        for m in re.finditer(r'add_argument\("--batch",\s*default="([^"]+)"', t):
            if m.group(1) != args.batch:
                stale.append("%s: --batch 默认 %r" % (bn, m.group(1)))
        for m in re.finditer(r'os\.environ\.get\("WPT_BATCH",\s*"([^"]+)"\)', t):
            if m.group(1) != args.batch:
                stale.append("%s: WPT_BATCH 默认 %r" % (bn, m.group(1)))
        for m in re.finditer(r'^\s*B\s*=\s*"([^"]+)"', t, re.M):
            if m.group(1) != args.batch:
                stale.append("%s: B = %r" % (bn, m.group(1)))
    if stale:
        warn("B8 脚本里残留**别的批次**的默认值（不传 --batch 会写错目录）",
             "、".join(stale))
    else:
        ok("B8 所有 CLI 默认批次名 == %s" % args.batch)


# --------------------------------------------------------------------- C 数据
def check_data(args):
    section("C 数据链路与参数表")

    if os.path.exists(BASE_PROJECT):
        lock = BASE_PROJECT + ".lock"
        if os.path.exists(lock):
            warn("C1 基础工程存在但带 .lock（可能被占用）", lock)
        else:
            ok("C1 基础工程就绪：%s（%.1f MB）"
               % (BASE_PROJECT, os.path.getsize(BASE_PROJECT) / 1048576.0))
    else:
        fail("C1 找不到基础工程 %s" % BASE_PROJECT)

    if not os.path.exists(args.plan):
        fail("C2 参数表不存在：%s" % args.plan, "用户提供参数表后必须先过本节校验")
        return

    with open(args.plan, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    cols = list(rows[0].keys()) if rows else []
    miss = [c for c in MAIN_COLS if c not in cols]
    if miss:
        fail("C2 参数表缺列", "缺：%s；实有：%s" % ("、".join(miss), "、".join(cols)))
        return
    ok("C2 参数表 %d 行，7 维齐全" % len(rows))

    if "case_id" not in cols:
        fail("C3 参数表没有 case_id 列", "必须先按 <batch>_0001 规则编号")
    else:
        ids = [r["case_id"] for r in rows]
        dup = len(ids) - len(set(ids))
        badprefix = [i for i in ids if not i.startswith(args.batch + "_")]
        if dup:
            fail("C3 case_id 有 %d 个重复" % dup)
        elif badprefix:
            fail("C3 %d 个 case_id 前缀不是 %s_" % (len(badprefix), args.batch),
                 "示例：%s" % "、".join(badprefix[:5]))
        else:
            ok("C3 case_id 唯一且前缀正确（%s_0001 形式）" % args.batch)

    bad = []
    for r in rows:
        for c in MAIN_COLS:
            try:
                float(r[c])
            except (TypeError, ValueError):
                bad.append("%s.%s=%r" % (r.get("case_id"), c, r.get(c)))
    if bad:
        fail("C4 参数表有非数值/空值", "、".join(bad[:8]))
    else:
        ok("C4 参数表全部数值可解析")

    for c in MAIN_COLS:
        v = [float(r[c]) for r in rows]
        print("         %-14s min %9.4f  max %9.4f" % (c, min(v), max(v)), flush=True)

    try:
        sys.path.insert(0, WPT_DIR)
        import coil_gen as CG
        import wpt_contract as WC
        K = CG.k_lc()
        n_opt = n_base = n_x_over = n_y_over = 0
        worst_need = 0.0
        gaps = []
        for r in rows:
            LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
            g = float(r["spacing_ratio"])
            gap = float(CG.path_dims(LC, KR)["gap_min"])
            gaps.append(gap)
            use_opt = gap >= OPT_MIN_GAP
            n_opt += 1 if use_opt else 0
            n_base += 0 if use_opt else 1
            S = LC * (2.0 + g)
            rx_half = LC * K / 2.0 + CG.WIDTH / 2.0
            need_x = max(S / 2.0 + rx_half, max(S / 2.0, LC / 2.0) + 15.0 + 10.0)
            worst_need = max(worst_need, need_x)
            if need_x + 40.0 > BOX_X + 1e-6:
                n_x_over += 1
            y_half = round(1.2 * LC) / 2.0
            if y_half > BOX_Y[1] - 1e-6 or -y_half < BOX_Y[0] - 1e-6:
                n_y_over += 1
        gaps.sort()
        pct = 100.0 * n_base / max(len(rows), 1)
        # 豁免来源：build_b2_plan 写进 plan_meta 的 box_margin_waiver（含实测证据）。
        # 这样"留边不足"只需在参数表校验时决定一次，后续各环节自动继承并可审计。
        _waiver = None
        _meta = os.path.join(args.root, "%s_plan_meta.json" % args.batch)
        if os.path.exists(_meta):
            try:
                with open(_meta, encoding="utf-8-sig") as f:
                    _waiver = (json.load(f) or {}).get("box_margin_waiver")
            except (OSError, ValueError):
                _waiver = None
        if n_y_over or (n_x_over and not _waiver):
            fail("C5 固定盒装不下 %d 个工况（X 留边不足 %d / Y 越界 %d）"
                 % (n_x_over + n_y_over, n_x_over, n_y_over),
                 "扫描端点时接收线圈会伸出解域 -> 解被截断。"
                 "最坏工况需 X±%.1f + 40 留边 = X±%.1f（当前 X±%.0f）"
                 % (worst_need, worst_need + 40.0, BOX_X))
        elif n_x_over:
            warn("C5 X 盒「+40 mm 留边」不足 %d 个工况 —— **已有豁免**（%s）"
                 % (n_x_over, _waiver),
                 "物体仍在 X±%.0f 内（最坏工况 need_x=%.1f，余量 %.1f mm），"
                 "ensure_region() 硬判据不会触发；越界量仅对自定留边准则而言。"
                 % (BOX_X, worst_need, BOX_X - worst_need))
            ok("C5 固定盒 X±%.0f / Y[%.2f, %.1f] 仍装得下全部 %d 工况 × %d 点（豁免已记录）"
               % (BOX_X, BOX_Y[0], BOX_Y[1], len(rows), N_PTS))
        else:
            ok("C5 固定盒 X±%.0f / Y[%.2f, %.1f] 装得下全部 %d 工况 × %d 点"
               % (BOX_X, BOX_Y[0], BOX_Y[1], len(rows), N_PTS))
        ok("C6 闸门分布预估：OPT %d / BASE %d（%.1f%% 走 BASE）"
           % (n_opt, n_base, pct),
           "gap_min 最小 %.4f / 中位 %.4f / 最大 %.4f（闸门 %.1f mm）"
           % (gaps[0], gaps[len(gaps) // 2], gaps[-1], OPT_MIN_GAP))
        if pct > 25:
            warn("C6 BASE 占比 %.1f%% 偏高（batch1 实测 13.7%%）" % pct,
                 "BASE 单点 ~20 min 是 OPT 的 2.8 倍，工期会显著拉长；"
                 "紧几何是必要不充分条件，不必然失败。")

        # ⚠️ 工期以 **b1 生产实测**为准：单工况 172.4 min（含 BASE 工况与 8 实例争用）。
        # 可独立复算：b1 的 8 份 raw 逐点 minutes 求和 = 735 实例·小时 / 5370 点。
        # 另一组常数（105.4/290.8 min 每工况 = 4.78/13.61 min 每点）是**单实例、旧几何、
        # 旧空气域**下测的，用于估工期会低估约 1.64 倍，这里仅作参考列出。
        T_MEAS = 172.4
        wall_h = (n_opt * 105.4 + n_base * 290.8) / 60.0 / args.n
        meas_h = len(rows) * T_MEAS / 60.0 / args.n
        ok("C7 工期预估（%d 实例）" % args.n,
           "**按 b1 生产实测 %.1f min/工况 ≈ %.1f 天**（纯计算，未含停机余量）；"
           "先验常数口径 %.1f 天仅供排序参考，不可用于工期"
           % (T_MEAS, meas_h / 24.0, wall_h / 24.0))
    except Exception as e:                       # noqa: BLE001
        fail("C5/C6 几何核查未能执行", repr(e))

    raw = glob.glob(os.path.join(args.root, "%s_raw_run*.csv" % args.batch))
    aedt = glob.glob(os.path.join(args.root, "Projecttonight_%s_run*.aedt" % args.batch))
    if raw or aedt:
        if batch_running(args.root, args.batch):
            ok("C8 批次运行中：raw %d 个 / 工程副本 %d 个（运行期的正常状态，不是脏目录）"
               % (len(raw), len(aedt)))
        else:
            warn("C8 本批次目录已有历史产物（raw %d 个 / 工程副本 %d 个）"
                 % (len(raw), len(aedt)),
                 "批次**未在运行**却有产物：若是全新批次，确认这不是误用同名批次；"
                 "若是断点续跑，则 raw 是真值来源，务必先备份再动。")
    else:
        ok("C8 本批次目录干净（全新批次）")

    ex = os.path.join(args.root, "%s_partial_exceptions.json" % args.batch)
    if os.path.exists(ex):
        try:
            d = json.load(open(ex, encoding="utf-8-sig"))
            known = list((d.get("cases") or {}).keys())
            unknown = [c for c in known if c not in set(
                r.get("case_id") for r in rows)]
            if unknown:
                warn("C9 例外表有 %d 个工况不在参数表内" % len(unknown),
                     "、".join(unknown[:5]))
            else:
                ok("C9 例外表 %d 个已登记缺口工况，均在本批参数表内" % len(known))
        except (OSError, ValueError) as e:
            warn("C9 例外表解析失败", repr(e))
    else:
        ok("C9 无例外表（新批次正常；出现缺口时再建）")


# --------------------------------------------------------------------- D 任务
def check_tasks(args):
    section("D 计划任务（无人值守的自愈与交付）")

    out = sh("Get-ScheduledTask -TaskName 'b1_*','b2_*' -ErrorAction SilentlyContinue | "
             "ForEach-Object { $_.TaskName + '|' + $_.State }")
    if not out:
        warn("D1 没有任何 b1_*/b2_* 计划任务",
             "批次启动前应注册 guard / deliver / clean 三个任务，否则断线后无人自愈。")
    else:
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            name, _, state = line.partition("|")
            if name.startswith("b1_") and state != "Disabled":
                warn("D1 旧批次任务 %s 仍是 %s" % (name, state),
                     "b1 已交付（禁止再动它的目录）。第二轮启动前建议 Disable："
                     "①b1 的 deliver 每 30 min 重刷 out\\b1_*.csv 与 manifest，"
                     "持续脏化已交付目录；②两批同时跑会争抢内存与 AEDT 席位。"
                     "（若确实要保留磁盘清理，只留 b1_batch_clean。）")
            else:
                ok("D1 任务 %s 状态 %s" % (name, state))

    want = {"%s_batch_guard" % args.batch: ["--restart", "--relaunch-stalled"],
            "%s_batch_deliver" % args.batch: ["--batch", args.batch],
            "%s_batch_clean" % args.batch: ["--batch", args.batch]}
    for t, keys in want.items():
        act = sh("(Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue).Actions | "
                 "ForEach-Object { $_.Arguments }" % t)
        exe = sh("(Get-ScheduledTask -TaskName '%s' -ErrorAction SilentlyContinue).Actions | "
                 "ForEach-Object { $_.Execute }" % t)
        if not act:
            warn("D2 任务 %s 未注册" % t)
            continue
        # ⚠️ 2026-10-12 新增（实测踩过）：参数**不能以解释器自身开头**。
        # 注册时若把 "python.exe 脚本.py ..." 整串写进 -Argument，而 -Execute 也是
        # python.exe，实际命令行就变成 `python.exe python.exe 脚本.py ...` —— 任务每次都以
        # "can't open file '...python.exe'" 退出码 1，**而参数里该有的关键字一个不少**，
        # 粗查会误判成"注册正确"。代价是这套任务静默地什么都没做（自愈全程失效 4 小时）。
        _exe = exe.strip().lower()
        _act = act.strip().lower()
        if _exe and _act.startswith(_exe):
            fail("D2 任务 %s 的参数里重复了解释器（Execute=%s 又出现在 Arguments 开头）"
                 % (t, exe.strip()),
                 "实际命令行会变成 `%s %s`，任务必然以退出码 1 失败且什么都不做。"
                 "正确写法：-Execute <解释器>，-Argument \"<脚本.py> <参数...>\""
                 % (exe.strip(), act.strip()[:120]))
            continue
        miss = [k for k in keys if k not in act]
        if miss or args.root not in act:
            warn("D2 任务 %s 参数可疑" % t, "args=%s" % act.strip()[:200])
        elif "Disabled" in sh("(Get-ScheduledTask -TaskName '%s' -EA SilentlyContinue).State" % t):
            # 启动前注册但保持 Disabled 是**有意的**（避免批次还没起就被 guard 拉起）。
            # 真正启动批次后必须 Enable，否则断线无人自愈 —— 这里只提醒。
            warn("D2 任务 %s 参数正确，但当前是 Disabled" % t,
                 "批次启动后必须 `Enable-ScheduledTask -TaskName %s`，否则失速/崩溃无人自愈。" % t)
        else:
            ok("D2 任务 %s 参数正确且已启用" % t)

    ok("D3 提醒：guard 自 2026-10-12 起按**本批次脚本目录**过滤进程（不再是全机口径），"
       "但两个批次同时跑仍会争抢内存/AEDT 席位 —— 同一时刻只跑一个批次")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--batch", default="b2")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--plan", default=None)
    args = ap.parse_args()
    args.root = os.path.abspath(args.root)
    args.plan = args.plan or os.path.join(args.root, "%s_plan.csv" % args.batch)

    print("=" * 78)
    print("批次启动前自检   batch=%s  root=%s  n=%d" % (args.batch, args.root, args.n))
    print("时间 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 78, flush=True)

    check_env(args)
    check_code(args)
    check_data(args)
    check_tasks(args)

    section("汇总")
    nf = sum(1 for lv, _, _ in R if lv == "FAIL")
    nw = sum(1 for lv, _, _ in R if lv == "WARN")
    nok = sum(1 for lv, _, _ in R if lv == "OK")
    print("OK %d / WARN %d / FAIL %d" % (nok, nw, nf), flush=True)
    if nf:
        print("\n存在 %d 个 FAIL —— **不要启动批次**，先逐条消掉：" % nf)
        for lv, item, _ in R:
            if lv == "FAIL":
                print("  · %s" % item)
        print("\n退出码 1")
        return 1
    print("\n可以启动。建议命令：")
    print('  %s "%s\\contract_launch.py" %d --batch %s --root "%s" --boxx %d --merge'
          % (PY, args.root, args.n, args.batch, args.root, int(BOX_X)))
    print("（先跑验收点子集冒烟，再放全量；见《第二轮启动前检查清单》第 4 节）")
    print("退出码 0")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                      # noqa: BLE001 —— 自检脚本自身出错必须显式暴露
        print("\n[FAIL] preflight 自身异常：%r" % (exc,), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)
