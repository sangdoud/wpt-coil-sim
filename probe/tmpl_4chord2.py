# -*- coding: utf-8 -*-
"""Generate "4 chords per corner" templates from the reference path.

TRUE STRUCTURE (verified by tmpl_diag.py):
  768 points, 64 per turn = 4 corner-units of 16 chords.
  Within a 16-chord unit (residues mod 16):
      residues 8..15 + next residue 0  ->  corner arc, 9 points / 8 chords
      residues 1..7                    ->  straight run interior, turn 0.01 deg/chord
  So:  arc run     = points [8+16k .. 16+16k]   (clipped at N-1)
       straight run= points [16+16k .. 24+16k]  (plus leading run [0..8])
  Runs share their junction points.

VARIANTS (all keep the junction points EXACTLY -> straight/arc joins unchanged):
  v_4_1      arcs 4 chords (radius k*R) + straights collapsed to 1 chord   [primary, 240 segs]
  v_4_8      arcs 4 chords (radius k*R) + straights kept at 8 chords       [literal,  576 segs]
  v_decim    arcs decimated to every 2nd original point (vertices ON path) + straights 1 chord
  k mode     "inscribed" (k=1) | "area" (k solves A_center == original) | "len" (k solves length)

Offline only - no AEDT.  ASCII report to _work\tmpl_4chord2_report.txt
"""
import json
import math
import os

import numpy as np

SRC = r"C:\wpt\coil_template_Rx.json"
WORK = r"C:\ansys maxwell2024\_work"
REP = os.path.join(WORK, "tmpl_4chord2_report.txt")

P3 = np.array(json.load(open(SRC, encoding="utf-8")), dtype=float)
Z = P3[:, 2].copy() if P3.shape[1] > 2 else np.zeros(len(P3))
P = P3[:, :2]
N = len(P)
BUF = []


def say(*a):
    BUF.append(" ".join(str(x) for x in a))


def turn_deg(i):
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
    T[i] = turn_deg(i)


def fit_circle(Q):
    n = len(Q)
    mx, my = Q[:, 0].mean(), Q[:, 1].mean()
    u, v = Q[:, 0] - mx, Q[:, 1] - my
    suu, svv, suv = (u * u).sum(), (v * v).sum(), (u * v).sum()
    suuu, svvv = (u ** 3).sum(), (v ** 3).sum()
    suvv, svuu = (u * v * v).sum(), (v * u * u).sum()
    det = suu * svv - suv * suv
    if abs(det) < 1e-12:
        return None, None
    c1, c2 = (suuu + suvv) / 2, (svvv + svuu) / 2
    uc = (c1 * svv - c2 * suv) / det
    vc = (c2 * suu - c1 * suv) / det
    r = math.sqrt(uc * uc + vc * vc + (suu + svv) / n)
    return np.array([mx + uc, my + vc]), r


# ---------------------------------------------------------------- run table
RUNS = [("st", 0, 8)]
for k in range(48):
    a0, a1 = 8 + 16 * k, 16 + 16 * k
    if a0 > N - 1:
        break
    RUNS.append(("arc", a0, min(a1, N - 1)))
    s0, s1 = 16 + 16 * k, 24 + 16 * k
    if s0 > N - 1:
        break
    RUNS.append(("st", s0, min(s1, N - 1)))

n_arc = sum(1 for r in RUNS if r[0] == "arc")
n_st = sum(1 for r in RUNS if r[0] == "st")
say("runs: arc=%d straight=%d total=%d" % (n_arc, n_st, len(RUNS)))
say("arc chord counts  : %s" % sorted(set(r[2] - r[1] for r in RUNS if r[0] == "arc")))
say("straight chords   : %s" % sorted(set(r[2] - r[1] for r in RUNS if r[0] == "st")))

# structural verification against turns
bad_arc = [i for kd, i0, i1 in RUNS if kd == "arc"
           for i in range(i0 + 1, i1) if abs(T[i]) < 1.0]
bad_st = [i for kd, i0, i1 in RUNS if kd == "st"
          for i in range(i0 + 1, i1) if abs(T[i]) > 0.2]
say("verify: arc-interior points with |turn|<1deg : %d" % len(bad_arc))
say("verify: straight-interior points with |turn|>0.2deg : %d  %s"
    % (len(bad_st), bad_st[:8]))

# straight-run collinearity (distance of interior points from end-to-end chord)
worst_col = 0.0
for kd, i0, i1 in RUNS:
    if kd != "st" or i1 - i0 < 2:
        continue
    a, b = P[i0], P[i1]
    for i in range(i0 + 1, i1):
        vx, vy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(vx, vy)
        d = abs((P[i][0] - a[0]) * vy - (P[i][1] - a[1]) * vx) / L
        worst_col = max(worst_col, d)
