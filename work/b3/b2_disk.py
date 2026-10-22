# -*- coding: utf-8 -*-
r"""AEDT 暂存区孤儿工程回收。

背景
----
contract_worker 对求解失败的处置是「同会话切 BASE 口径重试 → 再失败则重启会话重试」。
每次重启会话，AEDT 都会在工作暂存区新建一个

    %LOCALAPPDATA%\Temp\<n>\maxwell_<host>_<pid>.pjt

工程目录（实测 9~345 MB，常见 ~250 MB）。**会话退出后该目录不会被回收**，于是整批跑
下来持续累积：2026-09-19 批次 8 实例跑 10 小时留下 15 个孤儿 ≈ 2.6 GB，约 6 GB/天，
4 天批次会白占 ~24 GB。批次本身的结果目录是稳定的（WPT_CLEAN=point 生效，~2 GB），
所以这部分是纯粹的泄漏。

安全回收判据（两条必须**同时**满足）
------------------------------------
1. 目录 mtime 距今 > ``min_age_min`` 分钟，默认 120 —— 覆盖实测最坏单点 61 min
   （含失败→BASE 重试→会话重启）的两倍余量。
2. 目录内**没有任何文件**被进程独占持有。用 ``CreateFileW(dwShareMode=0)`` 逐个探测，
   这是 Windows 上与 PowerShell ``FileShare.None`` 等价的强判据；活着的 AEDT 会话总
   持有其 .pjt 内的锁文件，必然探测为占用。

任一条件不满足即跳过，绝不强删。因此本模块对正在运行的批次是安全的。

被删除的只是求解过程的中间暂存；真值来源 ``b1_raw_run*.csv`` 与交付物 ``out\`` 不在
暂存区，不受影响。
"""
import ctypes
import glob
import os
import shutil
import sys
import time
from ctypes import wintypes

# stdout 被管道捕获时中文 Windows 默认 GBK：中文日志会抛 UnicodeEncodeError
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

GENERIC_READ = 0x80000000
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                             ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                             ctypes.c_void_p]
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.restype = wintypes.BOOL


def default_temp_root():
    return os.path.join(os.environ.get("LOCALAPPDATA", ""), "Temp")


def _held(path, is_dir=False):
    """独占打开成功 = 无人持有 = False；失败 = 被占用 = True。"""
    flags = FILE_FLAG_BACKUP_SEMANTICS if is_dir else 0
    h = _k32.CreateFileW(path, GENERIC_READ, 0, None, OPEN_EXISTING, flags, None)
    if not h or h == INVALID_HANDLE_VALUE:
        return True
    _k32.CloseHandle(h)
    return False


def is_in_use(path):
    """目录本身或其内任一文件被进程独占持有 → True。"""
    if _held(path, is_dir=True):
        return True
    for r, _d, fs in os.walk(path):
        for f in fs:
            if _held(os.path.join(r, f)):
                return True
    return False


def dir_mb(path):
    tot = 0
    for r, _d, fs in os.walk(path):
        for f in fs:
            try:
                tot += os.path.getsize(os.path.join(r, f))
            except OSError:
                pass
    return tot / 1048576.0


def _clear_ro(func, path, _exc):
    """rmtree 回调：清掉只读属性后重试（ANSYS 的安装/暂存残留常带只读位）。"""
    try:
        os.chmod(path, 0o700)
        func(path)
    except OSError:
        pass


def rmtree_force(path):
    """删除目录，失败时清只读位重试。返回是否真的删掉了。"""
    try:
        if sys.version_info >= (3, 12):
            shutil.rmtree(path, onexc=_clear_ro)
        else:
            shutil.rmtree(path, onerror=_clear_ro)
    except Exception:
        pass
    return not os.path.exists(path)


def find_orphans(temp_root=None, min_age_min=120.0):
    """返回 [(path, age_min, mb)]，按体积降序。"""
    temp_root = temp_root or default_temp_root()
    pats = [os.path.join(temp_root, "*", "maxwell_*"),
            os.path.join(temp_root, "maxwell_*")]
    out, seen, now = [], set(), time.time()
    for pat in pats:
        for p in glob.glob(pat):
            if not os.path.isdir(p):
                continue
            key = os.path.normcase(os.path.abspath(p))
            if key in seen:
                continue
            seen.add(key)
            try:
                age_min = (now - os.path.getmtime(p)) / 60.0
            except OSError:
                continue
            if age_min < min_age_min:
                continue
            out.append((p, age_min, dir_mb(p)))
    return sorted(out, key=lambda x: -x[2])


def sweep(temp_root=None, min_age_min=120.0, log=print):
    """回收孤儿暂存工程。返回 (删除数, 释放MB, 跳过数)。不抛异常。"""
    try:
        orphans = find_orphans(temp_root, min_age_min)
    except Exception as e:                                   # 枚举失败不影响批次
        log("暂存回收：枚举失败 %r" % (e,))
        return 0, 0.0, 0
    n = skipped = 0
    freed = 0.0
    for path, _age, mb in orphans:
        try:
            if is_in_use(path):
                skipped += 1
                continue
            if rmtree_force(path):
                n += 1
                freed += mb
            else:
                skipped += 1
        except Exception:
            skipped += 1
    if n or skipped:
        log("暂存回收：删除 %d 个 AEDT 孤儿暂存工程，释放 %.2f GB；"
            "跳过 %d 个（仍被占用）" % (n, freed / 1024.0, skipped))
    return n, freed, skipped


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="AEDT 暂存区孤儿工程回收")
    ap.add_argument("--temp-root", default=None)
    ap.add_argument("--min-age-min", type=float, default=120.0)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    orph = find_orphans(a.temp_root, a.min_age_min)
    if not orph:
        print("没有超过 %.0f 分钟的孤儿暂存工程。" % a.min_age_min)
        sys.exit(0)
    print("%-10s %8s  %-8s %s" % ("年龄min", "MB", "状态", "路径"))
    print("-" * 100)
    tot = skip = 0.0
    for p, age, mb in orph:
        if a.apply:
            if is_in_use(p):
                print("%-10.1f %8.1f  %-8s %s" % (age, mb, "占用跳过", p))
                skip += mb
            elif rmtree_force(p):
                print("%-10.1f %8.1f  %-8s %s" % (age, mb, "已删除", p))
                tot += mb
            else:
                print("%-10.1f %8.1f  %-8s %s" % (age, mb, "删除失败", p))
                skip += mb
        else:
            print("%-10.1f %8.1f  %-8s %s" % (age, mb, "可删", p))
            tot += mb
    print("-" * 100)
    print("%s %.2f GB；跳过 %.2f GB" % ("已释放" if a.apply else "可释放", tot / 1024.0, skip / 1024.0))
    if not a.apply:
        print("\n预演模式，加 --apply 实际删除。")
