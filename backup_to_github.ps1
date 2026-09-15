# backup_to_github.ps1 — WPT 数据每小时备份到 GitHub
# 由 Windows 计划任务 "WPT-GitHub-每小时备份" 每小时调用一次。
#
# 设计原则：
#   1. 冻结仓库原件 Projecttonight.aedt —— 本机永远不提交它，保证仓库里那份校验过的
#      模型始终是 25155997 字节 / md5 9bb98917...（部署文档硬约束）
#      本机的工程改动走 Projecttonightxu.aedt，它会正常备份到 GitHub
#   2. 无人值守安全 —— 禁止一切交互式提示；缺凭据/断网时快速失败，不挂起、不弹窗
#   3. 先 rebase 再 push —— 若旧机器仍在推送造成分叉，自动重放本地提交；冲突立即 abort
#   4. 完全幂等 —— 无变更时不产生空提交

$ErrorActionPreference = 'Continue'

$Repo        = 'C:\wpt'
$Log         = Join-Path $Repo 'backup_to_github.log'
$MaxLogBytes = 512KB

# 无人值守：缺凭据就快速失败，绝不等待人工输入（凭据由 Windows 凭据管理器提供）
$env:GIT_TERMINAL_PROMPT = '0'
$env:GCM_INTERACTIVE     = 'never'

function Write-Log([string]$msg) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Output $line
    try { Add-Content -LiteralPath $Log -Value $line -Encoding UTF8 } catch { }
}

# 日志轮转，避免无限增长
try {
    if ((Test-Path -LiteralPath $Log) -and (Get-Item -LiteralPath $Log).Length -gt $MaxLogBytes) {
        Move-Item -LiteralPath $Log -Destination "$Log.1" -Force
    }
} catch { }

if (-not (Test-Path -LiteralPath (Join-Path $Repo '.git'))) {
    Write-Log "错误：$Repo 不是 git 仓库，退出"
    exit 1
}

Set-Location -LiteralPath $Repo

# ---------- 1. 暂存全部改动，唯独把仓库原件 Projecttonight.aedt 撤下 ----------
# 本机的工作工程是 Projecttonightxu.aedt，它必须被备份；
# 仓库原件 Projecttonight.aedt 必须保持字节不变，所以只冻结这一个精确路径
# （精确路径不会误伤 Projecttonightxu.aedt）。
git add -A 2>&1 | Out-Null
git reset -q -- 'Projecttonight.aedt' 2>&1 | Out-Null

# ---------- 2. 没有任何可提交内容就退出 ----------
git diff --cached --quiet
if ($LASTEXITCODE -eq 0) {
    Write-Log '无变更，跳过'
    exit 0
}

# ---------- 3. 提交 ----------
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm'
git commit -q -m "每小时数据备份 $stamp" 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log "提交失败 (exit=$LASTEXITCODE)"
    exit 2
}
Write-Log ('已提交 ' + (git rev-parse --short HEAD))

# ---------- 4. 同步远程 ----------
git fetch -q origin 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log "fetch 失败（断网或凭据失效，exit=$LASTEXITCODE）；本地提交已保留，下轮重试"
    exit 3
}

git rebase -q origin/master 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    git rebase --abort 2>&1 | Out-Null
    Write-Log 'rebase 出现冲突，已 abort；本地提交完好，需人工处理'
    exit 4
}

# ---------- 5. 推送 ----------
git push -q origin master 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Log "push 失败 (exit=$LASTEXITCODE)；本地提交已保留，下轮重试"
    exit 5
}
Write-Log '推送成功'

# ---------- 6. 大文件护栏：GitHub 单文件硬上限 100MB ----------
# 用 git 对象库取大小（git ls-tree -r -l），不访问文件系统 ——
# 避免 git 对非 ASCII 文件名输出的 "4 - \345\211\257..." 转义形式把 Test-Path 打挂。
try {
    $limit = 95MB
    foreach ($line in (git ls-tree -r -l HEAD)) {
        $parts = $line -split "`t", 2
        if ($parts.Count -lt 2) { continue }
        $meta = @(($parts[0] -split '\s+') | Where-Object { $_ -ne '' })
        if ($meta.Count -lt 4) { continue }
        $size = [int64]0
        if ([int64]::TryParse($meta[3], [ref]$size) -and $size -gt $limit) {
            Write-Log ('警告：已跟踪文件接近 GitHub 100MB 上限 -> ' + $parts[1])
        }
    }
} catch { }

exit 0
