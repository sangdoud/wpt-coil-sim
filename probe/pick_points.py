"""Pick a few already-computed points from sweep_all_unit30.csv to re-run as a
reproducibility check. Read-only."""

import csv

p = r"C:\wpt\sweep_all_unit30.csv"
rows = []
with open(p, newline="") as f:
    r = csv.reader(f)
    header = next(r)
    for row in r:
        if len(row) >= 13:
            rows.append(row)

print("header:", header)
print("total rows:", len(rows))

# distinct tx_gap values present
tgs = sorted({float(x[3]) for x in rows})
print("distinct tx_gap:", tgs)

# distinct mu
mus = sorted({float(x[4]) for x in rows})
print("distinct mu:", mus)


def show(label, pred, n=2):
    print()
    print("--- %s ---" % label)
    got = 0
    for row in rows:
        if pred(row):
            print("  W=%s G=%s dx=%s tg=%s mu=%s | L11=%s M13=%s k13=%s k23=%s"
                  % (row[0], row[1], row[2], row[3], row[4], row[5], row[9], row[11], row[12]))
            got += 1
            if got >= n:
                break
    if got == 0:
        print("  (none)")


show("tg=0", lambda r: float(r[3]) == 0.0)
show("tg=30", lambda r: float(r[3]) == 30.0)
show("tg=60", lambda r: float(r[3]) == 60.0)
show("mu!=1000", lambda r: float(r[4]) != 1000.0)
