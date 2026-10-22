# -*- coding: utf-8 -*-
r"""数据契约实现（《技术文档_项目后续改动方案》第 2 章）。

放在 C:\wpt，与 coil_gen.py / batch_sweep_lc.py 同目录。

本模块负责三件事（都不涉及仿真调度，仿真方案确定后再写采集脚本）：
  1. derived()      —— 7 个主变量 -> 派生几何（2.2 节公式，逐条实现）
  2. build_ferrite()—— 按两侧**独立** fill/厚度 铺铁氧体条，长度 = 1.2×Lc（取整1mm）
  3. 两个契约 CSV 的写出：batchN_cases.csv / batchN_curves.csv（3.5 节列名逐字对齐）

7 个主变量（列名即为契约列名）：
  coil_size(Lc) 120~220mm | hole_ratio(r_h) 0.2~0.5 | tx_fill 1/3~2/3
  rx_fill 1/3~2/3 | tx_thick 5~10mm | rx_thick 5~10mm | spacing_ratio(g) -0.5~+0.5
"""
import csv
import math
import os

import coil_gen as CG          # 复用线圈参数化（路径/引线/端子）

UNIT = 30.0                    # 铁氧体单元节距（条宽 + 条间气隙 = 30）
Z_GAP = 30.0                   # 线圈到铁氧体表面气隙
HOLE_RAD = 1.0                 # 接收引线穿铁氧体的开孔半径
N_POINTS = 41                  # 接收移动扫描固定点数
# ---------------- 提速开关（①②③ 见提速方案）----------------
HALF_SWEEP = True              # ① 只算 x>=0 的 21 点，另一半用镜像关系展开（零精度损失）
PASSES = 4                     # ③ 放宽自适应趟数（原 8）
PCT_ERROR = 10.0               # ③ 放宽收敛判据（原 5）
REGION_SCALE = True            # ② Region 随 Lc 缩放（原固定 ±330）

MAIN_COLS = ["coil_size", "hole_ratio", "tx_fill", "rx_fill",
             "tx_thick", "rx_thick", "spacing_ratio"]

CASES_COLS = ["case_id"] + MAIN_COLS + [
    "tx_bar_w", "rx_bar_w", "ferrite_len", "edge_gap", "center_dist",
    "sweep_span", "n_points", "n_bars_rx", "rx_volume", "M_pp", "raw_file"]

CURVES_COLS = ["case_id", "position_x", "M1", "M2", "M_pp",
               "L11", "L22", "L33", "k13", "k23"]


# ------------------------------------------------------------------ 派生几何
def derived(LC, g, tx_fill, rx_fill, rx_thick):
    """严格执行 2.2 节派生规则。返回 dict（长度 mm、体积 mm³）。"""
    tx_bar_w = UNIT * tx_fill                       # 发射条宽
    rx_bar_w = UNIT * rx_fill                       # 接收条宽
    ferrite_len = int(round(1.2 * LC))              # 两侧相同，取整 1mm
    edge_gap = int(round(g * LC))                   # 边沿间隙，取整 1mm
    center_dist = LC + edge_gap                     # = Lc(1+g)（取整后口径）
    sweep_span = LC * (2.0 + g)                     # 扫描跨度
    n_bars_rx = int(math.floor(LC / UNIT)) + 1      # 参照铺设规则，实际值由 build_ferrite 回报
    rx_volume = n_bars_rx * rx_bar_w * rx_thick * ferrite_len
    return dict(tx_bar_w=tx_bar_w, rx_bar_w=rx_bar_w, ferrite_len=ferrite_len,
                edge_gap=edge_gap, center_dist=center_dist, sweep_span=sweep_span,
                n_points=N_POINTS, n_bars_rx=n_bars_rx, rx_volume=rx_volume)


def sweep_positions(LC, g):
    """3.4 节：41 点等距，x_i = -S/2 + i*S/40，i=0..40（中心在两发射线圈中点）。"""
    S = LC * (2.0 + g)
    return [-S / 2.0 + i * S / 40.0 for i in range(N_POINTS)]


def mpp_scalar(curve_mpp):
    """M_pp 回退标量：路径均值口径（--mpp_mode mean）。"""
    v = [x for x in curve_mpp if x is not None]
    return sum(v) / len(v) if v else None


