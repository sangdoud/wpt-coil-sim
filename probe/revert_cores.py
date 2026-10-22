"""把 ANSYS 求解核数从 24 改回 8（撤销 patch_cores.py 的改动）。

用法:
  python revert_cores.py --dry-run
  python revert_cores.py

注意：与 patch_cores.py 同样的坑 —— 正则替换里必须用 \\g<n> 命名组引用，
      写 \\1/\2 紧跟数字会变成八进制转义，把要写入的数字吃掉。
"""

import os
import re
import sys

ROOT = r"C:\wpt"
EXCLUDE_DIRS = {"backup", "_incident_20260913", "_incident_20260914", "__pycache__", "_test_run"}

OLD_N, NEW_N = 24, 8

PATTERNS = [
    (re.compile(r"\bCORES(\s*)=(\s*)24\b"), r"CORES\g<1>=\g<2>" + str(NEW_N)),
    (re.compile(r"\bcores(\s*)=(\s*)24\b"), r"cores\g<1>=\g<2>" + str(NEW_N)),
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
            if re.search(r"\bcores\s*=\s*24\b", line, re.I):
                residual.append((path, i, line.strip()))

    print("=" * 64)
    print("files changed : %d" % files_changed)
    print("lines changed : %d" % lines_changed)
    if residual:
        print()
        print("!! 仍有 cores=24 残留:")
        for p, i, l in residual:
            print("   %s L%d: %s" % (p, i, l))
    else:
        print("no cores=24 remaining")
    if DRY:
        print()
        print("Re-run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
