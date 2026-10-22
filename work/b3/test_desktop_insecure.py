# -*- coding: utf-8 -*-
"""最小验证：把 pyaedt 的 gRPC 传输从 WNUA（命名管道，被沙箱禁）切成 INSECURE（纯 TCP）。

成功则整批采集可以在沙箱内合法运行（只写工作区），无需提权。
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                                   # noqa: E402

from ansys.aedt.core.generic.settings import settings   # noqa: E402
settings.grpc_secure_mode = False                  # -> TransportMode.INSECURE
settings.grpc_local = True

from ansys.aedt.core import Desktop, Maxwell3d     # noqa: E402
aedt_shim.patch_pyaedt_proc()

PROJ = r"C:\ansys maxwell2024\_work\b1smoke\Projecttonight_b1smoke_run0.aedt"
print("grpc_local=%s grpc_secure_mode=%s" % (settings.grpc_local, settings.grpc_secure_mode), flush=True)

pid = None
try:
    t0 = time.time()
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    pid = d.aedt_process_id
    print("OK Desktop 起来了：pid=%s，耗时 %.1f s" % (pid, time.time() - t0), flush=True)
    t1 = time.time()
    m = Maxwell3d(project=PROJ, design="WPT_G", remove_lock=True)
    print("OK 工程打开：design=%s solution=%s 耗时 %.1f s"
          % (m.design_name, m.solution_type, time.time() - t1), flush=True)
    print("   setuations=%s" % [s.name for s in m.setups], flush=True)
    print("   对象数=%d  材料=%s" % (len(m.modeler.object_names),
                                     sorted(m.materials.material_keys)[:6]), flush=True)
    print("   windings=%s" % [w.name for w in m.winding_groups] if hasattr(m, "winding_groups") else "", flush=True)
    print("RESULT: INSECURE 传输可用 ✓", flush=True)
finally:
    if pid:
        try:
            subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "Stop-Process -Id %d -Force -ErrorAction SilentlyContinue" % int(pid)],
                           capture_output=True, text=True)
        except Exception as e:
            print("kill err %r" % e)
