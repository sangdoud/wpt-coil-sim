# -*- coding: utf-8 -*-
"""C：端到端单工况验证（6 实例分片跑完整 21 点半扫 + 镜像展开 + 自检 + 契约 CSV）。

流程：
  1) 复制 6 份干净工程副本（各自的 .aedtresults 清掉）
  2) 把半扫 21 点交错分片给 6 个 worker（生产配置：柔性+⑥+pref10+rres1e-5）
  3) 合并成 21 点曲线 -> 镜像展开成 41 点（M1(-x):=M2(+x)、M2(-x):=M1(+x)）
  4) 自检：双阈值镜像、|k|<=1、自感>0、点位等距
  5) 输出契约格式 CSV（cases / curves）+ 独立自检表

用法：WPT_N=6 python queueE2E_case.py
"""
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import wpt_contract as WC                       # noqa: E402
from patch_wpt_contract_mirror import mirror_check, case_asymmetry_tag  # noqa: E402

SRC = os.path.join(WORK, "Projecttonight_ref.aedt")
OUTDIR = os.path.join(WORK, "e2e")
LOGF = os.path.join(WORK, "e2e.log")
OUT = os.path.join(WORK, "e2e_result.json")
N = int(os.environ.get("WPT_N", "6"))
CASE_ID = os.environ.get("WPT_CASE", "e2e_ref")
LC = float(os.environ.get("WPT_LC", "167.2829"))
KR = float(os.environ.get("WPT_KR", "0.3587"))
KX = float(os.environ.get("WPT_KX", "-0.3"))
W, G, THK = 10.0, 20.0, 10.0


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    with open(LOGF, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def sweep_half(LC, g):
    S = LC * (2.0 + g)
    return [i * S / 40.0 for i in range(0, 21)]


def expand_curve(xs_half, M1_half, M2_half):
    left = []
    for k in range(len(xs_half) - 1, 0, -1):
        left.append((-xs_half[k], M2_half[k], M1_half[k]))
    full = left + [(xs_half[i], M1_half[i], M2_half[i]) for i in range(len(xs_half))]
    return [p[0] for p in full], [p[1] for p in full], [p[2] for p in full]


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    log("=" * 78)
    log("C：端到端单工况 %s（%d 实例，LC=%.4f KR=%.4f KX=%+.2f）" % (CASE_ID, N, LC, KR, KX))
    xs = sweep_half(LC, KX)
    log("  半扫点位: %s" % ["%.2f" % x for x in xs])
    for i in range(N):
        dst = os.path.join(WORK, "Projecttonight_e%d.aedt" % i)
        shutil.copy2(SRC, dst)
        for p in (dst + ".lock",):
            if os.path.exists(p):
                os.remove(p)
        rd = os.path.join(WORK, "Projecttonight_e%d.aedtresults" % i)
        if os.path.isdir(rd):
            shutil.rmtree(rd, ignore_errors=True)
    for i in range(N):
        for f in ("e_run%d.json" % i, "e_run%d.log" % i):
            p = os.path.join(WORK, f)
            if os.path.exists(p):
                os.remove(p)
    parts = [xs[i::N] for i in range(N)]
    env = dict(os.environ)
    env.update({"PYTHONIOENCODING": "utf-8", "WPT_LC": str(LC), "WPT_KR": str(KR),
                "WPT_KX": str(KX), "WPT_FLEX": "1", "WPT_SIX": "1",
                "WPT_PREF": "10", "WPT_RRES": "1e-05", "WPT_CORES": "8"})
    procs = []
    t0 = time.time()
    for i, pxs in enumerate(parts):
        e = dict(env)
        e["WPT_RUN"] = str(i)
        e["WPT_SUFFIX"] = "e%d" % i
        e["WPT_XS"] = ",".join("%.6f" % x for x in pxs)
        p = subprocess.Popen([r"C:\anaconda\python.exe",
                              r"C:\ansys maxwell2024\_probe\worker_e2e.py"],
                             env=e, cwd=WORK,
                             stdout=open(os.path.join(WORK, "e_stdout_%d.txt" % i), "w"),
                             stderr=subprocess.STDOUT)
        procs.append(p)
        log("  启动实例 %d：%d 个位置 %s" % (i, len(pxs), ["%.1f" % x for x in pxs]))
        time.sleep(20)
    for i, p in enumerate(procs):
        p.wait()
        log("  实例 %d 退出码 %s" % (i, p.returncode))
    wall = (time.time() - t0) / 60.0
    log("  六实例全部结束，墙钟 %.1f 分钟" % wall)

    rows = {}
    bad = []
    for i in range(N):
        p = os.path.join(WORK, "e_run%d.json" % i)
        if not os.path.exists(p):
            bad.append("run%d 无结果文件" % i)
            continue
        dd = json.load(open(p, encoding="utf-8"))
        for r in dd.get("rows", []):
            if not r.get("row"):
                bad.append("x=%.2f 无结果行" % r["x"])
                continue
            v = [float(z) for z in r["row"].split(",")]
            if any(math.isnan(z) for z in v[8:14]) or v[8] <= 0:
                bad.append("x=%.2f 无效(NaN/0)" % r["x"])
                continue
            rows[round(r["x"], 6)] = dict(x=r["x"], L11=v[8], L22=v[9], L33=v[10],
                                          M12=v[11], M1=v[12], M2=v[13], k13=v[14], k23=v[15],
                                          minutes=r["minutes"])
    log("  合并: %d/%d 点有效" % (len(rows), len(xs)))
    if bad:
        log("  !! 异常: %s" % bad[:6])

    res = {"case_id": CASE_ID, "wall_minutes": round(wall, 2), "n_valid": len(rows),
           "n_expected": len(xs), "bad": bad}
    if len(rows) == len(xs):
        xs_h = sorted(rows)
        M1h = [rows[x]["M1"] for x in xs_h]
        M2h = [rows[x]["M2"] for x in xs_h]
        xs_f, M1f, M2f = expand_curve(xs_h, M1h, M2h)
        mc = mirror_check(xs_f, M1f, M2f)
        tag = case_asymmetry_tag(CASE_ID, xs_f, M1f, M2f)
        # 契约口径（LC 换算走 k_lc()，不硬编码）
        import coil_gen as CG
        LC_doc = LC / CG.k_lc()
        d = WC.derived(LC_doc, KX, W / 30.0, W / 30.0, THK)
        L11f = [rows[x]["L11"] for x in xs_h]
        L33f = [rows[x]["L33"] for x in xs_h]
        k13f = [rows[x]["k13"] for x in xs_h]
        k23f = [rows[x]["k23"] for x in xs_h]
        Msum = [a + b for a, b in zip(M1f, M2f)]
        obj = dict(M_sum_mean=sum(Msum) / len(Msum),
                   M_sum_var=sum((v - sum(Msum) / len(Msum)) ** 2 for v in Msum) / len(Msum),
                   M_pp=sum(rows[x]["M12"] for x in xs_h) / len(xs_h),
                   M_pp_min=min(rows[x]["M12"] for x in xs_h),
                   M_pp_max=max(rows[x]["M12"] for x in xs_h))
        # 等距检查
        dpts = [xs_f[i + 1] - xs_f[i] for i in range(len(xs_f) - 1)]
        equi = (max(dpts) - min(dpts)) < 1e-3     # mm 量级容差（点位经 6 位小数往返）
        k_ok = all(abs(v) < 1 for v in k13f + k23f)
        L_ok = all(v > 0 for v in L11f + L33f)
        # 写契约 CSV
        curve_csv = os.path.join(OUTDIR, "%s_curves.csv" % CASE_ID)
        with open(curve_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(WC.CURVES_COLS)
            for i, x in enumerate(xs_f):
                src = min(xs_h, key=lambda z: abs(z - abs(x)))
                r = rows[src]
                # M_pp 与位置无关（原边两发射线圈互感，路径均值口径），曲线表留空，
                # 由 cases 表的标量回退 —— 见《改动方案》3.5 节
                w.writerow([CASE_ID, round(x, 4), M1f[i], M2f[i], "",
                            r["L11"], r["L22"], r["L33"], r["k13"], r["k23"]])
        case_csv = os.path.join(OUTDIR, "%s_cases.csv" % CASE_ID)
        with open(case_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(WC.CASES_COLS)
            row = WC.build_case_row(CASE_ID, dict(coil_size=round(LC_doc, 4), hole_ratio=KR,
                                                  tx_fill=round(W / 30.0, 4),
                                                  rx_fill=round(W / 30.0, 4),
                                                  tx_thick=THK, rx_thick=THK,
                                                  spacing_ratio=KX),
                                    d, round(obj["M_pp"], 4))
            w.writerow([row.get(c, "") for c in WC.CASES_COLS])
        chk_csv = os.path.join(OUTDIR, "%s_selfcheck.csv" % CASE_ID)
        with open(chk_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["case_id", "x0_M1", "x0_M2", "asym_pct", "mirror_sum_pct",
                        "mirror_ind_pct", "mirror_pairs", "mirror_pass",
                        "equidistant", "k_ok", "L_positive"])
            w.writerow([CASE_ID, tag["x0_M1"], tag["x0_M2"], tag["asym_pct"],
                        tag["mirror_sum_pct"], tag["mirror_ind_pct"], tag["mirror_pairs"],
                        tag["mirror_pass"], equi, k_ok, L_ok])
        res.update(dict(objectives={k: round(v, 6) for k, v in obj.items()},
                        selfcheck=tag, equidistant=equi, k_ok=k_ok, L_positive=L_ok,
                        curve_csv=curve_csv, case_csv=case_csv, chk_csv=chk_csv,
                        per_point_minutes=[rows[x]["minutes"] for x in xs_h]))
        log("")
        log("=== 端到端结果 ===")
        log("  墙钟 %.1f 分钟（%d 点，%d 实例）" % (wall, len(rows), N))
        log("  自检: 和口径 %.3f%% / 个体口径 %.3f%% / 配对 %d -> %s"
            % (tag["mirror_sum_pct"], tag["mirror_ind_pct"], tag["mirror_pairs"],
               "通过 ✓" if tag["mirror_pass"] else "不通过 ✗"))
        log("        x=0 非对称度 %.3f%%  |k|<=1 %s  自感>0 %s  点位等距 %s"
            % (tag["asym_pct"], k_ok, L_ok, equi))
        log("  目标量: M_sum_mean=%.4f  M_sum_var=%.6f  M_pp=%.4f"
            % (obj["M_sum_mean"], obj["M_sum_var"], obj["M_pp"]))
        log("  输出: %s" % curve_csv)
    json.dump(res, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    log("结果 -> %s" % OUT)


if __name__ == "__main__":
    main()