say("straight-run collinearity: max interior offset = %.6f mm" % worst_col)

# arc fits
ARCS = []
for kd, i0, i1 in RUNS:
    if kd != "arc":
        continue
    qs = P[i0:i1 + 1]
    ctr, R = fit_circle(qs)
    a = [math.atan2(p[1] - ctr[1], p[0] - ctr[0]) for p in qs]
    for t in range(1, len(a)):
        while a[t] - a[t - 1] > math.pi:
            a[t] -= 2 * math.pi
        while a[t] - a[t - 1] < -math.pi:
            a[t] += 2 * math.pi
    ARCS.append(dict(i0=i0, i1=i1, ctr=ctr, R=R, a0=a[0], a1=a[-1],
                     span=abs(a[-1] - a[0]), resid=max(abs(math.hypot(p[0] - ctr[0],
                           p[1] - ctr[1]) - R) for p in qs)))
say("arc fit: n=%d  R range %.4f..%.4f  span range %.4f..%.4f rad  fit residual max %.5f mm"
    % (len(ARCS), min(a["R"] for a in ARCS), max(a["R"] for a in ARCS),
       min(a["span"] for a in ARCS), max(a["span"] for a in ARCS),
       max(a["resid"] for a in ARCS)))


# ---------------------------------------------------------------- builders
def build(n_arc_chord=4, n_st_chord=1, kmode="inscribed", decim=False):
    """Return (points, k_used). Junction points are kept exactly."""
    if decim:
        pts = []
        for idx, (kd, i0, i1) in enumerate(RUNS):
            if kd == "arc":
                qs = [tuple(P[i]) for i in range(i0, i1 + 1)]
                step = max(1, (len(qs) - 1) // n_arc_chord)
                sel = qs[::step]
                if sel[-1] != qs[-1]:
                    sel[-1] = qs[-1]
                sel = sel[:n_arc_chord + 1]
                new = sel
            else:
                qs = [tuple(P[i]) for i in range(i0, i1 + 1)]
                new = [qs[0], qs[-1]] if n_st_chord == 1 else qs
            pts.extend(new if idx == 0 else new[1:])
        return np.array(pts, dtype=float), 1.0

    def emit(k):
        pts = []
        for idx, (kd, i0, i1) in enumerate(RUNS):
            qs = [tuple(P[i]) for i in range(i0, i1 + 1)]
            if kd == "st":
                new = [qs[0], qs[-1]] if n_st_chord == 1 else qs
            else:
                n = min(n_arc_chord, len(qs) - 1)
                ctr, R, a0, a1 = None, None, None, None
                for A in ARCS:
                    if A["i0"] == i0:
                        ctr, R, a0, a1 = A["ctr"], A["R"], A["a0"], A["a1"]
                        break
                if ctr is None or n < 1:
                    new = [qs[0], qs[-1]]
                else:
                    new = [qs[0]]                       # junction pinned
                    for t in range(1, n):
                        ang = a0 + (a1 - a0) * t / float(n)
                        new.append((ctr[0] + k * R * math.cos(ang),
                                    ctr[1] + k * R * math.sin(ang)))
                    new.append(qs[-1])                  # junction pinned
            pts.extend(new if idx == 0 else new[1:])
        return np.array(pts, dtype=float)

    if kmode == "inscribed":
        return emit(1.0), 1.0
    A0 = area_center(P)
    L0 = plen(P)
    lo, hi = 0.80, 1.25
    for _ in range(60):
        mid = (lo + hi) / 2.0
        Q = emit(mid)
        v = area_center(Q) if kmode == "area" else plen(Q)
        ref = A0 if kmode == "area" else L0
        if (v - ref) * (1.0 if kmode == "area" else 1.0) < 0:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2.0
    return emit(k), k


def plen(A):
    return float(sum(math.dist(A[i - 1], A[i]) for i in range(1, len(A))))


def area_center(A):
    """Swept area from origin: 0.5*sum(x_i*y_{i+1}-x_{i+1}*y_i). Stable for open spiral."""
    s = 0.0
    for i in range(len(A) - 1):
        s += A[i][0] * A[i + 1][1] - A[i + 1][0] * A[i][1]
    return 0.5 * s


def area_closed(A):
    B = np.vstack([A, A[:1]])
    s = 0.0
    for i in range(len(B) - 1):
        s += B[i][0] * B[i + 1][1] - B[i + 1][0] * B[i][1]
    return 0.5 * s


def dist_to_polyline(pt, A):
    best = 1e9
    for i in range(1, len(A)):
        ax, ay = A[i - 1]
        bx, by = A[i]
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        t = 0.0 if L2 < 1e-18 else max(0.0, min(1.0, ((pt[0] - ax) * vx + (pt[1] - ay) * vy) / L2))
        d = math.hypot(pt[0] - (ax + t * vx), pt[1] - (ay + t * vy))
        best = min(best, d)
    return best


def densify(A, step=0.2):
    out = []
    for i in range(1, len(A)):
        a, b = A[i - 1], A[i]
        L = math.dist(a, b)
        kk = max(1, int(math.ceil(L / step)))
        for t in range(kk):
            f = t / float(kk)
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
    out.append((A[-1][0], A[-1][1]))
    return np.array(out)


S = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
i_max = int(np.argmax(S))
in_arc = any(kd == "arc" and i0 <= i_max <= i1 for kd, i0, i1 in RUNS)
say("")
say("ANCHORS: s[0]=%.5f  s_max=%.5f (at i=%d, %s run)"
    % (S[0], S.max(), i_max, "ARC" if in_arc else "straight"))
say("A_center=%.4f mm2   A_closed=%.4f mm2   len=%.4f mm"
    % (area_center(P), area_closed(P), plen(P)))

VARIANTS = [("v_4_1_inscribed", dict(n_arc_chord=4, n_st_chord=1, kmode="inscribed")),
            ("v_4_1_area", dict(n_arc_chord=4, n_st_chord=1, kmode="area")),
            ("v_4_1_len", dict(n_arc_chord=4, n_st_chord=1, kmode="len")),
            ("v_4_8_inscribed", dict(n_arc_chord=4, n_st_chord=8, kmode="inscribed")),
            ("v_decim_4_1", dict(decim=True)),
            ("v_selftest_8_8", dict(n_arc_chord=8, n_st_chord=8, kmode="inscribed"))]

summary = {}
for name, kw in VARIANTS:
    A, k = build(**kw)
    L = plen(A)
    Ac = area_center(A)
    Acl = area_closed(A)
    dev_fwd = max(dist_to_polyline(tuple(p), A) for p in P)
    Ad = densify(A, 0.2)
    dev_bwd = max(dist_to_polyline(tuple(p), P) for p in Ad[::3])
    Sa = np.maximum(np.abs(A[:, 0]), np.abs(A[:, 1]))
    bb_o = [P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max()]
    bb_n = [A[:, 0].min(), A[:, 1].min(), A[:, 0].max(), A[:, 1].max()]
    info = dict(n=len(A), segs=len(A) - 1, k=round(k, 6),
                len_mm=L, dlen_pct=100 * (L - plen(P)) / plen(P),
                area_mm2=Ac, darea_pct=100 * (Ac - area_center(P)) / area_center(P),
                aclosed_mm2=Acl, daclosed_pct=100 * (Acl - area_closed(P)) / area_closed(P),
                dev_fwd=dev_fwd, dev_bwd=dev_bwd,
                s0=float(Sa[0]), s_max=float(Sa.max()),
                bbox_diff=[float(bb_n[i] - bb_o[i]) for i in range(4)])
    summary[name] = info
    say("")
    say("[%s]  pts=%d segs=%d  k=%.6f" % (name, info["n"], info["segs"], k))
    say("   len  %.4f mm (%+.4f%%)   A_center %.2f mm2 (%+.4f%%)   A_closed (%+.4f%%)"
        % (L, info["dlen_pct"], Ac, info["darea_pct"], info["daclosed_pct"]))
    say("   dev: orig->new %.4f mm   new->orig %.4f mm" % (dev_fwd, dev_bwd))
    say("   s0 %.5f  s_max %.5f (orig %.5f)   bbox diff %s"
        % (info["s0"], info["s_max"], S.max(), ["%+.4f" % v for v in info["bbox_diff"]]))
    if name in ("v_4_1_inscribed", "v_4_1_area", "v_decim_4_1", "v_4_8_inscribed",
                "v_4_1_len"):
        out = os.path.join(WORK, "coil_template_Rx_%s.json" % name)
        json.dump([[float(p[0]), float(p[1]), float(Z[0])] for p in A],
                  open(out, "w", encoding="utf-8"))
        say("   -> %s" % out)

json.dump(summary, open(os.path.join(WORK, "tmpl_4chord2_report.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=2)
open(REP, "w", encoding="utf-8").write("\n".join(BUF) + "\n")
