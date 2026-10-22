# -*- coding: utf-8 -*-
"""验证 coil_gen.py 的拐角修正补丁。

四项硬性检查：
  1) legacy 模式与备份的旧模块**逐位一致**（回滚口径可信）
  2) phase 模式在参考参数下与模板逐点恒等（历史验证不受影响）
  3) phase 模式下全批 256 工况无 >15° 假尖角
  4) phase 模式仍满足 LC/KR 锚点口径（外缘 = LC·K_LC，环半径 = KR·LC·K_LC/2）
"""
import csv
import importlib.util
import math
import sys

import numpy as np

BACKUP = sys.argv[1] if len(sys.argv) > 1 else None
sys.path.insert(0, r"C:\wpt")
import coil_gen as CG          # noqa: E402  已打补丁

if BACKUP:
    spec = importlib.util.spec_from_file_location("coil_gen_old", BACKUP + r"\coil_gen.py")
    CG_OLD = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(CG_OLD)
else:
    CG_OLD = None

CASES = [(165.0, 30.0 / 83.6415), (216.7738, 0.2294), (120.1885, 0.2807),
         (219.9397, 0.3756), (218.8542, 0.4997), (121.7205, 0.4823)]


def kink(P):
    v = np.diff(P, axis=0)
    ang = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    d = np.abs((np.diff(ang) + 180.0) % 360.0 - 180.0)
    return float(d.max())


def main():
    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("  OK   " if cond else "  FAIL ") + msg)
        ok = ok and cond

    print("=" * 96)
    print("① legacy 模式 vs 备份旧模块（必须逐位一致）")
    CG.PATH_MODE = "legacy"
    worst = 0.0
    for LC, KR in CASES:
        a = CG.make_path(LC, KR)
        if CG_OLD is not None:
            b = CG_OLD.make_path(LC, KR)
            worst = max(worst, float(np.abs(a - b).max()))
    if CG_OLD is not None:
        check(worst < 1e-12, "6 组参数最大差异 %.3e mm（阈值 1e-12）" % worst)
    else:
        print("  (未提供备份路径，跳过)")

    print("② phase 模式参考点恒等性")
    CG.PATH_MODE = "phase"
    CG._load()
    T = np.array(CG._ref, dtype=float)[:, :2]
    P = CG.make_path(165.0, 30.0 / 83.6415)[:, :2]
    check(float(np.abs(P - T).max()) < 1e-4,
          "与模板最大差异 %.3e mm（阈值 1e-4）" % float(np.abs(P - T).max()))

    print("③ 全批 256 工况的尖角（phase）")
    rows = list(csv.DictReader(open(r"C:\ansys maxwell2024\_work\b1_plan.csv",
                                    encoding="utf-8-sig")))
    angs, gaps = [], []
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        Pp = CG.make_path(LC, KR)[:, :2]
        angs.append(kink(Pp))
        gaps.append(CG.path_dims(LC, KR)["gap_min"])
    angs = np.array(angs)
    check(angs.max() < 15.0, "最大转角 %.2f°（中位 %.2f°），>15° 的工况 %d/256"
          % (angs.max(), np.median(angs), int((angs > 15).sum())))
    check(min(gaps) > 0.5, "最小匝间隙 %.3f mm" % min(gaps))

    print("④ 锚点口径（phase）")
    K = CG.k_lc()
    wi = wo = 0.0
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        Pp = CG.make_path(LC, KR)[:, :2]
        s = np.maximum(np.abs(Pp[:, 0]), np.abs(Pp[:, 1]))
        # 外缘锚点：路径最外点应在 ±h_out（中心线外跨 = LC·K_LC/2）
        wo = max(wo, abs(float(s.max()) - LC * K / 2.0))
        # 环半径锚点：直边（用第 40 点附近，避开圆角）应等于 h_in 侧
        # 用 u=0 附近的直边半径（第 2~6 点）估计内环
        wi = max(wi, 0.0)
    check(wo < 0.02, "外缘锚点最大偏差 %.4f mm（= LC·K_LC/2）" % wo)

    # 直边点（局部转角≈0）的环半径必须严格等于 h_in' + (R_template - h_in_ref)·k；
    # 圆角处 s 低于环半径是**设计使然**（圆角切掉角），单独作为信息报告。
    dev, dip = [], []
    K2 = CG.k_lc()
    hin_ref, hout_ref = float(CG._s_ref[0]), float(CG._s_ref.max())
    s_tpl = CG._s_ref
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        Pp = CG.make_path(LC, KR)[:, :2]
        s = np.maximum(np.abs(Pp[:, 0]), np.abs(Pp[:, 1]))
        d = np.abs(np.diff(np.unwrap(np.arctan2(np.diff(Pp[:, 0]), np.diff(Pp[:, 1])))))
        straight = np.concatenate([[True], d < 0.0001, [True]])
        h_out, h_in = LC * K2 / 2.0, KR * LC * K2 / 2.0
        k = (h_out - h_in) / (hout_ref - hin_ref)
        want = h_in + (s_tpl - hin_ref) * k
        dev.append(float(np.abs(s[straight] - want[straight]).max()))
        dip.append(float((want - s).max()))
    check(max(dev) < 0.01, "直边环半径 vs 口径公式 最大偏差 %.5f mm" % max(dev))
    print("  INFO 圆角下沉（设计使然，随环半径等比）：%.2f ~ %.2f mm"
          % (min(dip), max(dip)))
    print("=" * 96)
    print("补丁验证%s" % ("通过 ✓" if ok else "失败 ✗"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
