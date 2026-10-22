# -*- coding: utf-8 -*-
"""验证 contract_merge 对「带 mesh 列」raw 格式的处理（含口径混合标记）。

场景：
  A) 迁移后的真实文件（mesh 全 OPT）        -> diag 应显示 mesh=OPT, mesh_mixed=False
  B) 模拟补偿后的混合文件（18 点 OPT + 3 点 BASE）-> mesh=OPT+BASE, mesh_mixed=True
  C) 旧格式（无 mesh 列）                    -> 默认 OPT，不报错
"""
import csv
import os
import shutil
import subprocess
import sys
import tempfile

HERE = r"C:\ansys maxwell2024\_work\b1"
SRC = os.path.join(HERE, "b1_raw_run5.csv")     # 一个已有真实数据的文件
PLAN = os.path.join(HERE, "b1_plan.csv")
sys.path.insert(0, HERE)
import contract_worker as W                      # noqa: E402

COLS = W.RAW_COLS


def build(root, cid, mode):
    """用真实点值造一个 21 点的 raw 文件；mode: all_opt / mixed / no_mesh"""
    rows = list(csv.DictReader(open(SRC, newline="", encoding="utf-8")))
    rows = [r for r in rows if r["case_id"] == cid]
    # 需要 21 点：把已有的点循环补齐（仅用于格式测试，值不重要）
    while len(rows) < 21:
        r = dict(rows[len(rows) % max(1, len(rows))] if rows else {})
        r["i"] = str(len(rows))
        r["x_mm"] = "%.6f" % (len(rows) * 5.0)
        rows.append(r)
    rows = rows[:21]
    for k, r in enumerate(rows):
        r["i"] = str(k)
    if mode == "mixed":
        for k in (3, 7, 11):
            rows[k]["mesh"] = "BASE"
    p = os.path.join(root, "b1_raw_run0.csv")
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        head = COLS if mode != "no_mesh" else [c for c in COLS if c != "mesh"]
        w.writerow(head)
        for r in rows:
            w.writerow([r.get(c, "") for c in head])
    return head


def run_case(name, mode, cid="b1_0238"):
    root = tempfile.mkdtemp(prefix="b1m_")
    shutil.copy2(PLAN, os.path.join(root, "b1_plan.csv"))
    head = build(root, cid, mode)
    r = subprocess.run([r"C:\anaconda\python.exe", os.path.join(HERE, "contract_merge.py"),
                        "--batch", "b1", "--root", root],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    diag = list(csv.DictReader(open(os.path.join(root, "out", "b1_diag.csv"), encoding="utf-8")))
    ok = r.returncode == 0 and diag
    print("--- %s（表头 %d 列）---" % (name, len(head)))
    if not ok:
        print("   ✗ merge 失败 rc=%d\n%s" % (r.returncode, (r.stderr or "")[-400:]))
        return False
    d = diag[0]
    print("   merge OK；cases=%d 行；mesh=%s  mesh_mixed=%s"
          % (len(diag), d.get("mesh"), d.get("mesh_mixed")))
    shutil.rmtree(root, ignore_errors=True)
    return d


def main():
    ok = True
    a = run_case("A 迁移后（全 OPT）", "all_opt")
    ok &= bool(a) and a.get("mesh") == "OPT" and a.get("mesh_mixed") == "False"
    b = run_case("B 混合口径（3 点 BASE）", "mixed")
    ok &= bool(b) and a and ("BASE" in (b.get("mesh") or "")) and b.get("mesh_mixed") == "True"
    c = run_case("C 旧格式（无 mesh 列）", "no_mesh")
    ok &= bool(c) and c.get("mesh") == "OPT" and c.get("mesh_mixed") == "False"
    print()
    print("mesh 列处理验证：%s" % ("全部通过 ✓" if ok else "有失败 ✗"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
