# -*- coding: utf-8 -*-
r"""批次守护：健康检查 +（可选）自动重启续跑。

判据：
  · worker 进程数（应为 N 实例）
  · AEDT 进程数（应为 N 实例）
  · 各实例最后落盘时间（单点 OPT ~7 min / BASE ~20 min，几何 7~10 min；>45 min 视为失速）
  · 结果目录体积（应处于平台期，不随点数线性增长）

行为：
  默认只检查并报告；加 --restart 时，判定「批次已死或整体失速」则
  杀掉残留 → 重新启动启动器（断点续跑，已解点位不丢）。
  --restart 不会在「单个实例失速」时重启整批（那会拖慢其余 7 个实例），
  只提示人工查看该实例日志。

用法：
  python b1_guard.py                      # 只检查
  python b1_guard.py --restart            # 检查 + 必要时重启
  python b1_guard.py --stall-min 60       # 自定义失速阈值（默认 90 分钟）
"""
import argparse
import csv
import ctypes
from ctypes import wintypes
import glob
import os
import re
import shutil
import subprocess
import sys
import time

# stdout 被重定向/管道捕获时中文 Windows 默认 GBK，而本脚本末行判定用的是
# ✓(U+2713)，GBK 编不出来 → 健康检查会在最后一行抛 UnicodeEncodeError 退出码 1。
# （2026-09-19 实测；b1_deliver / b1_accept / contract_merge / b1_partial_export
# 早已加这道加固，本脚本此前是漏网的一个。）计划任务下 stdout 接着真控制台，
# 所以一直没暴露；一旦从管道/重定向里调用（巡检脚本、CI、远程执行）就会踩到。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
PY = r"C:\anaconda\python.exe"

# 可用内存报警线（GB）——交接文档《故障处置手册》的「内存不足」判据
MEM_ALERT_GB = 2.0
# 提交量报警线（%）——比物理可用量更早的真实红线：物理内存有页缓存可回收，
# 提交量逼近上限时进程的分配请求会直接失败（实测本机常年在 85~90% 区间）
MEM_COMMIT_ALERT_PCT = 92.0

# 内存耗尽的自救线：提交量 ≥ 此值且多数实例失速时，不再等"全部失速"就重启。
# 2026-09-22 实测教训：内存耗尽会让实例**陆续**冻死（不是同时），
# 只要有一个幸运实例还在出点，`all_stalled` 就永远不成立 ——
# 7 个实例白停 6.5 小时，而 run4 一个实例撑住了整个判据。
# 取 88% 的理由：92% 是报警线，而实测"已被冻死"的批次提交量就在 92~95%；
# 88% 留一点余量，且单靠 88% 不会误触发（健康时提交量 53~75%）。
MEM_EXHAUST_RESTART_PCT = 88.0
# 触发自救所需的最少失速实例数（8 实例时即 5 个）
MEM_EXHAUST_MIN_STALLED = 5
# "重启进行中"的判定窗口（分钟）：启动器启动不足这么久，才认为重启还在进行。
# ⚠️ 2026-09-24 修正：原来取 5.0 min（只够错峰起 8 实例的 2.5 min）。但整批重启
# 现在走 _delayed_launch.py —— 先等 240 s 让 AEDT 退净，再起 8 个 worker（20 s 错峰），
# 全程约 6.5 min。窗口若短于此，guard 下一轮会误判"重启不在进行"→ **再次整批重启**，
# 把上一轮正在启动的 worker 杀掉，形成"越重启越起不来"的循环（实测 18:39 起了 3 个
# 启动器、worker 被反复杀剩 5 个）。故放宽到 20 min，安全盖住 240 s 等待 + 8 实例错峰
# + 前几个会话建立 gRPC（实测每个 12~30 s）。
LAUNCH_GRACE_MIN = 20.0
# 网格器崩溃率报警线（次/小时）。实测基线 ≈2 次/h（22~25 次 / 11 h），
# 取 2 倍作为报警；崩溃率上升通常先于点位增速下降出现。
MESHER_CRASH_ALERT_PER_HR = 4

# ---- 逐实例外科恢复（--relaunch-stalled）----
# 2026-09-23 事故：8 个实例在约 1 小时内**全部**先后僵死在同一个签名上——
# `网格: 整套优化=True` 之后、`analyze` 轮询之中，日志再无新增，而 AEDT 进程
# 仍在（Responding=True）却把工作集从 ~3.7 GB 掉到 13~846 MB，CPU 利用率只剩
# 0.14~0.29 核。会话实际已死（gRPC 全断，实测累计 7996 条 poll err），但 worker
# 卡在无超时的调用里，run_stage 的 2400 s 看门狗**只包住 Analyze 那一次调用**，
# 包不住其后的轮询循环，于是既不出点也不退出。
# guard 原设计「单个实例失速时只报告不动作」在 1 个实例时是对的（重启会拖慢其余 7 个），
# 但在 5 个实例同时僵死时变成彻底失能：白停 24 实例·小时，只会刷告警等人。
# 故新增本路径：对每个失速实例做**外科手术**——只杀它自己的 worker+AEDT，
# 再 _relaunch_one.py 拉起，完全不碰健康实例。
RELAUNCH_STALL_MIN = 150.0        # 失速多久才值得外科重启（须 > 最慢的 BASE 单点）
RELAUNCH_MIN_STALLED = 3          # 失速实例数达到几个才动手（1~2 个仍只报告）
_relaunched = set()               # 本进程内已处理过的实例（冷却，防重启循环）
CPU_IDLE_LOG_MIN = 45.0           # CPU 探针附带条件：日志至少这么久没更新才算僵死
                                  # （防止"实例正卡在两点之间"被误判——那种情况日志也会老）
                                  # ⚠️ 2026-10-12 由 20 → 45：用 b1 交付的 428 个 BASE 点实测，
                                  # 单点耗时均值 17.7 min、p90 23.1、**max 29.0 min**
                                  #（>20 min 的有 35 个 = 8.2%，>25 min 的有 14 个 = 3.3%）；
                                  # 而求解期间**日志本来就不会更新**。阈值取 20 会让这些
                                  # 健康实例被判"僵死"，再叠加 25 min 的快速通道
                                  # → **把正在求解的会话外科杀掉**（点位还没落盘，白烧一轮）。
                                  # 45 min 高于实测最坏值，也高于文档记载的 BASE 单点上限 41 min。
