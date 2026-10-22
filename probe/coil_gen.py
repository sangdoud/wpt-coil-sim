# -*- coding: utf-8 -*-
"""线圈参数化生成器：线宽 LC（120~220）x 内孔比 KR（0.2~0.5）。

做法：以现有 768 点路径为模板做**径向重映射**
     s(p)  = 切比雪夫半径 = max(|dx|,|dy|)   （对平边精确等于环半径）
     s'(p) = h_in' + (s - h_in_ref) * (h_out' - h_in')/(h_out_ref - h_in_ref)
     p'    = 中心 + (p - 中心) * s'/s
性质：
  * 在参考参数下是恒等映射 -> 逐点精确复现现有模型（可直接和已有数据对话）
  * 纯缩放时无失真；改内孔比时，一个圆角内各点缩放因子差 ~2~3%，形变 < 0.1mm
  * 匝间隙自动 = (h_out'-h_in')/12 匝，随区域自适应
锚点定义（本次采用）：
     LC = 2 x 最外匝中心线半径（"中心线外跨"）
     KR = 最内匝中心线半径 / 最外匝中心线半径
"""
import json
import math

import numpy as np

PATH_JSON = r"C:\ansys maxwell2024\_work\coil_paths.json"
OUT_JSON = r"C:\ansys maxwell2024\_work\coil_gen_check.json"

# ---- 参考（由测算得到）----
CENTER = (0.0, 0.0)


def load_ref():
    pts = np.array(json.load(open(PATH_JSON, encoding="utf-8"))["Rx"], dtype=float)
    return pts


REF = load_ref()
CX, CY = CENTER


def cheb(P):
    return np.maximum(np.abs(P[:, 0] - CX), np.abs(P[:, 1] - CY))


REF_S = cheb(REF)
H_OUT_REF = float(REF_S.max())        # 最外匝中心线半径（含末端引出段）
H_IN_REF = float(REF_S[0])            # 最内匝中心线半径（起点处）
LC_REF = 2.0 * H_OUT_REF
KR_REF = H_IN_REF / H_OUT_REF
print("参考: 中心(%.3f,%.3f)  h_in=%.4f h_out=%.4f  ->  LC_REF=%.4f  KR_REF=%.4f"
      % (CX, CY, H_IN_REF, H_OUT_REF, LC_REF, KR_REF))
print("      对应物理尺寸(2mm 线宽): 外边缘 %.3f  内孔(孔壁) %.3f"
      % (LC_REF + 2.0, 2 * H_IN_REF - 2.0))


def make_path(LC, KR, width=2.0):
    """返回 (N,3) 的新路径（局部坐标，中心在 CENTER，z 沿用模板的 z 平面）。"""
    h_out = LC / 2.0
    h_in = KR * LC / 2.0
    if h_in <= 0:
        raise ValueError("内孔半径必须 > 0")
    k = (h_out - h_in) / (H_OUT_REF - H_IN_REF)
    s = REF_S
    s2 = h_in + (s - H_IN_REF) * k
    f = s2 / s
    out = REF.copy()
    out[:, 0] = CX + (REF[:, 0] - CX) * f
    out[:, 1] = CY + (REF[:, 1] - CY) * f
    return out


def dims(P):
    s = cheb(P)
    return dict(h_in=float(s[0]), h_out=float(s.max()),
                lc=2 * float(s.max()), kr=float(s[0] / s.max()))


def min_turn_gap(P, width):
    """相邻匝最小净间隙的估计：同一方位上第 i 点与第 i+64 点（相隔一匝）的半径差。"""
    s = cheb(P)
    d = s[64:] - s[:-64]
    return float(d.min() - width), float(d.mean() - width)


def check_self_intersection(P):
    """粗查自交：相邻匝是否有重叠（按点对距离）。"""
    A = P[:, :2]
    B = np.roll(A, -64, axis=0)
    d = np.hypot(A[:, 0] - B[:, 0], A[:, 1] - B[:, 1])
    return float(d.min())


def _self_test():
    print("\n=== 参考点自检（LC=%.4f, KR=%.4f 必须逐点恒等）===" % (LC_REF, KR_REF))
    P0 = make_path(LC_REF, KR_REF)
    err = np.abs(P0 - REF).max()
    print("  最大逐点偏差 = %.3e mm  %s" % (err, "OK" if err < 1e-9 else "!! 不是恒等"))

    print("\n=== 网格点检查（LC=120~220 步长10，KR=0.2~0.5 步长0.1）===")
    print("  %-6s %-5s %8s %8s %9s %9s %9s %9s" %
          ("LC", "KR", "h_in", "h_out", "外边缘", "内孔", "最小间隙", "相邻匝距"))
    rows = []
    for LC in range(120, 221, 10):
        for KR in [round(0.2 + 0.1 * i, 1) for i in range(4)]:
            P = make_path(LC, KR)
            d = dims(P)
            gap_min, gap_avg = min_turn_gap(P, 2.0)
            dmin = check_self_intersection(P)
            ok = (gap_min > 0.2) and (dmin > 2.0)
            print("  %-6d %-5.1f %8.3f %8.3f %9.3f %9.3f %9.3f %9.3f %s" %
                  (LC, KR, d["h_in"], d["h_out"], LC + 2.0, KR * LC - 2.0,
                   gap_min, dmin, "" if ok else "  <== 可疑"))
            rows.append(dict(LC=LC, KR=KR, h_in=d["h_in"], h_out=d["h_out"],
                             gap_min=round(gap_min, 4), neighbour_min=round(dmin, 4), ok=bool(ok)))
    json.dump(dict(center=CENTER, h_in_ref=H_IN_REF, h_out_ref=H_OUT_REF,
                   LC_REF=LC_REF, KR_REF=KR_REF, rows=rows),
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n结果 -> %s" % OUT_JSON)


if __name__ == "__main__":
    _self_test()
