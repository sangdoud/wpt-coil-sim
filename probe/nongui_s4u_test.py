# -*- coding: utf-8 -*-
r"""S4U（计划任务/会话 0）环境下 AEDT 能否启动 —— GUI vs 无界面 对照实验。

背景（2026-10-13）：b2 批次在 01:35~03:27 停止出点、~06:36 进程消失；
guard（计划任务，S4U 运行）从 07:01 起连续 4 次重启**全部失败**，
报 `Failed to start new AEDT gRPC session on port ...`。
而同一时刻在**交互式会话**里手工启动 AEDT 只需 12.2 秒 —— 强烈指向
"计划任务所在的会话 0 没有交互桌面，GUI 模式的 AEDT 起不来"。

本脚本由计划任务以 S4U 身份运行，把结果写进 nongui_s4u_result.txt。
用法： python nongui_s4u_test.py <0|1>      # 0=GUI(non_graphical=False) 1=无界面(True)
"""
import os
import sys
import time
import traceback

OUT = r"C:\ansys maxwell2024\_probe\nongui_s4u_result.txt"


def w(s):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(s + "\n")


def main():
    mode = (sys.argv[1] if len(sys.argv) > 1 else "1") == "1"
    w("=== %s 开始：non_graphical=%s  pid=%d  会话=%s ==="
      % (time.strftime("%Y-%m-%d %H:%M:%S"), mode, os.getpid(),
         os.environ.get("SESSIONNAME", "?")))
    t0 = time.time()
    d = None
    try:
        from ansys.aedt.core import Desktop
        d = Desktop(version="2024.1", new_desktop=True, non_graphical=mode,
                    close_on_exit=False)
        w("  成功：aedt_pid=%s  用时 %.1f s"
          % (getattr(d, "aedt_process_id", "?"), time.time() - t0))
    except Exception as e:
        w("  失败（%.1f s）：%r" % (time.time() - t0, e))
        w("  " + traceback.format_exc().replace("\n", "\n  ")[-500:])
    finally:
        if d is not None:
            try:
                d.release_desktop()
                w("  会话已释放")
            except Exception as e:
                w("  释放异常：%r" % (e,))
    w("=== 结束 ===")


if __name__ == "__main__":
    main()
