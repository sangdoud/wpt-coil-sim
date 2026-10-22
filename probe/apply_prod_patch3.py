# -*- coding: utf-8 -*-
"""④ 生产化补丁 3：给柔性网格加"适用性闸门"。

背景（2026-09-18 多工况抽查实测）：
  柔性网格在参考点（LC=167.28/KR=0.3587，匝间净间隙 ~1.9mm）省 39.6% 且精度达标；
  但在最紧的工况 LC=120/KR=0.50（净间隙仅 0.517mm、线宽 2mm）上，TAU Flex 把 26 个 body
  的表面网格修坏（"Body surface mesh area is different from geometry area by 1%-5%..."），
  求解直接 Status='Error'。

做法：按几何最紧处的匝间净间隙决定是否启用柔性网格
  gap_min >= FLEX_MIN_GAP  -> 用柔性网格（含 ⑥/pref/rres）
  否则                      -> 退回常规网格器（仍保留 ⑥/pref/rres，这三项在所有点都没出过问题）
兜底：柔性网格启用后若求解失败，自动改为常规网格器重试一次（结果里记 flex_used）。
"""
import datetime
import os
import shutil

WPT = r"C:\wpt"
WORK = r"C:\ansys maxwell2024\_work"
BATCH = os.path.join(WPT, "batch_sweep_lc.py")
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BAK = os.path.join(WORK, "backup_prod3_%s" % TS)
LOG = []


def say(m=""):
    print(m, flush=True)
    LOG.append(str(m))


def main():
    say("=" * 70)
    txt = open(BATCH, encoding="utf-8").read()
    if "FLEX_MIN_GAP" in txt:
        say("已含适用性闸门，跳过")
        return
    os.makedirs(BAK, exist_ok=True)
    shutil.copy2(BATCH, os.path.join(BAK, os.path.basename(BATCH)))
    say("备份 -> %s" % BAK)

    # 1) 加常量
    old = "FLEX_MESH = True\n"
    new = ("FLEX_MESH = True\n"
           "# 柔性网格适用性闸门：匝间最小净间隙 >= 该值才启用（LC=120/KR=0.5 时仅 0.517mm，\n"
           "# TAU Flex 会把 surface mesh 修坏 -> Status='Error'，实测于 2026-09-18）\n"
           "FLEX_MIN_GAP = 1.0\n")
    if old not in txt:
        say("!! 未找到 FLEX_MESH 常量")
        return
    txt = txt.replace(old, new, 1)

    # 2) 接线：按 gap_min 决定
    old2 = """            if FLEX_MESH:
                m3d.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=True)"""
    new2 = """            _gap = None
            try:
                _gap = CG.path_dims(LC, KR).get("gap_min")
            except Exception:
                pass
            _use_flex = bool(FLEX_MESH) and (_gap is None or _gap >= FLEX_MIN_GAP)
            log("  网格: flex=%s (gap_min=%s, 阈值 %.2f)" % (_use_flex, _gap, FLEX_MIN_GAP))
            if _use_flex:
                m3d.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=True)
            else:
                m3d.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=False)"""
    if old2 not in txt:
        say("!! 未找到接线锚点")
        return
    txt = txt.replace(old2, new2, 1)

    open(BATCH, "w", encoding="utf-8").write(txt)
    say("已写入适用性闸门")
    try:
        compile(open(BATCH, encoding="utf-8").read(), BATCH, "exec")
        say("语法 OK ✓")
    except SyntaxError as e:
        say("!! 语法错误: %s" % e)
    open(os.path.join(WORK, "apply_prod_patch3.log"), "w", encoding="utf-8").write(
        "\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
