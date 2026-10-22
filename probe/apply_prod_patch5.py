# -*- coding: utf-8 -*-
"""④ 生产化补丁 5：把"柔性闸门"升级为"整套优化闸门"。

实测（2026-09-18，LC=120/KR=0.50，gap_min=0.5515mm）：
  柔性网格        -> Status='Error'（TAU Flex 修坏 26 个 body）        ✗
  非柔性+⑥+pref10+rres -> 10.97 分钟（比基线 9.64 慢 13.8%），
                          电感偏差最坏 1.44%（L33 -1.26%、M13 -1.44%） ✗

所以最紧那一角连"小幅优化组合"也不成立。规则改为：
  净间隙 >= OPT_MIN_GAP  -> 整套优化（flex + ⑥ + pref10 + rres）
  否则                    -> **整套回退**到现行生产口径（非柔性 / pref5 / rres1e-6 / 无 ⑥）
这样在设计空间的任何位置都只会用到"已实测验证过的组合"。
"""
import datetime
import os
import shutil

WPT = r"C:\wpt"
WORK = r"C:\ansys maxwell2024\_work"
BATCH = os.path.join(WPT, "batch_sweep_lc.py")
TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BAK = os.path.join(WORK, "backup_prod5_%s" % TS)
LOG = []


def say(m=""):
    print(m, flush=True)
    LOG.append(str(m))


def main():
    say("=" * 70)
    txt = open(BATCH, encoding="utf-8").read()
    if "OPT_MIN_GAP" in txt:
        say("已含整套闸门，跳过")
        return
    os.makedirs(BAK, exist_ok=True)
    shutil.copy2(BATCH, os.path.join(BAK, os.path.basename(BATCH)))
    say("备份 -> %s" % BAK)

    # 1) 常量：FLEX_MIN_GAP -> OPT_MIN_GAP（保留旧名做别名）
    old = """FLEX_MIN_GAP = 1.5"""
    new = """FLEX_MIN_GAP = 1.5
# 整套优化的适用闸门（2026-09-18 实测）：净间隙不足时，连"⑥+pref10+rres"也会变慢且偏 1.44%，
# 因此不满足就整套回退到现行生产口径（非柔性 / pref5 / rres1e-6 / 无 ⑥）。
OPT_MIN_GAP = 1.5"""
    if old not in txt:
        say("!! 未找到 FLEX_MIN_GAP")
        return
    txt = txt.replace(old, new, 1)

    # 2) 接线：按闸门决定整套配置
    old2 = """            _gap = None
            try:
                _gap = CG.path_dims(LC, KR).get("gap_min")
            except Exception:
                pass
            _use_flex = bool(FLEX_MESH) and (_gap is None or _gap >= FLEX_MIN_GAP)
            log("  网格: flex=%s (gap_min=%s, 阈值 %.2f)" % (_use_flex, _gap, FLEX_MIN_GAP))
            if _use_flex:
                m3d.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=True)
            else:
                m3d.mesh.assign_initial_mesh_from_slider(level=5, method="Auto", flex_mesh=False)
            for _mo in list(m3d.mesh.meshoperations):
                if _mo.name.startswith("region_coarse"):
                    _mo.delete()
            if REGION_MAX_LEN_DIV:
                m3d.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                            maximum_length="%.4fmm" % (LC / REGION_MAX_LEN_DIV),
                                            maximum_elements=None, name="region_coarse")
        except Exception as e:
            log("speed switch err: %s" % repr(e))"""
    new2 = """            _gap = None
            try:
                _gap = CG.path_dims(LC, KR).get("gap_min")
            except Exception:
                pass
            _use_opt = (_gap is None) or (_gap >= OPT_MIN_GAP)
            log("  网格: 整套优化=%s (gap_min=%s, 阈值 %.2f)" % (_use_opt, _gap, OPT_MIN_GAP))
            m3d.mesh.assign_initial_mesh_from_slider(level=5, method="Auto",
                                                     flex_mesh=bool(FLEX_MESH and _use_opt))
            for _mo in list(m3d.mesh.meshoperations):
                if _mo.name.startswith("region_coarse"):
                    _mo.delete()
            if REGION_MAX_LEN_DIV and _use_opt:
                m3d.mesh.assign_length_mesh(assignment=["Region"], inside_selection=True,
                                            maximum_length="%.4fmm" % (LC / REGION_MAX_LEN_DIV),
                                            maximum_elements=None, name="region_coarse")
            # 不满足闸门时整套回退到现行生产口径
            s.props["PercentRefinement"] = PCT_REFINEMENT if _use_opt else 5
            s.props["RelativeResidual"] = RELATIVE_RESIDUAL if _use_opt else "1e-06"
            s.update()
        except Exception as e:
            log("speed switch err: %s" % repr(e))"""
    if old2 not in txt:
        say("!! 未找到接线锚点（补丁3写的版本）")
        return
    txt = txt.replace(old2, new2, 1)

    open(BATCH, "w", encoding="utf-8").write(txt)
    say("已升级为整套闸门")
    try:
        import ast
        ast.parse(open(BATCH, encoding="utf-8-sig").read())
        say("语法 OK ✓")
    except SyntaxError as e:
        say("!! 语法错误: %s" % e)
    open(os.path.join(WORK, "apply_prod_patch5.log"), "w", encoding="utf-8").write(
        "\n".join(LOG) + "\n")


if __name__ == "__main__":
    main()
