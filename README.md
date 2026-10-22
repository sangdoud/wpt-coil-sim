# WPT 磁耦合机构批量仿真（仿真端仓库）

本仓库是「动态无线充电系统 · 双发射单接收 磁耦合机构参数优化」项目的**仿真端**代码/数据/工具仓库，
对应数据契约见优化端（B 端）《改动说明_B端同步与部署.md》。

## 目录结构（当前生产链路）

```
work/          批次脚本(b3) + ★母本工程 Projecttonight_ref.aedt + 参数表样板/输入
wpt/           代码底座（batch_sweep_lc.py / coil_gen.py / wpt_contract.py 等）
probe/         诊断与构建工具
docs/          经验文档
tools/         迁移工具（verify_pack.py / adapt_paths.py / check_target_env.py 等）
MANIFEST.json  迁移包 SHA256 清单（新机 clone 后校验用）
```

## ⚠️ 根目录平铺文件 = 早期遗留（仅归档，勿依赖）

仓库根目录下平铺的 `*.py`、`*.csv`、`*.aedt`、`*.zip`、`*.log` 等 100+ 个文件，
是**早期 `C:\wpt` 目录的整目录快照**（旧版脚本 + 早期实验数据），**不属于当前生产链路**。

- 它们**仅作历史归档保留，不删除**；
- 新工作一律以 `work/`、`wpt/`、`probe/`、`tools/` 结构化目录为准；
- 其中根目录 `Projecttonight.aedt`、`Projecttonightxu.aedt` 是**旧工程**，不是母本工程；
  ★母本工程是 `work/Projecttonight_ref.aedt`（12.11 MB）。

## 批次参数表（仿真输入登记）

| 仓库路径 | 来源 | case_id 范围 | 状态 |
|---|---|---|---|
| `work/input/batch2_samples_shard2b.csv` | 优化端 batch2 Sobol 抽样（shard2b 分片） | b2_2881 ~ b2_3840（960 组） | 待仿真 |
| `work/ref/b2_source_samples.csv` | batch2 shard1（样板） | b2_0001 ~ b2_1920（1920 组） | 已处理 |
| `work/ref/b1_plan.csv` | batch1 样板 | b1_0001 ~ b1_0256（256 组） | 已处理 |

> 参数表列（契约固定）：`case_id, coil_size, hole_ratio, tx_fill, rx_fill, tx_thick, rx_thick, spacing_ratio`

## shard2b 批次在目标设备 B 的部署

本批（shard2b，`b2_2881~b2_3840`，960 组）在目标设备 B 上的完整部署与批量仿真步骤，
见 **《shard2b批次部署执行手册.md》**（本仓库根目录）。要点：批次名保持 `b2`（跳过 rename）、
`--rows 960`、8 实例沿用源机 b2 口径。
