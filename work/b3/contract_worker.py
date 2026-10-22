# -*- coding: utf-8 -*-
r"""契约口径采集 worker（batch1）。

单实例、按工况串行。每工况：重建线圈 + 独立 fill/厚度的铁氧体 -> 21 点半扫 -> 逐点求 L 矩阵。
本脚本**只写"逐点原始结果"** b1_raw_runK.csv（可断点续跑）；
三个契约 CSV 由 contract_merge.py 从原始结果统一生成（保证可重放、无半截数据）。

环境变量：
  WPT_RUN    实例号（决定工程副本 / 原始结果 / 日志）
  WPT_BATCH  batch 前缀（默认 b1）
  WPT_PLAN   本次要跑的工况表（分片后的 CSV，契约 8 列）
  WPT_ROOT   工作根目录（默认 C:\ansys maxwell2024\_work\b1）
  WPT_XS     只解这些位置（逗号分隔 mm）—— 冒烟测试 / 定点复算
  WPT_CASES  只跑前 N 个工况
  WPT_BOXX   固定盒 X 半宽（mm，默认 420）
  WPT_BOXY   固定盒 Y 上界（mm，默认 161）

几何/求解口径（全部复用生产验证过的代码）：
  coil_gen.rebuild_all          路径径向重映射（LC 用文档口径，内部乘 k_lc）
  wpt_contract.derived          派生几何（edge_gap 取整、ferrite_len = 1.2*Lc）
  wpt_contract.build_ferrite    两侧**独立** fill/厚度的铁氧体铺条
  batch_sweep_lc.set_tx_gap     发射线圈按 edge_gap 摆位
  batch_sweep_lc.ensure_region  固定空气域盒（口径写死在 REGION_FIXED）
  batch_sweep_lc.solve_and_extract  生产求解路径（含柔性网格 + ⑥ + pref10 + rres 及 OPT_MIN_GAP 闸门）
  wpt_contract.sweep_positions_half 半扫 21 点 x_i = i*S/40，S = Lc(2+g)
"""
import csv
import json
import math
import os
import subprocess
import sys
import time
import traceback

# stdout 被管道捕获时中文 Windows 默认 GBK —— 中文日志会抛 UnicodeEncodeError
# 并以退出码 1 结束（第一轮实测：计划任务下正常，一旦经管道/远程执行就崩）。
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

ROOT = os.environ.get("WPT_ROOT", r"C:\ansys maxwell2024\_work\b2")
PROBE = r"C:\ansys maxwell2024\_probe"
sys.path.insert(0, PROBE)
import aedt_shim                                  # noqa: E402
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import coil_gen as CG                             # noqa: E402
import wpt_contract as WC                         # noqa: E402
import batch_sweep_lc as B                        # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d    # noqa: E402

RUN = int(os.environ.get("WPT_RUN", "0"))
BATCH = os.environ.get("WPT_BATCH", "b2")
PLAN = os.environ.get("WPT_PLAN", os.path.join(ROOT, "%s_plan_shard%d.csv" % (BATCH, RUN)))
XS_ENV = [float(v) for v in os.environ.get("WPT_XS", "").split(",") if v.strip()]
CASE_LIMIT = int(os.environ.get("WPT_CASES", "0"))
BOXX = float(os.environ.get("WPT_BOXX", "420"))
BOXY = float(os.environ.get("WPT_BOXY", "161"))

PROJ = os.path.join(ROOT, "Projecttonight_%s_run%d.aedt" % (BATCH, RUN))
RAW = os.path.join(ROOT, "%s_raw_run%d.csv" % (BATCH, RUN))
LOGF = os.path.join(ROOT, "%s_worker_run%d.log" % (BATCH, RUN))
PTCSV = os.path.join(ROOT, "%s_pt_run%d.csv" % (BATCH, RUN))
OUTJSON = os.path.join(ROOT, "%s_worker_run%d.json" % (BATCH, RUN))
# 求解数据清理口径（2026-09-19）：AEDT 每个解都会在 <工程>.aedtresults 里写
# fields.sol / current.ngmesh / fields.hlo|blo|spt|shd / 自适应趟数据（单解 ~100-200MB）。
# 原始 L 矩阵已落盘到 raw CSV，这些场数据对后续没有任何用处 —— 解完即删，
# 使磁盘占用恒定而不是随点数线性增长。
#   point（默认）：每个点提取完立刻清；case：每工况结束清一次；off：不清
CLEAN = os.environ.get("WPT_CLEAN", "point")
# 逐工况口径回退（2026-09-19）：实测 b1_0126 在 x=+24.854 于 OPT 口径下**确定性**求解失败
# （两个不同会话各失败一次，均在 ~4.4 min 报 Status=Error），单纯重试无效。
# 补偿策略：把该工况整套改用 BASE 口径（无柔性 / 无⑥ / pref5 / rres1e-6）重解，
# 口径在**单个工况内部**保持一致，不污染曲线形状；口径标记写进 raw 的 mesh 列。
MESH_FALLBACK = os.environ.get("WPT_MESH_FALLBACK", "1") == "1"
MESH = ["OPT"]          # 当前网格口径（可变，用于日志与 raw 标记）


