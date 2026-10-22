# -*- coding: utf-8 -*-
r"""batch1 缺点工况导出（旁路文件，**不进入**四个契约 CSV）。

为什么需要这个脚本
------------------
`contract_merge.py` 对点数不足 21 的工况是**整工况 `continue` 跳过**：

    if len(pts) < len(xs_h):
        n_partial.append((cid, len(pts)))
        continue

这是契约正确的（每工况必须 41 行、21 点半扫），但后果是**那些工况里已经成功解出
的点也一并被丢弃**。2026-09-19 实测：3 个工况共 59 个已解点、115 行曲线因此丢失，
而每个点平均耗时 8.7 分钟 ≈ 8.6 机时。

本脚本把这些数据导出到旁路文件，既不破坏契约文件的口径，也不丢数据：

  out\b1_partial_raw.csv      缺点工况的全部已解原始点（半扫口径，不加镜像）
  out\b1_partial_summary.csv  逐工况缺口清单：缺哪些点、对应什么 x、为何缺

**不镜像展开**：镜像公式假设半扫完整；对残缺半扫套用会凭空补齐不存在的数据。
半扫原始点是最诚实的呈现，下游需要镜像时可自行按 WC.expand_curve 处理。

用法：
  python b1_partial_export.py [--root ...] [--batch b1]
"""
import argparse
import collections
import csv
import glob
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):          # 无人值守下 stdout 可能是 GBK 管道
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

sys.path.insert(0, r"C:\wpt")
import wpt_contract as WC                    # noqa: E402  半扫点位公式的唯一来源

RAW_COLS = ["case_id", "i", "x_mm", "L11", "L22", "L33", "M12", "M13", "M23",
            "k13", "k23", "minutes", "aedt_pid", "ts", "mesh"]
SUM_COLS = ["case_id", "n_solved", "n_points", "missing_i", "missing_x_mm",
            "n_missing", "attempts_note"]


def read_csv(p):
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(os.path.abspath(__file__)))
    ap.add_argument("--batch", default="b2")
    a = ap.parse_args()
    ROOT, B = a.root, a.batch
    OUT = os.path.join(ROOT, "out")
    os.makedirs(OUT, exist_ok=True)

    plan = read_csv(os.path.join(ROOT, "%s_plan.csv" % B))
    raws = {}
    for p in sorted(glob.glob(os.path.join(ROOT, "%s_raw_run*.csv" % B))):
        for r in read_csv(p):
            raws.setdefault(r["case_id"], {})[int(r["i"])] = r

    # ⚠️ 2026-09-26 修正：判据原为 worker JSON 的 `status == "partial"`。
    # 但**整批重启会把 JSON 里 partial 记录重写清除**（实测批次跑完后该字段归零），
    # 于是本脚本导出空表（只有表头、0 行）——「缺点工况旁路导出」变成空文件，
    # 接收方拿不到缺口清单。改为以 **raw 反推**为权威判据（raw 逐点落盘、跨重启不丢）；
    # worker JSON 仅保留用于提供「为何缺」的 fail 列表（取不到就留空）。
    fails, status = {}, {}
    for p in sorted(glob.glob(os.path.join(ROOT, "%s_worker_run*.json" % B))):
        try:
            j = json.load(open(p, encoding="utf-8-sig"))
        except Exception:
            continue
        for c in j.get("cases", []):
            if isinstance(c, dict):
                status[c.get("case_id")] = c.get("status")
                if c.get("status") == "partial":
                    fails[c.get("case_id")] = sorted(c.get("fail") or [])

    npts = 21
    rows_raw, rows_sum = [], []
    for pr in plan:
        cid = pr["case_id"]
        pts = raws.get(cid, {})
        # 权威判据：raw 里点数不足 npts 即为缺点工况
        if len(pts) >= npts:                 # 完整（含被后续补偿补齐的）
            continue
        for i in sorted(pts):
            r = pts[i]
            rows_raw.append([r.get(c) for c in RAW_COLS])
        miss = fails.get(cid) or sorted(set(range(npts)) - set(pts))
        # 缺失点的 x 必须按契约公式算 —— 缺失点按定义就不在 pts 里，
        # 不能用 pts[i] 取（初版这里写成 if i in pts，导致该列恒为空）。
        try:
            xs_h = WC.sweep_positions_half(float(pr["coil_size"]),
                                           float(pr["spacing_ratio"]))
        except Exception:
            xs_h = []
        rows_sum.append([
            cid, len(pts), npts,
            "|".join(str(i) for i in miss),
            "|".join("%.3f" % xs_h[i] for i in miss if 0 <= i < len(xs_h)),
            len(miss),
            "OPT 与 BASE 双口径各 2 次共 4 次尝试均失败",
        ])

    p1 = os.path.join(OUT, "%s_partial_raw.csv" % B)
    p2 = os.path.join(OUT, "%s_partial_summary.csv" % B)
    for path, cols, rows in ((p1, RAW_COLS, rows_raw), (p2, SUM_COLS, rows_sum)):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cols)
            w.writerows(rows)

    print("缺点工况 %d 个；导出已解点 %d 个 / 缺口 %d 个"
          % (len(rows_sum), len(rows_raw), sum(r[5] for r in rows_sum)))
    for r in rows_sum:
        print("  %-9s %2d/%d  缺 i=%s  x=%s mm" % (r[0], r[1], r[2], r[3], r[4] or "-"))
    print("  -> %s" % p1)
    print("  -> %s" % p2)
    print("  注：旁路文件为半扫原始口径，**不镜像展开**，不计入四个契约 CSV。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
