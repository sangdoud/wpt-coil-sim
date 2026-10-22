# batch1 交付包说明（b1_delivery_20260926.zip）

**交付日期**：2026-09-26
**批次**：batch1（WPT 线圈电磁参数扫描，Maxwell 3D 静磁，半扫 21 点/工况镜像展开 41 点）
**结论**：**验收全部通过，可交付（带已登记缺口）**

---

## 0 一句话摘要

| 项 | 值 |
|---|---|
| 完整工况 | **251 / 256** |
| 点位 | **5370 / 5376（99.89%）** |
| 已登记缺口 | **5 工况 / 6 点（0.112%）** —— 明细见 `01_delivery/b1_partial_summary.csv` |
| 验收判定 | `01_delivery/b1_acceptance.md`：**全部检查通过，可交付** |

> ⚠️ **对外表述要求**：本批为「251 个完整工况 + 5 个已登记缺口工况」，
> **不得按 256 个完整工况表述**。依据批次政策（见 `03_manifest/b1_partial_exceptions.json` 的 `policy` 字段）。

---

## 1 包内结构

```
b1_delivery_20260926/
├── README.md                       ← 本文件
├── 01_delivery/                    【交付物】四个契约 CSV + 清单 + 验收报告
│   ├── b1_cases.csv                    每工况标量（下游建模主用）
│   ├── b1_curves.csv                   41 点镜像展开曲线
│   ├── b1_diag.csv                     网格口径分层（误差预算用）
│   ├── b1_selfcheck.csv                自检
│   ├── b1_manifest.json                终版清单（含缺口声明）
│   ├── b1_acceptance.md                验收报告
│   ├── b1_partial_summary.csv          缺口清单（5 工况 6 点，含坐标与原因）
│   └── b1_partial_raw.csv              缺口工况的全部已解原始点（半扫，不镜像）
├── 02_raw/                         【逐点原始数据】权威真值来源
│   └── b1_raw_run0..7.csv              8 个实例的逐点结果，合计 5370 点
├── 03_manifest/                    【过程记录】
│   ├── b1_partial_exceptions.json      缺口例外表（含完整证据链）
│   ├── b1_worker_run0..7.json          worker 状态快照
│   └── b1_plan.csv / b1_plan_shard0..7.csv   参数表与 8 个分片
├── 04_projects/                    【仿真工程】8 个 AEDT 工程副本（各 12.1 MB）
│   └── Projecttonight_b1_run0..7.aedt
├── 05_logs/                        【诊断日志】
│   ├── b1_worker_run0..7.log           各实例逐点日志（GBK 编码）
│   ├── b1_guard.log                    巡检/自愈记录
│   ├── b1_guard_launch.log             启动器记录
│   ├── b1_deliver.log                  交付校验记录
│   └── b1_status_snapshot.txt          终态进度快照
└── 06_reference/                   【口径与经验文档】
    ├── batch1_交付口径说明_20260919.md
    ├── batch规模与工期规划_20260919.md
    ├── 批量仿真故障总结与经验_20260926.md   ← 本批故障与解决办法
    └── 僵死事故与自动恢复改动_20260923.md
```

---

## 2 各层数据说明

### 2.1 `01_delivery/` —— 交付物（给下游用）

**`b1_cases.csv`**（251 行，19 列）
```
case_id, coil_size, hole_ratio, tx_fill, rx_fill, tx_thick, rx_thick,
spacing_ratio, tx_bar_w, rx_bar_w, ferrite_len, edge_gap, center_dist,
sweep_span, n_points, n_bars_rx, rx_volume, M_pp, raw_file
```
> ⚠️ `raw_file` 列**全为空**（本批未回填）；需要追溯原始文件请用 `case_id` 在 `02_raw/` 中查找。

**`b1_curves.csv`**（10291 行，10 列）
```
case_id, position_x, M1, M2, M_pp, L11, L22, L33, k13, k23
```
> ⚠️ `M_pp` 列**留空**，按契约由 `cases` 的标量回退（验收报告已确认此项）。

**`b1_diag.csv`**（251 行）—— 网格口径分层，交付说明需按层给误差预算：
- `mesh_gate`（整套口径）：OPT=219 / BASE=32
- `mesh`（逐点汇总）：OPT=88 / BASE+OPT=160 / BASE=3
- 混合工况（同时含 OPT 与 BASE 点）：160 / 251
- **全批 BASE 口径点占比：7.97%**

