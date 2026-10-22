# -*- coding: utf-8 -*-
"""
抓取正在运行的 AEDT 窗口画面（只读操作，不干扰批次求解）。

策略：
  1) 优先 PrintWindow(PW_RENDERFULLCONTENT) —— 不改焦点、不置顶，最无侵入；
  2) 若抓到的图是黑屏/全白，回退到"置顶 + 屏幕 BitBlt"。

用法：
  python capture_aedt_windows.py --out <dir> [--pid 26084] [--raise]
"""
import argparse
import ctypes
import os
import sys
import time
from ctypes import wintypes

OUT_DEFAULT = r"C:\ansys maxwell2024\_work\case_figures"

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

PW_RENDERFULLCONTENT = 0x00000002
SW_RESTORE = 9
SRCCOPY = 0x00CC0020

user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.PrintWindow.restype = wintypes.BOOL
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                         ctypes.c_int, wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]


def list_aedt_windows():
    """返回 [(pid, hwnd, title)]，按 pid 排序。"""
    import subprocess
    ps = (
        "Get-Process ansysedt -ErrorAction SilentlyContinue | "
        "ForEach-Object { \"$($_.Id)|$($_.MainWindowHandle)|$($_.MainWindowTitle)\" }"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                         capture_output=True, text=True).stdout
    rows = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        pid, hwnd, title = line.split("|", 2)
        if hwnd.strip() in ("", "0"):
            continue
        rows.append((int(pid), int(hwnd), title.strip()))
    rows.sort()
    return rows


def capture_hwnd(hwnd, use_printwindow=True):
    """返回 PIL.Image 或 None。"""
    from PIL import Image
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.8)
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None

    hdc_win = user32.GetWindowDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_win)
    hbm = gdi32.CreateCompatibleBitmap(hdc_win, w, h)
    gdi32.SelectObject(hdc_mem, hbm)
    try:
        if use_printwindow:
            ok = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)
            if not ok:
                gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_win, 0, 0, SRCCOPY)
        else:
            gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_win, 0, 0, SRCCOPY)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                        ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                        ("biClrImportant", wintypes.DWORD)]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h          # top-down
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
        return img
    finally:
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hwnd, hdc_win)


def looks_blank(img):
    """粗略判断是否黑屏/纯色。"""
    small = img.resize((48, 27))
    px = list(small.getdata())
    avg = sum(sum(p) / 3 for p in px) / len(px)
    var = sum((sum(p) / 3 - avg) ** 2 for p in px) / len(px)
    return avg < 12 or var < 3.0, avg, var


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--tag", default="aedt")
    ap.add_argument("--pid", type=int, default=None)
    ap.add_argument("--foreground", action="store_true",
                    help="置顶窗口后用屏幕拷贝（会在前台短暂切换焦点）")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    wins = list_aedt_windows()
    if args.pid:
        wins = [w for w in wins if w[0] == args.pid]
    if not args.all:
        wins = wins[:1]
    if not wins:
        print("没有找到 AEDT 窗口")
        return 1

    for pid, hwnd, title in wins:
        run_name = "unknown"
        for tok in title.split("-"):
            tok = tok.strip()
            if tok.startswith("Projecttonight_b1_run"):
                run_name = tok.replace("Projecttonight_b1_", "")
                break
        if args.foreground:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            time.sleep(1.2)
        img = capture_hwnd(hwnd, use_printwindow=not args.foreground)
        if img is None:
            print("PID %d 抓取失败" % pid)
            continue
        blank, avg, var = looks_blank(img)
        path = os.path.join(args.out, "%s_%s_pid%d.png" % (args.tag, run_name, pid))
        img.save(path)
        print("%s  size=%s  avg=%.1f var=%.1f %s" %
              (path, img.size, avg, var, "*** 疑似空屏 ***" if blank else "OK"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
