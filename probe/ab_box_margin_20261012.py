# -*- coding: utf-8 -*-
r"""A/B 实测：空气域固定盒 X±420 vs X±440 对结果的影响（判定 5 个"留边不足"工况能否照跑）。

背景：b2 参数表里有 5 个工况的 `need_x + 40mm留边` 略微超过 X±420（最坏 b2_0643 超 3.47 mm），
但**物体实际仍在盒内 36.5~39 mm**，`ensure_region()` 的硬判据（物体超出才失败）不会触发。
风险只在于：留边从 ≥40 缩小到 36.5，会不会因边界（默认自然边界，非 Open）更近而改变结果。

判据：Ab 对比**同一个工况、同一个扫描点**（该点接收线圈最远触及盒面）在两个盒宽下的
L/M。若 |Δ| 落在文档记录的 ~1% 会话间网格噪声内 → 边界影响不可测 → 可照跑。

用法： python ab_box_margin_20261012.py [--case b2_0643] [--point auto] [--boxA 420] [--boxB 440]
"""
import argparse
import csv
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
WORKER = r"C:\ansys maxwell2024\_work\b2\contract_worker.py"
BASE_PROJECT = r"C:\ansys maxwell2024\_work\Projecttonight_ref.aedt"
SRC = r"C:\Users\Administrator\Desktop\数据采集序列\batch2_samples_shard1.csv"
COLS = ["coil_size", "hole_ratio", "tx_fill", "rx_fill", "tx_thick", "rx_thick", "spacing_ratio"]
METRICS = ["L11", "L22", "L33", "M12", "M13", "M23", "k13", "k23"]


def run_one(tag, row, box, xmm, keep):
    root = os.path.join(tempfile.gettempdir(), "ab_box_%s" % tag)
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, exist_ok=True)
    cid = row["case_id"]
    with io.open(os.path.join(root, "ab_plan_shard0.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["case_id"] + COLS)
        w.writerow([cid] + [row[c] for c in COLS])
    shutil.copy2(BASE_PROJECT, os.path.join(root, "Projecttonight_ab_run0.aedt"))
    env = dict(os.environ)
    env.update({"PYTHONIOENCODING": "utf-8", "WPT_BATCH": "ab", "WPT_ROOT": root,
                "WPT_RUN": "0", "WPT_PLAN": os.path.join(root, "ab_plan_shard0.csv"),
                "WPT_CASES": "1", "WPT_XS": str(xmm),
                "WPT_BOXX": str(box), "WPT_BOXY": "161", "WPT_PATH_MODE": "ring",
                "WPT_CLEAN": "point", "WPT_MESH_FALLBACK": "1"})
    for k in ("WPT_EDGE_GAP", "WPT_KR", "WPT_LC"):
        env.pop(k, None)
    out = io.open(os.path.join(root, "ab_stdout.txt"), "w", encoding="utf-8", errors="replace")
    p = subprocess.Popen([PY, WORKER], env=env, cwd=root, stdout=out, stderr=subprocess.STDOUT)
    return root, p, out


def read_point(root, cid):
    raw = os.path.join(root, "ab_raw_run0.csv")
    if not os.path.exists(raw):
        return None
    with io.open(raw, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("case_id") == cid:
                return r
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="b2_0643")
    ap.add_argument("--boxA", type=float, default=420.0)
    ap.add_argument("--boxB", type=float, default=440.0)
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()

    with io.open(SRC, encoding="utf-8-sig") as f:
        rows = {r["case_id"]: r for r in csv.DictReader(f)}
    if a.case not in rows:
        print("参数表里没有 %s" % a.case)
        return 1
    row = rows[a.case]
    LC, g = float(row["coil_size"]), float(row["spacing_ratio"])
    S = LC * (2.0 + g)
    xmm = round(S / 2.0, 4)                 # 半扫最后一个点 = 接收线圈最远触及盒面
    print("工况 %s：LC=%.4f g=%+.4f -> S=%.3f mm，取最远点 x=+%.3f mm" % (a.case, LC, g, S, xmm))
    print("A 盒 X±%.0f ｜ B 盒 X±%.0f（并行跑 1 实例 1 点）\n" % (a.boxA, a.boxB), flush=True)

    ra, pa, oa = run_one("A", row, a.boxA, xmm, a.keep)
    rb, pb, ob = run_one("B", row, a.boxB, xmm, a.keep)
    t0 = time.time()
    pa.wait()
    print("A 盒完成（%.1f min，退出码 %s）" % ((time.time() - t0) / 60.0, pa.returncode), flush=True)
    pb.wait()
    print("B 盒完成（共 %.1f min，退出码 %s）\n" % ((time.time() - t0) / 60.0, pb.returncode), flush=True)

    rA, rB = read_point(ra, a.case), read_point(rb, a.case)
    if not rA or not rB:
        print("!! 至少一侧没解出点：A=%s B=%s" % (bool(rA), bool(rB)))
        print("   A stdout: %s\n   B stdout: %s" % (os.path.join(ra, "ab_stdout.txt"),
                                                    os.path.join(rb, "ab_stdout.txt")))
        return 1

    print("=" * 88)
    print("A/B 结果对比（同一工况、同一扫描点 x=+%.3f，仅空气域盒不同）" % xmm)
    print("=" * 88)
    print("  %-6s %14s %14s %10s" % ("量", "A: X±%.0f" % a.boxA, "B: X±%.0f" % a.boxB, "相对偏差"))
    worst = 0.0
    for k in METRICS:
        try:
            va, vb = float(rA[k]), float(rB[k])
        except (KeyError, ValueError):
            continue
        rel = abs(vb - va) / max(abs(va), 1e-12) * 100.0
        worst = max(worst, rel)
        print("  %-6s %14.5f %14.5f %9.3f%%" % (k, va, vb, rel))
    print("\n  最大相对偏差 = %.3f%%" % worst)
    print("  A: mesh=%s minutes=%s ｜ B: mesh=%s minutes=%s"
          % (rA.get("mesh"), rA.get("minutes"), rB.get("mesh"), rB.get("minutes")))
    print("\n判据：文档记录的会话间网格噪声约 1%。")
    if worst <= 1.0:
        print("结论：偏差 %.3f%% ≤ 1%% —— 盒宽 420 vs 440（20 mm，是越界量的 5.8 倍）"
              "都测不出边界影响，故 5 个工况照跑安全。" % worst)
    else:
        print("结论：偏差 %.3f%% > 1%% —— 边界影响超出噪声，**不要**照跑，"
              "应改为排除这 5 个工况或扩盒。" % worst)
    if not a.keep:
        shutil.rmtree(ra, ignore_errors=True)
        shutil.rmtree(rb, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
