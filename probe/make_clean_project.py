# -*- coding: utf-8 -*-
"""造一份"干净的参考工程"，供 ④ 的各实例复制分发。

动机：④ 首次试验里三个实例的求解都 Status='Error'，而同一时段单实例在原工程上跑得好好的
（A 组 A0/A1/A2 全部有效）。许可证文件已查实 anshpc / elec_solve_maxwell / electronics_desktop
都是 100 个授权，所以不是座位问题。最可疑的是**工程副本背着历史状态**：
donor 设计 WPT_mesh、⑦B 失败求解的残留、多余设计（WPT_F / Maxwell3DDesign1）等。

本脚本产出 `Projecttonight_ref.aedt`：
  - 只保留 WPT_G 一个设计
  - MeshLink 关闭、网格操作清空、全局初始网格滑块回 5
  - 几何 = 参考点（LC=167.2829 / KR=0.3587 / KX=-0.3 / W=10 / G=20 / thk=10 / Rx 在 0）
  - Region 重建为 X±205 / Y[-134.94,134] / Z[-45,75]
  - 存盘、退出、清锁
"""
import json
import os
import subprocess
import sys
import time
import traceback

WORK = r"C:\ansys maxwell2024\_work"
sys.path.insert(0, r"C:\ansys maxwell2024\_probe")
import aedt_shim                               # noqa: E402
sys.path.insert(0, r"C:\wpt")
os.chdir(r"C:\wpt")

import batch_sweep_lc as B                       # noqa: E402
import coil_gen as CG                            # noqa: E402
from ansys.aedt.core import Desktop, Maxwell3d   # noqa: E402

aedt_shim.patch_pyaedt_proc()

SRC = os.path.join(WORK, "Projecttonight_4ch.aedt")
DST = os.path.join(WORK, "Projecttonight_ref.aedt")
LOGF = os.path.join(WORK, "clean_project.log")
OUT = os.path.join(WORK, "clean_project.json")
PT = dict(LC=167.2829, KR=0.3587, KX=-0.3, W=10.0, G=20.0, mu=1000.0, thk=10.0)
REGION_REF = {"x": (-205.0, 205.0), "y": (-134.94, 134.0), "z": (-45.0, 75.0)}
RES = {}


def log(m=""):
    s = "%s | %s" % (time.strftime("%H:%M:%S"), m)
    print(s, flush=True)
    try:
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(s + "\n")
    except Exception:
        pass


def run_ps(cmd):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                          capture_output=True, text=True)


def kill_aedt_ps(wait_s=60):
    t0 = time.time()
    while time.time() - t0 < wait_s:
        run_ps("Get-Process -Name ansysedt,ansyscl -ErrorAction SilentlyContinue |"
               " Stop-Process -Force -ErrorAction SilentlyContinue")
        time.sleep(3)
        r = run_ps("@(Get-Process -Name ansysedt -ErrorAction SilentlyContinue).Count")
        if (r.stdout or "").strip() in ("0", ""):
            break


B.kill_aedt = kill_aedt_ps


def objs_bbox(m3d):
    bb = None
    for o in m3d.modeler.object_names:
        if o == "Region":
            continue
        try:
            b = m3d.modeler[o].bounding_box
        except Exception:
            continue
        bb = list(b) if bb is None else [min(bb[0], b[0]), min(bb[1], b[1]), min(bb[2], b[2]),
                                         max(bb[3], b[3]), max(bb[4], b[4]), max(bb[5], b[5])]
    return bb


