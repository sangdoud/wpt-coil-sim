# -*- coding: utf-8 -*-
r"""batch1 磁盘定时清理 + 余量报警。

背景（2026-09-19 实测）
----------------------
C: 一天可用空间从 131.3 GB 掉到 111.9 GB，根因**不是仿真漏文件**，而是系统自动
管理的 `pagefile.sys` 在真实内存压力下膨胀到了 46 GB（8 实例 AEDT + 网格器，
提交量 66/77 GB）。页面文件本身没问题，但它是求解器提交内存的**最后兜底**：

    磁盘没空间 -> 页面文件长不动 -> 提交分配失败 -> 求解器 OOM 死

而且 OOM 死的症状会和《b1_失败签名诊断》里的 `3dnms.exe` 崩溃混在一起，极难区分。
2026-09-19 20:03 磁盘触底 111.9 GB 时，20:30/20:36 就各崩了一次 3dnms。
所以本脚本有两个职责：**回收可再生垃圾** + **在余量见底前报警**。

清理分级（这是脚本的核心设计，别改动分级逻辑）
--------------------------------------------
  A 类 AUTO   —— 可再生垃圾，到龄即删，出错也不影响批次：
                 · CrashDumps 里 >48h 的 3dnms 转储（根因已查明，每份 76.6 MB）
                 · 回收站 >24h
                 · Windows\Temp 里 >72h 的普通文件
                 · SoftwareDistribution\Download 里 >7d（避免打断正在下载的更新）
                 · 跨会话遗留的 maxwell_*.pjt 孤儿（复用 b2_disk.py 双判据）
  B 类 需 --big —— 一次性大件，**默认只报告不动手**：
                 · Windows.old（24.9 GB，升级备份已 122 天）
                 · ANSYS 安装介质 C:\ansys maxwell2024\1（21.8 GB）
                 · Downloads（1.4 GB）

安全护栏（宁可少删）
------------------
1. **绝不碰在跑的批次**：_work\b1 下的 raw CSV / out / *.aedtresults / 工程副本一律不在
   清理范围内；`contract_worker` / `ansysedt` 进程的文件被占用时删除必然失败，天然兜底。
2. **年龄阈值**：活跃会话的暂存（今天仍在写的 Temp\<n>）不会到龄。
3. **排除名**：Temp 清理跳过 `maxwell_*`（交给 b2_disk 的占用判据，避免误删在建工程）。
4. `--dry-run` 先看清单；`--big` 才动 B 类。

用法：
  python b1_clean.py --root C:\ansys maxwell2024\_work\b1            # 只做 A 类
  python b1_clean.py --root ... --dry-run                            # 只看清单
  python b1_clean.py --root ... --big                                # 连 B 类一起
退出码：0 = 正常；1 = 磁盘余量低于报警线（需人工关注）
"""
import argparse
import ctypes
import glob
import os
import shutil
import sys
import time

# stdout 为管道时中文 Windows 默认 GBK，中文报告会乱码。
# 计划任务不会设 PYTHONIOENCODING，故在入口强制切 UTF-8（与其他脚本一致）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

# 磁盘余量报警线（GB）。依据：pagefile.sys 当前实际占用 ~22 GB 且仍在增长，
# 8 份 .aedtresults 稳态 ~1.8 GB，BASE 尾巴阶段负载更重。
# 低于此线时页面文件可能长不动 -> 提交失败 -> 求解器 OOM（症状与 3dnms 崩溃混淆）。
DISK_ALERT_GB = 40.0

# 各 A 类清理项的到龄阈值（小时）
AGE_CRASHDUMP_H = 48
AGE_RECYCLE_H = 24
AGE_WINTEMP_H = 72
AGE_WU_DL_H = 24 * 7
AGE_STALE_TMP_H = 24 * 7

# Temp 清理的排除名（maxwell 工程交由 b2_disk 的"静置+占用"双判据处理）
TEMP_EXCLUDE_PREFIX = ("maxwell_",)


def _log_factory(logf):
    def log(m):
        s = "%s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), m)
        print(s, flush=True)
        if logf:
            try:
                with open(logf, "a", encoding="utf-8") as f:
                    f.write(s + "\n")
            except OSError:
                pass
    return log


