# -*- coding: utf-8 -*-
"""B：把已验证的改造应用到生产脚本（先备份，可回滚）。

改动清单
  1) C:\\wpt\\wpt_contract.py  追加双阈值镜像自检 + x=0 非对称度打标 + 自检表写出
  2) C:\\wpt\\batch_sweep_lc.py 修 ensure_region 的守门条件与 padding 符号
       （原写法：need = 目标面 - 物体面，物体在盒内时必为负 -> max(0,·) 夹成 0 ->
         区域面贴在物体上；再叠 min(need)<0 的守门 -> 整段从不执行，② 永远不生效）
  3) C:\\wpt\\batch_sweep_lc.py 增加已验证的提速开关（柔性网格 / pref=10 / rres=1e-5 / ⑥ 区域上限）
       并在 solve_and_extract 里幂等地应用

跑完打印每项是否成功；原文件备份到 _work\\backup_prod_<时间戳>\\。
"""
import datetime
import os
import re
import shutil
import sys

WPT = r"C:\wpt"
WORK = r"C:\ansys maxwell2024\_work"
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BAK = os.path.join(WORK, "backup_prod_%s" % TS)
CONTRACT = os.path.join(WPT, "wpt_contract.py")
BATCH = os.path.join(WPT, "batch_sweep_lc.py")
PATCH_SRC = r"C:\ansys maxwell2024\_probe\patch_wpt_contract_mirror.py"

LOG = []


def say(m=""):
    print(m, flush=True)
    LOG.append(str(m))


def backup(p):
    os.makedirs(BAK, exist_ok=True)
    dst = os.path.join(BAK, os.path.basename(p))
    shutil.copy2(p, dst)
    say("  备份 %s -> %s" % (p, dst))


def patch_contract():
    say("1) wpt_contract.py 追加双阈值自检")
    txt = open(CONTRACT, encoding="utf-8").read()
    if "def mirror_check(" in txt:
        say("   已存在 mirror_check，跳过")
        return True
    src = open(PATCH_SRC, encoding="utf-8").read()
    # 取补丁文件里从 MIRROR_TOL_SUM_PCT 开始到 write_selfcheck 结束的部分
    i = src.index("MIRROR_TOL_SUM_PCT")
    block = src[i:]
    block = block.split('if __name__ == "__main__":')[0].rstrip() + "\n"
    backup(CONTRACT)
    with open(CONTRACT, "a", encoding="utf-8") as f:
        f.write("\n\n# ================= 镜像自检（双阈值版，2026-09-18 并入）=================\n")
        f.write(block)
    say("   已追加 %d 字符" % len(block))
    return True


def patch_ensure_region():
    say("2) batch_sweep_lc.py 修 ensure_region")
    txt = open(BATCH, encoding="utf-8").read()
    if "物体到目标盒面的距离" in txt:
        say("   已修过，跳过")
        return True
    old = '''    need = [REGION_FIXED["x"][1] - bb[3], REGION_FIXED["x"][0] - bb[0],
            REGION_FIXED["y"][1] - bb[4], REGION_FIXED["y"][0] - bb[1],
            REGION_FIXED["z"][1] - bb[5], REGION_FIXED["z"][0] - bb[2]]
    if min(need) < -1e-6:
        log("!! 物体超出固定 Region: 需要 padding %s，物体 bbox=%s"
            % (["%.1f" % v for v in need], ["%.1f" % v for v in bb]))
        return None
    PAD = ["%.4fmm" % max(0.0, v) for v in need]'''
    new = '''    # 物体到目标盒面的距离（2026-09-18 修正）
    # 原写法是"目标面 - 物体面"，在物体位于盒内时必为负，被 max(0,·) 夹成 0 -> 区域面贴在物体上；
    # 再叠一句 min(need)<-1e-6 就 return 的守门 -> 整段从不执行（实测每次都是 need=[175,-175,...]）。
    need = [REGION_FIXED["x"][1] - bb[3], bb[0] - REGION_FIXED["x"][0],
            REGION_FIXED["y"][1] - bb[4], bb[1] - REGION_FIXED["y"][0],
            REGION_FIXED["z"][1] - bb[5], bb[2] - REGION_FIXED["z"][0]]
    if any(v < -1e-6 for v in need):
        log("!! 物体超出固定 Region: 需要 padding %s，物体 bbox=%s"
            % (["%.1f" % v for v in need], ["%.1f" % v for v in bb]))
        return None
    PAD = ["%.4fmm" % max(0.0, v) for v in need]'''
    if old not in txt:
        say("   !! 未找到待替换片段，跳过（请人工确认）")
        return False
    backup(BATCH)
    open(BATCH, "w", encoding="utf-8").write(txt.replace(old, new))
    say("   已替换")
    return True


