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

平台适配: Linux 经 xpra 窗口协议路由 (mode=xpra); Windows/macOS 上用户就在机器前,
KiCad 窗口直接落在本机桌面 (mode=desktop), IPC 直连两平台同法。
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from daokicad import env as kicad_env

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"
DESKTOP_NATIVE = IS_WINDOWS or IS_MAC  # 窗口直落本机桌面, 无需 xpra 路由

DISPLAY = os.environ.get("DAO_XPRA_DISPLAY", ":100")
HTML_PORT = int(os.environ.get("DAO_XPRA_PORT", "9932"))


def _default_api_socket() -> str:
    """KiCad IPC socket 默认路径 (与 kipy._default_socket_path 同源同法)."""
    explicit = os.environ.get("KICAD_API_SOCKET")
    if explicit:
        return explicit.removeprefix("ipc://")
    if IS_WINDOWS:
        return str(Path(tempfile.gettempdir()) / "kicad" / "api.sock")
    return "/tmp/kicad/api.sock"


API_SOCKET = _default_api_socket()

# 最近打开的工程 (.kicad_pro): 模块标签免带路径直达当前工程
_LAST_PROJECT: Path | None = None


def _remember_project(path: str) -> None:
    global _LAST_PROJECT
    if not path:
        return
    p = Path(path)
    pro = p if p.suffix == ".kicad_pro" else p.with_suffix(".kicad_pro")
    if pro.is_file():
        _LAST_PROJECT = pro


def _module_default_path(prog: str) -> str:
    """模块无显式路径时, 复用最近工程的对应文件 (原理图/板图跟随当前工程)."""
    if _LAST_PROJECT is None:
        return ""
    ext = {"eeschema": ".kicad_sch", "pcbnew": ".kicad_pcb",
           "kicad": ".kicad_pro"}.get(prog)
    if not ext:
        return ""
    f = _LAST_PROJECT.with_suffix(ext)
    if f.is_file():
        return str(f)
    stem = _LAST_PROJECT.stem
    sibs = sorted(_LAST_PROJECT.parent.glob(f"*{ext}"),
                  key=lambda s: (not stem.startswith(s.stem), s.name))
    return str(sibs[0]) if sibs else ""


# ── xpra 会话 (窗口协议路由层) ─────────────────────────────────────────


def _xpra() -> str | None:
    return shutil.which("xpra")


def _kicad_bin(prog: str = "kicad") -> str | None:
    """定位 KiCad 可执行 (kicad/eeschema/pcbnew): PATH → 安装根 bin/."""
    found = shutil.which(prog)
    if found:
        return found
    kenv = kicad_env.detect()
    if kenv.root:
        exe = prog + (".exe" if IS_WINDOWS else "")
        for sub in ("bin", ""):
            cand = kenv.root / sub / exe
            if cand.is_file():
                return str(cand)
    return None


def _html_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", HTML_PORT), timeout=1):
            return True
    except OSError:
        return False


def _session_live() -> bool:
    if DESKTOP_NATIVE:
        return bool(_desktop_windows())
    x = _xpra()
    if not x:
        return False
    r = subprocess.run([x, "list"], capture_output=True, text=True, timeout=15)
    return f"LIVE session at {DISPLAY}" in r.stdout


def _kicad_config_root() -> Path:
    """KiCad 用户配置根 (各平台 kicad_common.json 所在)."""
    if IS_WINDOWS:
        return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "kicad"
    if IS_MAC:
        return Path.home() / "Library" / "Preferences" / "kicad"
    return Path.home() / ".config" / "kicad"


def _seed_lib_tables(d: Path) -> None:
    """铺默认全局库表, 免首启 "Configure Global Library Table" 向导挡住自动化."""
    tpl = kicad_env._find_share(kicad_env.detect().root, "template")
    if not tpl:
        return
    for name in ("sym-lib-table", "fp-lib-table", "design-block-lib-table"):
        src, dst = tpl / name, d / name
        if src.is_file() and not dst.exists():
            shutil.copyfile(src, dst)


