"""KiCad 软件本体承接 — 协议级窗口路由 + IPC 底层直连.

把 KiCad **软件本体**(工程管理器/原理图/PCB 等真实窗口)承接进任意单网页面
(VS Code 插件 webview / 浏览器):

* 窗口路由 (用户面): KiCad 运行在 xpra 无头会话里, xpra 在 X11 **窗口协议层**
  把每个真实窗口(绘制指令流+输入事件流)双向路由到 HTML5 客户端 —— 不是投屏/
  截图轮询, 而是应用窗口本体的协议级转发: 用户在面板里看到、点到、用到的就是
  KiCad 本体的那扇窗, 貌同心同。
* IPC 直连 (agent 面): 同一个 KiCad 进程开启官方 IPC API (kicad-python/kipy,
  UNIX socket protobuf), agent 不经 GUI 直接读写 board/commit/action —— 比用户
  在 GUI 里点更底层、更快、更稳。

GUI 与 IPC 指向**同一进程同一份内存文档**: 用户看到的与 agent 操作的是一体。
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

DISPLAY = os.environ.get("DAO_XPRA_DISPLAY", ":100")
HTML_PORT = int(os.environ.get("DAO_XPRA_PORT", "9932"))
API_SOCKET = os.environ.get("KICAD_API_SOCKET", "/tmp/kicad/api.sock")


# ── xpra 会话 (窗口协议路由层) ─────────────────────────────────────────


def _xpra() -> str | None:
    return shutil.which("xpra")


def _kicad_bin() -> str | None:
    return shutil.which("kicad")


def _html_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", HTML_PORT), timeout=1):
            return True
    except OSError:
        return False


def _session_live() -> bool:
    x = _xpra()
    if not x:
        return False
    r = subprocess.run([x, "list"], capture_output=True, text=True, timeout=15)
    return f"LIVE session at {DISPLAY}" in r.stdout


def _enable_ipc_api() -> None:
    """确保 KiCad 配置开启 IPC API server (kicad_common.json)."""
    cfg_dir = Path.home() / ".config" / "kicad"
    dirs = sorted(cfg_dir.glob("[0-9]*.[0-9]*")) or [cfg_dir / "9.0"]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        p = d / "kicad_common.json"
        try:
            cfg = json.loads(p.read_text()) if p.is_file() else {}
        except Exception:
            cfg = {}
        api = cfg.setdefault("api", {})
        if not api.get("enable_server"):
            api["enable_server"] = True
            p.write_text(json.dumps(cfg, indent=2))


def api_native_status(_q: dict) -> dict:
    live = _session_live()
    return {
        "ok": True,
        "xpra": bool(_xpra()),
        "kicad": bool(_kicad_bin()),
        "live": live,
        "html": _html_up(),
        "display": DISPLAY,
        "port": HTML_PORT,
        "url": f"http://127.0.0.1:{HTML_PORT}/",
        "ipc": Path(API_SOCKET).exists(),
        "ipc_socket": API_SOCKET,
        "windows": _windows() if live else [],
    }


def _windows() -> list[dict]:
    """列出 xpra 会话里的 KiCad 真实窗口 (wmctrl)."""
    wm = shutil.which("wmctrl")
    if not wm:
        return []
    env = {**os.environ, "DISPLAY": DISPLAY}
    r = subprocess.run([wm, "-l"], capture_output=True, text=True,
                       env=env, timeout=10)
    out = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 3)
        if len(parts) == 4:
            out.append({"id": parts[0], "title": parts[3]})
    return out


def api_native_start(body: dict) -> dict:
    """启动/接管 xpra 会话并在其中运行 KiCad 本体 (可带工程文件)."""
    x, k = _xpra(), _kicad_bin()
    if not x:
        return {"ok": False, "error": "xpra 未安装 (apt install xpra)"}
    if not k:
        return {"ok": False, "error": "kicad 未安装"}
    _enable_ipc_api()
    path = (body.get("path") or "").strip()
    child = f"kicad {path}" if path else "kicad"
    if not _session_live():
        cmd = [x, "start", DISPLAY,
               f"--bind-tcp=0.0.0.0:{HTML_PORT}", "--html=on",
               "--daemon=yes", f"--start-child={child}",
               "--exit-with-children=no", "--mdns=no", "--webcam=no",
               "--pulseaudio=no", "--notifications=no", "--system-tray=no"]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            return {"ok": False, "error": (r.stderr or r.stdout)[-500:]}
        for _ in range(40):
            if _html_up():
                break
            time.sleep(0.5)
    elif path:
        api_native_open({"path": path})
    return api_native_status({})


def api_native_open(body: dict) -> dict:
    """在已运行的 KiCad 本体会话里打开文件/工程 (窗口在面板内直接出现)."""
    x = _xpra()
    path = (body.get("path") or "").strip()
    if not x or not _session_live():
        return api_native_start(body)
    if not path:
        return {"ok": False, "error": "path required"}
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": f"no such file: {path}"}
    prog = {"kicad_sch": "eeschema", "kicad_pcb": "pcbnew"}.get(
        p.suffix.lstrip("."), "kicad")
    exe = shutil.which(prog) or prog
    # 直接在 xpra 显示上派生 (不经 xpra control, 避免非 ASCII 路径被转发层损坏)
    subprocess.Popen([exe, str(p)],
                     env={**os.environ, "DISPLAY": DISPLAY},
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return {"ok": True, "opened": path, "via": prog}


def api_native_stop(_body: dict) -> dict:
    x = _xpra()
    if not x:
        return {"ok": False, "error": "xpra 未安装"}
    r = subprocess.run([x, "stop", DISPLAY], capture_output=True,
                       text=True, timeout=30)
    return {"ok": r.returncode == 0, "out": (r.stdout + r.stderr)[-300:]}


# ── KiCad IPC API (agent 底层直连, 不经 GUI) ───────────────────────────


def _sockets() -> list[str]:
    """全部存活 IPC socket (主进程 api.sock + 独立编辑器 api-<pid>.sock)."""
    d = Path(API_SOCKET).parent
    socks = sorted(d.glob("api*.sock"), key=lambda p: p.stat().st_mtime,
                   reverse=True) if d.is_dir() else []
    return [str(p) for p in socks]


def _kicad_ipc(sock: str | None = None):
    from kipy import KiCad  # lazy: 只有装了 kicad-python 才需要
    return KiCad(socket_path=f"ipc://{sock or API_SOCKET}")


def _each_ipc():
    for s in _sockets() or [API_SOCKET]:
        try:
            yield s, _kicad_ipc(s)
        except Exception:
            continue


def api_ipc_status(_q: dict) -> dict:
    if not Path(API_SOCKET).exists():
        return {"ok": False, "error": f"IPC socket 不存在: {API_SOCKET} "
                                      "(先 POST /api/native/start)"}
    try:
        k = _kicad_ipc()
        k.ping()
        v = k.get_version()
        return {"ok": True, "version": str(v), "socket": API_SOCKET}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def api_ipc_board(_q: dict) -> dict:
    """活动 PCB 文档全息: 与 GUI 同一份内存文档 (agent 之眼)."""
    err = "no IPC socket"
    for sock, k in _each_ipc():
        try:
            b = k.get_board()
            nets = b.get_nets()
            fps = b.get_footprints()
            tracks = b.get_tracks()
            vias = b.get_vias()
            return {"ok": True, "name": b.name, "socket": sock,
                    "copper_layers": b.get_copper_layer_count(),
                    "nets": len(nets), "footprints": len(fps),
                    "tracks": len(tracks), "vias": len(vias),
                    "refs": sorted(f.reference_field.text.value
                                   for f in fps)[:200]}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    return {"ok": False, "error": err}


def api_ipc_run(body: dict) -> dict:
    """在 KiCad 本体内执行动作 (run_action) / 保存 — agent 直驱通道."""
    op = (body.get("op") or "").strip()
    if op not in ("action", "save", "refill_zones"):
        return {"ok": False, "error": f"unknown op: {op} "
                                      "(action|save|refill_zones)"}
    err = "no IPC socket"
    for sock, k in _each_ipc():
        try:
            if op == "action":
                name = body.get("name") or ""
                if not name:
                    return {"ok": False, "error": "name required"}
                r = k.run_action(name)
                return {"ok": True, "action": name, "socket": sock,
                        "result": str(r)}
            if op == "save":
                k.get_board().save()
                return {"ok": True, "saved": True, "socket": sock}
            k.get_board().refill_zones()
            return {"ok": True, "refilled": True, "socket": sock}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    return {"ok": False, "error": err}
