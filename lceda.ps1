# LCEDA Bridge launcher (PowerShell) - 项目根任意 cwd 可用
# 用法: .\lceda.ps1 <subcmd> [args...]
# 推荐: 设 alias: Set-Alias lceda "$PSScriptRoot\lceda.ps1"
$script = Join-Path $PSScriptRoot "PCB设计\lceda_bridge\lceda_cli.py"
& python $script @args