def _enable_ipc_api() -> None:
    """确保 KiCad 配置开启 IPC API server (kicad_common.json) 且全局库表就位."""
    cfg_dir = _kicad_config_root()
    dirs = sorted(cfg_dir.glob("[0-9]*.[0-9]*"))
    if not dirs:
        v = (kicad_env.detect().version or "9.0").split("-")[0]
        dirs = [cfg_dir / (".".join(v.split(".")[:2]) or "9.0")]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        _seed_lib_tables(d)
        p = d / "kicad_common.json"
        try:
            cfg = json.loads(p.read_text()) if p.is_file() else {}
        except Exception:
            cfg = {}
        api = cfg.setdefault("api", {})
        dns = cfg.setdefault("do_not_show_again", {})
        if not api.get("enable_server") or not dns.get("update_check_prompt"):
            api["enable_server"] = True
            dns["update_check_prompt"] = True  # 免首启更新弹窗遮挡内嵌视图
            p.write_text(json.dumps(cfg, indent=2))


def api_native_status(_q: dict) -> dict:
    live = _session_live()
    return {
        "ok": True,
        "mode": "desktop" if DESKTOP_NATIVE else "xpra",
        "xpra": bool(_xpra()),
        "kicad": bool(_kicad_bin()),
        "live": live,
        "html": _html_up(),
        "display": None if DESKTOP_NATIVE else DISPLAY,
        "port": HTML_PORT,
        "url": None if DESKTOP_NATIVE else f"http://127.0.0.1:{HTML_PORT}/",
        "ipc": bool(_sockets()),
        "ipc_socket": API_SOCKET,
        "windows": _windows() if live else [],
        "modules": MODULES,
    }


_KICAD_EXES = {"kicad", "pcbnew", "eeschema", "kicad-cli"}


def _desktop_windows() -> list[dict]:
    """本机桌面上的 KiCad 顶层窗口 (Windows: EnumWindows, 按属主进程判定)."""
    if not IS_WINDOWS:
        return []
    import ctypes
    import ctypes.wintypes as wt
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    out: list[dict] = []
    proto = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    exe_cache: dict[int, str] = {}

    def _exe(pid: int) -> str:
        if pid not in exe_cache:
            name = ""
            h = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFO
            if h:
                buf = ctypes.create_unicode_buffer(1024)
                size = wt.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = Path(buf.value).stem.lower()
                kernel32.CloseHandle(h)
            exe_cache[pid] = name
        return exe_cache[pid]

    def cb(hwnd, _lp):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if _exe(pid.value) not in _KICAD_EXES:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        out.append({"id": hex(hwnd), "title": buf.value})
        return True

    user32.EnumWindows(proto(cb), 0)
    return out


def _windows() -> list[dict]:
    """列出会话里的 KiCad 真实窗口 (Linux: wmctrl; Windows: EnumWindows)."""
    if DESKTOP_NATIVE:
        return _desktop_windows()
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


# 本体模块注册: 归一面板每个标签直达一个 KiCad 原生编辑器 (符号/封装编辑器
# 无独立可执行, 从工程管理器/原理图/PCB 窗口内直达)
MODULES = {
    "kicad": "工程管理器",
    "eeschema": "原理图编辑器",
    "pcbnew": "PCB 编辑器",
    "gerbview": "Gerber 查看器",
    "pcb_calculator": "计算工具",
    "bitmap2component": "图片转换器",
    "pl_editor": "图框编辑器",
}


def _prog_for(path: str) -> str:
    """按文件后缀选 KiCad 入口: .kicad_sch→eeschema, .kicad_pcb→pcbnew, 其余→kicad."""
    return {"kicad_sch": "eeschema", "kicad_pcb": "pcbnew"}.get(
        Path(path).suffix.lstrip("."), "kicad") if path else "kicad"


