# -*- coding: utf-8 -*-
"""对抓取的 AEDT 截图做程序化内容分析（无法人眼查看时的替代验证）。

输出每张图：
  - 尺寸、全图平均亮度/方差
  - 3D 视口区域（去掉菜单/工具栏/状态栏）的主色分布
  - 是否检测到"铜色 / 铁氧体灰 / 背景白"三类典型像素
  - 结论：是否含模型内容
"""
import os
import sys
import glob
import collections

from PIL import Image

# AEDT 3D Modeler 典型配色（近似）
BG = [(255, 255, 255), (240, 240, 240), (245, 245, 245), (250, 250, 250)]


def bucket(rgb, step=32):
    return tuple((c // step) * step for c in rgb)


def is_grayish(p, tol=18):
    r, g, b = p
    return abs(r - g) <= tol and abs(g - b) <= tol and abs(r - b) <= tol


def classify(p):
    r, g, b = p
    mx, mn = max(p), min(p)
    sat = mx - mn
    if sat < 20:
        if mx > 225:
            return "bg_light"
        if mx < 60:
            return "dark"
        return "gray"
    # 铜/橙色：R 明显最大，G 居中，B 最小
    if r > g > b and (r - b) > 40:
        if g > 0.6 * r:
            return "warm_light"      # 浅橙（铜带高光面）
        return "copper"              # 橙铜色
    if b >= r and b >= g:
        return "blue"
    if g >= r and g >= b:
        return "green"
    return "other"


def analyze(path, viewport=(0.06, 0.13, 0.99, 0.94)):
    img = Image.open(path).convert("RGB")
    W, H = img.size
    l, t, r, b = viewport
    box = (int(W * l), int(H * t), int(W * r), int(H * b))
    vp = img.crop(box)
    # 采样降规模
    vp_small = vp.resize((max(1, vp.width // 2), max(1, vp.height // 2)))
    px = list(vp_small.get_flattened_data()) if hasattr(vp_small, "get_flattened_data") else list(vp_small.getdata())

    cnt = collections.Counter(classify(p) for p in px)
    tot = len(px)
    top = collections.Counter(bucket(p) for p in px).most_common(6)

    n_bg = cnt["bg_light"]
    n_model = cnt["copper"] + cnt["warm_light"] + cnt["gray"] + cnt["other"] + cnt["green"] + cnt["blue"]
    frac_model = n_model / tot
    frac_bg = n_bg / tot

    # 全图统计
    all_small = img.resize((160, 90))
    ap = list(all_small.getdata())
    avg = sum(sum(p) / 3 for p in ap) / len(ap)

    print("=" * 78)
    print(os.path.basename(path))
    print("  尺寸 %dx%d   全图平均亮度 %.1f" % (W, H, avg))
    print("  视口区域 = 全图 x[%.0f%%~%.0f%%] y[%.0f%%~%.0f%%]  (%dx%d)"
          % (l * 100, r * 100, t * 100, b * 100, vp.width, vp.height))
    print("  类别占比： ", end="")
    for k, v in cnt.most_common():
        print("%s=%.1f%% " % (k, 100.0 * v / tot), end="")
    print()
    print("  主色 TOP6：", ", ".join("rgb%s %.1f%%" % (c, 100.0 * n / tot) for c, n in top))
    verdict = "含模型内容" if frac_model > 0.10 else ("几乎纯背景" if frac_bg > 0.85 else "内容稀少")
    print("  >>> 视口内非背景占比 %.1f%%  ->  %s" % (100 * frac_model, verdict))
    return dict(path=path, size=(W, H), frac_model=frac_model, frac_bg=frac_bg,
                copper=cnt["copper"] / tot, warm=cnt["warm_light"] / tot,
                gray=cnt["gray"] / tot, verdict=verdict)


def main():
    d = sys.argv[1] if len(sys.argv) > 1 else r"C:\ansys maxwell2024\_work\case_figures"
    pat = sys.argv[2] if len(sys.argv) > 2 else "*.png"
    files = sorted(glob.glob(os.path.join(d, pat)))
    if not files:
        print("没有匹配的图：", os.path.join(d, pat))
        return 1
    for f in files:
        analyze(f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