# ------------------------------------------------------------------ 铁氧体铺设
def _x_centers(lo, hi, w):
    """从 lo 到 hi 按 UNIT 节距居中排布条心，两端过覆盖。"""
    pitch = UNIT
    n = int(math.ceil((hi - lo) / pitch)) + 1
    center = (lo + hi) / 2.0
    start = center - (n - 1) * pitch / 2.0
    return [start + k * pitch for k in range(n)]


def build_ferrite(m, LC, g, tx_fill, rx_fill, tx_thick, rx_thick, rx_leads,
                  log=print):
    """按两侧独立参数铺铁氧体条（条长 1.2*Lc），返回派生量 dict（含实际 n_bars_rx）。

    rx_leads: 接收引线的 (x, y) 列表（绝对坐标，Rx 在 dx=0 时的位置），用于开孔。
    """
    d = derived(LC, g, tx_fill, rx_fill, rx_thick)
    W_tx, W_rx = d["tx_bar_w"], d["rx_bar_w"]
    y_half = d["ferrite_len"] / 2.0
    tg = float(d["edge_gap"])
    # 先清旧条 + 残留开孔柱
    for n in [n for n in m.modeler.object_names
              if n.startswith("ferrite_") or n.startswith("aux_hole")]:
        try:
            m.modeler.delete(n)
        except Exception:
            pass

    tx1_c = -tg / 2.0 - LC / 2.0
    tx2_c = tg / 2.0 + LC / 2.0
    emit_lo, emit_hi = tx1_c - LC / 2.0, tx2_c + LC / 2.0
    ferr = []
    for xc in _x_centers(emit_lo, emit_hi, W_tx):
        nm = "ferrite_Tx_%d" % len([n for n in ferr if n.startswith("ferrite_Tx_")])
        try:
            b = m.modeler.create_box(origin=[xc - W_tx / 2.0, -y_half, -Z_GAP - tx_thick],
                                     sizes=[W_tx, 2 * y_half, tx_thick], name=nm)
            b.material_name = "ferrite"
            ferr.append(nm)
        except Exception as e:
            log("ferrite Tx err: %s" % repr(e))

    n_rx = 0
    for xc in _x_centers(-LC / 2.0, LC / 2.0, W_rx):
        nm = "ferrite_Rx_%d" % n_rx
        try:
            b = m.modeler.create_box(origin=[xc - W_rx / 2.0, -y_half, Z_GAP + 30.0],
                                     sizes=[W_rx, 2 * y_half, rx_thick], name=nm)
            b.material_name = "ferrite"
            ferr.append(nm)
            n_rx += 1
        except Exception as e:
            log("ferrite Rx err: %s" % repr(e))

    # 接收引线穿铁氧体：开孔
    for (ax, ly) in rx_leads:
        aux = None
        try:
            aux = m.modeler.create_cylinder(orientation="Z",
                                            origin=[ax, ly, Z_GAP + 30.0 - 1.0],
                                            radius=HOLE_RAD, height=rx_thick + 2.0,
                                            name="aux_hole")
        except Exception:
            pass
        if aux is None:
            continue
        for fn in [n for n in ferr if n.startswith("ferrite_Rx_")]:
            try:
                bb = m.modeler[fn].bounding_box
                if (bb[0] <= ax + 1.0 and bb[3] >= ax - 1.0
                        and bb[1] <= ly + 1.0 and bb[4] >= ly - 1.0):
                    m.modeler.subtract(blank_list=[fn], tool_list=[aux.name],
                                       keep_originals=False)
            except Exception:
                pass
        try:
            if aux.name in m.modeler.object_names:
                m.modeler.delete(aux.name)
        except Exception:
            pass

    d["n_bars_rx"] = n_rx                     # 用实际铺设条数覆盖估计值
    d["rx_volume"] = n_rx * W_rx * rx_thick * d["ferrite_len"]
    log("  铁氧体: Tx %d 条(宽%.2f 厚%.1f) + Rx %d 条(宽%.2f 厚%.1f) 长%.0f  V_rx=%.1f mm³"
        % (len(ferr) - n_rx, W_tx, tx_thick, n_rx, W_rx, rx_thick,
           d["ferrite_len"], d["rx_volume"]))
    return d


# ------------------------------------------------------------------ 契约导出
def sweep_positions_half(LC, g):
    """① 半扫：只取 x >= 0 的 21 点（含中心 x=0 与最右点 +S/2）。

    依据：几何关于 x=0 镜像（Tx1 层1 ↔ Tx2 层2），因此
        M1(+x) = M2(-x),  M2(+x) = M1(-x)
    文档 3.6 的镜像自检项用的就是这条关系（参考模型实测 0.9% ≤ 2%）。
    """
    S = LC * (2.0 + g)
    return [i * S / 40.0 for i in range(0, 21)]        # x = 0, S/40, ..., S/2


