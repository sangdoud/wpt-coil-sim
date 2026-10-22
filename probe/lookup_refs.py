"""Look up the stored reference rows for the 3 points we will re-run."""

import csv

TARGETS = [
    (10.0, 20.0, -150.0, 0.0, 1000.0),
    (15.0, 15.0, -150.0, 30.0, 1000.0),
    (20.0, 10.0, -150.0, 60.0, 1000.0),
]

p = r"C:\wpt\sweep_all_unit30.csv"
found = {}
with open(p, newline="") as f:
    r = csv.reader(f)
    header = next(r)
    for row in r:
        if len(row) < 13:
            continue
        key = (float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]))
        if key in TARGETS:
            found[key] = row

print("header:", header)
for t in TARGETS:
    row = found.get(t)
    print()
    if row:
        print("FOUND  %s" % (t,))
        for name, val in zip(header, row):
            print("    %-12s %s" % (name, val))
    else:
        print("MISSING %s" % (t,))

print()
print("total found: %d / %d" % (len(found), len(TARGETS)))
