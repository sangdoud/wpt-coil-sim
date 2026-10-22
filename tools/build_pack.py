# -*- coding: utf-8 -*-
r"""迁移包生成器 —— 把「新机跑新参数批次」所需的全部资产收拢成一份可校验的迁移包。

设计原则（沿用本项目的血泪教训）：
  1) **清单驱动**：要拷什么、从哪来、到哪去，全部写在 MANIFEST 里，不靠人记；
  2) **可校验**：每个文件记 SHA256，新机解包后逐一比对，杜绝"看起来拷过去了"；
  3) **不改源**：本脚本只读源目录，绝不修改/删除源机上的任何文件；
  4) **参数化目标路径**：新机的根路径、解释器、ANSYS 安装路径全部写进
     _site_config.json，由 adapt_paths.py 消费 —— 排除在 SHA 校验之外（它本来就要被改）。

用法：
  python build_pack.py                          # 默认输出到 C:\ansys maxwell2024\_migration\pack
  python build_pack.py --out D:\pack            # 指定输出目录
  python build_pack.py --no-probe               # 不收 _probe（诊断/构建工具，可省）
  python build_pack.py --with-installer-notes   # 额外记录安装介质位置（不拷贝）
退出码：0=成功 / 1=有文件缺失 / 2=脚本自身异常
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
WS = r"C:\ansys maxwell2024"
WPT = r"C:\wpt"

# ---------------------------------------------------------------------------
# MANIFEST：(源路径, 包内相对路径, 是否必需)
#   「包内相对路径」决定新机上的落位，与迁移后的目录布局一一对应。
# ---------------------------------------------------------------------------
def build_manifest(with_probe=True):
    M = []

    def add_dir(src, dst, must=True, pattern=None):
        M.append(("DIR", src, dst, must, pattern))

    def add_file(src, dst, must=True):
        M.append(("FILE", src, dst, must, None))

    # ---- 1. 批次框架（b2 生产链路，已含 b1/b2 全部修复）-------------------
    B2 = os.path.join(WS, "_work", "b2")
    add_dir(B2, "work/b3", must=True, pattern="*.py")

    # ---- 2. 母本工程（★ 最关键的单个文件：没有它整个链路无法启动）---------
    add_file(os.path.join(WS, "_work", "Projecttonight_ref.aedt"),
             "work/Projecttonight_ref.aedt", must=True)

    # ---- 3. 口径冻结依赖的样例参数表（新参数表按同一列格式生成）-----------
    for n in ("b2_plan.csv", "b2_plan_meta.json", "b2_audit.csv",
              "b2_region_check.csv", "b2_source_samples.csv",
              "b2_partial_exceptions.json", "b1_plan.csv"):
        p = os.path.join(B2, n) if n.startswith("b2_") else os.path.join(WS, "_work", n)
        add_file(p, "work/ref/" + n, must=False)

    # ---- 4. 代码底座 C:\wpt ------------------------------------------------
    for n in ("batch_sweep_lc.py", "coil_gen.py", "wpt_contract.py",
              "coil_template_Rx.json", "backup_upload.py", ".gitignore"):
        add_file(os.path.join(WPT, n), "wpt/" + n, must=True)
    add_file(os.path.join(WPT, "backup", "Projecttonight.aedt"),
             "wpt/backup/Projecttonight.aedt", must=False)

    # ---- 5. 诊断与构建工具 ------------------------------------------------
    if with_probe:
        add_dir(os.path.join(WS, "_probe"), "probe", must=True)

    # ---- 6. 知识与经验文档（新机遇到问题时唯一能自救的东西）---------------
    DOCS = [
        ("第二轮启动前检查清单与经验总结_20261012.md", True),
        ("批量仿真故障总结与经验_20260926.md", True),
        ("batch1_交付口径说明_20260919.md", True),
        ("batch规模与工期规划_20260919.md", True),
        ("b1_delivery_README.md", True),
        ("交接_新会话启动指引_20260919.md", True),
        ("拐角重映射缺陷与修正_20260919.md", False),
        ("僵死事故与自动恢复改动_20260923.md", False),
        ("算法优化与提速汇总_20260926.md", False),
        ("仿真采集端技术文档_20260918.md", False),
        ("线圈LC参数化_20260916.md", False),
        ("核数测速对比_20260915.md", False),
    ]
    for n, must in DOCS:
        add_file(os.path.join(WS, n), "docs/" + n, must=must)
    for n in ("README_迁移指南.md", "README_服务器部署_Windows.md",
              "README_preflight_2025.md"):
        add_file(os.path.join(WPT, n), "docs/" + n, must=False)
    add_file(os.path.join(WPT, "backup", "路径修改清单_20260913.md"),
             "docs/路径修改清单_20260913.md", must=False)

    return M


# ---------------------------------------------------------------------------
def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def expand(M):
    """把 DIR 展开成 FILE 列表。"""
    out, missing = [], []
    for kind, src, dst, must, pattern in M:
        if kind == "FILE":
            if os.path.isfile(src):
                out.append((src, dst))
            elif must:
                missing.append(src)
            continue
        if not os.path.isdir(src):
            if must:
                missing.append(src + "\\  (目录)")
            continue
        for root, _dirs, files in os.walk(src):
            _dirs[:] = [d for d in _dirs if d != "__pycache__"]
            for fn in sorted(files):
                if pattern and not fn.lower().endswith(pattern.replace("*", "").lower()):
                    continue
                ap = os.path.join(root, fn)
                rel = os.path.relpath(ap, src).replace("\\", "/")
                out.append((ap, dst.rstrip("/") + "/" + rel))
    return out, missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "pack"))
    ap.add_argument("--no-probe", action="store_true", help="不收 _probe 目录")
    ap.add_argument("--with-installer-notes", action="store_true",
                    help="仅记录 ANSYS 安装介质位置（不拷贝，约 21.8 GB）")
    args = ap.parse_args()

    out = os.path.abspath(args.out)
    files, missing = expand(build_manifest(with_probe=not args.no_probe))

    print("=" * 78)
    print("迁移包生成器   输出=%s" % out)
    print("时间 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 78)
    print("清单展开：%d 个文件" % len(files))

    if missing:
        print("\n[FAIL] 下列**必需**条目不存在，迁移包不完整：")
        for m in missing:
            print("   · %s" % m)
        print("\n退出码 1 —— 先补回缺失项再打包。")
        return 1

    if os.path.isdir(out):
        print("\n输出目录已存在，清空重建：%s" % out)
        shutil.rmtree(out)
    os.makedirs(out)

    entries, total, nfail = [], 0, 0
    for src, dst in files:
        dp = os.path.join(out, dst.replace("/", os.sep))
        os.makedirs(os.path.dirname(dp), exist_ok=True)
        try:
            shutil.copy2(src, dp)
            size = os.path.getsize(dp)
            entries.append({
                "path": dst,
                "bytes": size,
                "sha256": sha256_of(dp),
                "source": src,
            })
            total += size
        except OSError as e:
            nfail += 1
            print("   [FAIL] %s -> %s : %r" % (src, dst, e))

    by_top = {}
    for e in entries:
        top = e["path"].split("/", 1)[0]
        d = by_top.setdefault(top, {"n": 0, "bytes": 0})
        d["n"] += 1
        d["bytes"] += e["bytes"]

    print("\n按顶层目录统计：")
    for k in sorted(by_top):
        v = by_top[k]
        print("   %-10s %4d 文件  %9.2f MB" % (k, v["n"], v["bytes"] / 1048576.0))
    print("   %-10s %4d 文件  %9.2f MB" % ("合计", len(entries), total / 1048576.0))

    manifest = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "generator": os.path.abspath(__file__),
        "source_machine": {
            "workspace": WS,
            "wpt_code": WPT,
            "os": "Windows Server 2022 (20348)",
            "aedt": "2024 R1",
            "pyaedt": "1.3.0",
            "note": "源机 31.6 GB 内存 / 72 逻辑核；生产并发 8 实例",
        },
        "n_files": len(entries),
        "total_bytes": total,
        "by_top": by_top,
        "files": entries,
    }
    if args.with_installer_notes:
        manifest["installer_media_on_source"] = [
            r"C:\ansys maxwell2024\1\ANSYS.2024.R1.Electronics.Suite.Win64.iso",
            r"C:\ansys maxwell2024\1\LicenseManager安装包_2024R1_WINX64.iso",
        ]
    mp = os.path.join(out, "MANIFEST.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print("\n清单已写出：%s" % mp)
    if nfail:
        print("\n[FAIL] %d 个文件拷贝失败 —— 退出码 1" % nfail)
        return 1
    print("\n[OK] 迁移包就绪。下一步：填入 _site_config.json，然后跑 adapt_paths.py。")
    print("退出码 0")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                      # noqa: BLE001
        print("\n[FAIL] build_pack 自身异常：%r" % (exc,), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)
