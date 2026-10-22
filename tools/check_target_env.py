# -*- coding: utf-8 -*-
r"""目标机环境自检 —— 迁移到新设备后、启动批次前跑这一份。

与 preflight.py 的分工（**不重复、互补**）
----------------------------------------
  preflight.py         查「批次链路」：口径常量、参数表、母本工程、计划任务、磁盘/内存
  check_target_env.py  查「新机底座」：解释器、pyaedt、AEDT 安装与版本、**授权服务器连通性**、
                       新路径存在性、编码环境

为什么必须单独查授权
--------------------
源机是 `ANSYSLMD_LICENSE_FILE=1055@localhost`（本机授权）。迁到新机后改为**机构浮动
License Server**，这是本次迁移唯一"外部依赖"。没有席位，AEDT 连启动都做不到，
而报错信息通常只是含糊的 `CONNECT FAILED` —— 会浪费大量时间在错误的方向上排查。
所以这里把"能否拿到席位"变成一个**显式的、带证据的**检查项。

用法
----
    python check_target_env.py --site _site_config.json
    python check_target_env.py --site _site_config.json --json out.json
    python check_target_env.py --site _site_config.json --no-license-net

退出码：0=无 FAIL（可有 WARN）/ 1=存在 FAIL / 2=脚本自身异常
本脚本**只读**：不安装、不创建、不修改任何东西。
"""
import argparse
import ctypes
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

R = []

# ---------------------------------------------------------------------------
# 「生产在用组合」—— 2026-10-13 在源机上**实测**得到，不是文档抄来的。
# 依据：源机 b2 批次正在用该组合真实求解（b2_worker_run0.log 有连续 OK 点，
# ansysedt 进程血缘可追到 contract_launch.py）。迁移时优先对齐这一组。
# ⚠️ 文档《README_迁移指南.md》写「Python 必须 3.11」与实测不符（源机是 3.14.6），
#    **以实测为准**；文档那条属于更早版本的残留。
# ---------------------------------------------------------------------------
PROVEN_PY = (3, 14, 6)
PROVEN_PYAEDT = "1.3.0"
PROVEN_DEPS = {
    "numpy": "2.4.6",
    "grpcio": "1.83.1",
    "protobuf": "6.33.5",
    "pandas": "3.0.3",
    "scipy": "1.18.0",
}


def rep(level, item, detail=""):
    R.append({"level": level, "item": item, "detail": detail})
    print("[%-4s] %s%s" % (level, item, ("\n         " + detail) if detail else ""),
          flush=True)


def ok(i, d=""):
    rep("OK", i, d)


def warn(i, d=""):
    rep("WARN", i, d)


def fail(i, d=""):
    rep("FAIL", i, d)


def section(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78, flush=True)


