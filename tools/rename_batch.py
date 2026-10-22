# -*- coding: utf-8 -*-
r"""批次改名器 —— 把 b2_* 生产脚本改名成新批次（如 b3_*）并同步内部引用。

为什么需要它
------------
生产脚本里有大量**写死的批次名**：`b2_guard.py` / `--batch` 默认值 `b2` /
`WPT_BATCH` 默认值 `b2` / `b2_plan.csv`、`b2_raw_runK.csv` 等文件名模板。
新机跑新参数批次时如果直接沿用 b2 的名字，会出现两类问题：
  * 与源机已交付/在跑的 b2 数据**同名混淆**（跨批数据不可比却看起来像同一批）；
  * 本项目的自检 `preflight.py` 的 **B8 检查**会告警"脚本里残留别的批次的默认值"。

设计约束（踩过的坑）
--------------------
  1) **不能用裸字符串替换**：`b2` 是短 token，`_b2_`（父目录
     `C:\wpt_runs\_work\b2\`）里也含它。源机吃过同类亏：
     `contract_launcher` 把 `b1` 写死后用正则一改，连不该动的地方也动了。
     故 token 替换用**负向后行断言** `(?<![A-Za-z0-9_])b2(?![A-Za-z0-9_])`。
  2) **预演优先 + 自动备份 + 幂等**：与 adapt_paths.py 同规格。
  3) **先改文件内容、后改文件名**：否则改到一半中断会留下半成品名字。

用法
----
    python rename_batch.py --site _site_config.json --dry-run
    python rename_batch.py --site _site_config.json --apply
    python rename_batch.py --site _site_config.json --verify

退出码：0=成功 / 1=有阻断项 / 2=脚本自身异常
"""
import argparse
import json
import os
import re
import shutil
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
SCAN_EXT = {".py", ".json", ".md", ".txt", ".bat", ".ps1"}


