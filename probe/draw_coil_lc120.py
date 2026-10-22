# -*- coding: utf-8 -*-
"""画 LC=120 / KR=0.5 的线圈：中心线路径 + 2mm 线宽轮廓 + 局部放大看匝间隙。"""
import os
import sys

os.environ.setdefault("MPLCONFIGDIR", r"C:\ansys maxwell2024\_work\mplcache")
os.makedirs(os.environ["MPLCONFIGDIR"], exist_ok=True)
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# 中文字体
from matplotlib import font_manager
for _f in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
    try:
        font_manager.fontManager.addfont(_f)
    except Exception:
        pass
plt.rcParams["font.family"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

sys.path.insert(0, r"C:\wpt")          # 用生产目录里的正式模块
from coil_gen import HEIGHT, WIDTH, make_path, path_dims  # noqa

LC, KR = 120.0, 0.5
OUT = r"C:\ansys maxwell2024\_work\coil_LC120_KR05.png"
P = make_path(LC, KR)
d = path_dims(LC, KR)
xy = P[:, :2]


def band(P, half):
    """把折线按法向 ±half 展开成两条边界线。"""
    p = P[:, :2]
    t = np.gradient(p, axis=0)
    n = np.stack([-t[:, 1], t[:, 0]], axis=1)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    n = n / ln
    return p + n * half, p - n * half


out_l, out_r = band(P, WIDTH / 2.0)
s = np.maximum(np.abs(xy[:, 0]), np.abs(xy[:, 1]))
i_min = int(np.argmin(s[64:] - s[:-64])) + 64        # 匝间隙最紧的位置
px, py = xy[i_min]
print("最紧处 i=%d 点(%.3f, %.3f)  最小净间隙 %.4f mm" % (i_min, px, py, d["gap_min"]))

fig = plt.figure(figsize=(15, 7.4))
gs = fig.add_gridspec(1, 2, width_ratios=[1.06, 1])

# ---------- 左：整只线圈 ----------
ax = fig.add_subplot(gs[0, 0])
ax.plot(xy[:, 0], xy[:, 1], lw=0.7, color="#888", label="中心线路径（768 点）")
ax.plot(out_l[:, 0], out_l[:, 1], lw=1.0, color="#c0392b")
ax.plot(out_r[:, 0], out_r[:, 1], lw=1.0, color="#c0392b", label="铜带外缘（线宽 2mm）")
ax.plot([xy[0, 0]], [xy[0, 1]], "o", ms=7, color="#27ae60")
ax.plot([xy[-1, 0]], [xy[-1, 1]], "s", ms=7, color="#2980b9")
ax.annotate("内端（引线接这里）", xy[0], textcoords="offset points", xytext=(14, -22),
            fontsize=9, color="#27ae60")
ax.annotate("外端（引线接这里）", xy[-1], textcoords="offset points", xytext=(-120, 16),
            fontsize=9, color="#2980b9")
h = LC / 2.0
ax.set_title("LC=120, KR=0.5  ·  外边缘 %.1fmm  ·  内孔 %.1fmm  ·  12 匝  ·  节距 %.2fmm"
             % (LC + WIDTH, KR * LC - WIDTH, (d["h_out"] - d["h_in"]) / 12), fontsize=11)
ax.set_aspect("equal")
ax.grid(alpha=0.25)
ax.set_xlabel("x (mm)")
ax.set_ylabel("y (mm)")
ax.legend(loc="upper right", fontsize=9)

# ---------- 右：局部放大 ----------
ax2 = fig.add_subplot(gs[0, 1])
m = 44
for arr, c, lw in ((out_l, "#c0392b", 1.6), (out_r, "#c0392b", 1.6)):
    ax2.plot(arr[:, 0], arr[:, 1], lw=lw, color=c)
ax2.plot(xy[:, 0], xy[:, 1], lw=0.7, ls="--", color="#888")
# 只画最紧处附近的匝
keep = (np.abs(xy[:, 0] - px) < m) & (np.abs(xy[:, 1] - py) < m)
ax2.plot(xy[keep, 0], xy[keep, 1], lw=0.7, ls="--", color="#555")
ax2.plot([px], [py], "o", ms=6, color="#e67e22")
ax2.set_xlim(px - m, px + m)
ax2.set_ylim(py - m, py + m)
ax2.set_aspect("equal")
ax2.grid(alpha=0.25)
ax2.set_title("最紧处放大：相邻两匝铜带间隙 %.3fmm" % d["gap_min"], fontsize=11)
ax2.set_xlabel("x (mm)")

fig.suptitle("LC=120mm / 内孔比 0.5 —— 全网格里最紧的一格", fontsize=13, y=0.985)
fig.tight_layout(rect=[0, 0, 1, 0.955])
fig.savefig(OUT, dpi=140)
print("已存图 %s" % OUT)
print("尺寸摘要: %s" % d)