def check_powershell(cfg):
    """PowerShell 版本与能力 —— 迁移期间真踩过这个坑。

    源机（以及 Windows Server 2022 目标机）自带的是 **PowerShell 5.1**，而非 7.x。
    5.1 与 7 在若干常用参数上**不兼容**，实测典型：
        Get-ChildItem -LiteralPath <dir> -Directory -Depth 2
      -> "A parameter cannot be found that matches parameter name 'Directory'"
    而本项目的全部巡检、自愈、计划任务注册、进程查询都通过 PowerShell 落地，
    一条不兼容的命令会让新会话在"找包"这第一步就翻车。
    """
    section("E PowerShell 版本与能力（脚本巡检/自愈链路依赖它）")
    out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
               "$PSVersionTable.PSVersion.ToString()"], timeout=60)
    ver = (out or "").strip().splitlines()[-1].strip() if (out or "").strip() else ""
    if re.match(r"^5\.1", ver):
        ok("E1 Windows PowerShell %s（Server 2022 自带）" % ver,
           "本项目全部实测都在 5.1 上完成 —— 这是**推荐**环境。"
           "注意 5.1 的 `-LiteralPath` 不能与 `-Directory`/`-Depth` 同用，脚本文档已按此规避。")
    elif re.match(r"^[67]\.", ver):
        warn("E1 当前是 PowerShell %s（非 5.1）" % ver,
             "本项目实测基线是 5.1。7.x 语法更宽松，**脚本能跑不代表计划任务能跑** —— "
             "计划任务默认走 `powershell.exe`（5.1）。放量前请确认两条路径都能执行。")
    elif ver:
        warn("E1 PowerShell 版本 %r 未见过" % ver, "请人工确认巡检脚本可执行")
    else:
        warn("E1 PowerShell 版本取不到", (out or "")[:200])

    out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
               "$p = $PSHOME; $p"], timeout=60)
    if out.strip():
        ok("E2 powershell.exe 位置", out.strip().splitlines()[-1])

    # 关键原语可用性（自愈链真正依赖的能力）
    probes = [
        ("Get-CimInstance Win32_Process",
         "(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Measure-Object).Count",
         "进程盘点（guard 用它判断 worker 数）"),
        ("Stop-Process",
         "(Get-Command Stop-Process -ErrorAction SilentlyContinue) -ne $null",
         "杀进程（外科恢复依赖它）"),
        ("Register-ScheduledTask",
         "(Get-Command Register-ScheduledTask -ErrorAction SilentlyContinue) -ne $null",
         "注册计划任务（无人值守的前提）"),
        ("Get-CimInstance Win32_PageFileSetting",
         "@(Get-CimInstance Win32_PageFileSetting -ErrorAction SilentlyContinue).Count",
         "页面文件托管判定"),
    ]
    for name, cmd, why in probes:
        o = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                timeout=60)
        v = (o or "").strip().splitlines()[-1].strip() if (o or "").strip() else ""
        if v.lower() in ("true", "false") or re.match(r"^\d+$", v):
            ok("E3 %s 可用 -> %s" % (name, v), why)
        else:
            fail("E3 %s 不可用" % name, "%s\n         返回：%s" % (why, (o or "").strip()[:160]))


