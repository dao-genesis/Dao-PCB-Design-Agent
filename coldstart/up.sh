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
export DAO_CDP_PORTS="${DAO_CDP_PORTS:-29229}"
export DAO_PREFER_LOCAL_EDA="${DAO_PREFER_LOCAL_EDA:-0}"

log() { echo "[coldstart] $*"; }

probe() { curl -sf -m 5 -H "Authorization: Bearer ${DAO_PCB_TOKEN:-}" "$1" >/dev/null 2>&1; }

if [[ "${1:-}" == "--status" ]]; then
  log "kicad-cli : $(command -v kicad-cli >/dev/null && kicad-cli version || echo MISSING)"
  log "kicad libs: $([[ -d /usr/share/kicad/footprints ]] && echo ok || echo MISSING)"
  log "devin-cli : $([[ -x "$DEVIN_CLI" ]] && echo ok || echo MISSING)"
  log "vsix      : $([[ -f "$VSIX" ]] && echo ok || echo MISSING)"
  log "kicad 桥 $KICAD_PORT: $(probe "http://127.0.0.1:$KICAD_PORT/api/health" && echo ok || echo DOWN)"
  log "lceda 桥 $LCEDA_PORT: $(probe "http://127.0.0.1:$LCEDA_PORT/api/health" && echo ok || echo DOWN)"
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
