# -*- coding: utf-8 -*-
# 测试 AEDT 中创建设计变量的各种写法
oProject = oDesktop.GetActiveProject()
oDesign  = oProject.GetActiveDesign()

def try_create(desc, func):
    try:
        func()
        oDesktop.AddMessage("", "", 0, "OK  %s" % desc)
    except Exception as e:
        oDesktop.AddMessage("", "", 0, "FAIL %s : %s" % (desc, e))

# 方式A: oDesign + LocalVariableTab + 完整属性
try_create("A oDesign LocalVarTab 完整", lambda: oDesign.ChangeProperty(
    ["NAME:AllTabs",
     ["NAME:LocalVariableTab",
      ["NAME:PropServers", "LocalVariables"],
      ["NAME:NewProps",
       ["NAME:testvarA", "UserDef:=", True, "Value:=", "1mm", "Description:=", ""]]]]))

# 方式B: oProject + DesignVariableTab + 完整属性
try_create("B oProject DesignVarTab 完整", lambda: oProject.ChangeProperty(
    ["NAME:AllTabs",
     ["NAME:DesignVariableTab",
      ["NAME:PropServers", "DesignVariables"],
      ["NAME:NewProps",
       ["NAME:testvarB", "UserDef:=", True, "Value:=", "1mm", "Description:=", ""]]]]))

# 方式C: oDesign + DesignVariableTab
try_create("C oDesign DesignVarTab", lambda: oDesign.ChangeProperty(
    ["NAME:AllTabs",
     ["NAME:DesignVariableTab",
      ["NAME:PropServers", "DesignVariables"],
      ["NAME:NewProps",
       ["NAME:testvarC", "UserDef:=", True, "Value:=", "1mm", "Description:=", ""]]]]))

# 方式D: oDesign + LocalVariableTab 简化(无 UserDef/Description)
try_create("D oDesign LocalVarTab 简化", lambda: oDesign.ChangeProperty(
    ["NAME:AllTabs",
     ["NAME:LocalVariableTab",
      ["NAME:PropServers", "LocalVariables"],
      ["NAME:NewProps",
       ["NAME:testvarD", "Value:=", "1mm"]]]]))

# 方式E: oProject + LocalVariableTab
try_create("E oProject LocalVarTab", lambda: oProject.ChangeProperty(
    ["NAME:AllTabs",
     ["NAME:LocalVariableTab",
      ["NAME:PropServers", "LocalVariables"],
      ["NAME:NewProps",
       ["NAME:testvarE", "UserDef:=", True, "Value:=", "1mm", "Description:=", ""]]]]))

# 方式F: oDesign + SetVariableValue（若变量自动创建后设值）
try_create("F SetVariableValue", lambda: oDesign.SetVariableValue("testvarF", "1mm"))

oDesktop.AddMessage("", "", 0, "=== 测试结束，请把上方 OK/FAIL 结果发我 ===")
