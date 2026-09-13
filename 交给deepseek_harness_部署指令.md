# 给 DeepSeek Harness 的部署指令（直接整段复制粘贴）

> 用途：让服务器上的 DeepSeek harness 把 WPT 仿真所需的 **Python 环境 + 文件** 部署好并自检通过。
> **本次明确只部署环境，不跑任何仿真。**

---

## ⬇️ 下面整段复制给 harness ⬇️

【任务】在这台 Windows 服务器上部署 WPT（三线圈无线电能传输）参数化仿真所需的 Python 环境，并完成只读自检。**只部署，不跑仿真。**

【硬约束 —— 违反任意一条即为失败】
1. 禁止启动任何 Maxwell/AEDT 求解，禁止调用 analyze / solve / 任何仿真动作。
2. 禁止新建、保存、修改、覆盖任何 `.aedt` 文件。
   （新版 AEDT 一旦保存会把工程**单向升级**，旧版软件将永远打不开，模型就废了。）
3. 禁止卸载、升级、改动本机已有的 ANSYS/AEDT 安装。
4. 除 `pyaedt==1.3.0` 外，禁止安装其他新依赖。
5. 唯一允许执行的程序是自检脚本 `preflight_2025.py --env-only`（它只读环境，全程不启动 AEDT，约 5 秒）。
6. 遇到任何一步失败：**原样贴出报错并停下**，不要"想办法绕过"、不要自己改脚本、不要伪造结果。

【目标环境】
- Windows 服务器，已安装 ANSYS Electronics Desktop / Maxwell（2025.x 或 2024.x 均可）
- Python 3.10+（3.11 最佳）
- pyaedt 固定 1.3.0
- 工作目录：`C:\wpt`（可自定，下文用该路径）

【执行步骤】

第 1 步 · 确认 Python
```
python --version
```
若不存在或低于 3.10 → 安装 Python 3.11（安装第一屏必须勾选 "Add python.exe to PATH"），装完**重开终端**再继续。

第 2 步 · 安装依赖
```
python -m pip install -U pip
python -m pip install pyaedt==1.3.0
python -c "import ansys.aedt.core, importlib.metadata as m; print('pyaedt', m.version('pyaedt'))"
```
最后一行必须打印 `pyaedt 1.3.0`。

第 3 步 · 从 GitHub 取文件（**私有仓库**）
仓库：`https://github.com/sangdoud/wpt-coil-sim`（私有，需令牌）
```
set GH_TOKEN=<把这里替换成我的 GitHub PAT>
git clone https://%GH_TOKEN%@github.com/sangdoud/wpt-coil-sim.git C:\wpt
```
或已登录 gh 的话：
```
gh auth status
gh repo clone sangdoud/wpt-coil-sim C:\wpt
```
克隆失败（网络/被墙/无权限）→ **停下回报**，并把失败的原始报错贴回来，不要用别的来源顶替。

第 4 步 · 校验文件（三个文件必须在同一目录 `C:\wpt`）
- `preflight_2025.py` —— 自检脚本（本次只需要它）
- `batch_sweep_unit30.py` —— 几何函数库（被上面 import，缺它自检会报错）
- `Projecttonight.aedt` —— 模型文件

校验模型完整性（**这一步很重要**，必须是新版权本）：
```
python -c "import hashlib,os;p=r'C:\wpt\Projecttonight.aedt';h=hashlib.md5();f=open(p,'rb');
[h.update(b) for b in iter(lambda:f.read(1<<20),b'')];print(os.path.getsize(p), h.hexdigest())"
```
期望：`25155997 9bb98917d803ca42191a6abee8360d82`
若 md5 不是 `9bb98917` 开头（例如是 24782600 字节的旧版）→ **停下回报**，不要继续。

第 5 步 · 只读环境自检（唯一允许"运行"的程序）
```
cd /d C:\wpt
python preflight_2025.py --env-only
```
它只检查 4 件事：pyaedt 是否装好 / AEDT 版本条目路径是否真实存在 / 版本配对是否合理 / 工程文件是否就位。
说明：若本机有一条指向**不存在路径**的版本条目（"幽灵版本"），脚本会自动跳过并回退到最高可用版，这是**正常行为**，不是报错。

第 6 步 · 回报
把下面两项原样发回：
1. 上面每条命令的**原始输出**（含任何红字报错）；
2. `C:\wpt\preflight_report.txt` 的**全文内容**。

期望看到结尾是：`PASS=4  FAIL=0`

【验收标准】
- [ ] `python --version` ≥ 3.10
- [ ] pyaedt 版本 == 1.3.0
- [ ] `Projecttonight.aedt` 大小 25155997、md5 = 9bb98917d803ca42191a6abee8360d82
- [ ] `preflight_2025.py --env-only` 输出 `PASS=4  FAIL=0`
- [ ] 全程未跑过任何仿真、未新建/修改任何 `.aedt`

【做完之后】
**先不要跑仿真。** 把上述结果发回，等我确认后再进行下一步（真跑仿真会占用 Maxwell 授权并持续几十分钟到几十小时，必须由我另行安排）。

## ⬆️ 复制到此为止 ⬆️

---

## 备注（只给自己看，不要发给 harness）

- **PAT 怎么给**：GitHub → Settings → Developer settings → Personal access tokens → 勾 `repo` 权限即可；用完可以随时吊销。不要用账号密码。
- **网络**：如果服务器连不上 github.com，让 harness 先试 `gh repo clone`；仍不行就停手，你手动把 3 个文件传过去（`Projecttonight.aedt` 25MB，微信/U盘/网盘都行）。
- **AEDT 版本不是 2025.1**：自检脚本会自动回退到最高可用版；若想让报告更精确，可改 `preflight_2025.py` 开头的 `TARGET_VERSION` 一行。
- **只读保证**：`--env-only` 全程不创建 AEDT 会话、不写任何工程文件；脚本里 `SAVE_PROJECT=False` 是死线，**任何情况下都不要改成 True**。
- **自检通过后**才谈跑仿真：届时把批量脚本里的 `AEDT_VERSION` 改成实际版本号（如 `"2025.2"`），并且**新版跑出来的数据不要和 2024.1 的 1705 点混进同一个训练集**。
