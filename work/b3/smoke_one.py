# -*- coding: utf-8 -*-
r"""正式启动前的单实例冒烟：用**真实参数表里的一行** + 1 个扫描点，跑通整条链路。

为什么需要它（第一轮的教训）：静态审查过的东西，第一次实跑才会暴露问题。
本脚本跑的与正式批次是同一份代码，只把工况数限成 1、扫描点限成 1 个，约 8~12 分钟，
一次性验证：AEDT 会话 / 几何重建 / 网格闸门 / 求解与提取 / raw 落盘格式 / 日志编码 / 会话清理。

**完全在临时目录里跑**，不碰 `<root>` 里任何真实批次文件（只读取参数表与基础工程）。
跑完自动核对产物并清理（`--keep` 可保留现场）。

用法：
  python smoke_one.py --root "C:\ansys maxwell2024\_work\b2" --batch b2          # 自动挑第 32 个验收点之后的第一个工况
  python smoke_one.py --root ... --batch b2 --case b2_0007

退出码：0 = 冒烟通过；1 = 失败（**不要**启动正式批次）；2 = 自身异常。
"""
import argparse
import csv
import glob
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

PY = r"C:\anaconda\python.exe"
HERE = os.path.dirname(os.path.abspath(__file__))
BASE_PROJECT = r"C:\ansys maxwell2024\_work\Projecttonight_ref.aedt"
MAIN_COLS = ["coil_size", "hole_ratio", "tx_fill", "rx_fill",
             "tx_thick", "rx_thick", "spacing_ratio"]