### 2.2 `02_raw/` —— 逐点原始数据（**权威真值来源**）

列：
```
case_id, i, x_mm, L11, L22, L33, M12, M13, M23, k13, k23, minutes, aedt_pid, ts, mesh
```
比交付 CSV 多三项关键信息：
- **`minutes`** —— 每点实际求解耗时（可用于产率分析）
- **`aedt_pid`** —— 该点属于哪个 AEDT 会话（会话切换会带来 ~1% 网格差异，需追溯时用）
- **`mesh`** —— 该点是 `OPT` 还是 `BASE` 口径（**误差预算必须靠它**）

### 2.3 `04_projects/` —— 仿真工程

8 个 AEDT 工程副本（Maxwell 2026.1 之前版本为 2024 R1 格式，各 12.1 MB）。
**求解结果目录 `.aedtresults/` 不在包内**（按 `WPT_CLEAN=point` 设计要求逐点清理，不保留场数据）。
若需完整复算某一工况，用工程副本 + `03_manifest/b1_plan.csv` 中的参数即可重跑。

---

## 3 已知缺口（必须随交付声明）

| 工况 | 缺失点 | 坐标 x (mm) | 日志中失败次数 | 跨度 |
|---|---|---|---|---|
| `b1_0016` | i=11 | +64.104 | 10 | 7 天 |
| `b1_0181` | i=15 | +79.799 | 11 | 7 天 |
| `b1_0081` | i=18 | +152.837 | 9 | 5 天 |
| `b1_0028` | i=18, 19 | +128.881 / +136.041 | 17 | 6 天 |
| `b1_0242` | i=14 | +110.969 | 3 | 1 天 |

**判据**：这些点在**跨 5~7 天、跨多轮全新 AEDT 会话、OPT 与 BASE 双口径**下均失败。
反证：同批 `b1_0241 / b1_0247 / b1_0251 / b1_0253 / b1_0052 / b1_0150` 曾是同样的缺点状态，
在最后几轮的【启动补偿】中**全部被解出**——说明这 5 个不是"重试次数不够"，而是几何决定论性失败。

> ⚠️ **`01_delivery/b1_partial_summary.csv` 的 `attempts_note` 列**写的是"各 2 次共 4 次尝试均失败"，
> 那是脚本模板文字；**实际失败次数以上表为准**（从日志逐条统计）。

> ⚠️ **`b1_0242` 是本批证据最弱的一条**：仅 3 次失败、单日、跨 2 个会话（登记时批次已结束，无进一步重试机会）。
> 其 `gap_min` 为负（-0.2050）的紧几何工况，与 `b1_0016`（-0.4839）、`b1_0181`（-0.2934）失败模式一致。
> **接收方若需补齐这 6 个点，应优先重试本条**（换更保守的网格口径）。

---

## 4 完整性校验清单（SHA256 前 16 位）

### 4.1 交付物

| 文件 | 字节 | 数据行 | SHA256(16) |
|---|---|---|---|
| `b1_cases.csv` | 35975 | 251 | `6ea2b7f9c9ed5e44` |
| `b1_curves.csv` | 706227 | 10291 | `3234c83a5bd4eb2b` |
| `b1_diag.csv` | 51984 | 251 | `4efe4ae9561498f5` |
| `b1_selfcheck.csv` | 15744 | 251 | `d0b93a5387305e04` |
| `b1_manifest.json` | 1260 | — | `345ff3c47c781a3f` |
| `b1_acceptance.md` | 4517 | — | `fdc4048382241ef4` |
| `b1_partial_raw.csv` | 11383 | 99 | `0afbed0cfc300372` |
| `b1_partial_summary.csv` | 503 | 5 | `52117c8ca97c3309` |

> 上述哈希对应**包内实际文件**（已逐项与归档校验一致）。
> ⚠️ `b1_manifest.json` 与 `b1_acceptance.md` 内嵌生成时间戳，**每次重跑交付脚本其哈希都会变**；
> 其余 6 个文件的哈希是内容性的，应恒定。

### 4.2 逐点原始数据（合计 5370 点）

