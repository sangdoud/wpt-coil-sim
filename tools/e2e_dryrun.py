# -*- coding: utf-8 -*-
r"""端到端演练 —— 在临时沙箱里真跑一遍改造流水线，证明新机不会踩坑。

为什么必须做这一步
------------------
本项目的核心教训（《第二轮启动前检查清单》§0.3.1）：
**"改动之后，看起来在工作，其实什么都没做"** —— P2/P4/P11/P13/P14 全是同一失效模式。
路径改造同理：一份"改完了"的脚本如果 import 就崩，批次会在 8 个实例上同时失败，
而现场看到的只是"worker 起不来"。

所以：**改造必须在沙箱里先跑通，再上目标机。**

本脚本做四件事：
  1) 把迁移包复制到临时沙箱；
  2) 用「临时布局」作为新机路径，实跑 adapt_paths.py --apply；
  3) 实跑 rename_batch.py --apply（b2 -> b3）；
  4) **逐个 .py 做 ast.parse 语法校验** + 残留的 C:\ 绝对路径扫描 +
     关键常量在位核查（口径冻结项必须还在）。

退出码：0=全通过 / 1=有失败项 / 2=脚本自身异常
"""
import ast
import json
import os
import re
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

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

# 改造后必须仍在位的关键常量（口径冻结项 —— 改了就是换口径，跨批数据不可比）
# ⚠️ 判据一律**按源码真实写法**核准，不要按"我以为的写法"写。
#    下面每条都已在源文件里逐行核对过（行号见注释），避免自检器自己误报：
#      PATH_MODE 在 coil_gen.py L72 是 os.environ.get("WPT_PATH_MODE", "ring")
#      CPU_STALL_SECS 是浮点 360.0 / OPT 三元组在 contract_worker.py L84
FROZEN = [
    (r'WPT_STAGE_TIMEOUT",\s*"1500"', "几何超时默认 1500 s（contract_worker L187）"),
    (r'WPT_SOLVE_TIMEOUT",\s*"2400"', "求解超时默认 2400 s（contract_worker L188）"),
    (r'WPT_CLEAN",\s*"point"', "逐点清场数据（contract_worker L74）"),
    (r'WPT_MESH_FALLBACK",\s*"1"', "逐点 BASE 回退（contract_worker L79）"),
    (r'WPT_SESSION_MAX_H",\s*"7"', "会话轮换 7 h（contract_worker L194）"),
    (r"OPT_MIN_GAP\s*=\s*True,\s*5\.0,\s*1\.5", "OPT 口径三元组 (柔性, ⑥, 1.5 mm)（L84）"),
    (r'WPT_PATH_MODE",\s*"ring"', "几何 ring 口径（coil_gen L72）"),
    (r"CPU_STALL_SECS\s*=\s*360", "僵死探针 360 s（batch_sweep_lc L603）"),
    (r"SESSION_DEAD_POLLS\s*=\s*12", "gRPC 断连判死 12 次（batch_sweep_lc L598）"),
    # ⚠️ 空气域有**两个来源**，这是最隐蔽的一条：
    #   batch_sweep_lc.py 的 REGION_FIXED 静态值是 ±330（旧文档值，**不是生产值**），
    #   生产真实口径靠 contract_worker.py 在运行时覆盖成 ±420。
    #   覆盖行若丢失，全部静态检查照样"全绿"，但解域退回 ±330 ->
    #   扫描端点时接收线圈伸出解域、解被截断 —— 结果是**错的**而不是精度略差。
    #   故必须**同时**核验静态常量与那行覆盖赋值。
    (r"REGION_FIXED\s*=\s*\{\s*[\"']x[\"']\s*:\s*\(\s*-330\.0",
     "batch_sweep_lc.REGION_FIXED 静态值仍在（±330，供对照）"),
    (r"B\.REGION_FIXED\s*=\s*\{\s*[\"']x[\"']\s*:\s*\(\s*-BOXX,\s*BOXX\s*\)",
     "★ contract_worker 的运行时覆盖行仍在（这条才是生产口径 ±420）"),
    (r'WPT_BOXX",\s*"420"', "WPT_BOXX 默认 420"),
    (r'WPT_BOXY",\s*"161"', "WPT_BOXY 默认 161"),
]

