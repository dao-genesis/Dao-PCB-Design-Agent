#!/usr/bin/env bash
# 冷启动 · 一键幂等 (Linux/Ubuntu · 后端优先, 零 GUI)
# 用法:
#   bash coldstart/up.sh            # 全链路 (产物存在即跳过)
#   bash coldstart/up.sh --status   # 只看现状
#   bash coldstart/up.sh --run-only # 已装机, 仅启双桥+探活
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLERS="$HOME/installers"
DEVIN_HOME="${DEVIN_DESKTOP_HOME:-$HOME/devin-desktop}"
DEVIN_CLI="$DEVIN_HOME/bin/devin-desktop"
VSIX="$REPO/vscode-dao-pcb/dao-pcb.vsix"
KICAD_PORT="${DAO_KICAD_PORT:-9931}"
LCEDA_PORT="${LCEDA_BRIDGE_PORT:-9940}"
EDA_HOME="/opt/apps/easyeda-pro"
EDA_CDP="${DAO_EDA_CDP_PORT:-9222}"
EDA_VER="${EASYEDA_PRO_VER:-3.2.149}"
EDA_ZIP_URL="https://image.easyeda.com/files/easyeda-pro-linux-x64-${EDA_VER}.zip"
# 激活文件(用户提供, 不入库): 存在即自动注入激活
EDA_LICENSE_FILE="${LCEDA_ACTIVATION_FILE:-$HOME/.dao/lceda-pro-activation.txt}"
export DAO_CDP_PORTS="${DAO_CDP_PORTS:-9222,29229}"
export DAO_PREFER_LOCAL_EDA="${DAO_PREFER_LOCAL_EDA:-1}"

log() { echo "[coldstart] $*"; }

probe() { curl -sf -m 5 -H "Authorization: Bearer ${DAO_PCB_TOKEN:-}" "$1" >/dev/null 2>&1; }

if [[ "${1:-}" == "--status" ]]; then
  log "kicad-cli : $(command -v kicad-cli >/dev/null && kicad-cli version || echo MISSING)"
  log "kicad libs: $([[ -d /usr/share/kicad/footprints ]] && echo ok || echo MISSING)"
  log "devin-cli : $([[ -x "$DEVIN_CLI" ]] && echo ok || echo MISSING)"
  log "vsix      : $([[ -f "$VSIX" ]] && echo ok || echo MISSING)"
  log "kicad 桥 $KICAD_PORT: $(probe "http://127.0.0.1:$KICAD_PORT/api/health" && echo ok || echo DOWN)"
  log "lceda 桥 $LCEDA_PORT: $(probe "http://127.0.0.1:$LCEDA_PORT/api/health" && echo ok || echo DOWN)"
  log "easyeda-pro: $([[ -x $EDA_HOME/easyeda-pro ]] && echo ok || echo MISSING)"
  log "easyeda cdp $EDA_CDP: $(curl -sf -m 3 "http://127.0.0.1:$EDA_CDP/json/version" >/dev/null 2>&1 && echo ok || echo DOWN)"
  exit 0
fi