def set_mesh_opt():
    B.FLEX_MESH, B.REGION_MAX_LEN_DIV, B.OPT_MIN_GAP = True, 5.0, 1.5
    MESH[0] = "OPT"


def set_mesh_base():
    B.FLEX_MESH, B.REGION_MAX_LEN_DIV, B.OPT_MIN_GAP = False, 0.0, 1e9
    MESH[0] = "BASE"


def effective_mesh(LC, KR):
    """本工况**实际**用的网格口径。

    注意：闸门（OPT_MIN_GAP）是在生产求解函数内部判定的，全局 MESH 反映不出来 ——
    实测 b1_0076（gap=0.815mm）走的是 BASE 口径，但早期版本把它标成了 OPT。
    这里按同一套判据复算：forced BASE（补偿）或闸门不通过 -> BASE，否则 OPT。
    """
    if MESH[0] == "BASE":
        return "BASE"
    try:
        gap = CG.path_dims(LC, KR).get("gap_min")
    except Exception:
        return "OPT"
    return "OPT" if (gap is None or gap >= B.OPT_MIN_GAP) else "BASE"

RAW_COLS = ["case_id", "i", "x_mm", "L11", "L22", "L33", "M12", "M13", "M23",
            "k13", "k23", "minutes", "aedt_pid", "ts", "mesh"]
MU = 1000.0
SESS = {"d": None, "m": None, "pid": None, "restarts": 0, "t0": None}
RES = {"run": RUN, "batch": BATCH, "cases": [], "box": {"x": BOXX, "y": BOXY}}


def log(msg=""):
    s = "%s | [%s%d] %s" % (time.strftime("%H:%M:%S"), BATCH, RUN, msg)
    print(s, flush=True)
    try:
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass


def dump():
    """原子落盘，且**绝不用空的 cases 覆盖已有记录**。

    ⚠️ 2026-10-12 修（第一轮实测事故，第二轮启动前）：main() 在 `open_session()`
    失败时走 `except -> RES["fatal"]=traceback -> finally: dump()`，而此刻
    `RES["cases"]` 还是空列表 —— 于是整份 JSON 被覆盖成 `{"cases": [], "fatal": ...}`。
    第一轮跑完后那次误重启（guard 每 30 min 重启已完工批次）就让 8 份
    `b1_worker_run*.json` 的工况记录**全部被抹掉**（实测 8/8 只剩 fatal traceback）。
    这正是《批量仿真故障总结》问题 6 的**写侧根因** —— 当时只修了读侧
    （deliver/partial_export 改 raw 反推），写侧一直在破坏数据。
    顺带改成 tmp + os.replace 原子写（原实现直接覆盖，强杀会留下半截 JSON，
    而 b1_deliver 的 json.load 没有 try，一份坏 JSON 会让交付闸门直接 traceback）。
    """
    try:
        cur = RES
        if not cur.get("cases"):
            old = None
            try:
                with open(OUTJSON, encoding="utf-8-sig") as f:
                    old = json.load(f)
            except (OSError, ValueError):
                old = None
            if isinstance(old, dict) and old.get("cases"):
                cur = dict(RES)
                cur["cases"] = old["cases"]           # 保住上一次的工况记录
                cur["_dump_note"] = ("本次写入时 cases 为空（多半是开会话/几何阶段失败），"
                                     "已保留上一次的工况记录；失败原因见 fatal")
        tmp = OUTJSON + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
        os.replace(tmp, OUTJSON)                      # 原子替换
    except Exception as e:
        log("!! dump 失败（不影响求解）：%r" % (e,))