# CPU 探针**已确认**僵死（增量<1 核 且 日志老化）的实例，走这条更短的阈值：
# 证据强度不同——"落盘慢"可能只是卡在两点之间，而"进程 CPU 零增长"是会话已死的直接证据。
# 故不必再等 150 min 的保守线。（2026-09-23 实测：run7 被探针连续 3 轮报僵死，
# 却因 150 min 门槛一动不动，白停近 2 h。）
RELAUNCH_CONFIRMED_MIN = 25.0

# 磁盘可用空间报警线（GB）。2026-09-19 查明：C: 一天掉 16 GB 的主因是系统自动管理的
# pagefile.sys 涨到 46 GB（8 实例内存压力，提交量 66/77 GB）。页面文件本身没问题，
# 但它是求解器提交内存的**最后兜底** —— 磁盘没空间它就长不动，提交分配失败会让
# 求解器 OOM 死，而症状会和 3dnms 崩溃混在一起极难区分（20:03 磁盘触底 111.9 GB，
# 20:30/20:36 就各崩了一次）。故低于此线必须显式报警。
DISK_ALERT_GB = 40.0


class _MEMSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def mem_gb():
    """(总物理内存 GB, 可用物理内存 GB)。ctypes 直接问内核，不额外起子进程。"""
    t, a, _cl, _ca = mem_info()
    return t, a


def mesher_crashes(win_min=60, win_hrs=24):
    """(近 win_min 分钟, 近 win_hrs 小时) 内 3dnms.exe 崩溃次数。

    3dnms.exe 是 ANSYS 网格生成器。2026-09-19 诊断确认它是**点失败的主因**：
    22 次崩溃 / 10.5 h，91% 的崩溃在 45 min 内引发点失败，传播延迟指纹 +1.8 min
    （前瞻预测命中误差 1 秒）。详见《b1_失败签名诊断_20260919.md》第 8 节。

    崩溃率是比「点位增速」更早的健康指标 —— 点失败会被 BASE 回退悄悄救回，
    但每一次都白烧一轮求解时间，所以要在源头盯着。

    注意：guard 的 sh() 调的是 Windows PowerShell 5.1，单元素结果不会自动成数组，
    因此必须用 @() 包裹才能拿到可靠 .Count。
    """
    cmd = ("$now=Get-Date; "
           "$e=@(Get-WinEvent -FilterHashtable @{LogName='Application';"
           "StartTime=$now.AddHours(-%d);ProviderName='Application Error'} "
           "-ErrorAction SilentlyContinue | Where-Object { $_.Message -match '3dnms' }); "
           "'{0}|{1}' -f @($e | Where-Object { $_.TimeCreated -ge $now.AddMinutes(-%d) }).Count, $e.Count"
           % (win_hrs, win_min))
    out = sh(cmd)
    a, sep, b = out.partition("|")
    return (a, b) if sep else ("?", "?")


def mem_info():
    """(总物理 GB, 可用物理 GB, 提交上限 GB, 可提交 GB)。

    提交率（committed/limit）比物理可用量更早报警：物理内存有页缓存可回收，
    提交量一旦逼近上限，进程的分配请求会直接失败。
    """
    st = _MEMSTATUSEX()
    st.dwLength = ctypes.sizeof(_MEMSTATUSEX)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return None, None, None, None
    except OSError:
        return None, None, None, None
    G = float(2 ** 30)
    return (st.ullTotalPhys / G, st.ullAvailPhys / G,
            st.ullTotalPageFile / G, st.ullAvailPageFile / G)


def sh(cmd):
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True, timeout=60)
        return (r.stdout or "").strip()
    except Exception as e:
        return "ERR:%r" % e


# kernel32 句柄（CPU 存活探针用；与 batch_sweep_lc.py 同一套 Win32 调用）
_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.OpenProcess.restype = wintypes.HANDLE
_k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_k32.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                 ctypes.POINTER(wintypes.FILETIME), ctypes.c_void_p]
_k32.CloseHandle.argtypes = [wintypes.HANDLE]


def aedt_pid_by_instance(root=None, batch=None):
    """{实例号(str): AEDT pid}。映射从各实例的 .aedt.lock 里读——那是权威来源。

    ⚠️ root/batch 必须显式传入：它们是 main() 的**局部**变量，不是模块全局
    （2026-09-23 实测在这里踩过 NameError）。
    """
    root = root if root is not None else globals().get("ROOT", ".")
    batch = batch if batch is not None else globals().get("B", "b1")
    out = {}
    for k in range(64):
        f = os.path.join(root, "Projecttonight_%s_run%d.aedt.lock" % (batch, k))
        if not os.path.exists(f):
            continue
        try:
            txt = open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        m = re.search(r"DesktopProcessID=(\d+)", txt)
        if m:
            out[str(k)] = int(m.group(1))
    return out


def aedt_cpu_map(root=None, batch=None):
    """{实例号: 该实例 AEDT 进程累计 CPU 秒数}；取不到的实例不出现。

    为什么需要它（2026-09-23 事故）：僵死会话的日志年龄、进程存在性、甚至历史平均
    CPU 利用率都会骗人——实测僵死会话 Responding=True、工作集 13~846 MB、累计平均
    利用率仍显示 15~21 核（因为它是"曾经很忙"）。唯一可靠的活体信号是**两次采样之间
    CPU 时间是否增长**。这里只做采样，判据与阈值放在调用处。
    """
    res = {}
    for k, pid in aedt_pid_by_instance(root, batch).items():
        try:
            c = _proc_cpu_seconds(pid)
        except Exception:
            c = None
        if c is not None:
            res[k] = c
    return res


