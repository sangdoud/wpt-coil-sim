# -*- coding: utf-8 -*-
"""确认垫片能绕开管道限制（ASCII 输出，不启动 AEDT）。"""
import sys

sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim  # noqa: F401,E402  (must come before pyaedt)

from ansys.aedt.core.generic.general_methods import (  # noqa: E402
    _get_pids_by_name_windows, active_sessions)
from ansys.aedt.core.generic.file_utils import available_license_feature  # noqa: E402

print("run patched:", __import__("subprocess").run is aedt_shim.run)
pids = _get_pids_by_name_windows("ansysedt.exe")
print("ansysedt pids:", pids)
print("active_sessions:", active_sessions())
try:
    print("license feature:", available_license_feature())
except Exception as e:
    print("license feature ERR:", repr(e)[:200])
