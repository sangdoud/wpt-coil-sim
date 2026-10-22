# shard2b 批次 · B 设备部署执行手册

> 本手册是《迁移操作手册.md》针对 **shard2b 批次**的适配执行版。
> shard2b = batch2 续接段（`b2_2881 ~ b2_3840`，**960 组**），在目标设备 B 上批量仿真。
> 环境事实、冻结口径、风险与陷阱一律以《迁移操作手册.md》为准，本手册只写**差异与执行顺序**。

---

## ⚠️ 先读：与《迁移操作手册》的三处差异

| # | 迁移手册原文 | shard2b 本批 | 原因 |
|---|---|---|---|
| 1 | 传输 = 直连打包（§2.4） | 传输 = `git clone` | 仓库已上 GitHub（`sangdoud/wpt-coil-sim`） |
| 2 | 批次名 `b3`，跑 `rename_batch.py`（§3.4） | **批次名保持 `b2`，跳过 rename** | shard2b 的 case_id 是 `b2_` 前缀，须与源机 shard1（`b2_0001~b2_1920`）合并成完整 batch2，改名会让数据不可比 |
| 3 | 参数表 = 新参数，`--rows 1920` | **参数表 = `work/input/batch2_samples_shard2b.csv`，`--rows 960`** | 本批只有 shard2b 960 组 |

> 🔴 **为什么必须保持 b2**：`build_b2_plan.py` 的校验会核对 case_id 前缀 == 批次名。
> shard2b 的 case_id 是 `b2_2881~b2_3840`，只有 `--batch b2` 才能通过；改成 b3 会 FAIL。
> 脚本目录叫 `work/b3/` 只是打包时的命名，**不影响批次名**——批次名由命令行 `--batch` 决定。

---

## 1. 环境安装（B 设备只有 Ansys，其余全部安装）

### 1.1 git

```powershell
winget install --id Git.Git -e --source winget
git --version
```

### 1.2 Python 3.14.6（与源机逐项对齐，权威版本）

源机生产组合：**Python 3.14.6（Anaconda）+ pyaedt 1.3.0 + numpy 2.4.6 + grpcio 1.83.1 + protobuf 6.33.5 + pandas 3.0.3 + scipy 1.18.0**。
（⚠️ 旧文档写的「必须 Python 3.11」是过时信息，不要照抄。）

```powershell
# 装 Python 3.14.6（Anaconda 或 python.org，二者其一）
# 装依赖（grpcio/protobuf 错位会表现为「AEDT 会话起不来 / gRPC 僵死」，必须对齐）
python -m pip install "pyaedt==1.3.0" "numpy==2.4.6" "grpcio==1.83.1" `
    "protobuf==6.33.5" "pandas==3.0.3" "scipy==1.18.0"

# 验证
python -c "import ansys.aedt.core as c; print('pyaedt', c.__version__)"
```

### 1.3 AEDT 授权（机构浮动授权）

```powershell
# 指向机构浮动授权服务器（替换成真实地址，勿照抄示例）
[Environment]::SetEnvironmentVariable('ANSYSLMD_LICENSE_FILE','1055@lic.corp.local','Machine')
$env:ANSYSLMD_LICENSE_FILE = '1055@lic.corp.local'
Test-NetConnection -ComputerName lic.corp.local -Port 1055
```

> ⚠️ 共享席位池：Maxwell 席位须 ≥ 计划并发实例数（留 1~2 余量）。席位不足会表现为随机求解失败，易误判为几何问题。

---

## 2. clone 仓库 + 完整性校验

```powershell
cd D:\
git clone https://github.com/sangdoud/wpt-coil-sim.git wpt_mig
cd wpt_mig

