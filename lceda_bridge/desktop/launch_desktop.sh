#!/usr/bin/env bash
# launch_desktop.sh — 以纯底层方式启动嘉立创EDA专业版【桌面客户端】(Electron),
# 开启 Chrome 远程调试(CDP),供 Agent 经 _EXTAPI_ROOT_ 官方接口纯 RPC 驱动。
#
# 设计原则(道法自然 · 锚定本源):
#   - 锚点是【桌面软件本体】(Electron 主进程 + 离线核心),不是网页、不是 GUI 点击。
#   - 无头运行(Xvfb 虚拟显示),渲染层照常加载 → window._EXTAPI_ROOT_ 挂载 →
#     用 EDA 自身机制完成 新建工程/放置/布线/DRC/导出,全程零屏幕点击。
#
# 环境变量:
#   LCEDA_HOME   桌面客户端解压根目录(含可执行文件 lceda-pro)。默认自动探测。
#   LCEDA_PORT   远程调试端口。默认 29230(避开网页版常用的 29229)。
#   LCEDA_DISPLAY  Xvfb 显示号。默认 :99。
set -euo pipefail

LCEDA_PORT="${LCEDA_PORT:-29230}"
LCEDA_DISPLAY="${LCEDA_DISPLAY:-:99}"

# --- 探测客户端根目录 ---
detect_home() {
  for d in \
    "${LCEDA_HOME:-}" \
    "/opt/apps/lceda-pro" \
    "$HOME/lceda/extracted/lceda-pro" \
    "$HOME/lceda-pro"; do
    [ -n "$d" ] && [ -x "$d/lceda-pro" ] && { echo "$d"; return 0; }
  done
  return 1
}

HOME_DIR="$(detect_home)" || {
  echo "[launch] 找不到桌面客户端可执行文件 lceda-pro。请设置 LCEDA_HOME 指向解压目录。" >&2
  exit 1
}
echo "[launch] LCEDA_HOME=$HOME_DIR  PORT=$LCEDA_PORT  DISPLAY=$LCEDA_DISPLAY"

# --- 虚拟显示(无头) ---
if ! xdpyinfo -display "$LCEDA_DISPLAY" >/dev/null 2>&1; then
  echo "[launch] 启动 Xvfb $LCEDA_DISPLAY"
  nohup Xvfb "$LCEDA_DISPLAY" -screen 0 1920x1080x24 >/tmp/dao_xvfb.log 2>&1 &
  sleep 2
fi
export DISPLAY="$LCEDA_DISPLAY"

# --- 已在跑则不重复拉起 ---
if curl -fsS -m 3 "http://127.0.0.1:${LCEDA_PORT}/json/version" >/dev/null 2>&1; then
  echo "[launch] 客户端已在运行,CDP :$LCEDA_PORT 可达。"
  exit 0
fi

cd "$HOME_DIR"
echo "[launch] 拉起 Electron 主进程(无沙箱/软件渲染)…"
nohup ./lceda-pro \
  --no-sandbox \
  --remote-debugging-port="${LCEDA_PORT}" \
  --remote-allow-origins=* \
  --disable-gpu --disable-software-rasterizer \
  >/tmp/dao_lceda.log 2>&1 &

# --- 等 CDP 就绪 ---
for i in $(seq 1 30); do
  if curl -fsS -m 3 "http://127.0.0.1:${LCEDA_PORT}/json/version" >/dev/null 2>&1; then
    echo "[launch] OK — CDP :$LCEDA_PORT 就绪。"
    curl -fsS "http://127.0.0.1:${LCEDA_PORT}/json/version" | sed 's/,/,\n  /g'
    exit 0
  fi
  sleep 1
done
echo "[launch] 超时:CDP 未就绪,见 /tmp/dao_lceda.log" >&2
tail -20 /tmp/dao_lceda.log >&2 || true
exit 1
