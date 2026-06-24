# 看当前 lceda-pro 进程之命令行参数 (区分 main vs render/gpu 子进程)
Get-CimInstance Win32_Process -Filter "Name = 'lceda-pro.exe'" |
    Select-Object ProcessId, ParentProcessId, @{
        Name='Cmd'
        Expression = { $_.CommandLine.Substring(0, [Math]::Min(220, $_.CommandLine.Length)) }
    } |
    Format-Table -AutoSize -Wrap

Write-Host "`n--- TCP :9222 ---"
$tcp = Get-NetTCPConnection -LocalPort 9222 -ErrorAction SilentlyContinue
if ($tcp) {
    $tcp | Format-Table -AutoSize
} else {
    Write-Host "  (端口未监听)"
}
