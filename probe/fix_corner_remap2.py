# -*- coding: utf-8 -*-
"""拐角缺陷修法 v2：用「累积转角」作环进度坐标做重映射（离线验证）。

现状：λ = s'/s，s = 逐点 max(|x|,|y|)。拐角圆角处 s 掉到环半径以下 ->
      圆角各点 λ 不同 -> 圆角被拉成径向尖刺（最大 98.7°）。

v2：环进度用「累积转角」u = Θ(p)/Θ_total（方螺旋每圈 360°，12 匝 = 4320°），
    与点的局部形状无关；环半径 R(u) = h_in + u·(h_out-h_in)；缩放 λ = R'(u)/R_ref(u)。
    性质：
      - 参考参数下 R' = R_ref -> λ ≡ 1 -> **逐点恒等**（历史验证不受影响）
      - 圆角跨越的 u 只有 ~2%（90°/4320°）-> λ 在圆角内近似常数 -> 形状保持
      - 直边同理 -> 不再出现假尖角

本脚本离线验证：恒等性、转角分布、匝间隙、内外锚点。
"""
import csv
import math
import sys

import numpy as np

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG          # noqa: E402

K_LC = CG.k_lc()
H_IN_REF, H_OUT_REF = 30.0, 83.6415


def turning_phase(P):
    """累积转角（度），归一化到 [0,1]。方螺旋 12 匝 ≈ 4320°。返回 (每点相位, 总转角)。"""
    v = np.diff(P, axis=0)                      # 767 段
    ang = np.arctan2(v[:, 1], v[:, 0])          # 767
    d = np.abs((np.diff(ang) + np.pi) % (2 * np.pi) - np.pi)   # 766 个段间转角
    theta = np.concatenate([[0.0, 0.0], np.cumsum(d)])         # 每点一个值（768）
    return theta / theta[-1], theta[-1]


def path_v2(LC, KR):
    P = CG.make_path(LC, KR)[:, :2]
    ref = np.array(CG.make_path(165.0, 30.0 / 83.6415)[:, :2])   # 参考路径（模板原生）
    u, total = turning_phase(ref)
    h_out, h_in = LC * K_LC / 2.0, KR * LC * K_LC / 2.0
    R_ref = H_IN_REF + u * (H_OUT_REF - H_IN_REF)
    R_new = h_in + u * (h_out - h_in)
    lam = R_new / R_ref
    return P * lam[:, None], math.degrees(total)


def metrics(P):
    v = np.diff(P, axis=0)
    ang = np.degrees(np.arctan2(v[:, 1], v[:, 0]))
    d = np.abs((np.diff(ang) + 180.0) % 360.0 - 180.0)
    s = np.maximum(np.abs(P[:, 0]), np.abs(P[:, 1]))
    gap = float((s[64:] - s[:-64]).min()) - CG.WIDTH
    return float(d.max()), gap, float(s.max()), float(s.min())


def main():
    rows = list(csv.DictReader(open(r"C:\ansys maxwell2024\_work\b1_plan.csv",
                                    encoding="utf-8-sig")))
    P0 = CG.make_path(165.0, 30.0 / 83.6415)[:, :2]
    P1, total = path_v2(165.0, 30.0 / 83.6415)
    print("=" * 100)
    print("① 参考点恒等性：最大位移 %.3e mm  %s（累积转角 %.1f° ≈ 12×360°）"
          % (np.abs(P1 - P0).max(), "恒等 ✓" if np.abs(P1 - P0).max() < 1e-9 else "★非恒等", total))
    print()
    print("② 逐工况对比（修正前 -> 修正后）")
    print("  %-9s %7s %7s | %8s %8s | %9s %9s | %8s"
          % ("case", "LC", "KR", "转角前", "转角后", "间隙前", "间隙后", "位移mm"))
    before, after, shifts = [], [], []
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        Pa = CG.make_path(LC, KR)[:, :2]
        Pb, _ = path_v2(LC, KR)
        ma, mb = metrics(Pa), metrics(Pb)
        before.append(ma[0])
        after.append(mb[0])
        shifts.append(float(np.abs(Pb - Pa).max()))
        if r["case_id"] in ("b1_0163", "b1_0169", "b1_0126", "b1_0213", "b1_0236",
                            "b1_0254", "b1_0003"):
            print("  %-9s %7.2f %7.4f | %8.2f %8.2f | %9.3f %9.3f | %8.2f"
                  % (r["case_id"], LC, KR, ma[0], mb[0], ma[1], mb[1], shifts[-1]))
    before, after, shifts = np.array(before), np.array(after), np.array(shifts)
    print()
    print("③ 全批 256 工况统计")
    print("   最大转角 修正前: 中位 %.2f°  p90 %.2f°  max %.2f°   (>15°: %d/256)"
          % (np.median(before), np.percentile(before, 90), before.max(), int((before > 15).sum())))
    print("   最大转角 修正后: 中位 %.2f°  p90 %.2f°  max %.2f°   (>15°: %d/256)"
          % (np.median(after), np.percentile(after, 90), after.max(), int((after > 15).sum())))
    print("   几何位移: 中位 %.2f mm  p90 %.2f mm  max %.2f mm" %
          (np.median(shifts), np.percentile(shifts, 90), shifts.max()))
    print()
    print("④ 锚点/间隙一致性（修正后应仍满足 Lc、KR 口径）")
    worst = dict(inp=0.0, out=0.0, gap=0.0)
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        ma = metrics(CG.make_path(LC, KR)[:, :2])
        mb = metrics(path_v2(LC, KR)[0])
        worst["inp"] = max(worst["inp"], abs(ma[3] - mb[3]))
        worst["out"] = max(worst["out"], abs(ma[2] - mb[2]))
        worst["gap"] = max(worst["gap"], abs(ma[1] - mb[1]))
    print("   内孔锚点变化 ≤ %.3f mm   外缘锚点变化 ≤ %.3f mm   匝间隙变化 ≤ %.3f mm"
          % (worst["inp"], worst["out"], worst["gap"]))
    print("=" * 100)


if __name__ == "__main__":
    main()