def kill_own():
    """只杀自己那个 AEDT 的 PID（多实例下无差别 taskkill 会互杀）。"""
    pid = SESS["pid"] or B.AEDT_PROCESS_ID
    if pid:
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Stop-Process -Id %d -Force -ErrorAction SilentlyContinue" % int(pid)],
                           capture_output=True, text=True)
        except Exception:
            pass
    for f in (PROJ + ".lock",):
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass
    time.sleep(3)


B.kill_aedt = kill_own          # 看门狗超时后由 run_stage 调用

# ============ 看门狗超时（2026-09-19 批次事故后调整）============
# 事故：8 实例并发下，本批几何（3 线圈 + 最多 20 条 Tx 条 + 9 条 Rx 条 + 固定盒）
#       实测耗时 7~8 分钟，而生产默认 STAGE_TIMEOUT=360s（按单实例 ~2 分钟定的）——
#       看门狗在铁氧体铺完之前就强杀 AEDT，后续 create_box 全部返回 None、
#       Region 也建不出来（表现为 ferrite Rx err: TypeError）。
# 调整：几何 25 分钟（~3 倍余量）；求解 40 分钟（BASE 回退点单点可达 ~20 分钟）。
B.STAGE_TIMEOUT = int(os.environ.get("WPT_STAGE_TIMEOUT", "1500"))
B.SOLVE_TIMEOUT = int(os.environ.get("WPT_SOLVE_TIMEOUT", "2400"))

# 会话最大存活时长（小时），超过则在工况边界主动轮换。见 recycle_session() 的背景说明。
# 取 7 h 的理由：实测 ~12 h 的会话私有内存已到 13 GB（8 个合计约 60 GB，是本机物理内存
# 的 1.9 倍），而膨胀是渐进的；7 h 留出充足余量，代价只是每 7 h 一次 ~7 分钟的重开。
# 设 0 可关闭轮换（退回旧行为）。
SESSION_MAX_H = float(os.environ.get("WPT_SESSION_MAX_H", "7"))


def open_session():
    """（重）开一个属于本实例的 AEDT 会话。"""
    kill_own()
    lk = PROJ + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = ROOT
    B.PROJECT = PROJ
    B.LOG_FILE = LOGF
    B.REGION_FIXED = {"x": (-BOXX, BOXX), "y": (-134.94, BOXY), "z": (-45.0, 75.0)}
    # ⚠️ 2026-10-13：GUI 模式（non_graphical=False）**只能在有交互桌面的会话里启动**。
    # 实测（_probe\nongui_s4u_test.py，同以 S4U/计划任务身份运行）：
    #   non_graphical=False → 失败（148.9 s，"Failed to start new AEDT gRPC session"）
    #   non_graphical=True  → 成功（7.0 s）
    # 后果：guard 在计划任务里（会话 0）拉起的所有 worker **都起不来 AEDT** ——
    # 于是"自愈"只会杀不会起，反而把还能跑的批次弄死（2026-10-13 07:01 实测）。
    # 现在由 WPT_NON_GRAPHICAL 控制：guard 的重启路径会置 1，保证会话无关。
    _nongui = os.environ.get("WPT_NON_GRAPHICAL", "0") == "1"
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=_nongui,
                close_on_exit=False)
    log("会话模式：%s" % ("无界面(non_graphical=True)" if _nongui else "GUI(non_graphical=False)"))
    SESS["pid"] = d.aedt_process_id
    B.AEDT_PROCESS_ID = SESS["pid"]
    m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
    CG.TEMPLATE = r"C:\wpt\coil_template_Rx.json"
    CG._ref = None
    CG._s_ref = None
    CG._load()
    SESS["d"], SESS["m"] = d, m
    SESS["t0"] = time.time()          # 会话起始，供 recycle_session 按存活时长轮换
    log("会话就绪 pid=%s 工程=%s" % (SESS["pid"], os.path.basename(PROJ)))
    return d, m