def disk_free_gb(path="C:\\"):
    try:
        return shutil.disk_usage(path).free / 2 ** 30
    except OSError:
        return float("nan")


def mem_info():
    """(总物理, 可用物理, 提交上限, 提交可用) GB —— 与 b1_guard 同源，ctypes 直问内核。"""
    class _M(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    st = _M()
    st.dwLength = ctypes.sizeof(_M)
    try:
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return (None,) * 4
    except OSError:
        return (None,) * 4
    G = float(2 ** 30)
    return (st.ullTotalPhys / G, st.ullAvailPhys / G,
            st.ullTotalPageFile / G, st.ullAvailPageFile / G)


def pagefile_gb():
    """C:\\pagefile.sys 占用的磁盘（GB），拿不到返回 nan。

    纯诊断项：**清理与报警都不依赖它**（真正的判据是下面的磁盘可用量）。
    pagefile.sys 是系统文件，枚举看不到、CreateFileW 需要 SeBackupPrivilege，
    这里用 GetCompressedFileSizeW 试探；失败就如实报"不可读"，不猜。
    """
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCompressedFileSizeW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.GetCompressedFileSizeW.restype = ctypes.c_uint32
    hi = ctypes.c_ulong(0)
    ctypes.set_last_error(0)
    lo = kernel32.GetCompressedFileSizeW("C:\\pagefile.sys", ctypes.byref(hi))
    if lo == 0xFFFFFFFF and ctypes.get_last_error() != 0:
        return float("nan")
    return ((hi.value << 32) | lo) / 2 ** 30


def dir_size(path):
    t = 0
    for r, _d, fs in os.walk(path, onerror=lambda e: None):
        for f in fs:
            try:
                t += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return t


def age_hours(path):
    try:
        return (time.time() - os.path.getmtime(path)) / 3600.0
    except OSError:
        return -1.0


def path_size(path):
    try:
        return os.path.getsize(path) if os.path.isfile(path) else dir_size(path)
    except OSError:
        return 0


def kill(path, dry, log, label):
    """删除文件或目录。删除**成功**返回 True，失败/跳过返回 False（绝不抛）。

    调用方一律在删除前先用 path_size() 记账，避免"删掉了但算不出释放量"。
    """
    if dry:
        log("    [dry] 将删除 %s  %s (%.1f MB)" % (label, path, path_size(path) / 2 ** 20))
        return True
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=False)
        else:
            os.remove(path)
        log("    [删] %s  %s" % (label, path))
        return True
    except OSError as e:
        log("    [跳过] %s（被占用或权限不足：%s）" % (path, e.__class__.__name__))
        return False


# ---------------- A 类各项 ----------------

def clean_crashdumps(dry, log):
    """3dnms 崩溃转储。根因已查明（见《b1_失败签名诊断》第 8 节），
    留存价值只在近期取证，故只清 >48h 的，最近两天的保留。"""
    d = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CrashDumps")
    if not os.path.isdir(d):
        log("  CrashDumps：目录不存在，跳过")
        return 0
    freed = 0
    n = 0
    for f in sorted(glob.glob(os.path.join(d, "*.dmp"))):
        if age_hours(f) <= AGE_CRASHDUMP_H:
            continue
        sz = path_size(f)
        if kill(f, dry, log, "崩溃转储"):
            freed += sz
            n += 1
    log("  CrashDumps：>%dh 的转储 %d 份，合计 %.1f MB%s"
        % (AGE_CRASHDUMP_H, n, freed / 2 ** 20, "（dry-run 未删）" if dry else ""))
    return freed


def clean_recyclebin(dry, log):
    """回收站：只删 >24h 的项，避免删掉用户刚扔进去还想还原的东西。"""
    freed = 0
    n = 0
    rb = r"C:\$Recycle.Bin"
    if os.path.isdir(rb):
        for sid in os.listdir(rb):
            p = os.path.join(rb, sid)
            if not os.path.isdir(p):
                continue
            for item in os.listdir(p):
                fp = os.path.join(p, item)
                if age_hours(fp) <= AGE_RECYCLE_H:
                    continue
                sz = path_size(fp)
                if kill(fp, dry, log, "回收站"):
                    freed += sz
                    n += 1
    log("  回收站：>%dh 的项 %d 个，合计 %.1f MB%s"
        % (AGE_RECYCLE_H, n, freed / 2 ** 20, "（dry-run 未删）" if dry else ""))
    return freed