def expand_curve(xs_half, M1_half, M2_half):
    """由半条曲线（x>=0）展开成完整 41 点。

    左半由镜像关系给出：x<0 时  M1(x)=M2(-x),  M2(x)=M1(-x)。
    返回 (xs_full, M1_full, M2_full)，均按 x 升序。
    """
    left = []
    for k in range(len(xs_half) - 1, 0, -1):           # x<0，从最左到接近 0
        left.append((-xs_half[k], M2_half[k], M1_half[k]))
    full = left + [(xs_half[i], M1_half[i], M2_half[i]) for i in range(len(xs_half))]
    xs = [p[0] for p in full]
    M1 = [p[1] for p in full]
    M2 = [p[2] for p in full]
    return xs, M1, M2


def mirror_error(xs_full, M1_full, M2_full):
    """文档 3.6 自检项 2：max|M1(x) - M2(-x)| / 峰值。用于验证①的前提成立。"""
    by_x = {round(x, 6): (m1, m2) for x, m1, m2 in zip(xs_full, M1_full, M2_full)}
    pk = max(abs(v) for v in list(M1_full) + list(M2_full)) or 1.0
    worst = 0.0
    for x, (m1, _m2) in by_x.items():
        peer = by_x.get(round(-x, 6))
        if peer:
            worst = max(worst, abs(m1 - peer[1]))
    return worst / pk


def apply_setup(m, passes=None, pct=None):
    """③ 放宽自适应：直接设到 setup 上。返回 (passes, pct)。"""
    p = PASSES if passes is None else passes
    e = PCT_ERROR if pct is None else pct
    try:
        s = m.setups[0]
        s.props["MaximumPasses"] = p
        s.props["PercentError"] = e
        s.update()
    except Exception:
        pass
    return p, e


def region_box(LC, g):
    """② Region 随 Lc 缩放（自相似），替代原来固定的 ±330。

    规则：X 半宽 = 线圈阵列半跨 + 60；Y 上限 = 线圈 Y 半跨 + 60；
    -Y 面必须落在发射引线端面(y=-134.94)上、+Z 面落在接收引线顶端(75)上，
    否则 Maxwell 报 Illegal external terminal。
    """
    S = LC * (2.0 + g)
    x_half = max(S / 2.0, LC / 2.0) + 60.0
    y_hi = 1.2 * LC / 2.0 + 60.0
    return {"x": (-x_half, x_half), "y": (-134.94, y_hi), "z": (-45.0, 75.0)}