| 文件 | 字节 | 数据行 | SHA256(16) |
|---|---|---|---|
| `b1_raw_run0.csv` | 76838 | 672 | `8d43e76b61be3a80` |
| `b1_raw_run1.csv` | 76893 | 672 | `718e0c475ca684f4` |
| `b1_raw_run2.csv` | 76634 | 671 | `43d1cbb068199ffd` |
| `b1_raw_run3.csv` | 76878 | 672 | `644dddf5a727d6e0` |
| `b1_raw_run4.csv` | 76629 | 670 | `c2c44988788f9ad0` |
| `b1_raw_run5.csv` | 76705 | 670 | `0be669ae3253d22c` |
| `b1_raw_run6.csv` | 76881 | 671 | `3578bae362520385` |
| `b1_raw_run7.csv` | 76818 | 672 | `5d0fb5c199ba80ac` |

**快速自检**：8 个 raw 文件的数据行之和应为 **5370**；
`b1_cases.csv` 行数应为 **251**；`b1_curves.csv` 行数应为 **10291**。

---

## 5 本包相对原始交付的改动

打包前修了 `b1_partial_export.py` 的一个缺陷并重新生成两份旁路文件：

- **缺陷**：该脚本判据原为 worker JSON 的 `status == "partial"`，而**整批重启会清空该字段**，
  导致导出的 `b1_partial_*.csv` **只有表头、0 行**——接收方拿不到缺口清单。
- **修法**：判据改为 **raw 反推**（raw 逐点落盘、跨重启不丢）；
  worker JSON 仅保留用于提供失败原因文本。备份：`_work/backup_partialexport_20260926_111643/`。
- **结果**：`b1_partial_summary.csv` 5 行、`b1_partial_raw.csv` 99 行。

同类缺陷此前也修过 `b1_deliver.py`（清单 `gaps_registered` / `points_missing` 曾漏报为 0），
备份：`_work/backup_deliverfix_20260926_110343/`。**这两个缺陷同源**：
都依赖"worker JSON 的 partial 状态"这个**不跨重启存活**的派生数据。
详见 `06_reference/批量仿真故障总结与经验_20260926.md` 问题 6。

---

## 6 复现信息

| 项 | 值 |
|---|---|
| 求解器 | Ansys Electronics Desktop **2024 R1**（Maxwell 3D，Magnetostatic） |
| 采集脚本 | `contract_launch.py` / `contract_worker.py` + `batch_sweep_lc.py`（`C:\wpt\`） |
| 空气域 | **X ±420 mm**，Y[-134.94, 161]，Z[-45, 75] |
| 路径口径 | `WPT_PATH_MODE=ring` |
| 超时 | 几何 1500 s / 求解 2400 s |
| 网格闸门 | `OPT_MIN_GAP = 1.5 mm`（低于此值整套回退 BASE 口径） |
| 并发 | 8 实例（本机 31.6 GB 内存上限） |
| 结果清理 | `WPT_CLEAN=point`（逐点删场数据） |

**实测性能**（可用于后续批次的工期估算）：
- 单点：均值 **8.18 min**、中位 6.90、p90 13.06
- 单工况（几何 + 21 点）：113.5 ~ 353.8 min，**均值 171.8 min**
- 全批墙钟：**522 min**（8.7 h，最后一轮）

---

## 7 交接注意事项

1. **`05_logs/` 里的 `.log` 是 GBK 编码**（Windows 中文），用 UTF-8 直接读会乱码；
   同目录的 `01_delivery` CSV 与 `03_manifest` JSON 均为 **UTF-8**。
2. **`03_manifest/b1_worker_run*.json` 是各实例最后一次写出的快照**，
   其 `cases[].status` 字段**已被整批重启清空**（本批已知行为）——
   **不要用它判断缺口**，缺口一律以 `01_delivery/b1_partial_summary.csv` 或 raw 反推为准。
3. **`b1_status.py` 的 ETA 数字对本批无效**（它不读例外表，会把已登记缺口仍算作未完成）。
   权威进度看 `01_delivery/b1_manifest.json`。
4. **计划任务仍在运行**（`b1_batch_guard` / `b1_batch_deliver`）。本包是**快照**；
   若原始目录后续被刷新，请以本包内的哈希为准。
