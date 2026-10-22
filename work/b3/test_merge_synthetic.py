# -*- coding: utf-8 -*-
"""契约 CSV 生成器离线自测：用合成原始结果跑 contract_merge，检查列名/行数/展开/自检。

不启动 AEDT。合成数据构造成完全可验证的形式：
    M13(x) = A*exp(-((x+c)/w)^2)   （Tx1 在 -c 附近）
    M23(x) = A*exp(-((x-c)/w)^2)   （Tx2 在 +c 附近）
    M12    = -2.2 + 微小漂移（验证 M_pp 的路径均值口径）
    L11/L22/L33 常数 + 1% 噪声；k = M/sqrt(L*L33)
"""
import csv
import json
import math
import os
import shutil
import subprocess
import sys

ROOT = r"C:\ansys maxwell2024\_work\b1syn"
PLAN = r"C:\ansys maxwell2024\_work\b1_plan.csv"
MERGE = r"C:\ansys maxwell2024\_work\b1\contract_merge.py"
sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                 # noqa: E402  沙箱禁管道：把 capture_output 改成临时文件
sys.path.insert(0, r"C:\wpt")
import wpt_contract as WC        # noqa: E402

RAW_COLS = ["case_id", "i", "x_mm", "L11", "L22", "L33", "M12", "M13", "M23",
            "k13", "k23", "minutes", "aedt_pid", "ts"]


def main():
    shutil.rmtree(ROOT, ignore_errors=True)
    os.makedirs(ROOT, exist_ok=True)
    rows = list(csv.DictReader(open(PLAN, encoding="utf-8-sig")))
    keep = rows[:3]
    with open(os.path.join(ROOT, "b1_plan.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(list(keep[0].keys()))
        for r in keep:
            w.writerow([r[k] for k in keep[0].keys()])

    raws = [os.path.join(ROOT, "b1_raw_run%d.csv" % k) for k in range(2)]
    files = [open(p, "w", newline="", encoding="utf-8") for p in raws]
    ws = [csv.writer(f) for f in files]
    for w in ws:
        w.writerow(RAW_COLS)
    meta = []
    for ci, r in enumerate(keep):
        cid = r["case_id"]
        LC = float(r["coil_size"]); g = float(r["spacing_ratio"])
        xs = WC.sweep_positions_half(LC, g)
        c = LC * (1.0 + g / 2.0) / 2.0
        w_ = LC / 4.0
        d = WC.derived(LC, g, float(r["tx_fill"]), float(r["rx_fill"]), float(r["rx_thick"]))
        meta.append((cid, len(xs), d))
        for i, x in enumerate(xs):
            M13 = 8.0 * math.exp(-((x + c) / w_) ** 2)
            M23 = 8.0 * math.exp(-((x - c) / w_) ** 2)
            L11 = 20.5 + 0.01 * ((i % 3) - 1)
            L22 = 20.6 + 0.01 * ((i % 3) - 1)
            L33 = 25.0 + 0.05 * ((i % 5) - 2)
            M12 = -2.2 - 0.0002 * i
            ws[ci % 2].writerow([cid, i, "%.6f" % x, L11, L22, L33,
                                 "%.4f" % M12, "%.4f" % M13, "%.4f" % M23,
                                 "%.5f" % (M13 / math.sqrt(L11 * L33)),
                                 "%.5f" % (M23 / math.sqrt(L22 * L33)),
                                 "6.0", 1234, "2026-09-19 00:00:00"])
    for f in files:
        f.close()

    r = subprocess.run([r"C:\anaconda\python.exe", MERGE, "--batch", "b1", "--root", ROOT],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout)
    if r.returncode:
        print("STDERR:", r.stderr[-2000:])
        raise SystemExit(1)

    outdir = os.path.join(ROOT, "out")
    cases = list(csv.DictReader(open(os.path.join(outdir, "b1_cases.csv"), encoding="utf-8")))
    curves = list(csv.DictReader(open(os.path.join(outdir, "b1_curves.csv"), encoding="utf-8")))
    chk = list(csv.DictReader(open(os.path.join(outdir, "b1_selfcheck.csv"), encoding="utf-8")))
    diag = list(csv.DictReader(open(os.path.join(outdir, "b1_diag.csv"), encoding="utf-8")))

    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("  OK   " if cond else "  FAIL ") + msg)
        ok = ok and cond

    print("-" * 70)
    check(list(cases[0].keys()) == WC.CASES_COLS, "cases 列名逐字对齐契约 (%d 列)" % len(WC.CASES_COLS))
    check(list(curves[0].keys()) == WC.CURVES_COLS, "curves 列名逐字对齐契约 (%d 列)" % len(WC.CURVES_COLS))
    check(len(cases) == len(keep), "cases 行数 = %d" % len(cases))
    check(len(curves) == 41 * len(keep), "curves 行数 = %d (41×%d)" % (len(curves), len(keep)))
    for c in cases:
        rows_c = [z for z in curves if z["case_id"] == c["case_id"]]
        check(len(rows_c) == 41, "%s 曲线 41 行" % c["case_id"])
        xs = [float(z["position_x"]) for z in rows_c]
        check(all(xs[i] < xs[i + 1] for i in range(40)), "%s position_x 升序" % c["case_id"])
        check(abs(sum(xs) / 41) < 1e-3, "%s 曲线关于 0 对称（均值 %.2e）" % (c["case_id"], sum(xs) / 41))
        d = [xs[i + 1] - xs[i] for i in range(40)]
        check(max(d) - min(d) < 1e-3, "%s 点位等距" % c["case_id"])
        # 镜像关系：M1(-x) == M2(+x)
        by = {round(float(z["position_x"]), 4): (float(z["M1"]), float(z["M2"])) for z in rows_c}
        worst = max(abs(by[round(-x, 4)][0] - by[round(x, 4)][1])
                    for x in sorted(by) if x > 0)
        check(worst < 1e-6, "%s 展开镜像关系逐位成立 (max %.2e)" % (c["case_id"], worst))
        check(all(z["M_pp"] == "" for z in rows_c), "%s 曲线表 M_pp 留空（由 cases 回退）" % c["case_id"])
    check(all(r["mirror_pass"] == "True" for r in chk), "自检 mirror_pass 全通过")
    check(all(r["k_ok"] == "True" and r["L_positive"] == "True" for r in chk), "k/L 有效性通过")
    check(all(r["equidistant"] == "True" for r in chk), "等距标记通过")
    for c, m in zip(cases, meta):
        expect = -2.2 - 0.0002 * (m[1] - 1) / 2.0
        got = float(c["M_pp"])
        check(abs(got - expect) < 0.02, "%s M_pp=%.4f（路径均值口径，期望≈%.4f）" % (c["case_id"], got, expect))
        check(float(c["ferrite_len"]) == m[2]["ferrite_len"], "%s ferrite_len=%s = 1.2*Lc 取整"
              % (c["case_id"], c["ferrite_len"]))
        check(abs(float(c["edge_gap"]) - m[2]["edge_gap"]) < 1e-9, "%s edge_gap=%s（取整口径）"
              % (c["case_id"], c["edge_gap"]))
    print("-" * 70)
    print("自测%s" % ("通过 ✓" if ok else "失败 ✗"))
    print("样例 cases 行: %s" % json.dumps(cases[0], ensure_ascii=False)[:220])
    print("样例 diag  行: %s" % json.dumps(diag[0], ensure_ascii=False)[:220])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