def api_native_start(body: dict) -> dict:
    """启动 KiCad 本体 (Linux: xpra 会话路由; Windows/macOS: 直落本机桌面)."""
    if DESKTOP_NATIVE:
        path = (body.get("path") or "").strip()
        _remember_project(path)
        prog = body.get("module") or _prog_for(path)
        k = _kicad_bin(prog) or (_kicad_bin() if prog != "kicad" else None)
        if not k:
            return {"ok": False, "error": "kicad 未安装"}
        _enable_ipc_api()
        args = [k] + ([path] if path else [])
        subprocess.Popen(args, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        for _ in range(20):
            if _desktop_windows():
                break
            time.sleep(0.5)
        return api_native_status({})
    path = (body.get("path") or "").strip()
    _remember_project(path)
    prog = body.get("module") or _prog_for(path)
    x, k = _xpra(), _kicad_bin(prog) or _kicad_bin()
    if not x:
        return {"ok": False, "error": "xpra 未安装 (apt install xpra)"}
    if not k:
        return {"ok": False, "error": "kicad 未安装"}
    _enable_ipc_api()
    child = f'{prog} "{path}"' if path else prog
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
    """在 KiCad 本体里打开文件/工程 (Linux: 面板内出窗; Windows/macOS: 本机桌面出窗)."""
    path = (body.get("path") or "").strip()
    if not DESKTOP_NATIVE:
        x = _xpra()
        if not x or not _session_live():
            return api_native_start(body)
    if not path:
        return {"ok": False, "error": "path required"}
    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": f"no such file: {path}"}
    _remember_project(str(p))
    prog = _prog_for(str(p))
    exe = _kicad_bin(prog) or prog
    if not DESKTOP_NATIVE:
        hit = [w for w in _windows() if p.stem in w["title"]]
        if hit:  # 已开同名窗口: 免重复派生 (KiCad 会弹 File Open Warning)
            return {"ok": True, "opened": path, "via": prog,
                    "already": True, "windows": hit}
    if DESKTOP_NATIVE:
        _enable_ipc_api()
        subprocess.Popen([exe, str(p)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return {"ok": True, "opened": path, "via": prog}
    # 直接在 xpra 显示上派生 (不经 xpra control, 避免非 ASCII 路径被转发层损坏)
    subprocess.Popen([exe, str(p)],
                     env={**os.environ, "DISPLAY": DISPLAY},
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return {"ok": True, "opened": path, "via": prog}


def api_native_module(body: dict) -> dict:
    """拉起指定 KiCad 原生模块 (归一面板标签直达): 会话已活则同显派生, 否则以其为根启会话."""
    prog = (body.get("module") or "kicad").strip()
    if prog not in MODULES:
        return {"ok": False,
                "error": f"unknown module '{prog}' (可选: {', '.join(MODULES)})"}
    path = (body.get("path") or "").strip() or _module_default_path(prog)
    exe = _kicad_bin(prog)
    if not exe:
        return {"ok": False, "error": f"{prog} 未安装"}
    if DESKTOP_NATIVE or not _session_live():
        return api_native_start({"module": prog, "path": path})
    marks = {"eeschema": "Schematic Editor", "pcbnew": "PCB Editor",
             "gerbview": "Gerber Viewer", "pcb_calculator": "Calculator",
             "bitmap2component": "Image Converter", "pl_editor": "Drawing Sheet"}
    mark = marks.get(prog)
    wins = _windows()
    if mark and any(mark in w["title"] for w in wins):
        return {"ok": True, "module": prog, "label": MODULES[prog],
                "already": True, "windows": wins}
    titles = {w["title"] for w in wins}
    subprocess.Popen([exe] + ([path] if path else []),
                     env={**os.environ, "DISPLAY": DISPLAY},
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    for _ in range(20):
        if {w["title"] for w in _windows()} - titles:
            break
        time.sleep(0.5)
    return {"ok": True, "module": prog, "label": MODULES[prog],
            "windows": _windows()}


def api_native_stop(_body: dict) -> dict:
    if DESKTOP_NATIVE:
        return {"ok": False,
                "error": "desktop 模式不代关用户桌面的 KiCad 窗口 (请在本机关闭)"}
    x = _xpra()
    if not x:
        return {"ok": False, "error": "xpra 未安装"}
    r = subprocess.run([x, "stop", DISPLAY], capture_output=True,
                       text=True, timeout=30)
    return {"ok": r.returncode == 0, "out": (r.stdout + r.stderr)[-300:]}


# ── KiCad IPC API (agent 底层直连, 不经 GUI) ───────────────────────────


def _sockets() -> list[str]:
    """全部存活 IPC 端点 (Unix: socket 文件; Windows: 命名管道 — 非文件系统路径)."""
    d = Path(API_SOCKET).parent
    if IS_WINDOWS:
        try:
            names = os.listdir("\\\\.\\pipe\\")
        except OSError:
            return []
        pre = (str(d) + "\\api").lower()
        return [n for n in names
                if n.lower().startswith(pre) and n.lower().endswith(".sock")]
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
    socks = _sockets()
    if not socks:
        return {"ok": False, "error": f"IPC socket 不存在: {API_SOCKET} "
                                      "(先 POST /api/native/start)"}
    err = "no IPC socket"
    for s in socks:
        try:
            k = _kicad_ipc(s)
            k.ping()
            v = k.get_version()
            return {"ok": True, "version": str(v), "socket": s}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    return {"ok": False, "error": err}


def _board_match(b, want: str) -> bool:
    """多实例时按板名定向: want 可为文件名/路径片段, 空则不限."""
    if not want:
        return True
    name = (b.name or "").lower()
    w = Path(want).name.lower()
    return bool(name) and (w in name or name in want.lower())


def api_ipc_board(q: dict) -> dict:
    """活动 PCB 文档全息: 与 GUI 同一份内存文档 (agent 之眼)."""
    want = (q.get("board") or "").strip()
    err = "no IPC socket"
    for sock, k in _each_ipc():
        try:
            b = k.get_board()
            if not _board_match(b, want):
                err = f"no board matching: {want}"
                continue
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


_IPC_OPS = ("action", "save", "refill_zones", "add_track", "add_via",
            "move_footprint")


def _mm(v: float):
    from kipy.util.units import from_mm
    return from_mm(float(v))


def _vec(xy):
    from kipy.geometry import Vector2
    return Vector2.from_xy(_mm(xy[0]), _mm(xy[1]))


def _pt(body: dict, key: str) -> list:
    """取坐标: 支持 key=[x,y] 或散写 x/y 字段; 缺失时报可读错误."""
    if body.get(key) is not None:
        return body[key]
    if key == "at" and body.get("x") is not None and body.get("y") is not None:
        return [body["x"], body["y"]]
    raise ValueError(f"missing '{key}': [x,y] mm")


def _op_add_track(b, body: dict) -> dict:
    """agent 直驱布线: 在活动 board 内存文档里落一段铜线."""
    from kipy.board_types import BoardLayer, Track
    t = Track()
    t.start = _vec(_pt(body, "start"))
    t.end = _vec(_pt(body, "end"))
    t.width = _mm(body.get("width_mm") or 0.25)
    t.layer = getattr(BoardLayer, body.get("layer") or "BL_F_Cu")
    created = b.create_items(t)
    return {"created": len(created), "kind": "track"}


def _op_add_via(b, body: dict) -> dict:
    from kipy.board_types import Via
    v = Via()
    v.position = _vec(_pt(body, "at"))
    v.diameter = _mm(body.get("size_mm") or 0.8)
    v.drill_diameter = _mm(body.get("drill_mm") or 0.4)
    created = b.create_items(v)
    return {"created": len(created), "kind": "via"}


def _op_move_footprint(b, body: dict) -> dict:
    ref = body.get("ref") or ""
    for f in b.get_footprints():
        if f.reference_field.text.value == ref:
            f.position = _vec(_pt(body, "at"))
            if body.get("rot") is not None:
                from kipy.geometry import Angle
                f.orientation = Angle.from_degrees(float(body["rot"]))
            b.update_items(f)
            return {"moved": ref}
    raise ValueError(f"footprint not found: {ref}")


def api_ipc_run(body: dict) -> dict:
    """在 KiCad 本体内执行动作/编辑 — agent 直驱通道 (不经 GUI 表层).

    op: action|save|refill_zones|add_track|add_via|move_footprint
    body.board (可选): 多实例时按板名/路径片段定向目标文档, 避免误落到其它板.
    """
    op = (body.get("op") or "").strip()
    if op not in _IPC_OPS:
        return {"ok": False, "error": f"unknown op: {op} "
                                      f"({'|'.join(_IPC_OPS)})"}
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
            b = k.get_board()
            if not _board_match(b, (body.get("board") or "").strip()):
                err = f"no board matching: {body.get('board')}"
                continue
            if op == "save":
                b.save()
                return {"ok": True, "saved": True, "socket": sock}
            if op == "refill_zones":
                b.refill_zones()
                return {"ok": True, "refilled": True, "socket": sock}
            fn = {"add_track": _op_add_track, "add_via": _op_add_via,
                  "move_footprint": _op_move_footprint}[op]
            return {"ok": True, "socket": sock, **fn(b, body)}
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
    return {"ok": False, "error": err}
