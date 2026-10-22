# -*- coding: utf-8 -*-
r"""b2_deliver.py 交付闸门的负向/正向回归测试（合成数据，不触碰真实批次目录）。

一个不会失败的检查等于没有检查。本脚本搭一个 **256 工况规模**的最小合成 root，
分别验证闸门能抓到：

  1. 某工况未进任何分片        -> 致命（退出码 2）
  2. 某工况被重复分配          -> 致命（退出码 2）
  3. 分片完整（仅未跑完）      -> 非致命（退出码 1）

夹具必须与真实参数表同为 256 工况，否则「参数表 256 个工况」这条致命检查会先触发，
把用例 3 淹没掉（初版夹具就踩过这个坑）。
"""
import csv
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "_delivertest")
PY = r"C:\anaconda\python.exe"

N = 256
CASES = ["b1_%04d" % (9001 + i) for i in range(N)]

HDR_PLAN = ["case_id", "coil_size", "hole_ratio", "tx_fill", "rx_fill",
            "tx_thick", "rx_thick", "spacing_ratio"]
HDR_RAW = ["case_id", "i", "x_mm", "L11", "L22", "L33", "M12", "M13", "M23",
           "k13", "k23", "minutes", "aedt_pid", "ts", "mesh"]
HDR_CASES = ["case_id", "coil_size", "hole_ratio", "tx_fill", "rx_fill", "tx_thick",
             "rx_thick", "spacing_ratio", "tx_bar_w", "rx_bar_w", "ferrite_len",
             "edge_gap", "center_dist", "sweep_span", "n_points", "n_bars_rx",
             "rx_volume", "M_pp", "raw_file"]
HDR_CURVES = ["case_id", "position_x", "M1", "M2", "M_pp", "L11", "L22", "L33", "k13", "k23"]
HDR_DIAG = ["case_id", "M_sum_mean", "mesh", "mesh_mixed", "mesh_gate", "mesh_points",
            "gap_min", "M_sum_var", "M_pp", "M_pp_min", "M_pp_max", "M_sum_min",
            "M_sum_max", "asym_pct", "asym_peak_pct", "mirror_pass", "k_ok", "L_positive",
            "equidistant", "x_err_mm", "n_points", "L33_dev_pct", "L33_outliers",
            "L11_dev_pct", "L11_outliers", "sum_minutes", "max_point_minutes",
            "n_sessions", "n_bars_rx", "tx_bar_w", "rx_bar_w", "ferrite_len",
            "edge_gap", "sweep_span", "rx_volume"]
HDR_CHK = ["case_id", "x0_M1", "x0_M2", "asym_pct", "mirror_sum_pct", "mirror_ind_pct",
           "mirror_pairs", "mirror_pass", "equidistant", "k_ok", "L_positive"]

BOOT = ("2026-09-19 00:27:00 | ==============================================\n"
        "2026-09-19 00:27:00 | 契约采集 worker 启动：plan=b1_plan_shard{r}.csv "
        "BOX=X±420 Y[-134.94,161] Z[-45,75] 超时=几何1500s/求解2400s XS=半扫21点\n")

FAILS = []


def check(label, got, want):
    ok = got == want
    print("  %-50s got=%-4s want=%-4s %s" % (label, got, want, "PASS" if ok else "FAIL"))
    if not ok:
        FAILS.append(label)


def plan_row(cid):
    return [cid] + [1.0] * 7


def w(path, header, rows=()):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        wr.writerows(rows)


def build(split_a, split_b):
    """split_a / split_b: 两个分片各自的 case_id 列表。"""
    shutil.rmtree(FIX, ignore_errors=True)
    os.makedirs(FIX, exist_ok=True)
    w(os.path.join(FIX, "b1_plan.csv"), HDR_PLAN, [plan_row(c) for c in CASES])
    w(os.path.join(FIX, "b1_plan_shard0.csv"), HDR_PLAN, [plan_row(c) for c in split_a])
    w(os.path.join(FIX, "b1_plan_shard1.csv"), HDR_PLAN, [plan_row(c) for c in split_b])

    for k in range(8):
        with open(os.path.join(FIX, "b1_worker_run%d.json" % k), "w", encoding="utf-8") as f:
            json.dump({"run": k, "batch": "b1", "cases": [],
                       "box": {"x": 420.0, "y": 161.0}, "path_mode": "ring",
                       "timeouts": {"stage": 1500, "solve": 2400}}, f, ensure_ascii=False)
        with open(os.path.join(FIX, "b1_worker_run%d.log" % k), "w", encoding="utf-8") as f:
            f.write(BOOT.format(r=k))

    # 1 个完整工况（21 点）。列数必须与 HDR_RAW 严格一致（15 列）：
    # case_id,i,x_mm + L11..k23(8) + minutes,aedt_pid,ts,mesh(4)
    done = CASES[0]
    rows = [[done, i, i * 1.0] + [1.0] * 8 + [0.5, 0, "t", "OPT"] for i in range(21)]
    w(os.path.join(FIX, "b1_raw_run0.csv"), HDR_RAW, rows)

    # 交付物：与「1 个完整工况」自洽，避免第 3 节误报
    w(os.path.join(FIX, "out", "b1_cases.csv"), HDR_CASES,
      [[done] + [1.0] * 17 + ["b1_raw_run0.csv"]])
    w(os.path.join(FIX, "out", "b1_diag.csv"), HDR_DIAG,
      [[done, 1.0, "OPT", "False", "OPT", 21.0] + [1.0] * 29])
    w(os.path.join(FIX, "out", "b1_curves.csv"), HDR_CURVES,
      [[done, (i - 20) * 1.0, 1.0, 1.0, 1.0, 20.0, 20.0, 25.0, 0.1, 0.2]
       for i in range(41)])
    w(os.path.join(FIX, "out", "b1_selfcheck.csv"), HDR_CHK,
      [[done] + [1.0] * 10])