def recycle_session(cid, case_i, case_n):
    """**主动**轮换 AEDT 会话，避免会话内存膨胀把整批拖死。

    背景（2026-09-21 实测）：AEDT 会话跑得越久越肿 —— 私有内存单个可达 10~13 GB，
    8 个合计约 60 GB，远超本机 31.6 GB 物理内存，于是全部压进页面文件
    （pagefile 46 -> 59.4 GB、峰值用 45 GB），提交量冲到 85.5/89.6 GB(95%)，
    换页失控，**8 个实例在凌晨陆续冻死 6~10 小时**（日志零新增、CPU 增量 0）。
    会话存活时长与会话肿大的相关性极强：~15 h 的会话私有 10.2 GB、
    ~12 h 的 13.0 GB。故按**存活时长**在膨胀到危险区之前主动换掉。

    为什么放在工况边界：几何本来每个工况都要重建，换会话不需要额外重建，
    代价只有重开会话的 ~7 分钟固定开销（而它换回的是避免整批停摆数小时）。
    """
    if SESSION_MAX_H <= 0:
        return True
    age_h = (time.time() - SESS.get("t0", time.time())) / 3600.0
    if age_h < SESSION_MAX_H:
        return True
    log("[%d/%d] === %s === 【主动轮换】会话已存活 %.1f h（阈值 %.1f h），"
        "在工况边界重开会话以释放内存" % (case_i, case_n, cid, age_h, SESSION_MAX_H))
    try:
        SESS["restarts"] += 1
        open_session()
        log("  轮换完成，新会话 pid=%s" % SESS["pid"])
        return True
    except Exception as e:
        log("  !! 轮换失败：%r —— 保留旧会话继续（批次仍受 guard --restart 兜底）" % (e,))
        return False