def family_cpu_seconds():
    """整个 AEDT 家族的累计 CPU 秒（ansysedt+3dnms+G3dMesher+ansyscl）。

    ⚠️ 2026-10-12 新增，为什么需要：**真正干活的是子进程，不是 GUI 进程**。
    实测 b2 批次运行中，8 个 ansysedt 各自的 CPU 增量只有 0.00~0.03 核（≈0~0.4 秒/12 秒），
    而同期 3dnms（网格器）单进程就有 ~1.1 核。也就是说，只看 ansysedt 会把"正在求解"的
    健康实例看成"CPU 零增长"。配合日志阈值就成了**误杀**（见 CPU_IDLE_LOG_MIN 的注释）。
    故判"僵死"必须再加上"全家族都没在动"这一条：只要 mesh/solver 子进程在烧 CPU，
    就不允许把任何实例判成僵死。
    """
    r = sh("(Get-Process -Name ansysedt,3dnms,G3dMesher,ansyscl -ErrorAction SilentlyContinue | "
           "Measure-Object -Property CPU -Sum).Sum")
    try:
        return float(str(r).strip())
    except (TypeError, ValueError):
        return float("nan")


def _proc_cpu_seconds(pid):
    """进程累计 CPU 秒；进程不存在或取不到返回 None。"""
    h = _k32.OpenProcess(0x1000, False, int(pid))
    if not h:
        h = _k32.OpenProcess(0x0400, False, int(pid))
        if not h:
            return None
    try:
        code = wintypes.DWORD()
        if not _k32.GetExitCodeProcess(h, ctypes.byref(code)):
            return None
        if code.value != 259:                    # STILL_ACTIVE
            return None
        _cre, _exi, kern, _usr = (wintypes.FILETIME(), wintypes.FILETIME(),
                                  wintypes.FILETIME(), wintypes.FILETIME())
        # GetProcessTimes 的 4 个出参必须传真实结构地址，传 NULL 会 access violation
        if not _k32.GetProcessTimes(h, ctypes.byref(_cre), ctypes.byref(_exi),
                                    ctypes.byref(kern), ctypes.byref(_usr)):
            return None
        return (kern.dwHighDateTime * 4294967296.0 + kern.dwLowDateTime) / 1e7
    finally:
        _k32.CloseHandle(h)


