# 模型快照索引

每个 `*.aedt.zip` 是一个 `Projecttonight.aedt` 的完整快照（zip 内文件名固定为
`Projecttonight.aedt`），解压后直接就是可用的 Maxwell 工程。
压缩率约 10%（原始 .aedt 是文本格式），所以放仓库里比直接提交原始大文件省得多。

| 快照 | 日期 | 内容 | 原始大小 | md5 |
|---|---|---|---|---|
| `Projecttonight_20260916_width2mm.aedt.zip` | 2026-09-16 | 线圈线宽 3mm → **2mm**（Tx1/Tx2/Rx），线厚 0.5mm 不变；批次脚本 `COIL_SIZE` 同步为 167.90 | 74656731 bytes | `C722B2F062BE575C92FBB02E820A955F` |

## 恢复方法

```powershell
Expand-Archive Projecttonight_20260916_width2mm.aedt.zip -DestinationPath C:\wpt -Force
```

注意：解压前先关掉 AEDT，并确认没有 `Projecttonight.aedt.lock`。

## 相关说明

- 改造报告见 `reports/线圈线宽2mm改造报告_20260916.md`
- 同一点的 2mm / 3mm A/B 电感数据见 `results/solve_width2.csv`、`results/solve_width3.csv`
- 线圈原始路径（768 点 × 3）见 `model_snapshots/coil_paths_20260916.json`
- 这个模型**不含**求解结果（`.aedtresults` 未打包）