def _clean_dir_by_age(root, max_age_h, dry, log, label, exclude_prefix=()):
    """删 root 下 mtime 超过 max_age_h 的文件/目录（不递归做二次筛选）。"""
    if not os.path.isdir(root):
        log("  %s：目录不存在，跳过" % label)
        return 0
    freed = 0
    n = 0
    try:
        entries = os.listdir(root)
    except OSError as e:
        log("  %s：无法列出（%s）" % (label, e.__class__.__name__))
        return 0
    for name in entries:
        if exclude_prefix and name.startswith(exclude_prefix):
            continue
        p = os.path.join(root, name)
        if age_hours(p) <= max_age_h:
            continue
        sz = path_size(p)
        if kill(p, dry, log, label):
            freed += sz
            n += 1
    log("  %s：>%dh 的项 %d 个，合计 %.1f MB%s"
        % (label, max_age_h, n, freed / 2 ** 20, "（dry-run 未删）" if dry else ""))
    return freed


def clean_worker_orphans(dry, log, min_age_min=120.0):
    """复用 b2_disk.py 的「静置超时 + 无占用」双判据清 maxwell_*.pjt 孤儿。

    这是**唯一**会碰到批次暂存的清理项，所以刻意复用已验证的实现，
    而不是自己写一套新的匹配规则。
    """
    try:
        if HERE not in sys.path:
            sys.path.insert(0, HERE)
        import b2_disk
        orphans = b2_disk.find_orphans(min_age_min=min_age_min)
    except Exception as e:
        log("  暂存孤儿：跳过（%r）" % (e,))
        return 0
    freed = 0
    for p in orphans:
        sz = path_size(p)
        if dry:
            kill(p, dry, log, "暂存孤儿")
            freed += sz
            continue
        try:
            b2_disk.rmtree_force(p)
            log("    [删] 暂存孤儿  %s" % p)
            freed += sz
        except Exception as e:
            log("    [跳过] %s（%r）" % (p, e))
    log("  暂存孤儿（静置>%d min 且无占用）：%d 个，合计 %.1f MB%s"
        % (min_age_min, len(orphans), freed / 2 ** 20, "（dry-run 未删）" if dry else ""))
    return freed


def clean_wu_cache(dry, log):
    """Windows 更新下载缓存。**默认不做**，因为 Windows Update 服务持有这些文件时
    删除会打断正在下载的更新（历史教训：直接删 SoftwareDistribution 会损坏更新状态）。
    要清就先停服务，删完再起 —— 所以只放在 --wu-cache 显式开关后面。
    """
    import subprocess
    d = r"C:\Windows\SoftwareDistribution\Download"
    if not os.path.isdir(d):
        log("  更新缓存：目录不存在，跳过")
        return 0
    freed = 0
    n = 0
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if age_hours(p) <= AGE_WU_DL_H:
            continue
        sz = path_size(p)
        if not dry:
            subprocess.run(["net", "stop", "wuauserv"], capture_output=True)
            subprocess.run(["net", "stop", "bits"], capture_output=True)
        if kill(p, dry, log, "更新缓存"):
            freed += sz
            n += 1
        if not dry:
            subprocess.run(["net", "start", "bits"], capture_output=True)
            subprocess.run(["net", "start", "wuauserv"], capture_output=True)
    log("  更新缓存：>%dh 的项 %d 个，合计 %.1f MB%s"
        % (AGE_WU_DL_H, n, freed / 2 ** 20, "（dry-run 未删）" if dry else ""))
    return freed


# ---------------- B 类（一次性大件，默认只报告） ----------------

