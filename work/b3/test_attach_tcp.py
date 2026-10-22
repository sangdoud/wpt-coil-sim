# -*- coding: utf-8 -*-
"""组合验证：手工用**裸端口**启动 AEDT（沙箱下可监听 TCP），再让 pyaedt 以 INSECURE(TCP) 客户端附着。

背景：
  - pyaedt 默认 WNUA 模式：服务端参数 = 裸端口（AEDT 接受，TCP 监听 OK），但**客户端走命名管道**
    -> 沙箱禁止命名管道 -> "Failed to start on gRPC port"。
  - pyaedt INSECURE 模式：客户端走 TCP（沙箱允许），但服务端参数是 `host:port:InsecureMode`，
    AEDT 2024 R1 静默忽略该形式 -> 端口从不开。
  两头各对一半。本脚本把两半拼起来：自己起服务端（裸端口），客户端用 TCP 附着。
"""
import os
import socket
import subprocess
import sys
import time

sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                                        # noqa: E402

from ansys.aedt.core.generic.settings import settings    # noqa: E402
settings.grpc_secure_mode = False                        # 客户端 -> TCP
settings.grpc_local = True

from ansys.aedt.core import Desktop, Maxwell3d           # noqa: E402
aedt_shim.patch_pyaedt_proc()

EXE = r"C:\Program Files\ANSYS 2024r1 Inc\ansys em\v241\Win64\ansysedt.exe"
PROJ = r"C:\ansys maxwell2024\_work\b1smoke\Projecttonight_b1smoke_run0.aedt"
PORT = 59931


def port_open(port, timeout=2.0):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def main():
    p = subprocess.Popen([EXE, "-grpcsrv", str(PORT)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("AEDT 起 pid=%d，等待 TCP 监听 %d ..." % (p.pid, PORT), flush=True)
    t0 = time.time()
    ok = False
    for _ in range(20):
        time.sleep(3)
        if port_open(PORT):
            ok = True
            break
    print("端口 %s（%.1f s）" % ("OPEN" if ok else "仍然 closed", time.time() - t0), flush=True)
    if not ok:
        raise SystemExit("服务端未监听，组合方案不成立")
    try:
        t1 = time.time()
        d = Desktop(version="2024.1", new_desktop=False, port=PORT,
                    aedt_process_id=p.pid, non_graphical=False, close_on_exit=False)
        print("OK Desktop 附着成功（%.1f s）" % (time.time() - t1), flush=True)
        t2 = time.time()
        m = Maxwell3d(project=PROJ, design="WPT_G", remove_lock=True,
                      aedt_process_id=p.pid, port=PORT)
        print("OK 工程打开：design=%s solution=%s（%.1f s）"
              % (m.design_name, m.solution_type, time.time() - t2), flush=True)
        print("   对象数=%d setups=%s" % (len(m.modeler.object_names),
                                          [s.name for s in m.setups]), flush=True)
        print("RESULT: 组合方案可用 ✓（沙箱内可跑，无需提权）", flush=True)
    finally:
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Stop-Process -Id %d -Force -ErrorAction SilentlyContinue" % int(p.pid)],
                           capture_output=True, text=True)
        except Exception as e:
            print("kill err %r" % e)


if __name__ == "__main__":
    main()