def main():
    global d, m
    log("=" * 78)
    log("造干净参考工程 %s" % os.path.basename(DST))
    kill_aedt_ps()
    import shutil
    shutil.copy2(SRC, DST)
    lk = DST + ".lock"
    if os.path.exists(lk):
        os.remove(lk)
    B.BASE_DIR = WORK
    B.LOG_FILE = os.path.join(WORK, "clean_project_solve.log")
    d = Desktop(version="2024.1", new_desktop=True, non_graphical=False, close_on_exit=False)
    m = Maxwell3d(project=DST, design=B.DESIGN, remove_lock=True)
    log("已打开 %s" % os.path.basename(DST))
    RES["designs_before"] = list(d.design_list())
    log("  设计: %s" % RES["designs_before"])

    # 1) 删掉除 WPT_G 以外的设计
    for name in list(d.design_list()):
        if name != B.DESIGN:
            try:
                m.delete_design(name)
                log("  删除设计 %s" % name)
            except Exception as e:
                log("  删 %s 失败: %r" % (name, e))
    RES["designs_after"] = list(d.design_list())
    log("  剩余设计: %s" % RES["designs_after"])

    # 2) 清 MeshLink / 网格操作 / 滑块
    try:
        s = m.setups[0]
        p = dict(s.props.get("MeshLink") or {})
        if p.get("ImportMesh"):
            p["ImportMesh"] = False
            s.props["MeshLink"] = p
            s.update()
        RES["meshlink"] = dict(s.props.get("MeshLink") or {})
        log("  MeshLink = %s" % RES["meshlink"])
    except Exception as e:
        log("  MeshLink: %r" % e)
    for mo in list(m.mesh.meshoperations):
        log("  删除网格操作 %s" % mo.name)
        mo.delete()
    try:
        m.mesh.assign_initial_mesh_from_slider(level=5, method="Auto")
        log("  全局初始网格滑块 -> 5")
    except Exception as e:
        log("  滑块设置失败: %r" % e)

    # 3) 重建参考几何
    CG.TEMPLATE = r"C:\wpt\coil_template_Rx.json"
    CG._ref = None
    CG._s_ref = None
    CG._load()
    B.set_rx_dx(m, 0.0)
    CG.rebuild_all(m, PT["LC"], PT["KR"], log=log)
    tg = PT["KX"] * PT["LC"]
    outer = CG.coil_outer(PT["LC"])
    rx_leads = CG.current_leads(m, "Rx")
    B.set_tx_gap(m, tg, outer)
    nf = B.rebuild_ferrite(m, PT["W"], PT["G"], tg, PT["thk"], outer, rx_leads)
    bb = objs_bbox(m)
    pad = [REGION_REF["x"][1] - bb[3], bb[0] - REGION_REF["x"][0],
           REGION_REF["y"][1] - bb[4], bb[1] - REGION_REF["y"][0],
           REGION_REF["z"][1] - bb[5], bb[2] - REGION_REF["z"][0]]
    try:
        m.modeler.delete("Region")
        time.sleep(1)
        m.modeler.create_region(pad_value=["%.4fmm" % max(0.0, v) for v in pad],
                                pad_type="Absolute Offset")
    except Exception as e:
        log("  region: %r" % e)
    rbb = m.modeler["Region"].bounding_box
    log("  铁氧体 %d 条；Region X[%.1f,%.1f] Y[%.1f,%.1f] Z[%.1f,%.1f]"
        % (nf, rbb[0], rbb[3], rbb[1], rbb[4], rbb[2], rbb[5]))
    RES["snapshot"] = {c: dict(faces=len(m.modeler[c].faces),
                              volume=round(m.modeler[c].volume, 4))
                       for c in ("Tx1", "Tx2", "Rx")}
    RES["region"] = [round(v, 3) for v in rbb]
    RES["n_ferrite"] = nf
    log("  快照: %s" % RES["snapshot"])

    # 4) 存盘退出清锁
    m.save_project()
    log("  已存盘")
    json.dump(RES, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    kill_aedt_ps(wait_s=40)
    for f in (DST + ".lock",):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass
    log("干净工程: %s (%.1f MB)" % (DST, os.path.getsize(DST) / 1048576.0))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log("!! 失败\n" + traceback.format_exc())
        RES["fatal"] = traceback.format_exc()
        try:
            json.dump(RES, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        except Exception:
            pass
        sys.exit(1)
