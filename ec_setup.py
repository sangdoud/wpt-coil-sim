from ansys.aedt.core import Desktop, Maxwell3d

d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=13520)
m3d = Maxwell3d(project="Project3", design="Maxwell3DDesign1")
print("designs:", m3d.design_list)

# 1) 复制设计
try:
    ok = m3d.duplicate_design("WPT_EC")
    print("duplicate result:", ok)
except Exception as e:
    print("duplicate err:", repr(e))

# 2) 重新获取副本
try:
    m3d_ec = Maxwell3d(project="Project3", design="WPT_EC")
    print("designs now:", m3d_ec.design_list)
except Exception as e:
    print("reopen err:", repr(e))
    raise SystemExit(1)

# 3) 改求解器类型为 Eddy Current
try:
    m3d_ec.solution_type = "EddyCurrent"
    print("SOLUTION TYPE NOW:", m3d_ec.solution_type)
except Exception as e:
    print("soltype err:", repr(e))

# 4) 删除旧激励
try:
    m3d_ec.oboundary.DeleteAllExcitations()
    print("excitations cleared")
except Exception as e:
    print("clear err:", repr(e))

# 5) 删除旧 setup
try:
    for s in list(m3d_ec.setups):
        m3d_ec.delete_setup(s.name)
        print("deleted setup:", s.name)
except Exception as e:
    print("setup del err:", repr(e))

# 6) 创建 Eddy Current setup（85kHz）
try:
    m3d_ec.create_setup(name="Setup1", props={
        "Frequency": "85kHz",
        "MaximumPasses": 10,
        "PercentRefinement": 30,
    })
    print("SETUP1 created (85kHz)")
except Exception as e:
    print("setup create err:", repr(e))

# 7) 检查几何
print("objects:", m3d_ec.modeler.object_names)
print("materials:", m3d_ec.modeler[ "Tx1" ].material_name if "Tx1" in m3d_ec.modeler.object_names else "Tx1 missing")