def write_cases(path, rows, append=False):
    """rows: dict 列表，键为 CASES_COLS（缺的填 ''）。"""
    new = (not append) or (not os.path.exists(path))
    with open(path, "a" if append else "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(CASES_COLS)
        for r in rows:
            w.writerow([r.get(c, "") for c in CASES_COLS])


def write_curves(path, rows, append=True):
    """rows: dict 列表，键为 CURVES_COLS。长表：每工况 41 行。"""
    new = (not append) or (not os.path.exists(path))
    with open(path, "a" if append else "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(CURVES_COLS)
        for r in rows:
            w.writerow([r.get(c, "") for c in CURVES_COLS])


def build_case_row(case_id, v, d, mpp):
    """把 7 主变量 + 派生量 + M_pp 组装成 cases 行。"""
    row = {"case_id": case_id, "M_pp": mpp, "raw_file": ""}
    row.update({k: v[k] for k in MAIN_COLS})
    row.update({k: d[k] for k in ("tx_bar_w", "rx_bar_w", "ferrite_len", "edge_gap",
                                  "center_dist", "sweep_span", "n_points",
                                  "n_bars_rx", "rx_volume")})
    return row


def build_curve_rows(case_id, xs, M1, M2, M_pp, L11, L22, L33, k13, k23):
    """组装 curves 长表（41 行）。L/k 可为标量或逐点列表。"""
    def at(v, i):
        if isinstance(v, (list, tuple)):
            return v[i]
        return v
    out = []
    for i, x in enumerate(xs):
        out.append({"case_id": case_id, "position_x": round(x, 4),
                    "M1": at(M1, i), "M2": at(M2, i), "M_pp": at(M_pp, i),
                    "L11": at(L11, i), "L22": at(L22, i), "L33": at(L33, i),
                    "k13": at(k13, i), "k23": at(k23, i)})
    return out


# ================= 镜像自检（双阈值版，2026-09-18 并入）=================
MIRROR_TOL_SUM_PCT = 2.0    # 和口径 |Δ(M1+M2)| / 峰值（%）
MIRROR_TOL_IND_PCT = 3.0    # 个体口径 max|ΔM1|,|ΔM2| / 峰值（%）


def mirror_check(xs_full, M1_full, M2_full,
                 tol_sum=MIRROR_TOL_SUM_PCT, tol_ind=MIRROR_TOL_IND_PCT):
    """文档 3.6 自检项 2（双阈值版）：判定 ① 镜像半扫的前提是否成立。

    返回 dict：
      peak      峰值 |M|
      sum_pct   max|Δ(M1+M2)| / 峰值  (%)   —— 决定目标量（f2/f3）能否用 ①
      ind_pct   max|ΔM1|,|ΔM2| / 峰值 (%)   —— 只影响导出的 M1/M2/k 列
      pass_sum / pass_ind / pass            各自与总判定
      n_pairs   参与比对的镜像点对数
    """
    by_x = {}
    for x, a, b in zip(xs_full, M1_full, M2_full):
        by_x[round(float(x), 6)] = (float(a), float(b))
    peak = max([abs(v) for v in list(M1_full) + list(M2_full)] or [1.0]) or 1.0
    sum_pct = ind_pct = 0.0
    n = 0
    for x, (m1p, m2p) in by_x.items():
        peer = by_x.get(round(-x, 6))
        if not peer:
            continue
        n += 1
        m1n, m2n = peer
        ind_pct = max(ind_pct, max(abs(m1n - m2p), abs(m2n - m1p)) / peak * 100.0)
        sum_pct = max(sum_pct, abs((m1n + m2n) - (m1p + m2p)) / peak * 100.0)
    return {"peak": peak, "sum_pct": sum_pct, "ind_pct": ind_pct, "n_pairs": n,
            "tol_sum": tol_sum, "tol_ind": tol_ind,
            "pass_sum": bool(sum_pct <= tol_sum), "pass_ind": bool(ind_pct <= tol_ind),
            "pass": bool(sum_pct <= tol_sum and ind_pct <= tol_ind)}


def asymmetry_at_center(M1_center, M2_center):
    """x=0 处的固有非对称度（%）。"""
    pk = max(abs(M1_center), abs(M2_center)) or 1.0
    return abs(M1_center - M2_center) / pk * 100.0


def case_asymmetry_tag(case_id, xs, M1, M2):
    """每工况的固有非对称度打标（**零额外求解**）。

    x=0 本来就是半扫 21 点里的第 0 点（`sweep_positions_half`：x = i*S/40, i=0..20），
    所以直接从该行取 M1/M2 即可：
        asym_pct = |M1(x=0) - M2(x=0)| / max(|M1|,|M2|) * 100
    再把整条曲线的双阈值镜像自检一起带上，供入库前筛选。
    返回 dict（键即 batchN_selfcheck.csv 的列）。
    """
    by_x = {round(float(x), 6): (float(a), float(b)) for x, a, b in zip(xs, M1, M2)}
    c = by_x.get(0.0)
    mc = mirror_check(xs, M1, M2)
    return {"case_id": case_id,
            "x0_M1": c[0] if c else None,
            "x0_M2": c[1] if c else None,
            "asym_pct": round(asymmetry_at_center(c[0], c[1]), 4) if c else None,
            "mirror_sum_pct": round(mc["sum_pct"], 4),
            "mirror_ind_pct": round(mc["ind_pct"], 4),
            "mirror_pairs": mc["n_pairs"],
            "mirror_pass": mc["pass"]}


SELFCHECK_COLS = ["case_id", "x0_M1", "x0_M2", "asym_pct",
                  "mirror_sum_pct", "mirror_ind_pct", "mirror_pairs", "mirror_pass"]


def write_selfcheck(path, rows, append=True):
    """写入**独立**的自检表（不是契约 CSV，契约列名不得改动）。"""
    import csv
    import os as _os
    new = (not append) or (not _os.path.exists(path))
    with open(path, "a" if append else "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(SELFCHECK_COLS)
        for r in rows:
            w.writerow([r.get(c, "") for c in SELFCHECK_COLS])