def load_site(p):
    with open(p, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def token_re(old, new):
    r"""批次名 token 替换：前面不能是标识符字符，后面**不能紧跟数字**。

    这一版是踩坑后改对的，原版写的是 `(?![A-Za-z0-9_])` —— 把**下划线也排除**了，
    于是 `b2_accept.py` 里的 `b2` 后面跟的是 `_`，判定为"不是边界"，
    **一个文件都不匹配**；而脚本仍照常打印「[OK] 无 b2 残留」并返回退出码 0。
    （又是"看起来在工作，其实什么都没做"这一类，实测被 e2e_dryrun 第 4 步抓到。）

    为什么不能简单放宽成"后面可以跟下划线"：源机 `_probe` 里有
    `queue_b2_sweep.py` 这类**并非以批次名开头**的文件，若不设下界，
    `_b2_` 会被误伤。故用**前界** `(?<![A-Za-z0-9_])` 承担这个职责：
      · `b2_accept.py`  / `b2`  / `C:\...\_work\b2\`  -> 前界是行首或分隔符，命中 ✅
      · `queue_b2_sweep.py` -> 前面是 `_`，前界不成立，不命中 ✅（正是我们要的）
      · `ab2cd` -> 前面是 `a`，不命中 ✅
      · `b22`   -> 后面紧跟数字，后界不成立，不命中 ✅
      · `prepare_b2.py` -> 后面是 `.`，后界 `(?![0-9A-Za-z])` 成立，命中 ✅
        （早期版本只写 `(?![0-9])`，会漏掉 `prepare_b2.py` —— 它同样是必须改名的
         生产脚本，靠 --verify 复校才暴露出来。）
    """
    return re.compile(r"(?<![A-Za-z0-9_])%s(?![0-9A-Za-z])" % re.escape(old)), new


def walk(root):
    for r, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs
                   if d != "__pycache__" and not d.startswith("_backup_rename_")]
        for fn in sorted(files):
            yield os.path.join(r, fn)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.path.join(HERE, "_site_config.json"))
    ap.add_argument("--root", default=None, help="默认取 site 的 new_work_root")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--verify", action="store_true")
    ap.add_argument("--old", default=None, help="默认 b2")
    ap.add_argument("--new", default=None, help="默认取 site 的 batch_name")
    args = ap.parse_args()

    cfg = load_site(args.site)
    root = os.path.abspath(args.root or cfg["new_work_root"])
    old = args.old or "b2"
    new = args.new or cfg.get("batch_name", "b3")

    print("=" * 78)
    print("批次改名器   %s  ->  %s" % (old, new))
    print("目录 %s" % root)
    print("时间 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 78, flush=True)

    if old == new:
        print("[FAIL] 新旧批次名相同，无可执行操作。退出码 1")
        return 1
    if not os.path.isdir(root):
        print("[FAIL] 目录不存在：%s" % root)
        return 1

    rx = token_re(old, new)

    # ---- 扫描 ----
    content_hits, name_hits = [], []
    for ap_ in walk(root):
        fn = os.path.basename(ap_)
        ext = os.path.splitext(fn)[1].lower()
        if ext in SCAN_EXT:
            raw = open(ap_, "rb").read()
            txt = raw.decode("latin-1")
            n = len(rx[0].findall(txt))
            if n:
                content_hits.append((os.path.relpath(ap_, root), n))
        if rx[0].search(fn):
            name_hits.append(os.path.relpath(ap_, root))

    print("\n内容替换点：%d 个文件，共 %d 处"
          % (len(content_hits), sum(n for _, n in content_hits)))
    for rel, n in content_hits:
        print("   %-46s x%d" % (rel, n))
    print("\n待改名文件/目录：%d 项" % len(name_hits))
    for rel in name_hits:
        print("   %s" % rel)

    if args.verify:
        left = [r for r, _ in content_hits]
        if left or name_hits:
            print("\n[FAIL] 仍有 %d 个文件含旧批次名、%d 项名字未改。退出码 1"
                  % (len(left), len(name_hits)))
            return 1
        print("\n[OK] 已无 %s 残留（内容与文件名）。退出码 0" % old)
        return 0

    if not args.apply:
        print("\n[预演] 未落盘。确认无误后加 --apply。")
        print("       注意：文件名改名在内容替换**之后**执行，"
              "中途中断可用 _backup_rename_<时间戳> 回滚。")
        print("退出码 0")
        return 0

    # ---- 实改 ----
    # ⚠️ 前置断言：**改名一个都没命中 = 正则错了，不是"本来就不需要改"**。
    # 这条来自真实事故：原正则的后界 `(?![A-Za-z0-9_])` 把下划线也排除，
    # `b2_accept.py` 一个都不匹配，脚本却照常打印「[OK] 无 b2 残留」并返回 0。
    # 判据要写成"有没有改到"，不能写成"遍历过了没有"。
    if not name_hits:
        print("\n[FAIL] 待改名文件 0 项 —— 这通常意味着**匹配正则写错了**，"
              "或批次名给错了（old=%s）。" % old)
        print("       目录：%s" % root)
        print("       目录下实际 .py：%s"
              % "、".join(sorted(f for f in os.listdir(root)
                                 if f.endswith(".py"))[:12]))
        print("       拒绝执行（否则会「什么都没改」却报成功）。退出码 1")
        return 1

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup = os.path.join(root, "_backup_rename_%s" % stamp)
    n_chg = n_ren = n_fail = 0

    print("\n[1/2] 替换文件内容 ...")
    for rel, _n in content_hits:
        fp = os.path.join(root, rel)
        bp = os.path.join(backup, rel.replace("/", os.sep))
        try:
            os.makedirs(os.path.dirname(bp), exist_ok=True)
            shutil.copy2(fp, bp)
            txt = open(fp, "rb").read().decode("latin-1")
            new_txt, cnt = rx[0].subn(rx[1], txt)
            with open(fp, "wb") as f:
                f.write(new_txt.encode("latin-1"))
            print("   [CHANGED] %-46s %d 处" % (rel, cnt))
            n_chg += 1
        except OSError as e:
            print("   [FAIL]    %-46s %r" % (rel, e))
            n_fail += 1

    print("\n[2/2] 重命名文件/目录（深度降序，先深后浅）...")
    for rel in sorted(name_hits, key=lambda s: -s.count(os.sep)):
        fp = os.path.join(root, rel)
        if not os.path.exists(fp):
            continue
        d, fn = os.path.split(fp)
        nfn = rx[0].sub(rx[1], fn)
        if nfn == fn:
            continue
        np_ = os.path.join(d, nfn)
        try:
            if not os.path.exists(backup):
                os.makedirs(backup, exist_ok=True)
            os.rename(fp, np_)
            print("   [RENAMED] %s -> %s" % (fn, nfn))
            n_ren += 1
        except OSError as e:
            print("   [FAIL]    %s : %r" % (fn, e))
            n_fail += 1

    print("\n改动 %d 个文件内容，重命名 %d 项，失败 %d 项" % (n_chg, n_ren, n_fail))
    print("原文件内容备份在：%s" % backup)

    # ---- 复校 ----
    left = []
    for ap_ in walk(root):
        fn = os.path.basename(ap_)
        if rx[0].search(fn):
            left.append(fn + "  (文件名)")
        if os.path.splitext(fn)[1].lower() in SCAN_EXT:
            if rx[0].search(open(ap_, "rb").read().decode("latin-1")):
                left.append(os.path.relpath(ap_, root))
    print("\n复校：")
    if left:
        for x in left[:30]:
            print("   [FAIL] 残留 %s" % x)
        print("\n退出码 1")
        return 1
    print("   [OK] 无 %s 残留" % old)
    print("\n回滚：robocopy \"%s\" \"%s\" /E 然后按备份文件名手工改回" % (backup, root))
    print("下一步：跑 preflight.py，确认 B8「所有 CLI 默认批次名 == %s」为 OK。" % new)
    print("退出码 0")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                      # noqa: BLE001
        print("\n[FAIL] rename_batch 自身异常：%r" % (exc,), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)