def read_csv(p):
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def build_full(partial=None, register=False):
    """终态夹具：256 工况全部完成。闸门应判「可出终版」（退出码 0）。

    这是交付当天真正会走的分支 —— 若它坏了，前面所有校验通过也没用。

    partial=(case_id, [缺失点索引]) 时，把该工况改成 worker final-partial：
    raw 去掉缺失点、worker JSON 标 partial、交付物排除该工况。
    register=True 时同时把它写进缺口例外表。
    """
    shutil.rmtree(FIX, ignore_errors=True)
    os.makedirs(FIX, exist_ok=True)
    half = N // 2
    w(os.path.join(FIX, "b1_plan.csv"), HDR_PLAN, [plan_row(c) for c in CASES])
    w(os.path.join(FIX, "b1_plan_shard0.csv"), HDR_PLAN, [plan_row(c) for c in CASES[:half]])
    w(os.path.join(FIX, "b1_plan_shard1.csv"), HDR_PLAN, [plan_row(c) for c in CASES[half:]])
    for k in range(8):
        with open(os.path.join(FIX, "b1_worker_run%d.json" % k), "w", encoding="utf-8") as f:
            json.dump({"run": k, "batch": "b1", "cases": [],
                       "box": {"x": 420.0, "y": 161.0}, "path_mode": "ring",
                       "timeouts": {"stage": 1500, "solve": 2400}}, f, ensure_ascii=False)
        with open(os.path.join(FIX, "b1_worker_run%d.log" % k), "w", encoding="utf-8") as f:
            f.write(BOOT.format(r=k))

    # 8 个实例各 32 工况 × 21 点 = 5376 点
    for k in range(8):
        rows = []
        for ci in range(k * 32, (k + 1) * 32):
            rows += [[CASES[ci], i, i * 1.0] + [1.0] * 8 + [0.5, 0, "t", "OPT"]
                     for i in range(21)]
        w(os.path.join(FIX, "b1_raw_run%d.csv" % k), HDR_RAW, rows)

    # 交付物：与 256 个完整工况自洽
    w(os.path.join(FIX, "out", "b1_cases.csv"), HDR_CASES,
      [[c] + [1.0] * 17 + ["b1_raw_run0.csv"] for c in CASES])
    w(os.path.join(FIX, "out", "b1_diag.csv"), HDR_DIAG,
      [[c, 1.0, "OPT", "False", "OPT", 21.0] + [1.0] * 29 for c in CASES])
    w(os.path.join(FIX, "out", "b1_curves.csv"), HDR_CURVES,
      [[c, (i - 20) * 1.0, 1.0, 1.0, 1.0, 20.0, 20.0, 25.0, 0.1, 0.2]
       for c in CASES for i in range(41)])
    w(os.path.join(FIX, "out", "b1_selfcheck.csv"), HDR_CHK,
      [[c] + [1.0] * 10 for c in CASES])

    if partial:
        cid, miss = partial
        k = CASES.index(cid) // 32
        rp = os.path.join(FIX, "b1_raw_run%d.csv" % k)
        rows = [r for r in read_csv(rp)
                if not (r["case_id"] == cid and int(r["i"]) in miss)]
        w(rp, HDR_RAW, [[r[c] for c in HDR_RAW] for r in rows])

        jp = os.path.join(FIX, "b1_worker_run%d.json" % k)
        j = json.load(open(jp, encoding="utf-8"))
        j["cases"] = [c for c in j.get("cases", []) if c.get("case_id") != cid]
        j["cases"].append({"case_id": cid, "status": "partial", "points": 21,
                           "solved": 21 - len(miss), "fail": sorted(miss)})
        json.dump(j, open(jp, "w", encoding="utf-8"), ensure_ascii=False)

        keep = [c for c in CASES if c != cid]          # 契约文件只收完整工况
        w(os.path.join(FIX, "out", "b1_cases.csv"), HDR_CASES,
          [[c] + [1.0] * 17 + ["b1_raw_run0.csv"] for c in keep])
        w(os.path.join(FIX, "out", "b1_diag.csv"), HDR_DIAG,
          [[c, 1.0, "OPT", "False", "OPT", 21.0] + [1.0] * 29 for c in keep])
        w(os.path.join(FIX, "out", "b1_curves.csv"), HDR_CURVES,
          [[c, (i - 20) * 1.0, 1.0, 1.0, 1.0, 20.0, 20.0, 25.0, 0.1, 0.2]
           for c in keep for i in range(41)])

        ep = os.path.join(FIX, "b1_partial_exceptions.json")
        if register:
            with open(ep, "w", encoding="utf-8") as f:
                json.dump({"cases": {cid: {"missing_points": sorted(miss)}}},
                          f, ensure_ascii=False)
        elif os.path.exists(ep):
            os.remove(ep)