# 先校验，再动任何东西（SHA256 逐文件核对，不校验传输就等于没传输）
python tools\verify_pack.py --pack .
```

**判定**：`OK 234 / 缺失 0 / 不一致 0`；且 `work\Projecttonight_ref.aedt` 存在、约 12.11 MB。

> 🔴 母本工程是 `work/Projecttonight_ref.aedt`。仓库根目录平铺的 `Projecttonight.aedt` 是旧工程，**不是**母本工程，勿混淆。

---

## 3. 落位 + 站点配置

### 3.1 铺开到工作根（路径不含中文与空格）

```powershell
$R = 'D:\wpt_runs'
New-Item -ItemType Directory -Force -Path "$R\_work","$R\wpt","$R\_probe","$R\docs" | Out-Null

Copy-Item "D:\wpt_mig\work\b3"  "$R\_work\b3"  -Recurse -Force
Copy-Item "D:\wpt_mig\work\ref" "$R\_work\ref" -Recurse -Force
Copy-Item "D:\wpt_mig\work\input" "$R\_work\input" -Recurse -Force
Copy-Item "D:\wpt_mig\work\Projecttonight_ref.aedt" "$R\_work\" -Force
Copy-Item "D:\wpt_mig\wpt\*"    "$R\wpt\"    -Recurse -Force
Copy-Item "D:\wpt_mig\probe\*"  "$R\_probe\" -Recurse -Force
Copy-Item "D:\wpt_mig\tools"    "$R\tools"   -Recurse -Force
Copy-Item "D:\wpt_mig\docs\*"   "$R\docs\"   -Recurse -Force
```

### 3.2 填 `tools\_site_config.json`（唯一输入）

复制 `D:\wpt_mig\tools\_site_config.example.json` → `D:\wpt_mig\tools\_site_config.json`，按本机实值改。
**本批的关键字段**：

```jsonc
{
  "new_work_root":    "D:\\wpt_runs\\_work",
  "new_wpt_root":     "D:\\wpt_runs\\wpt",
  "new_probe_root":   "D:\\wpt_runs\\_probe",
  "new_python":       "<本机 python.exe 绝对路径>",
  "new_project_ref":  "D:\\wpt_runs\\_work\\Projecttonight_ref.aedt",
  "new_workspace":    "D:\\wpt_runs",
  "new_aedt_exe":     "C:\\Program Files\\ANSYS Inc\\v241\\Win64\\ansysedt.exe",
  "license_server":   "1055@lic.corp.local",          // 真实值
  "batch_name":       "b2",                            // ★ 本批用 b2，不是 b3
  "instances":        8,                               // 按内存定，见 §8
  "expected_ram_gb":  64
}
```

---

## 4. 路径改造（先预演、后实改、再复校）

```powershell
cd D:\wpt_mig\tools
python adapt_paths.py --pack D:\wpt_runs --site D:\wpt_mig\tools\_site_config.json --dry-run
python adapt_paths.py --pack D:\wpt_runs --site D:\wpt_mig\tools\_site_config.json --apply
python adapt_paths.py --pack D:\wpt_runs --site D:\wpt_mig\tools\_site_config.json --verify
```

**判定**：`--verify` 末尾 `[OK] 无残留`，退出码 0。
**跳过 `rename_batch.py`**（本批保持 b2，见差异表 #2）。

---

## 5. 生成 b2 计划（shard2b 参数表 → plan）

```powershell
# build_b2_plan.py 在 _probe；参数表在 _work\input
python D:\wpt_runs\_probe\build_b2_plan.py `
    --src D:\wpt_runs\_work\input\batch2_samples_shard2b.csv `
    --outdir D:\wpt_runs\_work\b3 `
    --batch b2 --rows 960 --boxx 420
```

**输出**（写到 `--outdir`）：`b2_plan.csv`（32 个验收点在前）、`b2_audit.csv`、`b2_region_check.csv`、`b2_plan_meta.json`。

**判定**：校验 `FAIL 0`；`b2_plan.csv` 恰好 960 行（+表头）；`b2_plan_meta.json` 里 `n_cases=960`。
> 若 `C5`（固定盒包含性）告警，按迁移手册 §4.2 处理：重新定盒，或走显式豁免（A/B 实测 + 理由落盘 `box_margin_waiver`），不得默默放行。

