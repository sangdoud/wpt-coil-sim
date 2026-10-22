"""Compare the fresh 3-point test output against the stored 1705-point dataset."""

import csv

REF_CSV = r"C:\wpt\backup\pristine_data\sweep_all_unit30.csv"
NEW_CSV = r"C:\wpt\_test_run\sweep_all_unit30.csv"

FIELDS = ["L11_uH", "L22_uH", "L33_uH", "M12_uH", "M13_uH", "M23_uH", "k13", "k23"]


def load(path):
    out = {}
    with open(path, newline="") as f:
        r = csv.reader(f)
        header = next(r)
        for row in r:
            if len(row) < 13:
                continue
            key = (float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[4]))
            out[key] = {name: float(val) for name, val in zip(header[5:], row[5:13])}
    return out, header


ref, hdr = load(REF_CSV)
new, _ = load(NEW_CSV)

print("reference rows : %d" % len(ref))
print("new rows       : %d" % len(new))
print()

order = sorted(new.keys(), key=lambda k: (k[3], k[0]))
worst_overall = 0.0

for key in order:
    W, G, dx, tg, mu = key
    print("=" * 74)
    print("点: W=%.0f G=%.0f dx=%.0f tg=%.0f mu=%.0f" % key)
    print("  %-9s %14s %14s %10s" % ("量", "存档值(2024.1)", "本次复算", "偏差"))
    r = ref.get(key)
    if r is None:
        print("  !! 存档中找不到该点")
        continue
    worst = 0.0
    for f in FIELDS:
        a = r[f]
        b = new[key][f]
        d = abs(b - a) / abs(a) * 100.0 if a else 0.0
        worst = max(worst, d)
        flag = "  <== 超 2%" if d > 2.0 else ""
        print("  %-9s %14.4f %14.4f %9.3f%%%s" % (f, a, b, d, flag))
    worst_overall = max(worst_overall, worst)
    print("  该点最大偏差: %.3f%%   -> %s" % (worst, "OK" if worst <= 2.0 else "超容差"))

print()
print("=" * 74)
print("三点最大偏差: %.3f%%  ->  %s" % (worst_overall, "全部在 2% 容差内" if worst_overall <= 2.0 else "存在超容差项"))
