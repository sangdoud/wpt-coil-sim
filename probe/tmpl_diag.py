# -*- coding: utf-8 -*-
"""Diagnose the true periodic structure of coil_template_Rx.json (ASCII output)."""
import json
import math

import numpy as np

SRC = r"C:\wpt\coil_template_Rx.json"
OUT = r"C:\ansys maxwell2024\_work\tmpl_diag.txt"
P = np.array(json.load(open(SRC, encoding="utf-8")), dtype=float)[:, :2]
N = len(P)
BUF = []


def print(*a):                      # noqa: A001  (write to buffer, dump at end)
    BUF.append(" ".join(str(x) for x in a))


print("N=%d segs=%d  per_turn=%.3f" % (N, N - 1, (N - 1) / 12.0))


def turn(i):
    a0 = math.atan2(P[i][1] - P[i - 1][1], P[i][0] - P[i - 1][0])
    a1 = math.atan2(P[i + 1][1] - P[i][1], P[i + 1][0] - P[i][0])
    d = math.degrees(a1 - a0)
    while d > 180:
        d -= 360
    while d < -180:
        d += 360
    return d


T = [0.0] * N
for i in range(1, N - 1):
    T[i] = turn(i)
S = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))

print("\n--- i, turn(deg), seglen, s=cheb ---")
for i in range(0, 50):
    L = math.dist(P[i], P[i + 1]) if i + 1 < N else 0.0
    print("%3d  %+8.4f  %8.4f  %9.5f" % (i, T[i], L, S[i]))

print("\n--- turn magnitude histogram ---")
buckets = {}
for t in T:
    k = round(abs(t), 3)
    buckets[k] = buckets.get(k, 0) + 1
for k in sorted(buckets):
    if buckets[k] > 3 or k > 1.0:
        print("  |turn|=%.3f  count=%d" % (k, buckets[k]))

print("\n--- per-period (16 pts) count of |turn|>1 by residue ---")
res = {}
for i in range(1, N - 1):
    if abs(T[i]) > 1.0:
        r = i % 16
        res[r] = res.get(r, 0) + 1
for r in sorted(res):
    print("  residue %2d : %d" % (r, res[r]))

print("\n--- run structure by threshold ---")
for thr in (0.5, 1.0, 2.0, 4.0, 6.0, 8.0):
    runs = []
    i = 0
    kinds = ["arc" if abs(t) > thr else "st" for t in T]
    while i < N:
        j = i
        while j + 1 < N and kinds[j + 1] == kinds[i]:
            j += 1
        runs.append((kinds[i], i, j))
        i = j + 1
    na = sum(1 for r in runs if r[0] == "arc")
    acl = sorted(set(r[2] - r[1] for r in runs if r[0] == "arc"))
    scl = sorted(set(r[2] - r[1] for r in runs if r[0] == "st"))
    print("  thr=%.1f : runs=%d arc=%d  arc_chords=%s  st_chords=%s"
          % (thr, len(runs), na, acl, scl))

# geometric check: distance from spiral centre to each point (should be constant on flats)
print("\n--- s on flats (first 160 pts): min/max per 16-block ---")
for k in range(0, 10):
    blk = S[k * 16:(k + 1) * 16]
    if len(blk):
        print("  block %2d: s[%8.4f .. %8.4f]  uniq_round4=%s"
              % (k, blk.min(), blk.max(),
                 sorted(set(round(float(v), 4) for v in blk))[:6]))

open(OUT, "w", encoding="utf-8").write("\n".join(BUF) + "\n")
