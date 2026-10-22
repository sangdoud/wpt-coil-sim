"""Repoint stale C:/Users/lenovo/... paths to C:/wpt across the C:\\wpt scripts.

  python patch_paths.py --dry-run   -> show exactly what would change
  python patch_paths.py             -> apply

Only rewrites the known stale path prefixes. Reports every single change with
file, line number, and before/after text.
"""

import os
import sys

ROOT = r"C:\wpt"
EXCLUDE_DIRS = {"backup", "_incident_20260913", "__pycache__"}

# Ordered: most specific first.
REPLACEMENTS = [
    (r"C:/Users/lenovo/Desktop/zidong", r"C:/wpt"),
    (r"C:\Users\lenovo\Desktop\zidong", r"C:\wpt"),
    (r"C:\Users\lenovo\Desktop\L_Table.csv", r"C:\wpt\L_Table.csv"),
    (r"C:\Users\lenovo\Documents\Ansoft", r"C:\wpt"),
]

# Docs that give runnable instructions -> update.
MD_TARGETS = [
    "README_20260826_全参数扫描.md",
    "README_服务器部署_Windows.md",
]

# This one is a migration mapping table where the OLD path is the subject.
MD_SKIP = {"README_迁移指南.md"}

DRY = "--dry-run" in sys.argv


def walk_targets():
    out = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(os.path.join(dirpath, fn))
            elif fn in MD_TARGETS and fn not in MD_SKIP:
                out.append(os.path.join(dirpath, fn))
    return sorted(out)


def main():
    targets = walk_targets()
    print("scanning %d files under %s" % (len(targets), ROOT))
    print("mode:", "DRY-RUN (nothing written)" if DRY else "APPLY")
    print()

    changed_files = 0
    changed_hits = 0
    remaining = []

    for path in targets:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                lines = fh.readlines()
        except UnicodeDecodeError:
            with open(path, "r", encoding="gbk", errors="replace") as fh:
                lines = fh.readlines()

        new_lines = []
        file_hits = []
        for i, line in enumerate(lines, 1):
            original = line
            for old, new in REPLACEMENTS:
                if old in line:
                    line = line.replace(old, new)
            if line != original:
                file_hits.append((i, original.rstrip("\n"), line.rstrip("\n")))
            new_lines.append(line)

        if file_hits:
            changed_files += 1
            changed_hits += len(file_hits)
            print("--- %s  (%d 处)" % (path, len(file_hits)))
            for ln, before, after in file_hits:
                print("  L%d" % ln)
                print("    -  %s" % before.strip())
                print("    +  %s" % after.strip())
            if not DRY:
                with open(path, "w", encoding="utf-8", newline="") as fh:
                    fh.writelines(new_lines)
            print()

        # anything still mentioning lenovo afterwards?
        for line in new_lines:
            if "lenovo" in line:
                remaining.append((path, line.rstrip("\n").strip()))

    print("=" * 60)
    print("files changed : %d" % changed_files)
    print("lines changed : %d" % changed_hits)

    if remaining:
        print()
        print("!! still contains 'lenovo' after patching:")
        for p, l in remaining:
            print("   %s :: %s" % (p, l))
    else:
        print("no 'lenovo' remaining in scanned targets")

    print()
    print("NOTE: README_迁移指南.md intentionally skipped (migration mapping table).")
    if DRY:
        print("Re-run without --dry-run to apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