def relaunch_one(k, root=None, batch=None, boxx="420", boxy="161"):
    """外科手术式恢复单个实例：只杀它自己的 worker + AEDT，再用 _relaunch_one.py 拉起。

    安全性：lock 文件里 DesktopProcessID 是**权威**映射；杀之前再确认它的父进程
    确实是 contract_worker.exe，并且**先杀 AEDT 再杀父进程**——顺序反了的话，
    若目标 worker 恰好已退出、PID 被复用，就会误杀别的实例。
    ⚠️ root/batch 必须显式传入（它们是 main() 的局部变量，不是模块全局）。
    """
    root = root if root is not None else globals().get("ROOT", ".")
    batch = batch if batch is not None else globals().get("B", "b1")
    lockf = os.path.join(root, "Projecttonight_%s_run%d.aedt.lock" % (batch, k))
    try:
        txt = open(lockf, encoding="utf-8", errors="replace").read()
    except OSError:
        return False, "无 lock 文件（实例可能已退出）"
    m = re.search(r"DesktopProcessID=(\d+)", txt)
    if not m:
        return False, "lock 里没有 DesktopProcessID"
    aedt = int(m.group(1))
    if not os.path.exists(os.path.join(HERE, "_relaunch_one.py")):
        return False, "_relaunch_one.py 不存在"
    # 先杀 AEDT（按 PID + 进程名双重校验）
    cmd = ("$p=Get-Process -Id %d -ErrorAction SilentlyContinue; "
           "if($p -and $p.ProcessName -eq 'ansysedt'){"
           "$w=Get-CimInstance Win32_Process -Filter ('ProcessId=%d'); "
           "if($w){$par=Get-CimInstance Win32_Process -Filter ('ProcessId='+$w.ParentProcessId); "
           "if($par -and $par.Name -eq 'python.exe' -and $par.CommandLine -match 'contract_worker'){"
           "Stop-Process -Id $par.ProcessId -Force -ErrorAction SilentlyContinue}}; "
           "Stop-Process -Id %d -Force -ErrorAction SilentlyContinue; 'killed'} else {'noaedt'}"
           % (aedt, aedt, aedt))
    r = sh(cmd)
    if r.startswith("ERR"):
        return False, r
    try:
        # ⚠️ 2026-10-12：必须把 batch/root/box 一起传下去。原版只传实例号，而
        # _relaunch_one.py 里 B 写死 "b1" —— b2 的外科恢复会拉起 b1 口径的 worker
        # （读 b1 分片表、写 b1 raw/log），既救不活实例又污染另一批次数据。
        p = subprocess.Popen([PY, os.path.join(HERE, "_relaunch_one.py"), str(k),
                              str(batch), str(root), str(boxx), str(boxy)],
                             cwd=HERE, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
    except Exception as e:
        return False, "拉起失败 %r" % (e,)
    return True, "killed=%s -> 已拉起 pid=%d" % (r, p.pid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=HERE)
    ap.add_argument("--batch", default="b2")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--stall-min", type=float, default=90.0,
                    help="失速阈值（分钟）。默认 90 —— 与交接文档第 6 节的判据一致；"
                         "45 会在几何重建+网格（常 >45 min）时误报")
    ap.add_argument("--restart", action="store_true")
    ap.add_argument("--relaunch-stalled", action="store_true",
                    help="失速实例 ≥%d 个且单个失速 >%.0f min 时，逐实例外科恢复"
                         "（只杀各自 worker+AEDT，不打断健康实例）。默认关闭，"
                         "与 --restart 可叠加。"
                         % (RELAUNCH_MIN_STALLED, RELAUNCH_STALL_MIN))
    ap.add_argument("--relaunch-min-stalled", type=int, default=RELAUNCH_MIN_STALLED,
                    help="失速实例数达到几个才外科恢复（默认 %d）。设为 1 即"
                         "「任一实例僵死就换掉」——2026-09-23 实测单实例僵死（run7，"
                         "worker 进程 130 min 仅耗 20 s CPU）会白停 2 h 且不自愈。"
                         % RELAUNCH_MIN_STALLED)
    ap.add_argument("--relaunch-stall-min", type=float, default=RELAUNCH_STALL_MIN,
                    help="单个实例失速多久才外科恢复（默认 %.0f min，须 > 最慢的 BASE 单点）"
                         % RELAUNCH_STALL_MIN)
    ap.add_argument("--no-relaunch-stalled", dest="relaunch_stalled",
                    action="store_false", help="显式关闭外科恢复")
    ap.set_defaults(relaunch_stalled=False)
    ap.add_argument("--boxx", default="420")
    ap.add_argument("--boxy", default="161",
                    help="固定盒 Y 上界。⚠️ 必须与启动器一致：guard 的整批重启会把它"
                         "透传给 _delayed_launch.py / contract_launch.py，不一致会让"
                         "空气域口径在重启后静默变化。")
    ap.add_argument("--no-sweep", action="store_true",
                    help="跳过 AEDT 孤儿暂存回收")
    ap.add_argument("--sweep-min", type=float, default=120.0,
                    help="暂存工程静置多少分钟才算孤儿（默认 120）")
    ap.add_argument("--sweep-all", action="store_true",
                    help="忽略静置阈值，回收所有未被占用的暂存工程（首次大扫除用）")
    args = ap.parse_args()
    ROOT, B = args.root, args.batch

    logf = os.path.join(ROOT, "%s_guard.log" % B)

    def log(m):
        s = "%s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), m)
        print(s, flush=True)
        with open(logf, "a", encoding="utf-8") as f:
            f.write(s + "\n")

    # ---- 采集现状 ----
    # 注意：CPU 存活基线在下面"实时 CPU 探针"那一节取（需要 ROOT/B 已就位）。
    # 一次调用同时取 AEDT 进程数与 ANSYS 全家族驻留内存。
    # 注意：只统计 ansysedt 会严重少报 —— 实测网格器子进程 3dnms(5 个 8.6 GB)
    # 与 G3dMesher(3 个 3.4 GB) 合计 ≈12 GB，接近 GUI 进程(6.7 GB)的两倍。
    # 注意：PowerShell 的 -f 是 .NET String.Format，用 {0}/{1:F2}，不是 C 的 %d/%.2f
    aedt_stat = sh(
        "$a=Get-Process -Name ansysedt,3dnms,G3dMesher,ansyscl -ErrorAction SilentlyContinue; "
        "$e=@($a | Where-Object { $_.ProcessName -eq 'ansysedt' }); "
        "'{0}|{1:F2}|{2:F2}' -f $e.Count, "
        "((($a|Measure-Object -Property WorkingSet64 -Sum).Sum)/1GB), "
        "((($e|Measure-Object -Property WorkingSet64 -Sum).Sum)/1GB)")
    _parts = aedt_stat.split("|")
    if len(_parts) == 3:
        n_aedt, fam_gb, gui_gb = _parts
    else:                              # 查询异常时退回旧行为，别打断健康检查
        n_aedt, fam_gb, gui_gb = aedt_stat, "?", "?"
    try:
        ansys_rss, aedt_rss = float(fam_gb), float(gui_gb)
    except (TypeError, ValueError):
        ansys_rss = aedt_rss = float("nan")
    # ⚠️ 2026-10-12：进程计数必须**按本批次的脚本目录**过滤。原版只匹配
    # 'contract_worker' / 'contract_launch'，是**全机口径** —— b1 与 b2 同时在跑时
    # 两边的 worker/aedt 数会互相串（也会把恢复动作打到另一批次上）。
    _me_w = os.path.join(HERE, "contract_worker.py")
    _me_l = os.path.join(HERE, "contract_launch.py")
    n_worker = sh("(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                  "Where-Object { $_.CommandLine -like '*%s*' } | Measure-Object).Count" % _me_w)
    n_launch = sh("(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                  "Where-Object { $_.CommandLine -like '*%s*' } | Measure-Object).Count" % _me_l)
    # ⚠️ 启动器是**长期存活**的：contract_launch.py 末尾 `for k,p in enumerate(procs): p.wait()`
    # 会等 8 个 worker 全部结束才退出，即整个批次期间它一直在（实测跑了 24 h 仍未退）。
    # 所以「启动器存在」**不能**用来判断"重启正在进行" —— 那样会永久阻止所有重启。
    # 只有**刚启动的**启动器才代表重启窗口。
    # ⚠️ 2026-10-12 追加：整批重启现在先经 _delayed_launch.py 等 240 s，那段时间里
    # **根本没有 contract_launch 进程** —— 原查询返回 ''，重启闸门据此判"重启不在进行"
    # → 30 min 后再杀一轮正在启动的 worker（实测第一轮就是这样出现 3 个启动器互杀）。
    # 故查询必须把 _delayed_launch.py 一并算进来（取两者中最新那个的年龄）。
    launch_age_min = sh("$p=Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
                        "Where-Object { $_.CommandLine -like '*%s*' -and "
                        "$_.CommandLine -match 'contract_launch|_delayed_launch' }; "
                        "if ($p) { [math]::Round(((Get-Date) - "
                        "($p | Sort-Object CreationDate -Descending | Select-Object -First 1).CreationDate)"
                        ".TotalMinutes, 1) } else { '' }" % HERE)
    raws = sorted(glob.glob(os.path.join(ROOT, "%s_raw_run*.csv" % B)))
    pts = 0
    ages = {}
    for p in raws:
        run = os.path.basename(p).split("run")[-1].split(".")[0]
        with open(p, newline="", encoding="utf-8") as f:
            pts += max(0, sum(1 for _ in f) - 1)
        # ⚠️ 不能只看 raw 落盘时间：worker 重启后的【启动补偿】阶段会连续重解若干缺点工况
        # （每点 BASE 口径可达 ~20 min），这期间**合法地不写 raw**；几何重建+网格本身也
        # 常超过 45 min。只看 raw 会把"正在干活"误判成失速。
        # 2026-09-21 实测：8 个 worker 全在跑启动补偿、run7 21 秒前还在写日志，guard 却报
        # 「整体失速」——若无第 281 行的重启闸门，就会把正在跑的批次整个杀掉重启（死循环）。
        # 故取「raw 落盘」与「worker 日志写入」两者中较新的作为活跃度。
        a_raw = time.time() - os.path.getmtime(p)
        lg = os.path.join(ROOT, "%s_worker_run%s.log" % (B, run))
        a_log = (time.time() - os.path.getmtime(lg)) if os.path.exists(lg) else a_raw
        ages[run] = min(a_raw, a_log) / 60.0
    plan = list(csv.DictReader(open(os.path.join(ROOT, "%s_plan.csv" % B), encoding="utf-8-sig")))
    total_pts = 21 * len(plan)

    log("健康检查：AEDT %s/%d，worker %s/%d，launcher %s；点位 %d/%d (%.1f%%)"
        % (n_aedt, args.n, n_worker, args.n, n_launch, pts, total_pts,
           100.0 * pts / max(total_pts, 1)))

    # ---- 资源趋势 ----
    # 3.8 天长跑最怕缓慢泄漏，而单点快照看不出趋势。这里每轮记一行，
    # 30 min 粒度攒出完整历史；内存/提交量越线会显式报警。
    mt, ma, cl, ca = mem_info()
    try:
        dfree = shutil.disk_usage("C:\\").free / 2 ** 30
    except OSError:
        dfree = float("nan")
    if mt is not None:
        alarm = ""
        if ma < MEM_ALERT_GB:
            alarm += "  !! 可用<%.0fGB" % MEM_ALERT_GB
        if cl and (cl - ca) / cl >= MEM_COMMIT_ALERT_PCT / 100.0:
            alarm += "  !! 提交>%.0f%%" % MEM_COMMIT_ALERT_PCT
        if dfree == dfree and dfree < DISK_ALERT_GB:
            alarm += "  !! 磁盘<%.0fGB（页面文件将长不动→求解器OOM）" % DISK_ALERT_GB
        log("资源：内存 总%.1f/可用%.1f GB；提交 %.1f/%.1f GB (%.1f%%)%s；"
            "C: 可用%.1f GB；ANSYS 合计 %.2f GB（其中 ansysedt %.2f GB）"
            % (mt, ma, cl - ca, cl, 100.0 * (cl - ca) / cl if cl else 0.0, alarm,
               dfree, ansys_rss, aedt_rss))

    # ---- 已完工实例识别（2026-09-24 新增）----
    # worker 干完自己那 32 个工况后会**正常退出**，此后该实例既无日志更新也无新点，
    # 会被失速判据长期误报，guard 还会反复尝试"外科恢复"它（每次都因无 lock 而失败，
    # 刷满日志）。实测 run0/run3 完工后就是这样。这里按分片计算"该实例是否还有缺点工况"，
    # 已完工的直接从失速判据里摘掉。
    # 例外表里的**已登记缺口点**（跨多轮重试确认不可解）必须计入"完工"：
    # 否则这些实例永远被判成"还有活没干完"，guard 会无限重启整批。
    # 2026-10-12 第二轮启动前修正。
    registered_gaps = set()
    exceptions_unreadable = False
    _ex = os.path.join(ROOT, "%s_partial_exceptions.json" % B)
    if os.path.exists(_ex):
        try:
            import json as _json
            # ⚠️ 必须用 utf-8-sig：PowerShell 的 `Set-Content -Encoding utf8`（PS 5.1）
            # 和记事本另存都会写 BOM，而 json.load(utf-8) 遇到 BOM 直接抛
            # JSONDecodeError —— 2026-10-12 实测踩到。BOM 一出现，例外表就读不到，
            # 已登记缺口会被当成"还没跑完"，于是 guard 又去重启已完工的批次。
            with open(_ex, encoding="utf-8-sig") as _f:
                _d = _json.load(_f)
            for _c, _v in (_d.get("cases") or {}).items():
                for _i in (_v.get("missing_points") or []):
                    registered_gaps.add((_c, int(_i)))
            log("例外表：%d 个已登记缺口点不计入「未完工」判据" % len(registered_gaps))
        except Exception as e:
            # ⚠️ 读不出来**不能**静默降级成"没有缺口"：那会让完工批次被判"已死"并重启。
            # 这里显式置位，后面的重启闸门会因此拒绝动作，等人工看一眼。
            exceptions_unreadable = True
            log("!! 例外表解析失败：%r" % (e,))
            log("   —— 本文件存在但读不出来，本轮**禁止**整批重启（避免把已完工批次"
                "当成「已死」反复重启）。请修好 %s 后复查。" % _ex)

    # 契约点数：半扫 21 点/工况（镜像展开只影响 curves，raw 仍是 21 行）
    N_PTS = 21
    finished = set()
    try:
        for _k in range(args.n):
            _sh = os.path.join(ROOT, "%s_plan_shard%d.csv" % (B, _k))
            _rw = os.path.join(ROOT, "%s_raw_run%d.csv" % (B, _k))
            if not os.path.exists(_sh):
                finished.add(str(_k))        # 该实例没有分片（--n 大于分片数）→ 无活可干
                continue
            if not os.path.exists(_rw):
                continue
            _need = [r["case_id"] for r in csv.DictReader(open(_sh, encoding="utf-8-sig"))]
            _have = {}
            # ⚠️ utf-8-sig：防止 BOM 让首列名变成 "\ufeffcase_id" 而全部取不到
            # （取不到 → 每个工况都当"没跑过" → 完工批次被判已死 → 无限重启）。
            for _r in csv.DictReader(open(_rw, encoding="utf-8-sig")):
                _have.setdefault(_r.get("case_id"), set()).add(_r.get("i"))
            _ok = True
            for _c in _need:
                _got = _have.get(_c, set())
                _miss = [i for i in range(N_PTS) if str(i) not in _got]
                if _miss and not all((_c, i) in registered_gaps for i in _miss):
                    _ok = False
                    break
            if _ok:
                finished.add(str(_k))
        if finished:
            log("已完工实例（分片内工况满点，或所缺点已在例外表登记）：%s —— 其失速/缺 worker 不计入判据"
                % sorted(finished))
            for _k in finished:
                ages.pop(_k, None)
    except Exception as e:
        log("已完工实例识别跳过：%r" % (e,))

    # ---- 网格器崩溃率（点失败主因，见 mesher_crashes 文档串）----
    c60, c24 = mesher_crashes()
    try:
        hot = int(c60) >= MESHER_CRASH_ALERT_PER_HR
    except (TypeError, ValueError):
        hot = False
    log("网格器：近 60 min 崩溃 %s 次，近 24 h %s 次（3dnms.exe，点失败主因）%s"
        % (c60, c24, "  !! 崩溃率偏高" if hot else ""))

    # ---- 实时 CPU 探针：识别"哑会话"（两趟采样）----
    # 2026-09-23 事故判据：僵死会话的日志年龄/进程存在性/历史平均 CPU 都会骗人，
    # 唯一可靠信号是两次采样间 CPU 时间不增长。实测僵死实例 0.1~0.2 核，健康 1~56 核。
    # ⚠️ 必须放在下面「失速判定 + 外科恢复」**之前**：它会把确认僵死的实例并进 ages，
    # 而恢复逻辑要读 _idle 走更短的阈值（顺序反了会 UnboundLocalError，本次踩过）。
    _idle = {}
    try:
        _fam_a = family_cpu_seconds()            # 全家族基线（见函数注释：干活的是子进程）
        _cpu_a = aedt_cpu_map(ROOT, B)           # 第一趟基线
        time.sleep(12)                           # 攒采样窗口
        _cpu_b = aedt_cpu_map(ROOT, B)
        _fam_b = family_cpu_seconds()
        _pids = aedt_pid_by_instance(ROOT, B)
        # ⚠️ 两个数任意一个取不到 → 视为"有活动"，即**不允许**判僵死。
        # 理由：误杀一个正在求解的健康实例（点位未落盘、白烧 10~30 min，甚至永远解不完）
        # 的代价，远大于晚一轮（30 min）发现真僵死。见 CPU_IDLE_LOG_MIN 注释。
        if _fam_a != _fam_a or _fam_b != _fam_b:
            _fam_moved = 1.0
            log("CPU 探针：全家族 CPU 取不到 -> 本轮不做僵死判定（宁可漏报，不可误杀）")
        else:
            _fam_moved = _fam_b - _fam_a
        # ⚠️ 负增量是**无效测量**：12 秒窗口里有 3dnms/ansyscl 子进程退出，总和自然会变小。
        # 实测就抓到过 -47.8 秒（批次启动阶段子进程频繁生灭）。负值若直接过 `< 1.0` 这一关，
        # 会反过来被当成"家族没在动" → 又回到误杀。故负值一律按"测量无效、不许判僵死"处理。
        _fam_valid = (_fam_moved == _fam_moved) and _fam_moved >= 0.0
        if not _fam_valid:
            # 先把原始值写进日志再改写：否则日志里只留一个被清洗成 1.0 的数，
            # 28 天后回看会分不清"真的只用了 1 秒"还是"测量无效"。
            log("CPU 探针：全家族 CPU 增量 %.1f 秒（负/无效，子进程生灭）-> 本轮不做僵死判定"
                % _fam_moved)
            _fam_moved = 1.0
        for _k, _c in _cpu_b.items():
            _d = _c - _cpu_a.get(_k, _c)
            if (_k in _pids and _d < 1.0 and _fam_moved < 1.0
                    and ages.get(_k, 0.0) > CPU_IDLE_LOG_MIN):
                _idle[_k] = _d
        if _pids:
            log("CPU 探针：8 实例增量 %s；全家族 12 秒共 %.1f 秒 CPU"
                % (" ".join("run%s=%.1f核" % (_k, (_cpu_b.get(_k, 0.0) - _cpu_a.get(_k, 0.0)) / 12.0)
                            for _k in sorted(_pids, key=int)), _fam_moved))
        if _idle:
            log("!! CPU 探针：%s 静默（<1 核）且全家族无活动、日志 >%.0f min 未更新 —— "
                "判为会话僵死，无需再等满落盘失速阈值" % (sorted(_idle), CPU_IDLE_LOG_MIN))
            for _k in _idle:
                ages[_k] = max(ages.get(_k, 0.0), args.stall_min + 1e-6)
    except Exception as e:
        log("CPU 探针跳过：%r" % (e,))

    stall = [r for r, a in ages.items() if a > args.stall_min]
    for r in sorted(ages, key=lambda z: -ages[z]):
        log("   run%-2s 最后落盘 %6.1f 分钟前 %s" % (r, ages[r],
                                                 "OK" if ages[r] <= args.stall_min else "!! 失速"))

    # ---- 逐实例外科恢复（须在下面的整批重启之前；否则先整批重启就轮不到它）----
    stalled_now = []
    if args.relaunch_stalled and stall:
        # 探针已确认僵死的实例用更短阈值（证据更强）；其余仍用保守阈值防误杀长点。
        deep = []
        for r in stall:
            if r in _relaunched:
                continue
            if r in _idle and ages[r] > RELAUNCH_CONFIRMED_MIN:
                deep.append(r)
            elif ages[r] > args.relaunch_stall_min:
                deep.append(r)
        if len(stall) >= args.relaunch_min_stalled and deep:
            for r in sorted(deep, key=lambda z: -ages[z]):
                ok, msg = relaunch_one(int(r), ROOT, B, args.boxx, args.boxy)
                if ok:
                    _relaunched.add(r)
                    stalled_now.append(r)
                log("外科恢复 run%s（失速 %.0f min）：%s" % (r, ages[r], msg))
            log("已外科恢复 %d 个实例：%s（仅杀各自 worker+AEDT，未动健康实例）"
                % (len(stalled_now), stalled_now))
        elif deep:
            log("!! %d 个实例失速超过 %.0f min，但失速总数 %d < %d —— 按原设计只报告"
                % (len(deep), args.relaunch_stall_min, len(stall), args.relaunch_min_stalled))

    # ---- AEDT 孤儿暂存回收 ----
    # 每次「失败→重启会话重试」都会在暂存区留下一个 ~250 MB 的 maxwell_*.pjt
    # 目录且不会自动回收（实测 2026-09-19 批次 ~6 GB/天，4 天白占 ~24 GB）。
    # 回收判据为「静置超时 + 目录内无文件被独占持有」双条件，不会误伤运行中的会话；
    # 细节见 b2_disk.py。回收失败绝不影响健康检查。
    if not args.no_sweep:
        try:
            if HERE not in sys.path:
                sys.path.insert(0, HERE)
            import b2_disk
            b2_disk.sweep(min_age_min=(0.0 if args.sweep_all else args.sweep_min),
                          log=log)
        except Exception as e:
            log("暂存回收：跳过（%r）" % (e,))

    # ---- 判定 ----
    # 注意：AEDT 进程数不能作为"死亡"判据 —— worker 在失败重试时会主动杀掉自己的
    # AEDT 再重开（实测会瞬间出现 7/8），此时其余实例仍在正常出点（2026-09-19 误报一次）。
    # 真正的死亡判据：worker 数不足，或**所有**实例的落盘都超过失速阈值。
    #
    # ⚠️ 2026-09-24 修正：原判据是 `worker < args.n`（即少于 8 个就算死）。这在只掉
    # 1~2 个 worker 时是**误判**：那些 worker 可能刚收工退出、或正在重开会话，而其余
    # 实例仍在正常出点。实测 18:32 那轮 7/8 却点了整批重启，白扔 7 个健康实例的
    # 几何重建（每个 7~10 min）。改为「**多数** worker 都不在」才判整批已死；
    # 少量缺口交给逐实例外科恢复与下一轮复查。
    # 已完工实例不该被算作"缺 worker"：run0/run3 干完自己的分片后正常退出是**预期行为**，
    # 若把它算作缺口，就会误判整批已死并重启（2026-09-24 实测两次）。
    #
    # ⚠️ 2026-10-12 修（第二轮启动前）：上面那条修得**不彻底** —— `live_expected` 用了
    # `max(1, ...)`，于是 8/8 全部完工时算出 live_expected=1、need_workers 仍是 4，
    # worker=0 < 4 → dead=True → **对已完工批次每 30 分钟做一次无谓整批重启**
    # （实测 b1 跑完后已累计 841 次，每次复制 8 份 12.1 MB 工程副本 + 清 .aedtresults，
    # 并把 b1 目录的时间戳/日志不断刷脏）。
    # 正确判据：**先算"还剩几个实例有活要干"**，它为 0 就是"正常收工"，不是"已死"。
    try:
        live_expected = max(0, args.n - len(finished))
    except (TypeError, ValueError):
        live_expected = args.n
    if live_expected == 0:
        need_workers = 0
    else:
        need_workers = max(1, (live_expected + 1) // 2)
        try:
            if int(n_worker) < max(1, (args.n + 1) // 2):
                log("说明：worker %s 少于 %d，但已完工实例 %s 不计入 —— 按存活实例数判定为正常"
                    % (n_worker, args.n, sorted(finished)))
        except (TypeError, ValueError):
            pass
    dead = False
    # ⚠️ 2026-10-12：**必须区分"确实 0 个 worker"与"数不出来"**。
    # sh() 在 PowerShell 超时/抖动时返回 "ERR:..."，原代码 int() 抛 ValueError 后
    # 直接 `dead = True`（"按已死处理"）→ 带 --restart 时就会把一个**健康批次**
    # 整批杀掉重启。28 天的批次里这种抖动必然会遇到。故改为：数不出来就不做死亡判定，
    # 只报警、等下一轮（30 min 后）复核。
    n_worker_known = False
    try:
        n_worker_i = int(str(n_worker).strip())
        n_worker_known = True
    except (TypeError, ValueError):
        n_worker_i = -1
        log("!! worker 计数取不到（返回 %r）—— 本轮**不做**死亡判定，等下一轮复核；"
            "绝不因「数不出来」就重启整批" % (n_worker,))
    if n_worker_known and n_worker_i < need_workers:
        dead = True
    all_stalled = bool(ages) and min(ages.values()) > args.stall_min
    # 外科恢复生效时**抑制整批重启**：已把僵死实例逐个换掉，没必要再打断健康的。
    # 留到下一轮（30 min 后）再看——届时若它们仍失速，下面的整批判据自然接管。
    if stalled_now:
        all_stalled = False
        dead = False
        log("本轮已外科恢复 %s，抑制整批重启（下一轮复查）" % stalled_now)
    # 内存耗尽自救：提交量越线 + 多数实例失速。**不能只靠 all_stalled** ——
    # 内存耗尽时实例是"陆续"冻死的，只要剩下一个幸运实例在出点，all_stalled 永不成立
    # （2026-09-22：7 个实例停 6.5 小时，run4 一个撑住了判据，guard 全程未救）。
    commit_pct = 0.0
    if cl:
        commit_pct = 100.0 * (cl - ca) / cl
    mem_bloat = (commit_pct >= MEM_EXHAUST_RESTART_PCT
                 and len(stall) >= MEM_EXHAUST_MIN_STALLED)
    # ⚠️ 例外表读不出来时**一律不动作**：此时"完工/未完工"的判定不可信，
    # 贸然整批重启会把一个可能已经跑完的批次反复重启（第一轮 841 次事故的同型风险）。
    if exceptions_unreadable:
        dead = all_stalled = mem_bloat = False
        log("!! 例外表不可读 -> 本轮抑制整批重启，等人工修好 %s_partial_exceptions.json"
            % B)
    try:
        if int(n_aedt) < args.n:
            log("注意：AEDT 进程 %s/%d（可能是某实例正在重启会话，属正常；"
                "若持续 >15 分钟需人工查看）" % (n_aedt, args.n))
    except ValueError:
        pass
    # ---- 上一次重启到底生效了没有？（2026-10-13 事故后的新增防线）----
    # 事故：guard 每 30 min 重启一轮，日志写满「执行重启（断点续跑）…」，
    # 看起来在自愈；而实际上每个 worker 都在 2.5 分钟内失败退出（会话 0 起不来 GUI 版 AEDT），
    # 白停 7 小时。**"重启动作执行了" ≠ "实例真的起来了"**，必须显式核对。
    _mk = os.path.join(ROOT, "%s_restart_pending.txt" % B)
    if os.path.exists(_mk):
        try:
            _age = (time.time() - os.path.getmtime(_mk)) / 60.0
        except OSError:
            _age = 0.0
        try:
            _nw = int(str(n_worker).strip())
        except (TypeError, ValueError):
            _nw = -1
        if _nw >= max(1, need_workers):
            os.remove(_mk)
            log("上次重启已生效（worker %d/%d，历经 %.1f 分钟）—— 清除待核对标记"
                % (_nw, args.n, _age))
        elif _age > 20.0:
            log("!! 上次重启**未生效**：已过 %.1f 分钟，worker 仍只有 %s/%d —— "
                "不要再盲目重启，先查会话类型/授权/残留进程（见 %s_stdout_K.txt）"
                % (_age, n_worker, args.n, B))
    # ---- 判定 ----
    if exceptions_unreadable:
        log("判定：本轮已抑制（例外表不可读，完工判定不可信）—— **不是**「健康」，需人工处理")
    elif live_expected == 0:
        log("判定：批次已全部完工（%d/%d 实例无待解工况；例外表已登记缺口 %d 点）"
            "—— 不重启，这是正常收工" % (len(finished), args.n, len(registered_gaps)))
    elif dead:
        log("!! 判定：批次已死（worker 数 %s/%d，低于半数线 %d；未完工实例 %d 个）"
            % (n_worker, args.n, need_workers, live_expected))
    elif all_stalled:
        log("!! 判定：整体失速（所有实例 >%.0f 分钟无新点）" % args.stall_min)
    elif mem_bloat:
        log("!! 判定：内存耗尽（提交 %.1f%% ≥ %.0f%% 且 %d/%d 实例失速）—— "
            "会话内存膨胀压爆页面文件，实例已陆续冻死，需重启释放"
            % (commit_pct, MEM_EXHAUST_RESTART_PCT, len(stall), args.n))
    elif stall:
        log("!! 注意：%s 失速，其余实例正常 —— 不重启整批，请查该实例的 "
            "%s_worker_run<K>.log 与 %s_stdout_<K>.txt" % (stall, B, B))
    else:
        log("判定：健康 ✓")

    # ---- 重启闸门 ----
    # ⚠️ 防"重启循环"：启动器按 20 s 错峰起 8 个实例，全程 ~2.5 分钟。在这段时间里
    # worker 数还没到 8，若 guard 恰好在此窗口内再跑一次，就会把**正在启动**的实例
    # 又杀掉、重新拉起 —— 无限循环，批次永远起不满。
    # 2026-09-21 给计划任务加 --restart 时才发现这个隐患（30 min 周期虽不易撞上，
    # 但一旦撞上就是静默的死循环），故用"启动器已在运行"作为重启闸门。
    if args.restart and (dead or all_stalled or mem_bloat):
        try:
            restarting = float(launch_age_min) < LAUNCH_GRACE_MIN
        except (TypeError, ValueError):
            restarting = False      # 查不到启动器年龄 -> 不拦（宁可重启，也别永远不动作）
        if restarting:
            log("!! 需要重启，但启动器 %.1f 分钟前才启动（< %.0f min），判定为「重启进行中」"
                "→ 跳过，避免杀掉正在启动的实例。等下一轮（30 min 后）复查。"
                % (float(launch_age_min), LAUNCH_GRACE_MIN))
        else:
            log("执行重启（断点续跑）…")
            # ⚠️ 必须连**求解器/网格器子进程**一起杀：只杀 ansysedt 会留下
            # 3dnms / G3dMesher / ansyscl 孤儿，它们处于半死状态会让新会话起不来。
            # 实测 2026-09-24 两次整批重启全灭（`Failed to start new AEDT gRPC
            # session on port ...` × 6），根因就是上一次重启留下的这些孤儿；
            # 它们不会立刻退出而是慢慢老死，所以"隔一阵再重启就好了"——正是这个坑的伪装。
            sh("Get-Process -Name ansysedt,3dnms,G3dMesher,ansyscl -ErrorAction SilentlyContinue | "
               "Stop-Process -Force")
            # ⚠️ 2026-10-12：python 侧必须**按本批次脚本目录过滤**。原版正则
            # 'contract_(worker|launch)' 是全机的 —— 一次 b2 的重启会把 b1 的 worker 也杀掉。
            # 同时补上原版漏掉的 _delayed_launch.py / _relaunch_one.py：它们不匹配
            # 'contract_(worker|launch)'，会在杀完之后自行拉起第二个启动器（双链并起 →
            # 同一 run K 出现两个 worker 同时 append 同一个 raw CSV → 重复点，交付闸门判致命）。
            sh("Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
               "Where-Object { $_.CommandLine -like '*%s*' -and "
               "$_.CommandLine -match 'contract_(worker|launch)|_delayed_launch|_relaunch_one' } | "
               "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" % HERE)
            # 2026-09-24 追加：杀完不能立刻起 —— AEDT 强杀后有约 3~5 分钟的
            # 退出/清理窗口，窗口内新建会话必然失败（实测两次整批重启全灭：
            # `Failed to start new AEDT gRPC session on port ...` × 6/8），
            # 而"杀完等几分钟再起"则 100% 成功。原 time.sleep(5) 远远不够；
            # 这里改调 _delayed_launch.py（detached，等够 240 s 再拉起，
            # 且只要 AEDT 全家族退净就可提前结束等待），避免 guard 自己阻塞 4 分钟。
            for p in glob.glob(os.path.join(ROOT, "Projecttonight_%s_run*.aedt.lock" % B)):
                try:
                    os.remove(p)
                except Exception:
                    pass
            dl = os.path.join(HERE, "_delayed_launch.py")
            if os.path.exists(dl):
                cmd = [PY, dl, "240", str(args.n), B, ROOT, str(args.boxx), str(args.boxy)]
            else:                                   # 兜底：没有延迟启动器就走老路
                cmd = [PY, os.path.join(HERE, "contract_launch.py"), str(args.n),
                       "--batch", B, "--root", ROOT, "--boxx", args.boxx,
                       "--boxy", str(args.boxy), "--merge"]
            p = subprocess.Popen(cmd, cwd=HERE, stdout=open(os.path.join(ROOT, "%s_guard_launch.log" % B), "w"),
                                 stderr=subprocess.STDOUT)
            log("已拉起启动器 pid=%d" % p.pid)
            # 留一个"待核对"标记：下一轮巡检必须确认 worker 真的起来了，否则明确报
            # 「上次重启未生效」。2026-10-13 那次事故里，日志写满了"执行重启"却全是无效动作。
            try:
                with open(os.path.join(ROOT, "%s_restart_pending.txt" % B), "w",
                          encoding="utf-8") as _f:
                    _f.write("%s 发起重启（pid=%d）\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), p.pid))
            except OSError as e:
                log("（写待核对标记失败：%r，不影响重启）" % (e,))
    elif args.restart:
        log("无需重启")


if __name__ == "__main__":
    main()
