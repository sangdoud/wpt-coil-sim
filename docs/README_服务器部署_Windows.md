# WPT 三线圈仿真 — Windows 服务器从零部署指南

> 服务器是**全新空机器**时的完整部署步骤。
> 目标：让 `batch_sweep.py` 在服务器上跑完 1331 点全参数扫描。
> 前提：服务器是 **Windows**（10/11/Server），能联网或离线均可。

---

## 一、总共要做的事（5 步）

| 步骤 | 做什么 | 需要的东西 |
|---|---|---|
| 1 | 装 Ansys AEDT 2024 R1 | 安装包 + **License** |
| 2 | 装 Python 3.11 | 官方安装包 |
| 3 | 装 pyaedt 1.3.0 | 联网 pip / 离线 whl |
| 4 | 拷项目文件到服务器 | `Projecttonight.aedt` + 脚本 |
| 5 | 改配置 + 验证 + 开跑 | 本指南 |

---

## 二、第 1 步：装 Ansys AEDT 2024 R1

### 安装包
用你本机 E 盘的安装包：
```
E:\Ansys Electronics Suite 2024R1\ANSYS.2024.R1.Electronics.Suite.Win64.iso
```
在服务器上挂载 ISO（双击或右键装载），运行安装程序。

### ⚠️ License（最大的坑，必须先解决）
AEDT 没有 license **一步都算不了**。两种方式：

**方式 A：license 文件（推荐给离线服务器）**
1. 你本机已经在用 license（`ANSYSLMD_LICENSE_FILE=1055@localhost`，见本机环境变量）
2. 服务器上装同样的 **License Manager**（`E:\Ansys Electronics Suite 2024R1\LicenseManager安装包_2024R1_WINX64.iso`）
3. 把本机的 license 授权信息复制到服务器
4. 设置环境变量 `ANSYSLMD_LICENSE_FILE=1055@localhost`（指向服务器本机）

**方式 B：license server 共享**
- 如果 license 允许浮点，服务器直接连本机的 license server，环境变量指向本机 IP：
  ```
  ANSYSLMD_LICENSE_FILE=1055@<本机IP>
  ```
  但本机关机服务器就连不上了，不推荐长跑。

### 安装后验证
```cmd
where ansysedt
```
能输出路径即装好。

---

## 三、第 2 步：装 Python 3.11

1. 官网下载：`https://www.python.org/downloads/` 选 **3.11.x**（必须 3.11）
2. 双击安装，**勾选 "Add Python to PATH"**
3. 装完验证：
```cmd
python --version
```

---

## 四、第 3 步：装 pyaedt（唯一 Python 依赖）

```cmd
pip install pyaedt==1.3.0
```
- **必须 1.3.0**，其它版本 API 对不上
- 联网服务器直接装；离线服务器需先在本机导出 wheel：
  ```cmd
  pip download pyaedt==1.3.0 -d C:\pyaedt_wheels
  ```
  拷到服务器后：`pip install C:\pyaedt_wheels\*.whl`

### 验证
```cmd
python -c "import ansys.aedt.core; print('pyaedt OK')"
```

---

## 五、第 4 步：拷文件到服务器

建议在服务器建目录 `C:\wpt\`，拷入：

| 文件 | 来源 | 必须 |
|---|---|---|
| `Projecttonight.aedt` | 本机 `C:\wpt\` | ✅ 核心模型 |
| `batch_sweep.py` | 本机 zidong 目录 | ✅ |
| `combos.csv` | 本机 zidong 目录 | ✅ 1331 组合 |
| `solve_mag.py` | 本机 zidong 目录 | ✅ 先验证 |
| `close_ansys.py` | 本机 zidong 目录 | 可选，跑完关 AEDT |

> 若 `Projecttonight.aedtresults` 目录很大，可只拷 `.aedt` 文件，AEDT 会自动重建结果目录。

---

## 六、第 5 步：改配置 + 验证 + 开跑

### 改 `batch_sweep.py`（4 处）

```python
# 第 26 行
BASE_DIR = r"C:/wpt"                 # 改成服务器路径

# 第 31-32 行（保持默认，项目名随 .aedt 文件）
PROJECT = "Projecttonight"
DESIGN  = "WPT_G"

# 第 38 行
NEW_DESKTOP = True                   # 让脚本自己启动 AEDT

# 第 39 行
NON_GRAPHICAL = False                # Windows 有桌面可留 False；远程无桌面会话设 True
```

> 建议：服务器 Windows 有远程桌面就 `NON_GRAPHICAL=False`（看得见进度）；纯 headless 才设 True。

### 单点验证（关键！避免白跑）
```cmd
cd C:\wpt
python solve_mag.py
```
能算出 3×3 电感矩阵 = 环境 OK。**验证过了再跑全量**。

> ⚠️ `solve_mag.py` 用 `new_desktop=False` 连接**已运行的 AEDT**。验证前请先手动打开一次 AEDT（或先跑 `batch_sweep.py` 让它自动启动）。若提示连接失败，先双击桌面 AEDT 图标打开，再跑验证。

### 开跑全量（挂后台）
```cmd
cd C:\wpt
start /b python batch_sweep.py > batch_run.log 2>&1
```
或按 `Windows + R` 关掉窗口也继续？不，`start /b` 关窗口会停。想脱离终端：
- 用 **计划任务**（Task Scheduler）跑，或
- 用 `nohup`（git bash）：
  ```bash
  nohup python batch_sweep.py > /dev/null 2>&1 &
  ```

### 看进度
```cmd
type C:\wpt\batch_sweep.log
type C:\wpt\sweep_all.csv
```
`batch_sweep.log` 有每个点的 `W= G= dx=` 和 `k13`；`sweep_all.csv` 是结果汇总，**每算一点写一点**，中断不丢。

---

## 七、断点续跑（重要）

- 中断了直接**重跑** `python batch_sweep.py`，它自动读 `sweep_all.csv` 跳过已算点
- 所以断电/重启都不怕，数据只增不减

---

## 八、时间预估

1331 点 × 5~8 分钟/点 ≈ **110~177 小时**（5~7.5 天）
- 建议服务器配 8+ 核（脚本默认 `CORES=8`，机器核多可调大第 43 行 `CORES`）
- 想快可调松精度：第 44-46 行 `MAX_PASSES=8 / PCT_ERROR=5 / PCT_REFINEMENT=5`（更松更快，结果略糙）

---

## 九、常见坑速查

| 症状 | 原因 | 解决 |
|---|---|---|
| `CONNECT FAILED` | AEDT 没装/license 不对 | 先 `where ansysedt` 验证，再开一次 AEDT 手动确认能求解 |
| 报 `GetAvailableReportTypes` | 上一次求解没停干净 | 已修复：脚本现在求解前自动 `StopSimulations` |
| 铁氧体位置错乱 | 旧 bug | 已修复：脚本现在先归零 Rx 再重建 |
| 部分点 FAILED | 单点求解超时 | 脚本自动跳过继续；重跑会补齐 |
| pyaedt 导入报错 | 版本不对 | 确认 `pyaedt==1.3.0`，导入用 `ansys.aedt.core` |

---

## 十、跑完怎么拿数据

`sweep_all.csv` 就是最终全量训练数据（列同 `training_data.csv`：W,G,dx,μr,L11,L22,L33,M12,M13,M23,k13,k23）。
拷回本机即可训练。
