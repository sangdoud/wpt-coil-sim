# -*- coding: utf-8 -*-
r"""b2_disk.sweep 安全性回归测试（合成数据，不动真实暂存区）。

验证三件事：
  1. 无占用 + 静置超时  → 删除
  2. 被独占持有        → 跳过（保护运行中的会话）
  3. 静置不足          → 跳过
"""
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import b2_disk                                                      # noqa: E402

ROOT = os.path.join(HERE, "_sweeptest")
SUB = os.path.join(ROOT, "2")
FAILS = []


def mk(name, age_min):
    d = os.path.join(SUB, name)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(os.path.join(d, "sub"))
    for rel, data in (("proj.lock", b"x"), (os.path.join("sub", "big.dat"), b"0" * 2_000_000)):
        with open(os.path.join(d, rel), "wb") as f:
            f.write(data)
    t = time.time() - age_min * 60
    os.utime(d, (t, t))                         # 伪造目录 mtime
    for r, _dd, fs in os.walk(d):
        for f in fs:
            os.utime(os.path.join(r, f), (t, t))
    return d


def check(label, got, want):
    ok = got == want
    print("  %-46s got=%-6s want=%-6s %s" % (label, got, want, "PASS" if ok else "FAIL"))
    if not ok:
        FAILS.append(label)


print("=== 测试 1：无占用 + 静置 10 min（阈值 5 min）→ 应删除 ===")
logs = []
d1 = mk("maxwell_TEST_11111.pjt", 10)
size1 = b2_disk.dir_mb(d1)
n, mb, sk = b2_disk.sweep(temp_root=ROOT, min_age_min=5, log=logs.append)
check("删除数", n, 1)
check("释放 MB ≈ 1.91", round(mb, 1), round(size1, 1))
check("跳过数", sk, 0)
check("目录已消失", os.path.exists(d1), False)
print("  日志:", logs)

print("=== 测试 2：被独占持有（阈值 5 min）→ 应跳过 ===")
logs = []
d2 = mk("maxwell_TEST_22222.pjt", 10)
fh = open(os.path.join(d2, "proj.lock"), "r+b")            # 持有句柄
try:
    check("is_in_use 探测", b2_disk.is_in_use(d2), True)
    n, mb, sk = b2_disk.sweep(temp_root=ROOT, min_age_min=5, log=logs.append)
    check("删除数", n, 0)
    check("跳过数", sk, 1)
    check("目录仍存在（受保护）", os.path.exists(d2), True)
finally:
    fh.close()
print("  日志:", logs)

print("=== 测试 2b：句柄释放后 → 应可删除 ===")
logs = []
n, mb, sk = b2_disk.sweep(temp_root=ROOT, min_age_min=5, log=logs.append)
check("删除数", n, 1)
check("目录已消失", os.path.exists(d2), False)

print("=== 测试 3：静置不足（刚创建，阈值 120 min）→ 应跳过 ===")
logs = []
d3 = mk("maxwell_TEST_33333.pjt", 0)
n, mb, sk = b2_disk.sweep(temp_root=ROOT, min_age_min=120, log=logs.append)
check("删除数", n, 0)
check("跳过数", sk, 0)
check("目录仍存在", os.path.exists(d3), True)
print("  日志:", logs, "(空 = 未进入候选，符合预期)")

print("=== 测试 4：只读文件也应能删除（ANSYS 残留常见）===")
logs = []
d4 = mk("maxwell_TEST_44444.pjt", 10)
os.chmod(os.path.join(d4, "sub", "big.dat"), 0o444)
n, mb, sk = b2_disk.sweep(temp_root=ROOT, min_age_min=5, log=logs.append)
check("删除数", n, 1)
check("目录已消失", os.path.exists(d4), False)

shutil.rmtree(ROOT, ignore_errors=True)
print()
if FAILS:
    print("!! 失败 %d 项：%s" % (len(FAILS), FAILS))
    sys.exit(1)
print("全部通过 ✓")