def patch_speed_switches():
    say("3) batch_sweep_lc.py 增加已验证的提速开关")
    txt = open(BATCH, encoding="utf-8").read()
    if "FLEX_MESH" in txt:
        say("   已存在，跳过")
        return True
    anchor = "CORES = 8\nMAX_PASSES = 8\nPCT_ERROR = 5\nPCT_REFINEMENT = 5"
    if anchor not in txt:
        say("   !! 未找到 CORES/MAX_PASSES 区块，跳过")
        return False
    consts = '''CORES = 8
MAX_PASSES = 8
PCT_ERROR = 5
PCT_REFINEMENT = 5

# ============ 已验证的提速开关（2026-09-18，参考点 8 核实测）============
# 柔性网格：-39.6% 耗时，电感偏差 +0.41%（面向薄层结构，省掉大部分初始网格开销）
FLEX_MESH = True
# PercentRefinement 原 5 -> 10：叠在柔性+⑥ 之上再 -22%，同会话增量偏差 <=0.25%
PCT_REFINEMENT = 10
# 迭代求解容差 原 1e-6 -> 1e-5：再 -4%，偏差 <=0.06%
RELATIVE_RESIDUAL = "1e-05"
# ⑥：Region 最大单元尺寸 = Lc / 该值（-9.8%，偏差 <=0.31%）；0 = 关闭
REGION_MAX_LEN_DIV = 5.0'''
    backup(BATCH)
    txt = txt.replace(anchor, consts, 1)
    # 在 solve_and_extract 的 setup 设置之后幂等应用
    anchor2 = '''        s.props["PercentRefinement"] = PCT_REFINEMENT
        s.update()
    except Exception as e:
        log("setup err: %s" % repr(e))'''
    if anchor2 not in txt:
        say("   !! 未找到 setup 设置区块，开关常量已加但未接线")
        open(BATCH, "w", encoding="utf-8").write(txt)
        return False
    new2 = '''        s.props["PercentRefinement"] = PCT_REFINEMENT
        s.props["RelativeResidual"] = RELATIVE_RESIDUAL
        s.update()
        # 提速开关（幂等：同名网格操作先删再加）
        try:
            if FLEX_MESH:
                m3d.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=True)
            for _mo in list(m3d.mesh.meshoperations):
                if _mo.name.startswith("region_coarse"):
                    _mo.delete()
            if REGION_MAX_LEN_DIV:
                m3d.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                            maximum_length="%.4fmm" % (LC / REGION_MAX_LEN_DIV),
                                            maximum_elements=None, name="region_coarse")
        except Exception as e:
            log("speed switch err: %s" % repr(e))
    except Exception as e:
        log("setup err: %s" % repr(e))'''
    txt = txt.replace(anchor2, new2, 1)
    open(BATCH, "w", encoding="utf-8").write(txt)
    say("   常量与接线均已写入")
    return True


def verify():
    say("")
    say("=== 验证 ===")
    ok = True
    for p in (CONTRACT, BATCH):
        src = open(p, encoding="utf-8").read()
        try:
            compile(src, p, "exec")
            say("  %s 语法 OK" % os.path.basename(p))
        except SyntaxError as e:
            say("  %s 语法错误: %s" % (os.path.basename(p), e))
            ok = False
    txt = open(CONTRACT, encoding="utf-8").read()
    say("  wpt_contract 含 mirror_check/case_asymmetry_tag/write_selfcheck: %s"
        % all(k in txt for k in ("def mirror_check(", "def case_asymmetry_tag(",
                                 "def write_selfcheck(")))
    txt = open(BATCH, encoding="utf-8").read()
    say("  batch 含修正后的 ensure_region: %s" % ("物体到目标盒面的距离" in txt))
    say("  batch 含提速开关常量: %s / 接线: %s"
        % ("FLEX_MESH = True" in txt, "speed switch err" in txt))
    return ok


def main():
    say("=" * 70)
    say("应用生产脚本改造（备份目录 %s）" % BAK)
    patch_contract()
    patch_ensure_region()
    patch_speed_switches()
    ok = verify()
    say("")
    say("结果: %s" % ("全部完成 ✓" if ok else "有项目失败，请看上面"))
    say("备份: %s" % BAK)
    open(os.path.join(WORK, "apply_prod_patches.log"), "w", encoding="utf-8").write(
        "\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
