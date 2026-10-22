# -*- coding: utf-8 -*-
r"""目标机路径改造器 —— 把迁移包里的绝对路径改写为新机布局。

为什么需要它
------------
本项目的脚本有 **14 处硬编码绝对路径**（分布在 contract_launch / contract_worker /
preflight / guard / deliver / _relaunch_one / _delayed_launch / prepare_* / wpt 侧
共 40 余个文件）。这些不是「风格问题」而是**正确性问题**，且有三处会**静默出错**：

  * `contract_launcher.DEFAULT_BASE`  → 指错就复制不到母本工程，整批起不来；
  * `contract_worker` 的 `os.chdir(r"C:\\wpt")` → 几何代码从错误目录加载；
  * `preflight.py` 的 `WPT_DIR / BASE_PROJECT / PY` → **校验器自己指错**，
    于是它会报「全绿」而实际路径是错的。（本项目已有同类前科：
    计划任务参数写坏后关键字一个不少，粗查判为"注册正确"，实际 4 小时全程没跑。）

设计原则
--------
  1) **预演优先**：默认 `--dry-run`，只打印将要改什么，不落盘；
  2) **可回滚**：实改前自动把原文件备份到 `_backup_adapt_<时间戳>/`；
  3) **幂等**：重复执行结果一致（旧串没了就是 0 处替换，不报错）；
  4) **不猜**：新路径必须真实存在才允许实改（`--allow-missing` 可显式放行）；
  5) **字节级替换**：按二进制读入 → ASCII 替换 → 原样写回，
     不碰编码、不碰换行符、不碰 BOM（本项目日志/文档有 GBK 与 BOM 前科）。

用法
----
    # 1) 先看要改什么（不落盘）
    python adapt_paths.py --site _site_config.json --dry-run

    # 2) 确认无误后实改（自动备份）
    python adapt_paths.py --site _site_config.json --apply

    # 3) 自查：改造后不应再有任何旧路径残留
    python adapt_paths.py --site _site_config.json --verify

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

# 扫描范围：迁移包内需要改造的顶层目录。
#
# ⚠️⚠️ 这里曾经写死成 ["work", "wpt", "probe"] —— 而沙箱/目标机上的真实目录名是
#      **_work**（带下划线，因为它是 `D:\wpt_runs\_work\`）。后果：
#      `os.walk` 一个目录都没进去 → **0 个文件被改** → 备份目录 0 文件 →
#      而脚本**依然打印「[OK] 无残留」并返回退出码 0**。
#      这是本项目最贵的失效模式（"看起来在工作，其实什么都没做"），
#      是端到端演练 `e2e_dryrun.py` 抓出来的 —— 静态审查看不出来。
#
# 修正：**两套目录名都收**（打包态的 `work/docs/...` 与落位态的 `_work/_probe/...`），
#      并且最终以「有没有改到东西」为判据，而不是以「遍历了什么」为判据。
SCAN_DIRS = ["work", "_work", "docs", "wpt", "_probe", "probe"]
SCAN_EXT = {".py", ".json", ".md", ".txt", ".csv", ".bat", ".ps1", ".cfg", ".ini"}

# 「必须替换」的旧路径：出现在代码里的执行路径。缺一处就可能静默跑错。
CRITICAL_OLD = [
    "C:\\wpt",
    "C:\\ansys maxwell2024\\_work",
    "C:\\ansys maxwell2024\\_probe",
    "C:\\anaconda\\python.exe",
    "C:\\ansys maxwell2024",
]  # 全部转义 —— 普通字符串里的 \w \a \_ 会触发 SyntaxWarning 并污染 stderr
# 「顺带替换」的旧路径：旧机器的安装位置/版本号，不影响新机执行但会误导阅读
COSMETIC_PATTERNS = [
    (rb"C:\\Program Files\\ANSYS 2024r1 Inc\\ansys em\\v241\\Win64\\ansysedt\.exe",
     b"__AEDT_EXE__"),
]


def load_site(p):
    with open(p, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    need = ["new_work_root", "new_wpt_root", "new_python", "new_project_ref"]
    miss = [k for k in need if not cfg.get(k)]
    if miss:
        raise ValueError("_site_config.json 缺字段：%s" % "、".join(miss))
    cfg.setdefault("old_work_root", r"C:\ansys maxwell2024\_work")
    cfg.setdefault("old_wpt_root", r"C:\wpt")
    cfg.setdefault("old_probe_root", r"C:\ansys maxwell2024\_probe")
    cfg.setdefault("old_python", r"C:\anaconda\python.exe")
    cfg.setdefault("old_workspace", r"C:\ansys maxwell2024")
    cfg.setdefault("new_probe_root",
                   os.path.join(os.path.dirname(cfg["new_work_root"]), "_probe"))
    cfg.setdefault("new_workspace", os.path.dirname(cfg["new_work_root"]))
    cfg.setdefault("new_aedt_exe", "")
    return cfg


def build_rules(cfg):
    r"""构造 (旧串, 新串) 列表。覆盖反斜杠 / 正斜杠 / 双反斜杠三种写法。

    顺序很重要：**长串先替换**，否则 `C:\ansys maxwell2024` 会先把
    `C:\ansys maxwell2024\_work` 的前缀吃掉，留下半截路径。
    （本文档字符串必须是 raw string —— 普通字符串里的 `\_` 会触发
    SyntaxWarning 并污染 stderr，让上层把它当成命令失败。）
    """
    pairs_raw = [
        (cfg["old_work_root"], cfg["new_work_root"]),
        (cfg["old_probe_root"], cfg["new_probe_root"]),
        (cfg["old_wpt_root"], cfg["new_wpt_root"]),
        (cfg["old_python"], cfg["new_python"]),
        (cfg["old_workspace"], cfg["new_workspace"]),
    ]
    # 按旧串长度降序，保证长前缀优先
    pairs_raw.sort(key=lambda kv: -len(kv[0]))

    rules = []
    for old, new in pairs_raw:
        # ⚠️ **必须跳过「旧 == 新」的空操作规则**。踩过的坑：沙箱演练时
        # _site_config 里 new_python 就是当前解释器 C:\anaconda\python.exe，
        # 于是规则 `C:\anaconda\python.exe -> C:\anaconda\python.exe` 成了恒等替换，
        # 而 verify 会把"原样保留"当成"残留"报出来 —— 改造明明成功却报 12 个 FAIL。
        # 判据：只把**真正发生变化**的路径纳入规则与校验，两边同源同口径。
        if old.rstrip("\\/").lower() == new.rstrip("\\/").lower():
            continue
        # ⚠️⚠️ **分隔符风格必须保持**（真实踩到的坑）。
        # `C:/wpt`（正斜杠）与 `C:\wpt`（反斜杠）要替换成**同风格**的新路径。
        # 反例：源机 _probe 里的补丁脚本把路径写进引号字符串：
        #     old = 'BASE_DIR = r"C:/wpt"'
        # 若把它改成反斜杠写法 `C:\Users\...`，中间就出现了 `\U` ——
        # Python 当成 Unicode 转义序列，`\UXXXXXXXX` 不足 8 位十六进制即 SyntaxError
        # （实测 10 个 probe 脚本因此无法解析）。原文件用正斜杠正是为了避开这个坑，
        # 改造不得把它重新引回来。
        new_bs = new.replace("/", "\\")
        new_fs = new.replace("\\", "/")
        variants = (
            (old, new_bs),                          # C:\wpt -> 反斜杠风格
            (old.replace("\\", "/"), new_fs),       # C:/wpt -> 正斜杠风格
        )
        for v, nv in variants:
            if len(v) < 4:
                continue
            rules.append((v, nv))
    # 去重并再次按长度降序
    seen, out = set(), []
    for o, n in sorted(rules, key=lambda kv: -len(kv[0])):
        if o in seen:
            continue
        seen.add(o)
        out.append((o, n))
    return out


def scan(pack, rules, cfg):
    hits, files_scanned, files_hit = [], 0, 0
    for top in SCAN_DIRS:
        base = os.path.join(pack, top)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs
                       if d != "__pycache__" and not d.startswith("_backup_adapt_")]
            for fn in sorted(files):
                if os.path.splitext(fn)[1].lower() not in SCAN_EXT:
                    continue
                ap = os.path.join(root, fn)
                rel = os.path.relpath(ap, pack).replace("\\", "/")
                if rel.endswith("MANIFEST.json"):
                    continue
                files_scanned += 1
                with open(ap, "rb") as f:
                    raw = f.read()
                txt = raw.decode("latin-1")
                n_here = 0
                for old, new in rules:
                    c = txt.count(old)
                    if c:
                        hits.append({"file": rel, "old": old, "new": new, "n": c})
                        n_here += c
                if n_here:
                    files_hit += 1
    return hits, files_scanned, files_hit


def apply_rules(pack, rules, cfg, backup_dir):
    changed, failed = [], []
    for top in SCAN_DIRS:
        base = os.path.join(pack, top)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs
                       if d != "__pycache__" and not d.startswith("_backup_adapt_")]
            for fn in sorted(files):
                if os.path.splitext(fn)[1].lower() not in SCAN_EXT:
                    continue
                ap = os.path.join(root, fn)
                rel = os.path.relpath(ap, pack).replace("\\", "/")
                if rel.endswith("MANIFEST.json"):
                    continue
                with open(ap, "rb") as f:
                    raw = f.read()
                txt = raw.decode("latin-1")
                new_txt, n = txt, 0
                for old, new in rules:
                    c = new_txt.count(old)
                    if c:
                        new_txt = new_txt.replace(old, new)
                        n += c
                if not n:
                    continue
                bp = os.path.join(backup_dir, rel.replace("/", os.sep))
                try:
                    os.makedirs(os.path.dirname(bp), exist_ok=True)
                    shutil.copy2(ap, bp)
                    with open(ap, "wb") as f:
                        f.write(new_txt.encode("latin-1"))
                    changed.append((rel, n))
                except OSError as e:
                    failed.append((rel, repr(e)))
    return changed, failed


def verify(pack, rules):
    """改造后不应再有「本该被替换掉的旧路径」残留。

    ⚠️ 判据必须**复用 build_rules() 的规则表**，不能另抄一份旧串列表。
    踩过的坑（两次，同一根因"双份真相"）：
      · 早先这里独立拼了一份 olds，里面含 `C:\\anaconda\\python.exe`；
        而当新机解释器恰好也是该路径时，build_rules 已把它当空操作**剔除**，
        替换不涉及它，校验却仍把它算作残留 → 改造成功却报 21 个 FAIL（假阳性）。
      · 更早一次是子串匹配没转义，把 `C:\\Python311\\python.exe` 误判成
        `C:\\anaconda\\python.exe` 的残留。
    结论：**替换与校验共用同一份规则**，见 build_rules()。
    """
    ignore_files = {
        "docs/README_迁移指南.md",              # 本就是"旧路径→新路径"映射表
        "docs/路径修改清单_20260913.md",         # 历史记录
    }
    residual = []
    for top in SCAN_DIRS:
        base = os.path.join(pack, top)
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            dirs[:] = [d for d in dirs
                       if d != "__pycache__" and not d.startswith("_backup_adapt_")]
            for fn in sorted(files):
                if os.path.splitext(fn)[1].lower() not in SCAN_EXT:
                    continue
                ap = os.path.join(root, fn)
                rel = os.path.relpath(ap, pack).replace("\\", "/")
                if rel.endswith("MANIFEST.json") or rel in ignore_files:
                    continue
                txt = open(ap, "rb").read().decode("latin-1")
                for old, _new in rules:
                    # 用与替换同一套转义语义做匹配（re.escape），
                    # 不能用子串 in/count —— 反斜杠会制造假阳性。
                    c = len(re.findall(re.escape(old), txt))
                    if c:
                        residual.append((rel, old, c))
    return residual


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.path.join(HERE, "_site_config.json"))
    ap.add_argument("--pack", default=os.path.join(HERE, "pack"))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="只预演（默认）")
    g.add_argument("--apply", action="store_true", help="实改（自动备份）")
    g.add_argument("--verify", action="store_true", help="检查旧路径残留")
    ap.add_argument("--allow-missing", action="store_true",
                    help="新路径不存在时也放行（仅用于演练，不推荐）")
    args = ap.parse_args()

    print("=" * 78)
    print("目标机路径改造器   包=%s" % os.path.abspath(args.pack))
    print("时间 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 78, flush=True)

    cfg = load_site(args.site)
    rules = build_rules(cfg)

    print("\n替换规则（长串优先）：")
    for old, new in rules:
        print("   %-34s -> %s" % (old, new))

    if args.verify:
        res = verify(args.pack, rules)
        print("\n残留扫描（旧的可执行路径）：")
        if not res:
            print("   [OK] 无残留 —— 改造完整。")
            print("\n退出码 0")
            return 0
        for rel, v, c in res:
            print("   [FAIL] %s : %s x%d" % (rel, v, c))
        print("\n退出码 1 —— 仍有 %d 处残留，逐条处置后再交付。" % len(res))
        return 1

    # ---- 新路径存在性检查（防"改了一堆指向不存在目录的路径"）------------
    checks = [("工作根 new_work_root", cfg["new_work_root"]),
              ("代码根 new_wpt_root", cfg["new_wpt_root"]),
              ("解释器 new_python", cfg["new_python"]),
              ("母本工程 new_project_ref", cfg["new_project_ref"])]
    if cfg.get("new_aedt_exe"):
        checks.append(("AEDT 可执行 new_aedt_exe", cfg["new_aedt_exe"]))
    print("\n新路径存在性：")
    bad = []
    for label, p in checks:
        okk = os.path.exists(p)
        print("   [%s] %-28s %s" % ("OK  " if okk else "FAIL", label, p))
        if not okk:
            bad.append(label)

    hits, n_scan, n_hit = scan(args.pack, rules, cfg)
    print("\n扫描：%d 个文件，其中 %d 个含旧路径，共 %d 处替换点"
          % (n_scan, n_hit, sum(h["n"] for h in hits)))
    by_file = {}
    for h in hits:
        by_file.setdefault(h["file"], []).append(h)
    print("\n逐文件明细：")
    for rel in sorted(by_file):
        for h in by_file[rel]:
            print("   %-46s %-34s x%d" % (rel, h["old"], h["n"]))

    if not args.apply:
        if bad and not args.allow_missing:
            print("\n[预演] 有 %d 项新路径不存在：%s" % (len(bad), "、".join(bad)))
            print("       实改前请先在新机建好目录/装好解释器，或用 --allow-missing 演练。")
        print("\n[预演] 未落盘。确认无误后加 --apply 实改。")
        print("退出码 0")
        return 0

    # ---- 实改 ----
    if bad and not args.allow_missing:
        print("\n[FAIL] 有 %d 项新路径不存在，拒绝实改：%s" % (len(bad), "、".join(bad)))
        print("       先补齐，或（仅演练时）加 --allow-missing。退出码 1")
        return 1

    # ⚠️ 前置断言：**扫描到了替换点，实改就必须改到东西**。
    # 这条断言直接来自一次真实事故：SCAN_DIRS 写死了 "work"，而沙箱里是 "_work"，
    # 于是扫描 0 命中、实改 0 命中，脚本照样报 "[OK] 无残留" 并退出码 0。
    # 判据要写成"改到了没有"，不能写成"遍历过了没有"。
    if not hits:
        print("\n[FAIL] 扫描到 0 处需要替换的路径 —— 这通常意味着**扫描目录名不对**，"
              "而不是「本来就不用改」。")
        print("       当前扫描目录：%s" % "、".join(SCAN_DIRS))
        print("       包内实际顶层目录：%s"
              % "、".join(sorted(d for d in os.listdir(args.pack)
                                 if os.path.isdir(os.path.join(args.pack, d)))))
        print("       拒绝执行（否则会「什么都没改」却报成功）。退出码 1")
        return 1

    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(args.pack, "_backup_adapt_%s" % stamp)
    os.makedirs(backup_dir, exist_ok=True)
    changed, failed = apply_rules(args.pack, rules, cfg, backup_dir)

    print("\n实改结果：")
    for rel, n in changed:
        print("   [CHANGED] %-46s %d 处" % (rel, n))
    for rel, e in failed:
        print("   [FAIL]    %-46s %s" % (rel, e))
    print("\n   改动 %d 个文件；备份在 %s" % (len(changed), backup_dir))

    if changed and not os.listdir(backup_dir):
        print("\n[FAIL] 报告改了 %d 个文件，但备份目录是空的 —— 状态不一致，拒绝报成功。"
              % len(changed))
        return 1
    if len(changed) < len({h["file"] for h in hits}):
        print("\n[FAIL] 扫描命中 %d 个文件，实改只动了 %d 个 —— 有文件没被处理。"
              % (len({h["file"] for h in hits}), len(changed)))
        return 1

    res = verify(args.pack, rules)
    print("\n改造后残留扫描：")
    if res:
        for rel, v, c in res:
            print("   [FAIL] %s : %s x%d" % (rel, v, c))
        print("\n退出码 1 —— 仍有残留。")
        return 1
    print("   [OK] 无残留。")

    print("\n回滚方法（如新机启动异常，想退回未改造状态）：")
    print('   robocopy "%s" "%s" /E' % (backup_dir, args.pack))
    print("\n下一步：跑 verify_pack.py 核对 SHA256，再按《迁移操作手册》继续。")
    print("退出码 0")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                      # noqa: BLE001
        print("\n[FAIL] adapt_paths 自身异常：%r" % (exc,), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)