def report_big(dry, log, do_it):
    targets = [
        ("Windows.old（升级备份，已 122 天）", r"C:\Windows.old"),
        ("ANSYS 安装介质（ISO/帮助文档）", r"C:\ansys maxwell2024\1"),
        ("Downloads", os.path.join(os.environ.get("USERPROFILE", ""), "Downloads")),
    ]
    total = 0
    for label, p in targets:
        if not os.path.exists(p):
            continue
        sz = dir_size(p) if os.path.isdir(p) else os.path.getsize(p)
        total += sz
        if do_it:
            kill(p, dry, log, label)
            log("  B 类 %s：%s %.1f GB" % (label, "将删除" if dry else "已删", sz / 2 ** 30))
        else:
            log("  B 类 %-38s %7.2f GB  （需 --big 才动）" % (label, sz / 2 ** 30))
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=HERE)
    ap.add_argument("--batch", default="b2")
    ap.add_argument("--log", default=None)
    ap.add_argument("--dry-run", action="store_true", help="只列清单，不删任何东西")
    ap.add_argument("--big", action="store_true",
                    help="连 B 类大件一起删（Windows.old / 安装介质 / Downloads）")
    ap.add_argument("--wu-cache", action="store_true",
                    help="连 Windows 更新下载缓存一起清（会临时停 wuauserv/bits，默认不动）")
    ap.add_argument("--sweep-min", type=float, default=120.0,
                    help="maxwell 暂存孤儿静置阈值（分钟，默认 120）")
    a = ap.parse_args()

    logf = a.log or os.path.join(a.root, "%s_clean.log" % a.batch)
    log = _log_factory(logf)

    free0 = disk_free_gb()
    mt, ma, cl, ca = mem_info()
    pf = pagefile_gb()
    pf_s = "%.1f GB" % pf if pf == pf else "不可读"
    log("=" * 74)
    log("磁盘清理%s | C: 可用 %.1f GB | pagefile %s | 物理可用 %.1f GB | 提交 %.1f/%.1f GB"
        % ("（dry-run）" if a.dry_run else "", free0, pf_s,
           ma if ma else float("nan"),
           (cl - ca) if cl else float("nan"), cl if cl else float("nan")))

    log("-- A 类：可再生垃圾（自动清）--")
    freed = 0
    freed += clean_crashdumps(a.dry_run, log)
    freed += clean_recyclebin(a.dry_run, log)
    freed += _clean_dir_by_age(os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Temp"),
                               AGE_WINTEMP_H, a.dry_run, log, "Windows\\Temp")
    # 跨会话遗留的临时目录（今天仍在写的活跃会话目录不会到龄）
    freed += _clean_dir_by_age(os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp"),
                               AGE_STALE_TMP_H, a.dry_run, log, "用户 Temp 陈旧项",
                               exclude_prefix=TEMP_EXCLUDE_PREFIX)
    freed += clean_worker_orphans(a.dry_run, log, a.sweep_min)

    log("-- A2 类：需显式开关 --")
    if a.wu_cache:
        freed += clean_wu_cache(a.dry_run, log)
    else:
        d = r"C:\Windows\SoftwareDistribution\Download"
        n = len(os.listdir(d)) if os.path.isdir(d) else 0
        log("  更新缓存：%d 个项，%.1f MB —— 默认不动（需 --wu-cache；"
            "要停 wuauserv/bits，可能打断正在下载的更新）" % (n, dir_size(d) / 2 ** 20))

    log("-- B 类：一次性大件（需 --big）--")
    report_big(a.dry_run, log, a.big)

    free1 = disk_free_gb()
    log("A 类可回收（估算）%.2f GB；C: 可用 %.1f -> %.1f GB" % (freed / 2 ** 30, free0, free1))

    low = free1 < DISK_ALERT_GB
    if low:
        log("!! 磁盘可用 %.1f GB 低于报警线 %.0f GB —— 页面文件可能长不动，"
            "提交分配失败会让求解器 OOM（症状与 3dnms 崩溃混淆）。"
            "请清理或结束部分负载。" % (free1, DISK_ALERT_GB))
    else:
        log("判定：磁盘余量充足（%.1f GB >= %.0f GB）✓" % (free1, DISK_ALERT_GB))
    return 1 if low else 0


if __name__ == "__main__":
    sys.exit(main())