def load_site(p):
    with open(p, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def run(cmd, timeout=60):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           errors="replace")
        return (p.stdout or "") + (p.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return "ERR:%r" % (e,)


def mem_info():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
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


# ------------------------------------------------------------------ A 新机底座
def check_paths(cfg):
    section("A 目录与文件落位（迁移后必须项）")
    items = [
        ("A1 工作根 new_work_root", cfg["new_work_root"], "dir"),
        ("A2 代码根 new_wpt_root", cfg["new_wpt_root"], "dir"),
        ("A3 母本工程 new_project_ref", cfg["new_project_ref"], "file"),
    ]
    for k, v in (("4 诊断工具 new_probe_root", cfg.get("new_probe_root")),
                 ("5 解释器 new_python", cfg.get("new_python")),
                 ("6 AEDT new_aedt_exe", cfg.get("new_aedt_exe"))):
        if v:
            items.append(("A" + k, v, "file" if k.startswith(("5", "6")) else "dir"))
    for label, p, kind in items:
        if not p:
            warn(label, "配置里为空，跳过")
            continue
        e = os.path.isfile(p) if kind == "file" else os.path.isdir(p)
        if e:
            extra = ""
            if kind == "file":
                extra = "（%.2f MB）" % (os.path.getsize(p) / 1048576.0)
            ok(label + extra, p)
        else:
            fail(label + " 不存在", p)

    # 口径三件套必须同在代码根
    trio = ["batch_sweep_lc.py", "coil_gen.py", "wpt_contract.py"]
    wpt = cfg.get("new_wpt_root", "")
    miss = [n for n in trio if not os.path.isfile(os.path.join(wpt, n))]
    tpl = os.path.join(wpt, "coil_template_Rx.json")
    if not os.path.isfile(tpl):
        miss.append("coil_template_Rx.json")
    if miss:
        fail("A7 口径依赖文件缺失", "缺：%s（worker 启动时会 import 失败）" % "、".join(miss))
    else:
        ok("A7 口径依赖四件套齐备", "batch_sweep_lc / coil_gen / wpt_contract / coil_template_Rx.json")

    # 批次脚本是否已按新批次名重命名
    bn = cfg.get("batch_name", "b3")
    stale = [n for n in os.listdir(cfg["new_work_root"])
             if n.startswith("b2_") and n.endswith(".py")] \
        if os.path.isdir(cfg["new_work_root"]) else []
    proper = [n for n in os.listdir(cfg["new_work_root"])
              if n.startswith(bn + "_") and n.endswith(".py")] \
        if os.path.isdir(cfg["new_work_root"]) else []
    if stale and not proper:
        fail("A8 批次脚本仍是旧批次名", "发现 %d 个 b2_*.py，但没有任何 %s_*.py。"
             "直接跑会写错目录（preflight 的 B8 会告警但不阻断）" % (len(stale), bn))
    elif proper:
        ok("A8 批次脚本已改为 %s_*.py（%d 个）" % (bn, len(proper)))
    else:
        warn("A8 未找到 %s_*.py" % bn, "若尚未重命名，见《迁移操作手册》第 4 步")


# ------------------------------------------------------------- B Python 与 pyaedt
def check_python(cfg):
    section("B Python 解释器与 pyaedt（版本错了整条链路都跑不起来）")
    py = cfg.get("new_python", "")
    if not py or not os.path.isfile(py):
        fail("B1 解释器不存在，后续无法检查", py or "(空)")
        return
    ok("B1 解释器存在", py)

    out = run([py, "-c",
               "import sys;print(sys.version_info[0],sys.version_info[1],"
               "sys.version_info[2]);print(sys.executable)"])
    m = re.match(r"\s*(\d+)\s+(\d+)\s+(\d+)", out)
    if not m:
        fail("B2 解释器无法执行", out.strip()[:300])
        return
    maj, mi, pa = (int(x) for x in m.groups())
    ver = "%d.%d.%d" % (maj, mi, pa)
    # 判据来源：**源机生产在用组合实测**（见下面 PROVEN_* 常量），不是文档里的旧说法。
    # 文档《README_迁移指南.md》写"必须 Python 3.11" —— 那是更早一版的记录，
    # 与源机实际不符（源机是 3.14.6 且正在正常求解）。**以实测为准。**
    if (maj, mi, pa) == PROVEN_PY:
        ok("B2 Python %s —— 与源机生产在用版本**完全一致**（最强兼容性）" % ver)
    elif (maj, mi) == (3, 11):
        ok("B2 Python %s（3.11）" % ver,
           "与源机实测版本不同但属文档记载的口径；放量前务必先跑 smoke_one.py 验证。")
    else:
        warn("B2 Python %s，与源机实测 %s 不同" % (ver, "%d.%d.%d" % PROVEN_PY),
             "**不必然失败**，但迁移验证必须重做：pyaedt 与 AEDT 之间的 gRPC 协议"
             "对解释器/依赖版本敏感。先跑 smoke_one.py，通过再放量。")

    out = run([py, "-c",
               "import ansys.aedt.core as c;"
               "from ansys.aedt.core import Desktop, Maxwell3d;"
               "print(getattr(c,'__version__','?'))"])
    if "Traceback" in out or "ModuleNotFoundError" in out:
        fail("B3 无法导入 ansys.aedt.core", out.strip()[:400]
             + "\n         装法：<解释器> -m pip install pyaedt==1.3.0")
    else:
        pv = out.strip().splitlines()[-1] if out.strip() else "?"
        if pv.startswith("1.3"):
            ok("B3 pyaedt %s（导入路径 ansys.aedt.core 正确）" % pv)
        else:
            warn("B3 pyaedt 版本 %s（源机实测为 %s）" % (pv, PROVEN_PYAEDT),
                 "版本不同不必然失败，但**迁移验证需要重新做**："
                 "网格口径与 API 都可能变，跨批数据不再严格可比。")

    # gRPC / protobuf 是 pyaedt 与 AEDT 通信的实际管道，版本错位表现为
    # 「会话起不来」或「GetAvailableReportTypes 死循环」，极难归因 —— 故显式核对。
    probe = ("import importlib.metadata as md\n"
             "for n in ('numpy','grpcio','protobuf','pandas','scipy'):\n"
             "    try: print(n, md.version(n))\n"
             "    except Exception: print(n, 'n/a')\n")
    out = run([py, "-c", probe])
    got = {}
    for line in out.strip().splitlines():
        k, _, v = line.partition(" ")
        got[k.strip()] = v.strip()
    if not got:
        warn("B4 依赖版本取不到", out.strip()[:200])
        return
    diff = {k: (got.get(k), PROVEN_DEPS[k]) for k in PROVEN_DEPS
            if got.get(k) != PROVEN_DEPS[k]}
    if not diff:
        ok("B4 关键依赖与源机生产在用组合**逐项一致**",
           "、".join("%s %s" % (k, got[k]) for k in sorted(PROVEN_DEPS)))
    else:
        det = "；".join("%s 本机 %s / 源机 %s" % (k, a, b) for k, (a, b) in sorted(diff.items()))
        warn("B4 关键依赖与源机不一致", det + "\n         其中 grpcio/protobuf 错位会表现为"
             "「AEDT 会话起不来」或「gRPC 僵死」，症状与崩溃混淆 —— 优先对齐这两个。")


# ------------------------------------------------------------------ C AEDT 与授权
def check_aedt(cfg, do_net=True):
    section("C AEDT 安装与授权（迁移唯一的外部依赖）")
    exe = cfg.get("new_aedt_exe", "")
    if exe and os.path.isfile(exe):
        ok("C1 ansysedt.exe 存在", exe)
        # 版本判定：**先读 exe 自带的 ProductVersion**（实测源机为 2024.1.0），
        # 读不到才回退到路径里的 v241 写法。历史教训：按 v241 -> "24.1" 硬拼字符串
        # 会误报"与源机不一致"，属校验器自己的缺陷。
        pv = None
        out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                   "(Get-Item -LiteralPath '%s').VersionInfo.ProductVersion" % exe])
        mm = re.search(r"(\d{4})\.(\d+)", out or "")
        if mm:
            pv = "%s.%s" % (mm.group(1), mm.group(2))
        if pv is None:
            mv = re.search(r"v(\d{3})", exe)
            if mv:
                v = mv.group(1)
                pv = "20%s.%s" % (v[:2], v[2:].lstrip("0") or "0")
        if pv == "2024.1":
            ok("C2 AEDT 版本 %s（= 2024 R1，与源机一致）" % pv)
        elif pv:
            warn("C2 AEDT 版本 %s **与源机 2024 R1 不一致**" % pv,
                 "几何/网格可能出现差异，跨批数据可比性需重新建立："
                 "先用同一工况复算并与源机 b1/b2 raw 比对，偏差应为 0.000%"
                 "（源机实测两独立会话 8 项电感全部 0.000% 偏差）。")
        else:
            warn("C2 无法判定 AEDT 版本", "请人工确认是否为 2024 R1（v241）")
    elif exe:
        fail("C1 ansysedt.exe 不存在", exe + "\n         装完 AEDT 后核对此路径，或改 _site_config.json")
    else:
        warn("C1 未在配置中给 new_aedt_exe", "跳过安装检查；worker 用 pyaedt 的默认查找逻辑")

    for n in ("ansysedt", "3dnms", "G3dMesher", "ansyscl"):
        out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                   "@(Get-Process -Name %s -ErrorAction SilentlyContinue).Count" % n])
        cnt = out.strip().splitlines()[-1].strip() if out.strip() else "?"
        if cnt not in ("0", ""):
            warn("C3 存在 %s 幽灵进程 %s 个" % (n, cnt),
                 "启动批次前 AEDT 全家族必须清零。强杀后 AEDT 有 **3~5 分钟静默窗口**，"
                 "窗口内新建会话必然失败（源机实测整批重启 8/8 全灭）。等 ≥4 min 再启动。")
    ok("C3 AEDT 家族进程检查完成", "启动前要求全为 0")

    # 环境变量
    lf = os.environ.get("ANSYSLMD_LICENSE_FILE", "")
    al = os.environ.get("ANSYSLIC_DIR", "")
    ar = os.environ.get("ANSYSEM_ROOT241") or os.environ.get("ANSYSEM_ROOT242") or ""
    if lf:
        ok("C4 ANSYSLMD_LICENSE_FILE = %s" % lf)
    else:
        fail("C4 未设置 ANSYSLMD_LICENSE_FILE",
             "没有它 AEDT 一步都算不了。设为 <端口>@<授权服务器>，例如 1055@lic.corp.local")
    ok("C5 ANSYSLIC_DIR = %s" % al) if al else warn("C5 未设置 ANSYSLIC_DIR",
                                                    "通常由 AEDT 安装程序设置；若授权工具跑不起来，先查这个")
    ok("C6 ANSYSEM_ROOT241 = %s" % ar) if ar else warn(
        "C6 未设置 ANSYSEM_ROOT24x", "pyaedt 会自行查找安装，但设好更稳")

    # 授权服务器连通性
    srv = (cfg.get("license_server") or "").strip()
    if not srv:
        warn("C7 配置里未给 license_server", "跳过连通性检查")
        return
    if not do_net:
        warn("C7 已按 --no-license-net 跳过授权服务器连通性检查", srv)
        return
    m = re.match(r"^(?:(\d+)@)?(.+)$", srv)
    port = int(m.group(1) or 1055)
    host = m.group(2).strip()
    # 允许 端口@主机:端口 写法
    if ":" in host and not host.startswith("["):
        host, _, p2 = host.rpartition(":")
        if p2.isdigit():
            port = int(p2)
    try:
        ip = socket.gethostbyname(host)
        ok("C7a 授权服务器域名解析", "%s -> %s" % (host, ip))
    except OSError as e:
        fail("C7a 授权服务器无法解析", "%s : %r\n         先确认 DNS/hosts 与网络策略" % (host, e))
        return
    t0 = time.time()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5.0)
    try:
        s.connect((ip, port))
        ok("C7b TCP %s:%d 可达（%.0f ms）" % (ip, port, (time.time() - t0) * 1000))
    except OSError as e:
        fail("C7b TCP %s:%d 不可达" % (ip, port),
             "%r\n         ANSYS 授权用的是 lmgrd 协议端口；防火墙放行或换端口后再试" % (e,))
    finally:
        s.close()

    # 真正拿到席位：用 ANSYS 自带的 lmutil（若有）
    lmutil = None
    for c in (os.path.join(os.environ.get("ANSYSLIC_DIR", ""), "winx64", "lmutil.exe"),
              os.path.join(os.environ.get("ANSYSLIC_DIR", ""), "lmutil.exe"),
              r"C:\Program Files\ANSYS Inc\Shared Files\Licensing\winx64\lmutil.exe"):
        if c and os.path.isfile(c):
            lmutil = c
            break
    if lmutil:
        out = run([lmutil, "lmstat", "-a", "-c", "%d@%s" % (port, host)], timeout=60)
        n_used = len(re.findall(r"Maxwell|AnsysElectronics|Electronics", out))
        if "Error" in out or "Cannot" in out or not out.strip():
            warn("C8 lmstat 未取到有效输出", out.strip()[:300])
        else:
            ok("C8 lmstat 可查询授权（匹配到 %d 行相关特性）" % n_used,
               "完整输出见 --json 导出的 raw_lmstat")
            return out
    else:
        warn("C8 未找到 lmutil.exe，无法查席位占用",
             "建议向运维确认：AEDT 2024 R1 的 Maxwell 席位数量 ≥ 计划并发实例数。"
             "源机靠本机授权规避了这个问题，新机是共享池，**席位被别的用户占满时"
             "表现为随机的求解失败**，极易误判成模型问题。")
    return None