def run_gate():
    p = subprocess.run([PY, os.path.join(HERE, "b2_deliver.py"),
                        "--root", FIX, "--batch", "b1", "--no-refresh"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "")


def main():
    # 用例 1：最后 1 个工况故意不放进任何分片
    print("=== 用例 1：1 个工况未进任何分片 -> 致命（退出码 2）===")
    a, b = CASES[:128], CASES[128:255]                 # 丢掉 CASES[255]
    build(a, b)
    rc, out = run_gate()
    check("退出码", rc, 2)
    check("报出未分配 1 个", "未分配 1 个" in out, True)
    check("标注该工况", CASES[255] in out, True)
    check("分片覆盖行标 ✗", "✗ 分片覆盖全部工况" in out, True)

    # 用例 2：最后 1 个工况被放进两个分片
    print("=== 用例 2：1 个工况被重复分配 -> 致命（退出码 2）===")
    a, b = CASES[:128], CASES[128:] + [CASES[255]]
    build(a, b)
    rc, out = run_gate()
    check("退出码", rc, 2)
    check("报出重复 1 个", "重复 1 个" in out, True)

    # 用例 3：分片完整，只是没跑完 -> 非致命（退出码 1）
    print("=== 用例 3：分片完整（仅未跑完）-> 非致命（退出码 1）===")
    build(CASES[:128], CASES[128:])
    rc, out = run_gate()
    check("退出码", rc, 1)
    check("分片覆盖 ✓", "✓ 分片覆盖全部工况" in out, True)
    check("无 ✗ 分片项", "✗ 分片覆盖" not in out, True)
    check("无其他致命项", out.count("✗") == 0, True)

    # 用例 4：256 工况全部完成 -> 可出终版（退出码 0）
    print("=== 用例 4：256/256 全部完成 -> 可出终版（退出码 0）===")
    build_full()
    rc, out = run_gate()
    check("退出码", rc, 0)
    check("无任何 ✗", out.count("✗") == 0, True)
    check("判为可出终版", "可出终版" in out, True)
    check("完整 256/256", "完整 256 / 256" in out, True)
    check("点位 5376/5376", "点位 5376 / 5376" in out, True)

    # 用例 5：出现未登记的 final-partial -> 仍必须致命（例外机制不能变成放行开关）
    print("=== 用例 5：未登记的 final-partial -> 致命（退出码 2）===")
    build_full(partial=(CASES[7], [3]), register=False)
    rc, out = run_gate()
    check("退出码", rc, 2)
    check("报出未登记缺口", "✗ 无未登记的缺口" in out, True)
    check("点出该工况", CASES[7] in out, True)
    check("未判可出终版", "可出终版" not in out, True)

    # 用例 6：同一缺口登记后 -> 可出终版（带缺口），但必须显式声明
    print("=== 用例 6：缺口登记后 -> 可出终版（带缺口，退出码 0）===")
    build_full(partial=(CASES[7], [3]), register=True)
    rc, out = run_gate()
    check("退出码", rc, 0)
    check("无任何 ✗", out.count("✗") == 0, True)
    check("判为带缺口可出终版", "可出终版（带缺口）" in out, True)
    check("列出已登记缺口", "已登记缺口" in out, True)
    check("要求交付说明显式声明", "交付说明必须显式声明" in out, True)
    check("未误报为 256 全完成", "工况全部完成" not in out, True)
    return out


if __name__ == "__main__":
    last = main()
    shutil.rmtree(FIX, ignore_errors=True)
    print()
    if FAILS:
        print("!! 失败 %d 项：%s" % (len(FAILS), FAILS))
        print("\n--- 用例 3 完整输出 ---")
        print(last)
        sys.exit(1)
    print("全部通过 ✓")
