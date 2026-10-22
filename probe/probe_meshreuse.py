# -*- coding: utf-8 -*-
"""探针：AEDT 2024.1 里有没有「套用上一次网格」的脚本接口（⑦ 用）。

输出到 _work\probe_meshreuse.txt（ASCII）。会开一次会话、打开工程，然后：
  1) 列出 design 对象上名字里带 Mesh/Adaptive 的方法
  2) 列出 setup 对象的方法与 props 键
  3) 试几个候选接口是否可调用（只报告，不真求解）
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                               # noqa: E402
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import batch_sweep_lc as B                       # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

aedt_shim.patch_pyaedt_proc()

WORK = r"C:\ansys maxwell2024\_work"
PROJ = os.path.join(WORK, "Projecttonight_4ch.aedt")
OUT = os.path.join(WORK, "probe_meshreuse.txt")
BUF = []


def say(*a):
    BUF.append(" ".join(str(x) for x in a))


def kill_aedt_ps(wait_s=60):
    t0 = time.time()
    while time.time() - t0 < wait_s:
        subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "Get-Process -Name ansysedt,ansyscl -ErrorAction SilentlyContinue |"
                        " Stop-Process -Force -ErrorAction SilentlyContinue"],
                       capture_output=True, text=True)
        time.sleep(3)
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                            "@(Get-Process -Name ansysedt -ErrorAction SilentlyContinue).Count"],
                           capture_output=True, text=True)
        if (r.stdout or "").strip() in ("0", ""):
            break


kill_aedt_ps()
for lk in (PROJ + ".lock",):
    if os.path.exists(lk):
        os.remove(lk)

d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
m = Maxwell3d(project=PROJ, design=B.DESIGN, remove_lock=True)
say("design=%s  solutions=%s" % (m.design_name, m.existing_analysis_sweeps))

say("")
say("=== odesign 上带 Mesh/Adapt 的方法 ===")
try:
    names = sorted(x for x in dir(m.odesign)
                   if any(k in x.lower() for k in ("mesh", "adapt", "solve", "copy")))
    for n in names:
        say("  " + n)
except Exception as e:
    say("  ERR %r" % e)

say("")
say("=== setup 对象 ===")
s = m.setups[0]
say("  name=%s" % s.name)
say("  props keys: %s" % sorted(s.props.keys()))
say("  setup methods(带 Mesh/Adapt):")
try:
    for n in sorted(x for x in dir(s) if any(k in x.lower() for k in ("mesh", "adapt"))):
        say("    " + n)
except Exception as e:
    say("  ERR %r" % e)

say("")
say("=== 候选接口探测（不执行求解）===")
cands = ["ApplyMesh", "CopyMesh", "ResetMesh", "GetMeshStats", "SetMeshReuse"]
for c in cands:
    ok = hasattr(m.odesign, c)
    say("  odesign.%-12s exists=%s" % (c, ok))

say("")
say("=== meshoperations / mesh 相关 ===")
try:
    say("  meshoperations: %s" % [o.name for o in m.mesh.meshoperations])
except Exception as e:
    say("  meshoperations ERR %r" % e)
try:
    say("  initial_mesh_settings: %s" % m.mesh.initial_mesh_settings)
    say("  initial_mesh_settings props: %s"
        % sorted(getattr(m.mesh.initial_mesh_settings, "props", {}).keys()))
except Exception as e:
    say("  initial_mesh_settings ERR %r" % e)

say("")
say("=== add_mesh_link 是否可用（只检查签名/属性，不调用）===")
try:
    import inspect
    say("  " + str(inspect.signature(s.add_mesh_link)))
    say("  MeshLink in props: %s" % ("MeshLink" in s.props))
    say("  MeshLink value: %s" % (s.props.get("MeshLink") if "MeshLink" in s.props else None))
except Exception as e:
    say("  ERR %r" % e)

open(OUT, "w", encoding="utf-8").write("\n".join(BUF) + "\n")
kill_aedt_ps(wait_s=40)
for lk in (PROJ + ".lock",):
    if os.path.exists(lk):
        try:
            os.remove(lk)
        except Exception:
            pass
