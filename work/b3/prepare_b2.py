# -*- coding: utf-8 -*-
r"""b2 启动前一条命令：参数表校验 -> 生成 plan/audit -> 启动前自检 -> 打印启动命令。

**有意不自动启动批次、也不自动启用计划任务** —— 启动是不可逆的重动作
（会占满 8 个 AEDT 席位、持续 28 天），必须由人确认最后一步。

用法：
  python prepare_b2.py --src "D:\path\参数表.csv"
  python prepare_b2.py --src ... --rows 1920 --batch b2 --boxx 420

退出码：0 = 三步全通过（可以按打印的命令启动）；1 = 某步 FAIL（不要启动）；2 = 自身异常。
"""
import argparse
import os
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

PY = r"C:\anaconda\python.exe"
PROBE = r"C:\ansys maxwell2024\_probe"
HERE = os.path.dirname(os.path.abspath(__file__))


def run(title, cmd, env=None):
    print("\n" + "=" * 84)
    print(title)
    print("=" * 84, flush=True)
    p = subprocess.run(cmd, text=True, encoding="utf-8", errors="replace", env=env)
    print("---- 退出码 %d" % p.returncode, flush=True)
    return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="用户提供的参数表 CSV")
    ap.add_argument("--root", default=HERE)
    ap.add_argument("--batch", default="b2")
    ap.add_argument("--rows", type=int, default=1920)
    ap.add_argument("--boxx", type=int, default=420)
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--waive-box-margin", default=None, metavar="REASON",
                    help="显式豁免「+40mm 留边」不足（物体仍需在盒内）。必须写明实测证据；"
                         "会写进 plan_meta 的 box_margin_waiver，preflight 会自动继承。")
    a = ap.parse_args()
    root = os.path.abspath(a.root)

    if not os.path.exists(a.src):
        print("找不到参数表: %s" % a.src)
        return 1

    # 口径相关环境变量显式写死：PATH_MODE 一旦被环境里的 legacy 顶掉，
    # 整批几何会静默退回未修正的拐角重映射（第一轮实测 214/256 工况受影响）。
    env = dict(os.environ)
    env["WPT_PATH_MODE"] = "ring"
    env["PYTHONIOENCODING"] = "utf-8"

    _waive = (["--waive-box-margin", a.waive_box_margin] if a.waive_box_margin else [])

    rc = run("[1/3] 参数表只读校验（列名/数值/唯一性/行数/7 维范围/空气域包含性/闸门/工期）",
             [PY, os.path.join(PROBE, "validate_b2_plan.py"),
              "--src", a.src, "--rows", str(a.rows), "--batch", a.batch,
              "--boxx", str(a.boxx), "--expect-path-mode", "ring"] + _waive, env=env)
    if rc != 0:
        print("\n!! 参数表校验未通过 —— 先修表，不要启动批次。")
        return 1

    rc = run("[2/3] 生成 plan / audit / region_check / plan_meta（验收点前置 + 按耗时降序）",
             [PY, os.path.join(PROBE, "build_b2_plan.py"),
              "--src", a.src, "--outdir", root, "--batch", a.batch,
              "--rows", str(a.rows), "--boxx", str(a.boxx)] + _waive, env=env)
    if rc != 0:
        print("\n!! 生成计划失败（validate 内的校验未过则不会产出任何文件）。")
        return 1

    rc = run("[3/3] 启动前自检（环境/代码口径/数据链路/计划任务，22 项）",
             [PY, os.path.join(root, "preflight.py"),
              "--root", root, "--batch", a.batch, "--n", str(a.n)], env=env)
    if rc != 0:
        print("\n!! 自检存在 FAIL —— 逐条消掉再启动（清单见 preflight 输出与"
              "《第二轮启动前检查清单与经验总结_20261012.md》§2）。")
        return 1

    print("\n" + "=" * 84)
    print("三步全通过。接下来**人工**执行（不可逆，故不自动跑）：")
    print("=" * 84)
    print("""
# 0) 确认没有残留 AEDT 进程（有则先杀，且必须等 >=4 分钟再启动）
Get-Process ansysedt,3dnms,G3dMesher,ansyscl -ErrorAction SilentlyContinue

# 1) 【强烈建议】先单实例冒烟 1 个工况 1 个点，确认会话/几何/落盘链路（~15 min）
#    $env:WPT_BATCH="b2smoke"; $env:WPT_ROOT="<临时目录>"; $env:WPT_RUN="0"
#    $env:WPT_PLAN="<临时目录>\\b2smoke_plan_shard0.csv"; $env:WPT_CASES="1"; $env:WPT_XS="0"
#    & C:\\anaconda\\python.exe "%s\\contract_worker.py"
#    ⚠️ 冒烟后必须删掉冒烟写入的 raw 行与 .aedtresults，否则会被当成"已完成"而跳过

# 2) 正式启动：8 实例（不要把 --merge 加在这里，28 天批次结束后再手动合并）
& C:\\anaconda\\python.exe "%s\\contract_launch.py" %d --batch %s --root "%s" --boxx %d --boxy 161

# 3) 启用三个计划任务（否则失速/崩溃无人自愈）
Enable-ScheduledTask -TaskName %s_batch_guard, %s_batch_deliver, %s_batch_clean

# 4) 启动后 10 分钟内复查一次
& C:\\anaconda\\python.exe "%s\\b2_status.py" --root "%s" --batch %s
& C:\\anaconda\\python.exe "%s\\preflight.py" --root "%s" --batch %s
""" % (root, root, a.n, a.batch, root, a.boxx,
       a.batch, a.batch, a.batch, root, root, a.batch, root, root, a.batch))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                      # noqa: BLE001 —— 自身异常必须显式暴露
        print("\n[FAIL] prepare_b2 自身异常：%r" % (exc,), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)
