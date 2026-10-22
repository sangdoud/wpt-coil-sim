# -*- coding: utf-8 -*-
r"""迁移包完整性校验 —— 在新机解包后逐文件核对 SHA256。

为什么单独写一个校验器
----------------------
本项目反复出现同一类事故：**"看起来成功了"，其实什么都没做**
（计划任务参数写坏 → LastTaskResult=1 而关键字一个不少；guard 的"重启进行中"
闸门写成"启动器是否存在" → 永久拦截重启；partial 导出只出表头 0 行）。
传输环节同样容易静默失真：拷贝被中断、盘满、编码转换、杀软隔离。

所以：**不校验传输，就等于没传输。**

用法：
    python verify_pack.py --pack <迁移包目录>                  # 校验全部
    python verify_pack.py --pack <目录> --list-changed         # 只列出不一致项
    python verify_pack.py --pack <目录> --skip-adapted         # 跳过已被
                                                               # adapt_paths 改过的文件

说明：
  * adapt_paths.py 实改后，被改文件的 SHA256 **必然**与新机不一致 ——
    这时请加 --skip-adapted；它会把"已改造清单"从备份目录反推出来。
  * 本脚本**只读**，不修改任何文件。
退出码：0=全部一致 / 1=有缺失或哈希不符 / 2=脚本自身异常
"""
import argparse
import hashlib
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def adapted_set(pack):
    """从 _backup_adapt_* 备份目录反推「哪些文件已被改造」。"""
    out = set()
    for d in sorted(os.listdir(pack)):
        if not d.startswith("_backup_adapt_"):
            continue
        base = os.path.join(pack, d)
        for root, _dirs, files in os.walk(base):
            for fn in files:
                ap = os.path.join(root, fn)
                out.add(os.path.relpath(ap, base).replace("\\", "/"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default=os.path.join(HERE, "pack"))
    ap.add_argument("--manifest", default=None,
                    help="默认取 <pack>/MANIFEST.json")
    ap.add_argument("--list-changed", action="store_true")
    ap.add_argument("--skip-adapted", action="store_true",
                    help="跳过已被 adapt_paths 改造过的文件（它们必然哈希不符）")
    args = ap.parse_args()

    pack = os.path.abspath(args.pack)
    mp = args.manifest or os.path.join(pack, "MANIFEST.json")
    if not os.path.isfile(mp):
        print("[FAIL] 找不到清单 %s" % mp)
        return 1

    with open(mp, "r", encoding="utf-8-sig") as f:
        man = json.load(f)

    skip = adapted_set(pack) if args.skip_adapted else set()

    print("=" * 78)
    print("迁移包完整性校验")
    print("  包     %s" % pack)
    print("  清单   %s（生成于 %s）" % (mp, man.get("generated")))
    print("  条目   %d 个文件 / %.2f MB"
          % (man.get("n_files", 0), man.get("total_bytes", 0) / 1048576.0))
    if args.skip_adapted:
        print("  跳过   %d 个已改造文件" % len(skip))
    print("=" * 78, flush=True)

    n_ok = n_miss = n_bad = n_skip = 0
    bad, miss = [], []
    for e in man.get("files", []):
        rel = e["path"]
        if rel in skip:
            n_skip += 1
            continue
        p = os.path.join(pack, rel.replace("/", os.sep))
        if not os.path.isfile(p):
            n_miss += 1
            miss.append(rel)
            continue
        if os.path.getsize(p) != e["bytes"]:
            n_bad += 1
            bad.append((rel, "字节数 %d != %d" % (os.path.getsize(p), e["bytes"])))
            continue
        got = sha256_of(p)
        if got != e["sha256"]:
            n_bad += 1
            bad.append((rel, "SHA256 %s != %s" % (got[:16], e["sha256"][:16])))
            continue
        n_ok += 1

    print("\n结果：OK %d / 缺失 %d / 不一致 %d / 跳过 %d"
          % (n_ok, n_miss, n_bad, n_skip))
    if miss:
        print("\n缺失文件：")
        for r in miss[:40]:
            print("   · %s" % r)
        if len(miss) > 40:
            print("   ... 另有 %d 个" % (len(miss) - 40))
    if bad:
        print("\n不一致文件：")
        for r, why in bad[:40]:
            print("   · %-46s %s" % (r, why))
        if len(bad) > 40:
            print("   ... 另有 %d 个" % (len(bad) - 40))

    if n_miss or n_bad:
        print("\n退出码 1 —— 传输不完整。**不要继续后面的步骤**，重新传输并复校。")
        return 1
    print("\n[OK] 传输完整。下一步：核对新机环境（preflight 的 A 节）与授权。")
    print("退出码 0")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                      # noqa: BLE001
        print("\n[FAIL] verify_pack 自身异常：%r" % (exc,), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)
