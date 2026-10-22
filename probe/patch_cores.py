"""把 ANSYS 求解核数从 8 改成 24。

覆盖两种写法：
  CORES = 8          ->  CORES = 24          (模块级常量，被 analyze(cores=CORES) 使用)
  cores=8            ->  cores=24            (直接写在 analyze(...) 里的字面量)

用法:
  python patch_cores.py --dry-run
  python patch_cores.py
"""

import os
import re
import sys

ROOT = r"C:\wpt"
EXCLUDE_DIRS = {"backup", "_incident_20260913", "_incident_20260914", "__pycache__", "_test_run"}

OLD_N, NEW_N = 8, 24

# 只替换这两种精确形态，注释与其余参数一律保留
# 注意：必须用 \g<n> 命名组引用，不能写 \1/\2 —— 紧跟数字会变成八进制转义
#       （r"\224" 会被当成一个字符，把要写入的数字吃掉）
PATTERNS = [
    (re.compile(r"\bCORES(\s*)=(\s*)8\b"), r"CORES\g<1>=\g<2>" + str(NEW_N)),
    (re.compile(r"\bcores(\s*)=(\s*)8\b"), r"cores\g<1>=\g<2>" + str(NEW_N)),
]

DRY = "--dry-run" in sys.argv


def main():
    targets = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                targets.append(os.path.join(dirpath, fn))
    targets.sort()

    print("scanning %d .py files under %s" % (len(targets), ROOT))
    print("mode:", "DRY-RUN (nothing written)" if DRY else "APPLY")
    print()

    files_changed = 0
    lines_changed = 0
    residual = []

    for path in targets:
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

        new_lines = []
        hits = []
        for i, line in enumerate(lines, 1):
            original = line
            for rx, rep in PATTERNS:
                line = rx.sub(rep, line)
            if line != original:
                hits.append((i, original.rstrip("\n"), line.rstrip("\n")))
            new_lines.append(line)

        if hits:
            files_changed += 1
            lines_changed += len(hits)
            print("--- %s  (%d 处)" % (path, len(hits)))
            for ln, before, after in hits:
                print("  L%-5d - %s" % (ln, before.strip()))
                print("        + %s" % after.strip())
            if not DRY:
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.writelines(new_lines)
            print()

        for i, line in enumerate(new_lines, 1):
            if re.search(r"\bcores\s*=\s*8\b", line, re.I):
                residual.append((path, i, line.strip()))

    print("=" * 64)
    print("files changed : %d" % files_changed)
    print("lines changed : %d" % lines_changed)
    if residual:
        print()
        print("!! 仍有 cores=8 残留:")
        for p, i, l in residual:
            print("   %s L%d: %s" % (p, i, l))
    else:
        print("no cores=8 remaining")
    if DRY:
        print()
        print("Re-run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