# -------------------------------------------------------------------- D 资源
def check_res(cfg):
    section("D 资源与并发上限（源机就是被内存卡死的）")
    wr = cfg["new_work_root"]
    drive = os.path.splitdrive(os.path.abspath(wr))[0] + "\\"
    try:
        du = shutil.disk_usage(drive)
        free = du.free / 2 ** 30
        if free < 40:
            fail("D1 %s 可用 %.1f GB（<40 GB 报警线）" % (drive, free),
                 "页面文件是求解器提交内存的最后兜底：磁盘长不动 -> 提交分配失败 -> "
                 "求解器 OOM 死，症状与网格器崩溃混淆，极难区分。")
        elif free < 60:
            warn("D1 %s 可用 %.1f GB（40~60 GB，启动前建议清到 >60 GB）" % (drive, free))
        else:
            ok("D1 %s 可用 %.1f GB" % (drive, free))
    except OSError as e:
        fail("D1 磁盘余量取不到", repr(e))

    try:
        mt, ma, cl, ca = mem_info()
        pct = 100.0 * (cl - ca) / cl if cl else 0.0
        detail = "物理总 %.1f / 可用 %.1f GB；提交 %.1f/%.1f GB (%.1f%%)" % (
            mt, ma, cl - ca, cl, pct)
        if ma < 2:
            fail("D2 可用物理内存 %.1f GB（<2 GB）" % ma, detail)
        elif mt < 30:
            warn("D2 物理内存 %.1f GB 偏紧" % mt, detail)
        else:
            ok("D2 内存 %s" % detail)

        # 并发实例数推荐：源机实测 31.6 GB ↔ 8 实例；单会话私有内存可达 13 GB
        n_cfg = int(cfg.get("instances", 8))
        # 保守模型：每实例按 4 GB 常驻 + 1.5 倍弹性余量；上限仍受源机经验约束
        n_by_ram = max(1, int(mt / 4.0))
        n_rec = min(16, n_by_ram)
        ok("D3 并发实例数建议", "配置 %d；按物理内存 %.1f GB 估算上限 ≈ %d"
           % (n_cfg, mt, n_rec))
        if n_cfg > n_rec:
            warn("D3 配置的 %d 实例可能偏多" % n_cfg,
                 "源机实测：8 个 AEDT 会话私有内存合计可达 ~60 GB（32 GB 物理内存的 1.9 倍），"
                 "压爆页面文件后 **8 个实例陆续冻死 6~10 小时**。"
                 "判据：提交量 ≥88% 且 ≥5 个实例失速 -> 判定内存耗尽。"
                 "首次放量建议先用 4 实例观察 1 小时，再逐步加到上限。")
        if mt < 32:
            warn("D4 物理内存 %.1f GB 未超过源机（31.6 GB）" % mt,
                 "换机不会变快。源机并发 8 实例已实测是本机硬上限，"
                 "内存更少时必须下调实例数，否则会重现冻死事故。")
        else:
            ok("D4 物理内存 %.1f GB（源机 31.6 GB）—— 有余量，可上调实例数" % mt)
    except (OSError, ValueError) as e:
        fail("D2 内存信息取不到", repr(e))

    # 页面文件：判据要分辨「系统托管」与「固定大小」。
    # ⚠️ 不能用 Win32_PageFileUsage 的 AllocatedBaseSize 当"是否固定"的判据 ——
    # 那个值在**系统托管**时也会报出当前实际大小（源机实测报 59377 MB 而实为托管），
    # 会把正常的机器误判成固定页面文件。正确判据是 Win32_PageFileSetting：
    # **系统托管时该类的条目数为 0**（源机实测计数为空）。
    out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
               "$s=@(Get-CimInstance Win32_PageFileSetting -EA SilentlyContinue);"
               "$u=@(Get-CimInstance Win32_PageFileUsage -EA SilentlyContinue);"
               "'SETTING_COUNT='+$s.Count;"
               "$s | ForEach-Object {'SET|'+$_.Name+'|'+$_.InitialSize+'|'+$_.MaximumSize};"
               "$u | ForEach-Object {'USE|'+$_.Name+'|'+$_.AllocatedBaseSize}"])
    o = (out or "").strip()
    mcnt = re.search(r"SETTING_COUNT=(\d+)", o)
    n_set = int(mcnt.group(1)) if mcnt else -1
    uses = [l.split("|") for l in o.splitlines() if l.startswith("USE|")]
    cur = ", ".join("%s 当前 %.1f GB" % (u[1], int(u[2]) / 1024.0) for u in uses if len(u) > 2)
    if n_set == 0:
        ok("D5 页面文件为**系统托管**（推荐）",
           (cur + "；" if cur else "") + "系统会随内存压力自动增长 —— 源机靠它撑住 8 实例")
    elif n_set > 0:
        sets = [l for l in o.splitlines() if l.startswith("SET|")]
        warn("D5 页面文件是**固定大小**", "；".join(sets) + ("；" + cur if cur else "")
             + "\n         源机页面文件曾自动涨到 46 GB 才撑住 8 实例并发。"
               "固定过小会在放量时直接 OOM，症状与网格器崩溃混淆。建议改为系统托管。")
    else:
        warn("D5 页面文件状态取不到", o[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=r"_site_config.json")
    ap.add_argument("--json", default=None, help="把结果导出为 JSON")
    ap.add_argument("--no-license-net", action="store_true")
    args = ap.parse_args()

    print("=" * 78)
    print("目标机环境自检（迁移后 / 启动批次前）")
    print("时间 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 78, flush=True)

    cfg = load_site(args.site)
    print("站点配置：%s" % os.path.abspath(args.site))
    print("  工作根 %s\n  代码根 %s\n  解释器 %s"
          % (cfg.get("new_work_root"), cfg.get("new_wpt_root"), cfg.get("new_python")))

    lm = None
    try:
        check_paths(cfg)
        check_python(cfg)
        lm = check_aedt(cfg, do_net=not args.no_license_net)
        check_res(cfg)
        check_powershell(cfg)
    except Exception as exc:                      # noqa: BLE001
        fail("检查过程异常", repr(exc))

    section("汇总")
    nf = sum(1 for r in R if r["level"] == "FAIL")
    nw = sum(1 for r in R if r["level"] == "WARN")
    nk = sum(1 for r in R if r["level"] == "OK")
    print("OK %d / WARN %d / FAIL %d" % (nk, nw, nf), flush=True)
    if nf:
        print("\n存在 %d 个 FAIL —— **不要启动批次**，先逐条消掉：" % nf)
        for r in R:
            if r["level"] == "FAIL":
                print("  · %s" % r["item"])
        rc = 1
    else:
        print("\n底座就绪。下一步：跑 preflight.py 查批次链路，再跑 smoke_one.py 冒烟。")
        rc = 0

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"time": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "site": os.path.abspath(args.site),
                       "results": R, "raw_lmstat": lm}, f,
                      ensure_ascii=False, indent=2)
        print("结果已导出：%s" % args.json)
    print("退出码 %d" % rc)
    return rc


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                      # noqa: BLE001
        print("\n[FAIL] check_target_env 自身异常：%r" % (exc,), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)
