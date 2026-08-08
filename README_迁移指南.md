# WPT 三线圈仿真 — 迁移到其他设备指南

> 本套仿真由 **pyaedt 脚本**驱动 Ansys AEDT 自动完成，不依赖任何 AI agent。
> 迁移 = 复制文件 + 装环境 + 改 3 个参数，然后在目标设备直接跑脚本。

---

## 1. 这套东西是什么

用 pyaedt（Python 控制 Ansys AEDT）做三线圈无线充电（WPT）仿真：
- 3 个线圈（Tx1/Tx2/Rx）+ 铁氧体阵列
- 静磁场（Magnetostatic）求解，提取电感矩阵 L 和耦合系数 k
- 支持 **Rx 沿 X 方向移动扫描**（错位-耦合曲线）

关键脚本（在 `Desktop\zidong\` 目录）：
| 脚本 | 作用 |
|---|---|
| `scan_resume.py` | **主扫描脚本**（断点续跑，11 点 Rx X 移动）|
| `build_ec6.py` | 建模（线圈+铁氧体+引线+开孔）|
| `solve_mag.py` / `solve_mag2.py` | 单点求解+提取矩阵 |
| `test_dx50_*.py` | 求解速度/精度测试 |

## 2. 目标设备需要装什么

| 组件 | 要求 | 说明 |
|---|---|---|
| **Ansys AEDT** | **2024 R1 (v241)** | 仿真引擎，必须有 license |
| **Python** | 3.11 | 跑脚本 |
| **pyaedt** | 1.3.0 | `pip install pyaedt`（注意：1.3.0 导入路径是 `ansys.aedt.core`，不是 `pyaedt`）|

> ⚠️ 没有 AEDT 就没法算。pyaedt 只是"遥控器"，算的是 AEDT。

## 3. 需要复制的文件

把以下都拷到目标设备的**相同相对位置**（或改脚本里的路径）：

1. **整个 `zidong` 脚本目录**（含 `scan_resume.py` 等所有 `.py`）
2. **项目文件**（在 `Documents\Ansoft\` 下）：
   - `Projecttonight.aedt` —— 主力（含 WPT_G 带铁氧体模型 + 已算结果）
   - `Project10.aedt` —— 铁氧体模型备份
   - `Projectzidong.aedt` —— 无铁氧体基准

## 4. 安装步骤

```bash
# 1) 装 Ansys AEDT 2024 R1（按官方流程，确保 license 可用）
# 2) 装 Python 3.11（官网或 Anaconda）
# 3) 装 pyaedt
pip install pyaedt
# 4) 把 zidong 目录和 .aedt 项目文件复制到目标设备
```

## 5. 运行前要改的 3 个参数（硬编码）

打开 `scan_resume.py`，改这几处：

| 位置 | 现在（本机） | 改成 |
|---|---|---|
| `aedt_process_id=8016` | 本机 AEDT 进程 ID | 目标设备 AEDT 的 PID（任务管理器看，或用 `Get-Process ansysedt` 查）|
| `CSV = r"C:/Users/lenovo/Desktop/zidong/scan_RxX.csv"` | 本机路径 | 目标设备路径 |
| `LOG = ...` 同上 | 本机路径 | 目标设备路径 |

另外如果目标设备 AEDT 版本不同，`Desktop(version="2024.1")` 也要对应改。

> 项目名 `Projecttonight` / 设计名 `WPT_G` 保持不变（项目文件带过来了）。

## 6. 运行

```bash
# 1) 先启动 AEDT（默认 gRPC 端口 50051）
# 2) 在 zidong 目录跑扫描（断点续跑：CSV 里已有的点会自动跳过）
python scan_resume.py
```

想让它脱离终端持续跑（不怕关窗口）：
```bash
nohup python scan_resume.py > /dev/null 2>&1 &
```

## 7. 断点续跑

`scan_resume.py` 每次启动会读 `scan_RxX.csv`：
- CSV 里已有点 **自动跳过**，只算没完成的
- 每个点算完**立即写入 CSV**，中断不丢数据
- 所以迁移到新设备后，把旧的 `scan_RxX.csv` 一起拷过去，就能接着算

## 8. 常见坑

- **pyaedt 版本**：必须 1.3.0（导入 `ansys.aedt.core`）。装成别的版本 API 对不上。
- **Desktop.__del__ 会停求解**：不要在脚本里用 `analyze(blocking=True)` 后马上退出脚本——`scan_resume.py` 已经用"触发+轮询"方式处理好，别改成别的写法。
- **求解慢是正常的**：带铁氧体 Magnetostatic 每点约 5-8 分钟，11 点约 1-1.5 小时。
- **找不到设计**：确认项目名 `Projecttonight` 和设计名 `WPT_G` 没改。
- **铁氧体材料**：脚本里设 `μr=300`、电导率 0。要改回真实值（如 1000）在脚本里搜 `permeability.value`。

## 9. 常见命令速查

```python
# 连接 AEDT
from ansys.aedt.core import Desktop
d = Desktop(version="2024.1", new_desktop=False, non_graphical=False,
            close_on_exit=False, aedt_process_id=<PID>)
m3d = Maxwell3d(project="Projecttonight", design="WPT_G")

# 查 AEDT PID（Windows PowerShell）
Get-Process ansysedt | Select Id
```
