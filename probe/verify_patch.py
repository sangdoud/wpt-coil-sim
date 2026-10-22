"""Post-patch verification: syntax-check every .py under C:\\wpt and re-scan for
stale lenovo paths. Read-only.
"""

import ast
import os
import sys

ROOT = r"C:\wpt"
EXCLUDE_DIRS = {"backup", "_incident_20260913", "__pycache__"}

py_files = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
    for fn in filenames:
        if fn.endswith(".py"):
            py_files.append(os.path.join(dirpath, fn))
py_files.sort()

print("=== syntax check (%d .py files) ===" % len(py_files))
bad = []
for p in py_files:
    try:
        with open(p, "r", encoding="utf-8") as fh:
            src = fh.read()
        ast.parse(src, filename=p)
    except SyntaxError as e:
        bad.append((p, "SyntaxError line %s: %s" % (e.lineno, e.msg)))
    except Exception as e:
        bad.append((p, "%s: %s" % (type(e).__name__, e)))

if bad:
    print("!! FAILURES:")
    for p, msg in bad:
        print("   %s -> %s" % (p, msg))
else:
    print("all %d files parse cleanly" % len(py_files))

print()
print("=== residual 'lenovo' scan (all text files) ===")
exts = (".py", ".md", ".bat", ".txt", ".csv", ".json", ".log", ".cfg", ".ini")
hits = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
    for fn in filenames:
        if not fn.endswith(exts):
            continue
        p = os.path.join(dirpath, fn)
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if "lenovo" in line:
                        hits.append((p, i, line.strip()))
        except Exception as e:
            print("  (could not read %s: %s)" % (p, e))

if hits:
    print("%d residual occurrence(s):" % len(hits))
    for p, i, l in hits:
        print("   %s L%d: %s" % (p, i, l))
else:
    print("none")

print()
print("=== batch_sweep_unit30.py config block ===")
with open(os.path.join(ROOT, "batch_sweep_unit30.py"), encoding="utf-8") as fh:
    lines = fh.readlines()
for i, line in enumerate(lines[13:23], 14):
    print("  %2d: %s" % (i, line.rstrip()))

sys.exit(1 if bad else 0)