# 改造后**不允许**残留的旧机器绝对路径
FORBIDDEN = [r"C:\wpt", r"C:\ansys maxwell2024", r"C:\anaconda\python.exe"]
# 允许出现的例外（历史文档本就是"旧→新"映射表）
FORBIDDEN_EXEMPT = {"docs/README_迁移指南.md", "docs/路径修改清单_20260913.md"}

R = []


def rep(level, item, detail=""):
    R.append((level, item, detail))
    print("[%-4s] %s%s" % (level, item, ("\n         " + detail) if detail else ""),
          flush=True)


def ok(i, d=""):
    rep("OK", i, d)


def fail(i, d=""):
    rep("FAIL", i, d)


def warn(i, d=""):
    rep("WARN", i, d)


def main():
    print("=" * 78)
    print("端到端演练（沙箱）")
    print("时间 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 78, flush=True)

    sand = tempfile.mkdtemp(prefix="wpt_mig_sandbox_")
    print("沙箱：%s\n" % sand)

    try:
        # ---------------- 1) 搭建"新机"目录布局 ----------------
        # ⚠️ 布局必须与**迁移包内的顶层目录名**一致（work / wpt / probe / docs），
        #    因为 adapt_paths.py 是按顶层目录名遍历的。曾经沙箱用 `_work` 而扫描
        #    用的是 `work`，导致"0 命中却报成功"——详见 adapt_paths.py 的注释。
        work = os.path.join(sand, "_work", "b3")
        wpt = os.path.join(sand, "wpt")
        probe = os.path.join(sand, "probe")
        for d in (work, wpt, probe):
            os.makedirs(d, exist_ok=True)

        # ---------------- 2) 铺开迁移包 ----------------
        pack = os.path.join(HERE, "pack")
        shutil.copytree(os.path.join(pack, "work", "b3"), work, dirs_exist_ok=True)
        shutil.copytree(os.path.join(pack, "work", "ref"),
                        os.path.join(sand, "_work", "ref"), dirs_exist_ok=True)
        shutil.copytree(os.path.join(pack, "wpt"), wpt, dirs_exist_ok=True)
        shutil.copytree(os.path.join(pack, "probe"), probe, dirs_exist_ok=True)
        shutil.copytree(os.path.join(pack, "docs"), os.path.join(sand, "docs"),
                        dirs_exist_ok=True)
        ok("1 迁移包已铺开", "work=%s\n         wpt=%s\n         probe=%s" % (work, wpt, probe))

        # ---------------- 3) 生成沙箱站点配置 ----------------
        site = {
            "new_work_root": os.path.join(sand, "_work"),
            "new_wpt_root": wpt,
            "new_probe_root": probe,
            "new_python": PY,
            "new_project_ref": os.path.join(sand, "_work",
                                            "Projecttonight_ref.aedt"),
            "new_workspace": sand,
            "new_aedt_exe": "",
            "old_work_root": "C:\\ansys maxwell2024\\_work",
            "old_wpt_root": "C:\\wpt",
            "old_probe_root": "C:\\ansys maxwell2024\\_probe",
            "old_python": "C:\\anaconda\\python.exe",
            "old_workspace": "C:\\ansys maxwell2024",
            "batch_name": "b3",
            "instances": 4,
        }
        # 母本工程必须真的存在，否则 adapt 会拒绝实改
        src_ref = os.path.join(pack, "work", "Projecttonight_ref.aedt")
        if os.path.isfile(src_ref):
            shutil.copy2(src_ref, site["new_project_ref"])
            ok("2 母本工程就位（%.2f MB）"
               % (os.path.getsize(site["new_project_ref"]) / 1048576.0))
        else:
            fail("2 迁移包里没有母本工程 Projecttonight_ref.aedt",
                 "没有它 adapt_paths 会拒绝实改，整批也起不来")
            return 1

        sp = os.path.join(sand, "_site.json")
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(site, f, ensure_ascii=False, indent=2)

        # ---------------- 4) 跑 adapt_paths.py ----------------
        print("\n--- adapt_paths.py --apply ---")
        p = subprocess.run([PY, os.path.join(HERE, "adapt_paths.py"),
                            "--site", sp, "--pack", sand, "--apply"],
                           capture_output=True, text=True, errors="replace",
                           encoding="utf-8")
        lines = (p.stdout or "").strip().splitlines()
        if p.returncode == 0 and any("实改结果" in l for l in lines):
            ok("3 adapt_paths 实改成功（退出码 0）",
               "\n         ".join(l for l in lines if "[CHANGED]" in l)[:600]
               or "\n         ".join(lines[-4:]))
        else:
            # 失败时把**判定性**的行挑出来，不要把 300 行明细全糊在报告里
            key = [l for l in lines
                   if l.startswith("[FAIL]") or l.startswith("[OK  ]")
                   or "退出码" in l or "实改结果" in l or "扫描：" in l]
            fail("3 adapt_paths 失败（退出码 %d）" % p.returncode,
                 "\n".join((key or lines)[-14:]))
            return 1

        # ---------------- 5) 跑 rename_batch.py（b2 -> b3）----------------
        # 沙箱里目录已叫 b3，但**文件内容**里还是 b2_* —— 这正是新机的真实起点
        print("\n--- rename_batch.py --apply ---")
        p = subprocess.run([PY, os.path.join(HERE, "rename_batch.py"),
                            "--site", sp, "--root", work, "--old", "b2",
                            "--new", "b3", "--apply"],
                           capture_output=True, text=True, errors="replace",
                           encoding="utf-8")
        tail = (p.stdout or "").strip().splitlines()[-5:]
        if p.returncode == 0:
            ok("4 rename_batch 改名成功", "\n         ".join(tail))
        else:
            fail("4 rename_batch 失败（退出码 %d）" % p.returncode,
                 "\n".join((p.stdout or "").strip().splitlines()[-15:]))
            return 1

        # ---------------- 6) 逐个 .py 语法校验 ----------------
        print("\n--- 语法校验（ast.parse）---")
        bad, n_py = [], 0
        for root in (work, wpt, probe):
            for r, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs
                           if d != "__pycache__" and not d.startswith("_backup_")]
                for fn in files:
                    if not fn.endswith(".py"):
                        continue
                    n_py += 1
                    fp = os.path.join(r, fn)
                    try:
                        ast.parse(open(fp, "rb").read(), filename=fp)
                    except SyntaxError as e:
                        bad.append("%s : %s" % (os.path.relpath(fp, sand), e))
        if bad:
            fail("5 语法校验：%d/%d 个 .py 解析失败" % (len(bad), n_py),
                 "\n         ".join(bad[:10]))
            return 1
        ok("5 语法校验：%d 个 .py 全部解析通过" % n_py)

        # ---------------- 7) 旧路径残留扫描 ----------------
        print("\n--- 旧路径残留扫描 ---")
        # ⚠️ 残留下来的 `C:\anaconda\python.exe` 在沙箱里是**假阳性**：
        # 沙箱用的新解释器就是它（sys.executable），于是 "旧串 == 新串"，
        # build_rules 正确地把它当空操作剔除、替换不涉及它 —— 那么它当然"还在"。
        # 判据必须与替换同源：**凡是与站点配置的新值相同的，都不算残留**。
        news = {v.rstrip("\\/").lower() for k, v in site.items()
                if k.startswith("new_") and isinstance(v, str) and v}
        resid = []
        for r, dirs, files in os.walk(sand):
            dirs[:] = [d for d in dirs
                       if d != "__pycache__" and not d.startswith("_backup_")]
            for fn in files:
                if os.path.splitext(fn)[1].lower() not in (
                        ".py", ".json", ".md", ".txt", ".bat", ".ps1", ".csv"):
                    continue
                fp = os.path.join(r, fn)
                rel = os.path.relpath(fp, sand).replace("\\", "/")
                if rel in FORBIDDEN_EXEMPT or rel.endswith("_site.json"):
                    continue
                try:
                    txt = open(fp, "rb").read().decode("latin-1")
                except OSError:
                    continue
                for pat in FORBIDDEN:
                    if not re.search(re.escape(pat), txt):
                        continue
                    if pat.rstrip("\\/").lower() in news:
                        continue          # 与站点新值相同 -> 合法的空操作，不算残留
                    resid.append((rel, pat))
        if resid:
            fail("6 仍有 %d 处旧路径残留" % len(resid),
                 "\n         ".join("%s : %s" % (a, b) for a, b in resid[:12]))
            return 1
        ok("6 旧路径零残留（C:\\wpt / C:\\ansys maxwell2024 均已改写；"
           "与站点新值相同的路径按空操作豁免）")

        # ---------------- 8) 口径冻结核查 ----------------
        print("\n--- 口径冻结核查（改造不得动口径）---")
        blob = {}
        for n in ("contract_worker.py", "preflight.py", "b3_guard.py"):
            fp = os.path.join(work, n)
            if os.path.isfile(fp):
                blob[n] = open(fp, "rb").read().decode("utf-8", "replace")
        for n in ("batch_sweep_lc.py", "coil_gen.py"):
            fp = os.path.join(wpt, n)
            if os.path.isfile(fp):
                blob[n] = open(fp, "rb").read().decode("utf-8", "replace")
        alltxt = "\n".join(blob.values())
        miss = [d for pat, d in FROZEN if not re.search(pat, alltxt)]
        if miss:
            fail("7 口径常量缺失或已被改动", "缺：%s" % "、".join(miss))
            return 1
        ok("7 口径冻结项全部在位（%d 项）" % len(FROZEN),
           "超时/清理/回退/轮换/闸门/ring 几何/僵死探针")

        # ---------------- 9) 新路径确实写进去了 ----------------
        print("\n--- 新路径落位核查 ---")
        cw = blob.get("contract_worker.py", "")
        checks = [
            (site["new_wpt_root"].replace("\\", "/") in cw
             or site["new_wpt_root"] in cw, "contract_worker 指向新代码根"),
            (site["new_work_root"] in cw, "contract_worker 指向新工作根"),
            ("b3" in open(os.path.join(work, "contract_worker.py"),
                          encoding="utf-8", errors="replace").read(),
             "contract_worker 批次名已为 b3"),
        ]
        pf = os.path.join(work, "preflight.py")
        if os.path.isfile(pf):
            t = open(pf, encoding="utf-8", errors="replace").read()
            checks.append((site["new_wpt_root"] in t, "preflight.WPT_DIR 指向新代码根"))
            checks.append((site["new_project_ref"] in t,
                           "preflight.BASE_PROJECT 指向新母本工程"))
            checks.append((site["new_python"] in t, "preflight.PY 指向新解释器"))
        nbad = [d for c, d in checks if not c]
        if nbad:
            fail("8 新路径未正确落位", "问题项：%s" % "、".join(nbad))
            return 1
        ok("8 新路径落位正确（%d 项）" % len(checks),
           "含校验器 preflight.py 自身 —— 它指错会报「全绿」而实际全错")

        # ---------------- 10) 汇编报告 ----------------
        print("\n" + "=" * 78)
        print("演练结论")
        print("=" * 78)
        nf = sum(1 for lv, _, _ in R if lv == "FAIL")
        print("OK %d / FAIL %d" % (sum(1 for lv, _, _ in R if lv == "OK"), nf))
        if nf == 0:
            print("\n[通过] 改造流水线在沙箱中端到端跑通：")
            print("   · 迁移包铺开 → 路径改造 → 批次改名 → 语法校验 → 残留扫描 → 口径核验")
            print("   · 沙箱保留在 %s（供人工抽查）" % sand)
            print("\n可以上目标机执行。")
        return 0 if nf == 0 else 1

    finally:
        pass


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                      # noqa: BLE001
        print("\n[FAIL] e2e_dryrun 自身异常：%r" % (exc,), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)