def migrate_raw():
    """旧格式 raw 文件（表头无 mesh 列）迁移成新表头，缺失的 mesh 记 'OPT'。

    必须做：csv.DictReader 按表头映射列，若沿用旧表头再追加多一列，
    第 15 个字段会落到 None 键上，mesh 标记就丢了（会让 BASE 补偿点被误标成 OPT）。
    """
    if not os.path.exists(RAW) or os.path.getsize(RAW) == 0:
        return
    with open(RAW, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        head = list(r.fieldnames or [])
        if "mesh" in head:
            return
        rows = list(r)
    tmp = RAW + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=RAW_COLS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            row["mesh"] = "OPT"          # 旧行全部是 OPT 口径（BASE 补偿是 9/19 才引入的）
            w.writerow({k: row.get(k, "") for k in RAW_COLS})
    os.replace(tmp, RAW)
    print("%s | 已迁移旧 raw 表头 -> 新格式（%d 行，mesh=OPT）" % (time.strftime("%H:%M:%S"),
                                                                len(rows)))


def read_raw():
    """已完成的点：{(case_id, i): row}。"""
    done = {}
    if not os.path.exists(RAW):
        return done
    with open(RAW, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                done[(r["case_id"], int(r["i"]))] = r
            except (KeyError, ValueError):
                continue
    return done


def append_raw(row):
    new = not os.path.exists(RAW) or os.path.getsize(RAW) == 0
    with open(RAW, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(RAW_COLS)
        w.writerow([row.get(c, "") for c in RAW_COLS])


def build_case(m, v):
    """重建本工况的全部几何，返回派生量 dict。

    ★ 几何完整性硬校验（2026-09-19 新增）：铁氧体条数不足或 Region 未建成时**抛异常**，
    由看门狗判 ERR/重试；否则会带着残缺几何去求解，产出错误物理却看不出来。
    """
    LC, KR, g = v["coil_size"], v["hole_ratio"], v["spacing_ratio"]
    B.set_rx_dx(m, 0.0)
    CG.rebuild_all(m, LC, KR, log=log)
    outer = CG.coil_outer(LC)
    rx_leads = CG.current_leads(m, "Rx")
    dg = WC.derived(LC, g, v["tx_fill"], v["rx_fill"], v["rx_thick"])
    tg = float(dg["edge_gap"])
    B.set_tx_gap(m, tg, outer)
    dd = WC.build_ferrite(m, LC, g, v["tx_fill"], v["rx_fill"],
                          v["tx_thick"], v["rx_thick"], rx_leads, log=log)
    rbb = B.ensure_region(m, tg)
    want_rx = len(WC._x_centers(-LC / 2.0, LC / 2.0, dd["rx_bar_w"]))
    want_tx = len(WC._x_centers(-tg / 2.0 - LC, tg / 2.0 + LC, dd["tx_bar_w"]))
    log("几何: LC=%.2f KR=%.4f g=%+.4f tg=%.0f 条宽 Tx/Rx=%.2f/%.2f 厚=%.2f/%.2f "
        "条长=%d n_bars Rx=%d/%d Tx=%d/%d Region=%s"
        % (LC, KR, g, tg, dd["tx_bar_w"], dd["rx_bar_w"], v["tx_thick"], v["rx_thick"],
           dd["ferrite_len"], dd["n_bars_rx"], want_rx,
           len([n for n in m.modeler.object_names if n.startswith("ferrite_Tx_")]), want_tx,
           ("X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]"
            % (rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5])) if rbb else "??"))
    if dd["n_bars_rx"] != want_rx:
        raise RuntimeError("Rx 铁氧体条数不足: %d/%d（几何残缺，拒绝求解）"
                           % (dd["n_bars_rx"], want_rx))
    n_tx_now = len([n for n in m.modeler.object_names if n.startswith("ferrite_Tx_")])
    if n_tx_now != want_tx:
        raise RuntimeError("Tx 铁氧体条数不足: %d/%d（几何残缺，拒绝求解）" % (n_tx_now, want_tx))
    if rbb is None:
        raise RuntimeError("Region 未建成（固定盒 X±%.0f）" % BOXX)
    return dd


def aedt_messages(n=6):
    """抓取 AEDT 消息窗口的错误文本（求解失败时定位根因用）。"""
    try:
        d = SESS["d"]
        msgs = d.odesktop.GetMessages(os.path.basename(PROJ), B.DESIGN, 0)
        txt = msgs[2] if isinstance(msgs, (list, tuple)) and len(msgs) > 2 else msgs
        lines = [z for z in str(txt).splitlines() if z.strip()]
        return lines[-n:]
    except Exception as e:
        return ["(GetMessages 失败: %r)" % e]


def clean_solution(tag=""):
    """删掉已提取过的求解数据（场/网格/自适应趟），控制 .aedtresults 体积。

    原始 L 矩阵已写进 raw CSV，这些数据之后不再需要；每点清一次可让磁盘占用恒定。
    清掉旧解还有额外好处：下一个点的轮询不可能误读到上一个点的"已解"状态。
    """
    if CLEAN == "off":
        return 0.0
    t0 = time.time()
    try:
        SESS["m"].cleanup_solution()          # -> odesign.DeleteFullVariation(["All"])
    except Exception as e:
        log("  清理求解数据失败 %s: %r" % (tag, e))
        return 0.0
    dt = time.time() - t0
    if dt > 3.0:
        log("  清理求解数据 %s: %.1fs" % (tag, dt))
    return dt


def solve_point(x, tag):
    """解一个接收位置，返回 (status, dict|None)。"""
    if os.path.exists(PTCSV):
        os.remove(PTCSV)
    B.OUT_CSV = PTCSV
    m = SESS["m"]
    g = float(tag["spacing_ratio"])
    dg = tag["_dg"]
    B.set_rx_dx(m, x + 0.05)          # 0.05mm 往返强制网格失效（生产口径）
    B.set_rx_dx(m, x)
    t0 = time.time()
    st, ok = B.run_stage("x=%.3f" % x, lambda: B.solve_and_extract(
        SESS["d"], m, tag["coil_size"], tag["hole_ratio"], g,
        dg["tx_bar_w"], 30.0 - dg["tx_bar_w"], x, MU, tag["rx_thick"]), B.SOLVE_TIMEOUT)
    dt = (time.time() - t0) / 60.0
    row = None
    if os.path.exists(PTCSV):
        lines = [z.strip() for z in open(PTCSV) if z.strip()]
        if len(lines) > 1:
            v = lines[-1].split(",")
            if len(v) >= 16:
                try:
                    fv = [float(z) for z in v]
                    if not any(math.isnan(z) for z in fv[8:16]) and fv[8] > 0:
                        row = dict(L11=fv[8], L22=fv[9], L33=fv[10], M12=fv[11],
                                   M13=fv[12], M23=fv[13], k13=fv[14], k23=fv[15])
                except ValueError:
                    row = None
    if row is None:
        for line in aedt_messages():
            log("      AEDT: %s" % line[:220])
    return (st if row else ("ERR" if st == "OK" else st)), row, dt


def main():
    os.makedirs(ROOT, exist_ok=True)
    log("=" * 78)
    log("契约采集 worker 启动：plan=%s BOX=X±%.0f Y[%.2f,%.0f] Z[-45,75] 超时=几何%ds/求解%ds XS=%s"
        % (os.path.basename(PLAN), BOXX, -134.94, BOXY, B.STAGE_TIMEOUT, B.SOLVE_TIMEOUT,
           XS_ENV or "半扫21点"))
    RES["timeouts"] = {"stage": B.STAGE_TIMEOUT, "solve": B.SOLVE_TIMEOUT}
    RES["path_mode"] = CG.PATH_MODE
    with open(PLAN, encoding="utf-8-sig") as f:
        cases = list(csv.DictReader(f))
    for c in cases:
        for k in ("coil_size", "hole_ratio", "tx_fill", "rx_fill",
                  "tx_thick", "rx_thick", "spacing_ratio"):
            c[k] = float(c[k])
    if CASE_LIMIT:
        cases = cases[:CASE_LIMIT]
    log("本实例 %d 个工况" % len(cases))

    migrate_raw()                       # 旧表头 -> 新表头（补 mesh 列），必须在 read_raw 之前
    done = read_raw()
    log("已有原始点 %d 个（断点续跑）" % len(done))
    open_session()

    def repair_partial(where, only=None):
        """把「解过一部分但缺点的工况」用 BASE 口径补齐缺失点。

        这批缺失点通常是 OPT 口径下确定性解不出来的位置（实测 b1_0126 的 x=+24.854）。
        缺失点用 BASE 口径补，同工况内会出现两种网格口径 —— 单点差异约 0.25%，
        远优于整条工况缺失；口径混合情况由 contract_merge 在诊断表里打标。

        only: 只补该集合内的工况（用于「启动补偿」只补上次确认失败的，避免把
              刚开头、尚未跑完的工况也整套重跑）。
        """
        if not MESH_FALLBACK or XS_ENV:
            return
        part = []
        for v0 in cases:
            if only is not None and v0["case_id"] not in only:
                continue
            xs0 = WC.sweep_positions_half(v0["coil_size"], v0["spacing_ratio"])
            have0 = sum(1 for i in range(len(xs0)) if (v0["case_id"], i) in done)
            if 0 < have0 < len(xs0):
                part.append((v0["case_id"], have0, len(xs0)))
        if not part:
            return
        log("【%s补偿】%d 个工况有点缺失（多为 OPT 口径下 Status=Error）-> 用 BASE 口径补齐"
            % (where, len(part)))
        set_mesh_base()
        try:
            for c0, have0, n0 in part:
                v0 = next(x for x in cases if x["case_id"] == c0)
                xs0 = WC.sweep_positions_half(v0["coil_size"], v0["spacing_ratio"])
                t0 = time.time()
                st, dd0 = B.run_stage("几何(补偿) %s" % c0,
                                      lambda: build_case(SESS["m"], v0), B.STAGE_TIMEOUT)
                if st != "OK" or not dd0:
                    log("  !! 补偿几何失败 %s: %s -> 重开会话，留待下次补偿" % (c0, st))
                    SESS["restarts"] += 1
                    open_session()
                    continue
                v0["_dg"] = dd0
                miss = [i for i in range(len(xs0)) if (c0, i) not in done]
                log("  补偿 %s：缺 %d/%d 点，BASE 口径重解" % (c0, len(miss), len(xs0)))
                got = 0
                for i in miss:
                    st2, row, dt = solve_point(xs0[i], v0)
                    if row is None:
                        log("    !! 补偿仍失败 %s x=%+.3f（%s）" % (c0, xs0[i], st2))
                        continue
                    raw = dict(row)
                    raw.update(case_id=c0, i=i, x_mm=round(xs0[i], 6), minutes=round(dt, 3),
                               aedt_pid=SESS["pid"], ts=time.strftime("%Y-%m-%d %H:%M:%S"),
                               mesh=MESH[0])
                    append_raw(raw)
                    done[(c0, i)] = raw
                    got += 1
                    log("    ✓ %s x=%+.3f  %.2f min  L11=%.3f M13=%.3f M23=%.3f（BASE）"
                        % (c0, xs0[i], dt, row["L11"], row["M13"], row["M23"]))
                RES.setdefault("repairs", []).append(
                    dict(case_id=c0, missing=len(miss), got=got,
                         minutes=round((time.time() - t0) / 60.0, 2), where=where))
                dump()
        finally:
            # ★ 无论成功或异常都必须恢复，否则后续所有工况会静默降级成 BASE 口径
            set_mesh_opt()
            log("【%s补偿】结束，已恢复 OPT 口径" % where)

    # 上次运行里状态为 partial 的工况：只有这些才在「启动补偿」里补，
    # 避免把刚开头、还没跑完的工况也整套用 BASE 重跑。
    prev_partial = set()
    try:
        if os.path.exists(OUTJSON):
            _pv = json.load(open(OUTJSON, encoding="utf-8-sig"))
            prev_partial = {c["case_id"] for c in _pv.get("cases", [])
                            if c.get("status") == "partial"}
    except Exception:
        prev_partial = set()
    if prev_partial:
        log("上次运行确认失败的工况 %d 个：%s" % (len(prev_partial), sorted(prev_partial)))

    repair_partial("启动", only=prev_partial)
    for ci, v in enumerate(cases):
        cid = v["case_id"]
        xs = XS_ENV if XS_ENV else WC.sweep_positions_half(v["coil_size"], v["spacing_ratio"])
        need = list(range(len(xs)))
        have = [i for i in need if (cid, i) in done]
        if len(have) == len(need):
            log("[%d/%d] %s 已完成（%d 点），跳过" % (ci + 1, len(cases), cid, len(need)))
            RES["cases"].append(dict(case_id=cid, status="skipped", points=len(need)))
            dump()
            continue
        log("[%d/%d] === %s === LC=%.2f KR=%.4f tf=%.3f rf=%.3f tt=%.2f rt=%.2f g=%+.4f，待解 %d 点"
            % (ci + 1, len(cases), cid, v["coil_size"], v["hole_ratio"], v["tx_fill"],
               v["rx_fill"], v["tx_thick"], v["rx_thick"], v["spacing_ratio"],
               len(need) - len(have)))

        # 工况边界是唯一安全的轮换点：此处没有进行中的求解，且几何本来就要重建。
        recycle_session(cid, ci + 1, len(cases))

        t_case = time.time()
        rec = dict(case_id=cid, status="running", points=len(need), solved=0, fail=[])

        # ---- 几何（挂死则重开会话重试一次）----
        geom_ok = False
        for attempt in range(B.HANG_RETRIES + 1):
            st, dd = B.run_stage("几何 %s" % cid, lambda: build_case(SESS["m"], v),
                                 B.STAGE_TIMEOUT)
            if st == "OK":
                geom_ok = True
                v["_dg"] = dd
                rec.update(n_bars_rx=dd["n_bars_rx"], tx_bar_w=round(dd["tx_bar_w"], 4),
                           rx_bar_w=round(dd["rx_bar_w"], 4),
                           ferrite_len=dd["ferrite_len"], edge_gap=dd["edge_gap"],
                           rx_volume=round(dd["rx_volume"], 2))
                break
            log("  !! 几何 %s（第 %d 次）" % (st, attempt + 1))
            SESS["restarts"] += 1
            open_session()
        if not geom_ok:
            rec["status"] = "geom_failed"
            log("  !! %s 几何连续失败，跳过" % cid)
            RES["cases"].append(rec)
            dump()
            continue

        # ---- 逐点求解 ----
        for i, x in enumerate(xs):
            if (cid, i) in done:
                rec["solved"] += 1
                continue
            st, row, dt = solve_point(x, v)
            mesh_used = effective_mesh(v["coil_size"], v["hole_ratio"])
            # ★ 同会话 BASE 口径重试（2026-09-19）：实测 ~9% 的点在 OPT 口径下失败，
            # 错误文件 nominalmesh.g3derr 明确写 "Body surface mesh area is different
            # from geometry area by 1%-5%(planar)/5%-10%(curved)" —— 即文档失败模式 #4
            # 的 TAU Flex 表面网格损坏，但**与位置相关、集中在大线圈的大偏移处**，
            # 文档的 OPT_MIN_GAP 闸门（只防紧几何）挡不住。
            # 失败后不重启会话、不重建几何，直接切成 BASE 口径再解一次：省掉约 10 分钟
            # 会话重启，而且能把该点救回来（不让它变成缺失点）。口径按点记进 raw 的 mesh 列。
            if row is None and MESH_FALLBACK and MESH[0] == "OPT":
                log("  !! [%d/%d] %s x=%+.3f 在 OPT 口径下失败（%.2f min）"
                    "-> 同会话改 BASE 口径重试" % (i + 1, len(xs), cid, x, dt))
                set_mesh_base()
                st2, row2, dt2 = solve_point(x, v)
                dt += dt2
                set_mesh_opt()
                if row2 is not None:
                    row, st, mesh_used = row2, st2, "BASE"
            if row is None:
                log("  !! [%d/%d] %s x=%+.3f %s（%.2f min）重开会话后重试一次"
                    % (i + 1, len(xs), cid, x, st, dt))
                SESS["restarts"] += 1
                open_session()
                st2, dd2 = B.run_stage("几何(重试) %s" % cid,
                                       lambda: build_case(SESS["m"], v), B.STAGE_TIMEOUT)
                if st2 == "OK" and dd2:
                    v["_dg"] = dd2
                if st2 != "OK":
                    rec["fail"].append(i)
                    log("  !! 重试时几何失败，该点放弃")
                    continue
                st, row, dt = solve_point(x, v)
            if row is None:
                rec["fail"].append(i)
                log("  !! [%d/%d] %s x=%+.3f 求解失败（%.2f min），记失败后继续"
                    % (i + 1, len(xs), cid, x, dt))
                continue
            raw = dict(row)
            raw.update(case_id=cid, i=i, x_mm=round(x, 6), minutes=round(dt, 3),
                       aedt_pid=SESS["pid"], ts=time.strftime("%Y-%m-%d %H:%M:%S"),
                       mesh=mesh_used)
            append_raw(raw)
            done[(cid, i)] = raw
            rec["solved"] += 1
            if mesh_used != "OPT":
                rec.setdefault("mesh_fallback_points", []).append(i)
            log("  [%d/%d] %s x=%+9.3f  %s  %.2f min  L11=%.3f L33=%.3f M13=%.3f M23=%.3f k13=%.4f"
                % (i + 1, len(xs), cid, x, st, dt, row["L11"], row["L33"],
                   row["M13"], row["M23"], row["k13"]))
            dump()
            if CLEAN == "point":
                rec["clean_s"] = round(rec.get("clean_s", 0.0) + clean_solution("%s#%d" % (cid, i)), 1)
        if CLEAN == "case":
            rec["clean_s"] = round(clean_solution(cid), 1)
        # 本工况若仍有点缺失 -> 立刻用 BASE 口径补齐，别让它长期不完整
        # （缺失点通常就是 OPT 口径下确定性解不出来的位置，见上方 g3derr 证据）
        if rec["fail"] and MESH_FALLBACK and not XS_ENV:
            log("!! %s 仍缺 %d 点 -> 立刻用 BASE 口径补齐" % (cid, len(rec["fail"])))
            try:
                repair_partial("工况后", only={cid})
            except Exception as e:
                log("  !! 工况后补偿异常: %r" % e)
            have_now = sum(1 for i in range(len(need)) if (cid, i) in done)
            rec["solved"] = have_now
            rec["fail"] = [i for i in range(len(need)) if (cid, i) not in done]
        rec["minutes"] = round((time.time() - t_case) / 60.0, 2)
        rec["status"] = "done" if not rec["fail"] and rec["solved"] == len(need) else "partial"
        log("=== %s %s：%d/%d 点，%.1f 分钟（口径 %s%s）==="
            % (cid, rec["status"], rec["solved"], len(need), rec["minutes"],
               "+".join(sorted({(done[(cid, i)].get("mesh") or "OPT")
                                for i in range(len(need)) if (cid, i) in done})),
               "，含补偿" if rec.get("mesh_fallback_points") else ""))
        RES["cases"].append(rec)
        dump()

    repair_partial("收尾")
    RES["t_end"] = time.strftime("%Y-%m-%d %H:%M:%S")
    log("worker 结束：%d 个工况，会话重启 %d 次" % (len(cases), SESS["restarts"]))
    dump()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        RES["fatal"] = traceback.format_exc()
        log("!! worker 致命错误\n" + RES["fatal"])
    finally:
        dump()
        kill_own()