if [[ "${1:-}" != "--run-only" ]]; then
  mkdir -p "$INSTALLERS"

  # 1) KiCad 9 (PPA · 库必须装: --no-install-recommends 会漏掉 footprints/symbols 导致布线为空)
  if ! command -v kicad-cli >/dev/null; then
    log 'installing kicad 9 (ppa)...'
    sudo add-apt-repository -y ppa:kicad/kicad-9.0-releases >/dev/null
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends kicad >/dev/null
  fi
  if [[ ! -d /usr/share/kicad/footprints ]]; then
    log 'installing kicad footprint/symbol libs...'
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y kicad-footprints kicad-symbols >/dev/null
  fi
  log "kicad $(kicad-cli version)"

  # 2) Devin Desktop (Linux tar.gz, 免安装解包)
  if [[ ! -x "$DEVIN_CLI" ]]; then
    tgz="$INSTALLERS/devin-linux.tar.gz"
    if [[ ! -f "$tgz" ]]; then
      log 'downloading devin desktop (linux)...'
      curl -sL 'https://windsurf.com/api/windsurf/download-redirect?build=linux-x64&isNext=false' -o "$tgz"
    fi
    log 'extracting devin desktop...'
    mkdir -p "$DEVIN_HOME"
    tar -xzf "$tgz" -C "$DEVIN_HOME" --strip-components=1
    [[ -x "$DEVIN_CLI" ]] || { echo 'devin desktop extract failed'; exit 1; }
  fi
  log 'devin desktop ok'

  # 3) VSIX 打包 + 装入 (dao.dao-pcb)
  if [[ ! -f "$VSIX" ]]; then
    log 'packaging vsix...'
    (cd "$REPO/vscode-dao-pcb" && npx --yes @vscode/vsce package --no-dependencies --allow-missing-repository -o "$VSIX" >/tmp/vsce.log 2>&1) || true
    [[ -f "$VSIX" ]] || { cat /tmp/vsce.log; exit 1; }
  fi
  if ! "$DEVIN_CLI" --list-extensions 2>/dev/null | grep -q '^dao\.dao-pcb$'; then
    log 'installing vsix...'
    "$DEVIN_CLI" --install-extension "$VSIX" >/dev/null
  fi
  log 'vsix ok (dao.dao-pcb)'

  # 4) 嘉立创EDA/EasyEDA Pro 桌面客户端 (Linux zip · 国际 CDN 数据中心 IP 可直下; lceda.cn CDN 对数据中心限速)
  if [[ ! -x "$EDA_HOME/easyeda-pro" ]]; then
    zipf="$INSTALLERS/easyeda-pro-linux-x64-${EDA_VER}.zip"
    if [[ ! -f "$zipf" ]]; then
      log "downloading easyeda pro ${EDA_VER}..."
      curl -s -o "$zipf" -m 900 "$EDA_ZIP_URL"
    fi
    log 'installing easyeda pro...'
    rm -rf /tmp/easyeda-unpack && mkdir -p /tmp/easyeda-unpack
    unzip -q "$zipf" -d /tmp/easyeda-unpack
    (cd /tmp/easyeda-unpack && sudo bash install.sh >/dev/null)
  fi
  log 'easyeda pro ok'
fi

# 4b) 客户端拉起 (CDP 调试口, 供 LCEDA 桥直连; 幂等)
if [[ -x "$EDA_HOME/easyeda-pro" ]] && ! curl -sf -m 3 "http://127.0.0.1:$EDA_CDP/json/version" >/dev/null 2>&1; then
  log "starting easyeda pro (cdp :$EDA_CDP)..."
  (DISPLAY="${DISPLAY:-:0}" setsid nohup "$EDA_HOME/easyeda-pro" --remote-debugging-port="$EDA_CDP" --no-sandbox >/tmp/easyeda.log 2>&1 < /dev/null &)
  sleep 8
fi
# 4c) 离线激活 (仅当激活文件存在且客户端停在激活页; 全 CDP 后端注入, 零人工)
if [[ -f "$EDA_LICENSE_FILE" ]] && curl -sf -m 3 "http://127.0.0.1:$EDA_CDP/json" 2>/dev/null | grep -q 'entry=regist'; then
  log 'activating easyeda pro (offline license)...'
  python3 "$REPO/coldstart/activate_lceda.py" "$EDA_LICENSE_FILE" --cdp "$EDA_CDP" || log 'activation failed (manual step may be needed)'
fi

# 4) 双桥 (幂等: 健康即跳过; setsid 脱离会话防一次性 shell 退出连带杀桥)
if ! probe "http://127.0.0.1:$KICAD_PORT/api/health"; then
  log "starting kicad bridge :$KICAD_PORT"
  (cd "$REPO" && setsid nohup python3 coldstart/run_kicad_bridge.py >/tmp/kicad_bridge.log 2>&1 < /dev/null &)
fi
if ! probe "http://127.0.0.1:$LCEDA_PORT/api/health"; then
  log "starting lceda bridge :$LCEDA_PORT (CDP: $DAO_CDP_PORTS)"
  (cd "$REPO" && setsid nohup python3 coldstart/run_lceda_bridge.py >/tmp/lceda_bridge.log 2>&1 < /dev/null &)
fi

# 5) 探活 (最长 30s)
for p in "$KICAD_PORT" "$LCEDA_PORT"; do
  ok=DOWN
  for _ in $(seq 15); do
    if probe "http://127.0.0.1:$p/api/health"; then ok=ok; break; fi
    sleep 2
  done
  log "bridge $p: $ok"
done
log 'done · 道法自然'
