# 冷启动 · 一键幂等 (Windows · 后端优先, 零 GUI)
# 用法:
#   powershell -ExecutionPolicy Bypass -File coldstart\up.ps1            # 全链路 (产物存在即跳过)
#   powershell -ExecutionPolicy Bypass -File coldstart\up.ps1 -Status    # 只看现状
#   powershell -ExecutionPolicy Bypass -File coldstart\up.ps1 -RunOnly   # 已装机, 仅启双桥+探活
param([switch]$Status, [switch]$RunOnly)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $PSScriptRoot
$Installers = "$env:USERPROFILE\installers"
$KicadCli = "C:\Program Files\KiCad\9.0\bin\kicad-cli.exe"
$DevinCli = "$env:LOCALAPPDATA\Programs\Devin\bin\devin-desktop.cmd"
$Vsix = "$Repo\vscode-dao-pcb\dao-pcb.vsix"
$KicadPort = if ($env:DAO_KICAD_PORT) { $env:DAO_KICAD_PORT } else { '9931' }
$LcedaPort = if ($env:LCEDA_BRIDGE_PORT) { $env:LCEDA_BRIDGE_PORT } else { '9940' }

function Log($m) { Write-Host "[coldstart] $m" }

function Resolve-Python {
  foreach ($p in @('C:\devin\python\python.exe', 'C:\Program Files\Python312\python.exe', 'C:\Program Files\Python313\python.exe')) {
    if (Test-Path $p) { return $p }
  }
  $c = Get-Command python -ErrorAction SilentlyContinue
  if ($c -and $c.Source -notmatch 'WindowsApps') { return $c.Source }
  throw 'python not found'
}

function Probe($url) {
  try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 -Headers @{Authorization = "Bearer $env:DAO_PCB_TOKEN"} $url).StatusCode -eq 200 } catch { $false }
}

if ($Status) {
  Log ("kicad-cli : " + $(if (Test-Path $KicadCli) { & $KicadCli version } else { 'MISSING' }))
  Log ("devin-cli : " + $(if (Test-Path $DevinCli) { 'ok' } else { 'MISSING' }))
  Log ("vsix      : " + $(if (Test-Path $Vsix) { 'ok' } else { 'MISSING' }))
  Log ("kicad 桥 ${KicadPort}: " + $(if (Probe "http://127.0.0.1:$KicadPort/api/health") { 'ok' } else { 'DOWN' }))
  Log ("lceda 桥 ${LcedaPort}: " + $(if (Probe "http://127.0.0.1:$LcedaPort/api/health") { 'ok' } else { 'DOWN' }))
  exit 0
}

if (-not $RunOnly) {
  New-Item -ItemType Directory -Force $Installers | Out-Null

  # 1) KiCad (NSIS /S 静默, 已验证; 目标 C:\Program Files\KiCad\9.0)
  if (-not (Test-Path $KicadCli)) {
    $kc = "$Installers\kicad-9.0.9.exe"
    if (-not (Test-Path $kc)) {
      Log 'downloading kicad...'
      curl.exe -L -o $kc 'https://github.com/KiCad/kicad-source-mirror/releases/download/9.0.9/kicad-9.0.9-x86_64.exe'
    }
    Log 'installing kicad (silent)...'
    Start-Process $kc -ArgumentList '/S', '/allusers' -Wait
    if (-not (Test-Path $KicadCli)) { throw 'kicad install failed' }
  }
  Log ("kicad " + (& $KicadCli version))

  # 2) Devin Desktop (Inno 用户级静默装)
  if (-not (Test-Path $DevinCli)) {
    $di = "$Installers\DevinUserSetup.exe"
    if (-not (Test-Path $di)) {
      Log 'downloading devin desktop...'
      curl.exe -L -o $di 'https://windsurf.com/api/windsurf/download-redirect?build=win32-x64-user&isNext=false'
    }
    Log 'installing devin desktop (silent)...'
    Start-Process $di -ArgumentList '/VERYSILENT', '/NORESTART', '/MERGETASKS=!runcode,addtopath' -Wait
    if (-not (Test-Path $DevinCli)) { throw 'devin desktop install failed' }
  }
  Log 'devin desktop ok'

  # 3) VSIX 打包 + 装入 (dao.dao-pcb)
  if (-not (Test-Path $Vsix)) {
    Log 'packaging vsix...'
    Push-Location "$Repo\vscode-dao-pcb"
    # vsce 在非交互 stdout 下会 EPIPE, 重定向到日志并以产物存在为准
    cmd /c "npx --yes @vscode/vsce package --no-dependencies --allow-missing-repository -o `"$Vsix`" > `"$env:TEMP\vsce.log`" 2>&1"
    Pop-Location
    if (-not (Test-Path $Vsix)) { Get-Content "$env:TEMP\vsce.log"; throw 'vsix package failed' }
  }
  $installed = & $DevinCli --list-extensions 2>$null
  if ($installed -notcontains 'dao.dao-pcb') {
    Log 'installing vsix...'
    & $DevinCli --install-extension $Vsix
  }
  Log 'vsix ok (dao.dao-pcb)'
}

# 4) 双桥 (幂等: 健康即跳过; embedded python 需 wrapper 注入 sys.path)
$Py = Resolve-Python
if (-not (Probe "http://127.0.0.1:$KicadPort/api/health")) {
  Log "starting kicad bridge :$KicadPort"
  Start-Process $Py -ArgumentList "$Repo\coldstart\run_kicad_bridge.py" -WindowStyle Hidden
}
if (-not (Probe "http://127.0.0.1:$LcedaPort/api/health")) {
  Log "starting lceda bridge :$LcedaPort (CDP: $(if ($env:DAO_CDP_PORTS) { $env:DAO_CDP_PORTS } else { '29229' }))"
  if (-not $env:DAO_CDP_PORTS) { $env:DAO_CDP_PORTS = '29229' }
  if (-not $env:DAO_PREFER_LOCAL_EDA) { $env:DAO_PREFER_LOCAL_EDA = '0' }
  Start-Process $Py -ArgumentList "$Repo\coldstart\run_lceda_bridge.py" -WindowStyle Hidden
}

# 5) 探活 (最长 30s)
foreach ($p in @($KicadPort, $LcedaPort)) {
  $ok = $false
  for ($i = 0; $i -lt 15; $i++) {
    if (Probe "http://127.0.0.1:$p/api/health") { $ok = $true; break }
    Start-Sleep 2
  }
  Log ("bridge ${p}: " + $(if ($ok) { 'ok' } else { 'DOWN (查 wrapper 输出)' }))
}
Log 'done · 道法自然'
