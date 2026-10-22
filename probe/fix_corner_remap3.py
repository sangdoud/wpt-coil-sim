# -*- coding: utf-8 -*-
"""拐角缺陷修法 v3：直接对**原始模板**施加「相位式」径向重映射（离线验证）。

现状 make_path：s = 逐点 max(|x|,|y|)；f = [h_in' + (s-h_in_ref)k]/s；p' = 模板点 × f
    -> 圆角处 s 掉到环半径以下，f 与直边不同 -> 圆角被拉成径向尖刺（最大 98.7°）

v3：相位 u = 累积转角/总转角（与局部形状无关，方螺旋 12 匝 ≈ 4320°）
    R_ref(u) = h_in_ref + u·(h_out_ref-h_in_ref)
    R_new(u) = h_in'    + u·(h_out'-h_in')
    f(u) = R_new/R_ref；p' = 模板点 × f(u)
性质：参考参数下 f ≡ 1（逐点恒等）；圆角跨越 u 仅 ~2% -> f 在圆角内近似常数 -> 形状保持。
"""
import csv
import math
import sys

import numpy as np

sys.path.insert(0, r"C:\wpt")
import coil_gen as CG          # noqa: E402

K_LC = CG.k_lc()
H_IN_REF, H_OUT_REF = 30.0, 83.6415
CG._load()
T = np.array(CG._ref, dtype=float)[:, :2]        # 原始模板（768×2）


def phase(P):
    v = np.diff(P, axis=0)
    ang = np.arctan2(v[:, 1], v[:, 0])
    d = np.abs((np.diff(ang) + np.pi) % (2 * np.pi) - np.pi)
    th = np.concatenate([[0.0, 0.0], np.cumsum(d)])
    return th / th[-1], math.degrees(th[-1])


U, TOTAL = phase(T)


def path_v3(LC, KR):
    h_out, h_in = LC * K_LC / 2.0, KR * LC * K_LC / 2.0
    R_ref = H_IN_REF + U * (H_OUT_REF - H_IN_REF)
    R_new = h_in + U * (h_out - h_in)
    f = R_new / R_ref
    return T * f[:, None]


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
    print("=" * 102)
    print("① 模板相位：总累积转角 %.1f°（12 匝理论 4320°），u 单调 %s"
          % (TOTAL, "是 ✓" if np.all(np.diff(U) >= -1e-12) else "否 ✗"))
    P0 = CG.make_path(165.0, 30.0 / 83.6415)[:, :2]
    P1 = path_v3(165.0, 30.0 / 83.6415)
    print("② 参考点恒等性：与现行路径最大位移 %.3e mm  %s"
          % (np.abs(P1 - P0).max(), "恒等 ✓" if np.abs(P1 - P0).max() < 1e-9 else "★非恒等"))
    print()
    print("③ 逐工况（现行 -> v3）")
    print("  %-9s %7s %7s | %8s %8s | %9s %9s | %8s"
          % ("case", "LC", "KR", "转角现", "转角v3", "间隙现", "间隙v3", "位移mm"))
    before, after, shifts = [], [], []
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        Pa, Pb = CG.make_path(LC, KR)[:, :2], path_v3(LC, KR)
        ma, mb = metrics(Pa), metrics(Pb)
        before.append(ma[0]); after.append(mb[0]); shifts.append(float(np.abs(Pb - Pa).max()))
        if r["case_id"] in ("b1_0163", "b1_0169", "b1_0126", "b1_0213", "b1_0236",
                            "b1_0254", "b1_0003"):
            print("  %-9s %7.2f %7.4f | %8.2f %8.2f | %9.3f %9.3f | %8.2f"
                  % (r["case_id"], LC, KR, ma[0], mb[0], ma[1], mb[1], shifts[-1]))
    before, after, shifts = np.array(before), np.array(after), np.array(shifts)
    print()
    print("④ 全批 256 工况")
    print("   最大转角 现行 : 中位 %6.2f°  p90 %6.2f°  max %6.2f°   >15°: %d/256"
          % (np.median(before), np.percentile(before, 90), before.max(), int((before > 15).sum())))
    print("   最大转角 v3   : 中位 %6.2f°  p90 %6.2f°  max %6.2f°   >15°: %d/256"
          % (np.median(after), np.percentile(after, 90), after.max(), int((after > 15).sum())))
    print("   几何位移: 中位 %.2f mm  p90 %.2f mm  max %.2f mm"
          % (np.median(shifts), np.percentile(shifts, 90), shifts.max()))
    print()
    print("⑤ 锚点与匝间隙一致性")
    wi = wo = wg = 0.0
    for r in rows:
        LC, KR = float(r["coil_size"]), float(r["hole_ratio"])
        ma, mb = metrics(CG.make_path(LC, KR)[:, :2]), metrics(path_v3(LC, KR))
        wi = max(wi, abs(ma[3] - mb[3])); wo = max(wo, abs(ma[2] - mb[2]))
        wg = max(wg, abs(ma[1] - mb[1]))
    print("   内孔锚点 ≤ %.3f mm   外缘锚点 ≤ %.3f mm   匝间隙 ≤ %.3f mm" % (wi, wo, wg))
    print("=" * 102)


if __name__ == "__main__":
    main()