def verify(root, batch, case_id):
    """核对冒烟产物。返回 (ok, 消息列表)。"""
    msgs = []
    ok = True

    raw = os.path.join(root, "%s_raw_run0.csv" % batch)
    rows = []
    if os.path.exists(raw):
        with io.open(raw, encoding="utf-8-sig") as f:
            rows = [r for r in csv.DictReader(f) if r.get("case_id") == case_id]
    if len(rows) != 1:
        ok = False
        msgs.append("FAIL  raw 里应有该工况 1 行，实际 %d 行" % len(rows))
    else:
        r = rows[0]
        need = ["case_id", "i", "x_mm", "L11", "L22", "L33", "M12", "M13", "M23",
                "k13", "k23", "minutes", "aedt_pid", "ts", "mesh"]
        miss = [c for c in need if c not in r]
        if miss:
            ok = False
            msgs.append("FAIL  raw 缺列: %s" % miss)
        else:
            msgs.append("OK    raw 15 列齐全；i=%s x=%s mesh=%s minutes=%s"
                        % (r["i"], r["x_mm"], r["mesh"], r["minutes"]))
            if r["mesh"] not in ("OPT", "BASE"):
                ok = False
                msgs.append("FAIL  mesh 列取值非法: %r" % r["mesh"])
            try:
                if float(r["L11"]) <= 0 or float(r["L33"]) <= 0:
                    ok = False
                    msgs.append("FAIL  自感非正（物理上不可能）")
            except ValueError:
                ok = False
                msgs.append("FAIL  自感不可解析")

    jp = os.path.join(root, "%s_worker_run0.json" % batch)
    if os.path.exists(jp):
        try:
            d = json.load(io.open(jp, encoding="utf-8-sig"))
            msgs.append("OK    worker JSON 可解析：cases=%d path_mode=%s box.x=%s"
                        % (len(d.get("cases") or []), d.get("path_mode"),
                           (d.get("box") or {}).get("x")))
            if d.get("fatal"):
                ok = False
                msgs.append("FAIL  worker JSON 里有 fatal")
            if d.get("path_mode") != "ring":
                ok = False
                msgs.append("FAIL  path_mode=%r（应为 ring）" % d.get("path_mode"))
        except (OSError, ValueError) as e:
            ok = False
            msgs.append("FAIL  worker JSON 解析失败: %r" % (e,))
    else:
        ok = False
        msgs.append("FAIL  没有 worker JSON")

    if glob.glob(os.path.join(root, "*.tmp")):
        ok = False
        msgs.append("FAIL  有 .tmp 残留（原子写被破坏）")

    lg = os.path.join(root, "%s_worker_run0.log" % batch)
    if os.path.exists(lg):
        try:
            io.open(lg, encoding="utf-8").read()
            msgs.append("OK    worker 日志是合法 UTF-8")
        except UnicodeDecodeError as e:
            ok = False
            msgs.append("FAIL  worker 日志不是合法 UTF-8（编码混编回归）: %s" % e)

    n_left = 0
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "@(Get-Process -Name ansysedt,3dnms,G3dMesher,ansyscl "
                            "-ErrorAction SilentlyContinue).Count"],
                           capture_output=True, text=True, timeout=60)
        n_left = int((r.stdout or "0").strip() or 0)
    except (OSError, ValueError, subprocess.SubprocessError):
        n_left = -1
    if n_left == 0:
        msgs.append("OK    收工后无 AEDT 家族残留进程")
    elif n_left > 0:
        msgs.append("WARN  仍有 %d 个 AEDT 家族进程（正式启动前必须清零，并等 ≥4 min）" % n_left)
    return ok, msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--batch", default="b2")
    ap.add_argument("--case", default=None, help="指定 case_id（默认取参数表第 33 行，即验收点之后）")
    ap.add_argument("--keep", action="store_true", help="保留冒烟现场不清理")
    ap.add_argument("--non-graphical", action="store_true",
                    help="用无界面模式启动 AEDT（会话 0 / 计划任务里必须用它）。"
                         "⚠️ 2026-10-13 事故的关键：GUI 模式在 S4U 会话里起不来。")
    ap.add_argument("--timeout-min", type=float, default=45.0)
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    plan = os.path.join(root, "%s_plan.csv" % a.batch)
    if not os.path.exists(plan):
        print("找不到参数表 %s —— 先跑 prepare_b2.py" % plan)
        return 1
    with io.open(plan, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("参数表为空")
        return 1
    if a.case:
        hit = [r for r in rows if r["case_id"] == a.case]
        if not hit:
            print("参数表里没有 %s" % a.case)
            return 1
        row = hit[0]
    else:
        row = rows[min(32, len(rows) - 1)]
    cid = row["case_id"]
    miss = [c for c in MAIN_COLS if c not in row]
    if miss:
        print("参数表缺列: %s" % miss)
        return 1

    if not os.path.exists(BASE_PROJECT):
        print("找不到基础工程 %s" % BASE_PROJECT)
        return 1

    S = os.path.join(tempfile.gettempdir(), "%s_smoke" % a.batch)
    shutil.rmtree(S, ignore_errors=True)
    os.makedirs(S, exist_ok=True)
    hdr = ["case_id"] + MAIN_COLS
    with io.open(os.path.join(S, "%s_plan_shard0.csv" % a.batch), "w",
                 encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(hdr)
        w.writerow([cid] + [row[c] for c in MAIN_COLS])
    shutil.copy2(BASE_PROJECT, os.path.join(S, "Projecttonight_%s_run0.aedt" % a.batch))

    env = dict(os.environ)
    env.update({"PYTHONIOENCODING": "utf-8", "WPT_BATCH": a.batch, "WPT_ROOT": S,
                "WPT_RUN": "0", "WPT_PLAN": os.path.join(S, "%s_plan_shard0.csv" % a.batch),
                "WPT_CASES": "1", "WPT_XS": "0",
                "WPT_BOXX": "420", "WPT_BOXY": "161", "WPT_PATH_MODE": "ring",
                "WPT_CLEAN": "point", "WPT_MESH_FALLBACK": "1",
                "WPT_NON_GRAPHICAL": "1" if a.non_graphical else
                                     os.environ.get("WPT_NON_GRAPHICAL", "0")})
    for k in ("WPT_EDGE_GAP", "WPT_KR", "WPT_LC"):
        env.pop(k, None)

    print("=" * 84)
    print("单实例冒烟：case=%s  参数=%s" % (cid, {c: row[c] for c in MAIN_COLS}))
    print("现场=%s（跑完%s）" % (S, "保留" if a.keep else "自动清理"))
    print("=" * 84, flush=True)
    t0 = time.time()
    p = subprocess.run([PY, os.path.join(HERE, "contract_worker.py")], env=env, cwd=S,
                       text=True, encoding="utf-8", errors="replace")
    mins = (time.time() - t0) / 60.0

    print("\n" + "=" * 84)
    print("冒烟核对（用时 %.1f 分钟，worker 退出码 %d）" % (mins, p.returncode))
    print("=" * 84)
    ok, msgs = verify(S, a.batch, cid)
    for m in msgs:
        print("  " + m)
    if p.returncode != 0:
        ok = False
        print("  FAIL  worker 退出码 %d（非 0）" % p.returncode)

    print("\n结论：%s" % ("**冒烟通过** —— 可以按 prepare_b2.py 打印的命令启动正式批次"
                        if ok else "**冒烟未通过** —— 先修问题，不要启动正式批次"))
    if a.keep or not ok:
        print("现场保留在：%s" % S)
    else:
        shutil.rmtree(S, ignore_errors=True)
        print("现场已清理（临时目录，未触碰真实批次目录）")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                      # noqa: BLE001
        print("\n[FAIL] smoke_one 自身异常：%r" % (exc,), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)