---

## 6. 冒烟（真实 AEDT，1 工况 × 1 点，放量前必须过）

```powershell
python D:\wpt_runs\_work\b3\preflight.py --root D:\wpt_runs\_work --batch b2 `
    --plan D:\wpt_runs\_work\b3\b2_plan.csv --n 8
python D:\wpt_runs\_work\b3\smoke_one.py --root D:\wpt_runs\_work --batch b2
```

**判定**：`preflight.py` `FAIL 0`；`smoke_one.py` 真实起 AEDT → 工程加载 → 几何重建 → 求解 → 逐点落盘，日志出现 `OK` 与一组有限电感值。

> 🔴 冒烟必须真实跑 AEDT，不能只看退出码。源机 `smoke_one.py` 自带 9 项现场判定，实测能抓到「非法 mesh / 缺 raw / 自感非正」等问题。

---

## 7. 放量批量仿真（8 实例，沿用源机 b2 口径）

```powershell
# 分离启动，不受 shell 生命周期影响
Start-Process -FilePath '<本机 python.exe>' `
  -ArgumentList '"D:\wpt_runs\_work\b3\contract_launch.py"','8','--batch','b2',
                '--root','D:\wpt_runs\_work','--boxx','420','--merge' `
  -WorkingDirectory 'D:\wpt_runs\_work\b3' -WindowStyle Hidden

# 上线确认
python D:\wpt_runs\_work\b3\b2_status.py --root D:\wpt_runs\_work --batch b2
```

**上线确认清单**：8 worker / 8 AEDT / 1 启动器；8 个分片已生成；8 份工程副本；首个点位 ~3.5 min 内落盘。

**三个计划任务**（无人值守自愈，B 设备无 Slurm/PBS，必须实跑验证）：`b2_batch_guard`（30min）、`b2_batch_deliver`（30min）、`b2_batch_clean`（每天 03:10）——注册与实跑方法见迁移手册 §4.5，**注意 `-Execute` 只放解释器、`-Argument` 只放脚本与参数**（否则会变成 `python.exe python.exe b2_guard.py` 静默失效）。

---

## 8. 口径（沿用源机 b2 实测，不调整）

| 项 | 值 |
|---|---|
| 并发实例数 | **8**（源机 31.6 GB 内存硬上限；B 设备物理内存若 ≤32 GB 需下调，按每实例 ≥4 GB、总提交量 ≤75%） |
| 几何/求解超时 | 1500 s / 2400 s（`contract_worker.py`） |
| 逐点清理 / 回退 | `WPT_CLEAN=point` / `WPT_MESH_FALLBACK=1`（三级回退 ≈20 min/点） |
| 会话轮换 | `WPT_SESSION_MAX_H=7` |
| 失败隔离 | 单工况崩溃判失败 +106 s 落盘；单工况失败不阻断其余工况；`b2_guard.py` 每 30 min 巡检自愈 |
| 空气域 | X±420（`contract_worker.py` L206 运行时覆盖，**逐字确认该行存在**） |
| 工期基线 | 单点均值 8.18 min / 单工况 171.8 min / 8 实例 48.9 点·h⁻¹ |
| **本批工期估算** | **960 组 × 171.8 min ÷ 8 实例 ÷ 60 ≈ 343.6 小时 ≈ 14.3 天**（wall time，不含失败重试） |

---

## 9. 结果回传（给源机 / 优化端）

1. `verify_pack.py` 输出（`OK 234 / 缺失 0 / 不一致 0`）
2. `preflight.py` 完整输出（FAIL 0）
3. `b2_plan_meta.json`（`n_cases=960`）
4. 冒烟 `OK` 日志末 20 行
5. 放量后 `b2_status.py` 的上线确认行

有这五项，即可判断本批是否真正跑起来——而不是"看起来跑起来"。
