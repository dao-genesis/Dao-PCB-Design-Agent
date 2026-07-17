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
$EdaVer = if ($env:EASYEDA_PRO_VER) { $env:EASYEDA_PRO_VER } else { '3.2.149' }
$EdaHome = "C:\Program Files\easyeda-pro"
$EdaExe = "$EdaHome\easyeda-pro.exe"
$EdaCdp = if ($env:DAO_EDA_CDP_PORT) { $env:DAO_EDA_CDP_PORT } else { '9222' }
# 激活文件(用户提供, 不入库): 存在即自动注入激活
$EdaLicense = if ($env:LCEDA_ACTIVATION_FILE) { $env:LCEDA_ACTIVATION_FILE } else { "$env:USERPROFILE\.dao\lceda-pro-activation.txt" }
# 测试/桥打印中文, Windows 控制台默认 cp1252 会 UnicodeEncodeError
$env:PYTHONIOENCODING = 'utf-8'

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

function ProbeCdp {
  try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:$EdaCdp/json/version").StatusCode -eq 200 } catch { $false }
}

if ($Status) {
  Log ("kicad-cli : " + $(if (Test-Path $KicadCli) { & $KicadCli version } else { 'MISSING' }))
  Log ("devin-cli : " + $(if (Test-Path $DevinCli) { 'ok' } else { 'MISSING' }))
  Log ("vsix      : " + $(if (Test-Path $Vsix) { 'ok' } else { 'MISSING' }))
  Log ("kicad 桥 ${KicadPort}: " + $(if (Probe "http://127.0.0.1:$KicadPort/api/health") { 'ok' } else { 'DOWN' }))
  Log ("lceda 桥 ${LcedaPort}: " + $(if (Probe "http://127.0.0.1:$LcedaPort/api/health") { 'ok' } else { 'DOWN' }))
  Log ("easyeda-pro: " + $(if (Test-Path $EdaExe) { 'ok' } else { 'MISSING' }))
  Log ("easyeda cdp ${EdaCdp}: " + $(if (ProbeCdp) { 'ok' } else { 'DOWN' }))
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

  # 4) 嘉立创EDA/EasyEDA Pro 桌面客户端 (Inno 静默装; 国际 CDN 数据中心 IP 可直下, lceda.cn CDN 对数据中心限速)
  if (-not (Test-Path $EdaExe)) {
    $ee = "$Installers\easyeda-pro-windows-x64-$EdaVer.exe"
    if (-not (Test-Path $ee)) {
      Log "downloading easyeda pro $EdaVer..."
      curl.exe -sL -o $ee "https://image.easyeda.com/files/easyeda-pro-windows-x64-$EdaVer.exe"
    }
    Log 'installing easyeda pro (silent)...'
    # Inno Setup: /VERYSILENT /SUPPRESSMSGBOXES 压掉“是否继续”确认框与安装模式选择 (已在 Server 2022 实测)
    Start-Process $ee -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/ALLUSERS', '/NORESTART', '/SP-' -Wait
    if (-not (Test-Path $EdaExe)) { throw 'easyeda pro install failed' }
  }
  Log 'easyeda pro ok'
}

# 4b) 客户端拉起 (CDP 调试口, 供 LCEDA 桥直连; 幂等)
if ((Test-Path $EdaExe) -and -not (ProbeCdp)) {
  Log "starting easyeda pro (cdp :$EdaCdp)..."
  Start-Process $EdaExe -ArgumentList "--remote-debugging-port=$EdaCdp"
  Start-Sleep 10
}
# 4c) 离线激活 (仅当激活文件存在且客户端停在激活页; 全 CDP 后端注入, 零人工)
if ((Test-Path $EdaLicense) -and (ProbeCdp)) {
  $targets = try { (Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 "http://127.0.0.1:$EdaCdp/json").Content } catch { '' }
  if ($targets -match 'entry=regist') {
    Log 'activating easyeda pro (offline license)...'
    & (Resolve-Python) "$Repo\coldstart\activate_lceda.py" $EdaLicense --cdp $EdaCdp
  }
}

# 4) 双桥 (幂等: 健康即跳过; embedded python 需 wrapper 注入 sys.path)
$Py = Resolve-Python
if (-not (Probe "http://127.0.0.1:$KicadPort/api/health")) {
  Log "starting kicad bridge :$KicadPort"
  Start-Process $Py -ArgumentList "$Repo\coldstart\run_kicad_bridge.py" -WindowStyle Hidden
}
if (-not (Probe "http://127.0.0.1:$LcedaPort/api/health")) {
  if (-not $env:DAO_CDP_PORTS) { $env:DAO_CDP_PORTS = "$EdaCdp,29229" }
  if (-not $env:DAO_PREFER_LOCAL_EDA) { $env:DAO_PREFER_LOCAL_EDA = $(if (Test-Path $EdaExe) { '1' } else { '0' }) }
  Log "starting lceda bridge :$LcedaPort (CDP: $env:DAO_CDP_PORTS)"
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
