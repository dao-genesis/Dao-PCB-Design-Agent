"""_live_server — KiCad pcbnew 进程内活体融合内核。

道法自然 · 守一: 不再"每步起一个无头子进程 LoadBoard→改→SaveBoard→退出即忘",
而是常驻在**一个活着的 pcbnew 进程**里, 把 BOARD 握在内存中跨调用长存, 对外开
localhost HTTP JSON-RPC。云端 Agent 一句话即驱动那块活板: 有状态、免重载、
可达全 SWIG 面 (7913 方法) 与 DRC/布线/连通等本源引擎。

两种形态, 同一内核:
  ① 守护形态 (headless daemon, 本 VM 主用): `run_daemon(board, port)` —— 进程内
     LoadBoard 一次, 板常驻内存; HTTP 服务在主进程跑, 全局锁串行化每次操作
     (SWIG 对象非线程安全), 稳、快、深。GetBoard() 无 GUI 故用内存板。
  ② GUI 驻留形态 (depth-2): 被 pcbnew GUI 当 Action Plugin import 时, 服务线程经
     wx.CallAfter 把操作编组到主线程, board=pcbnew.GetBoard() (用户正编辑的活板),
     可达 TOOL_MANAGER/画布。GUI 未初始化脚本子系统时可由 `pcbnew.LoadPlugins()`
     主动触发。

唯一通用原语 `eval`: 在进程内命名空间执行表达式/语句, 回传 JSON —— 一即一切。
安全: 仅绑 127.0.0.1; 设 DAO_LIVE_TOKEN 则校验 Bearer。
反臆造: 所有回传取自真实内存板状态, 转不了 JSON 的给 repr, 不吞真值。
"""
from __future__ import annotations

import json
import os
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pcbnew

try:
    import wx
    _HAS_WX = True
except Exception:                                    # noqa: BLE001
    wx = None                                         # type: ignore
    _HAS_WX = False

HOST = "127.0.0.1"
PORT = int(os.environ.get("DAO_LIVE_PORT", "8137"))
_TOKEN = os.environ.get("DAO_LIVE_TOKEN", "")

# 进程内常驻状态 (跨 RPC 调用保活)
_NS: dict = {}                    # 用户脚本可用的持久命名空间
_BOARD = None                     # 守护形态下常驻内存的板
_LOCK = threading.RLock()         # SWIG 非线程安全 → 串行化所有触板操作
_server_started = threading.Event()
_GUI_MODE = False                 # 由启动路径决定


# ───────────────────────── 主线程编组 (仅 GUI 形态需要) ─────────────────────────
def _run(fn, timeout: float = 300.0):
    """守护形态: 全局锁内直跑。GUI 形态: 编组到 wx 主线程。"""
    if _GUI_MODE and _HAS_WX and not wx.IsMainThread():
        box: dict = {}
        done = threading.Event()

        def _w():
            try:
                box["r"] = fn()
            except BaseException as e:                # noqa: BLE001
                box["e"] = e
                box["tb"] = traceback.format_exc()
            finally:
                done.set()

        wx.CallAfter(_w)
        if not done.wait(timeout):
            raise TimeoutError(f"main-thread op timed out after {timeout}s")
        if "e" in box:
            raise RuntimeError(f"{box['e']}\n{box.get('tb', '')}")
        return box.get("r")
    with _LOCK:
        return fn()


def _live_board():
    """活板: GUI 形态取当前编辑板; 守护形态取常驻内存板。"""
    if _GUI_MODE:
        b = pcbnew.GetBoard()
        if b is not None:
            return b
    return _BOARD


def _find_frame():
    if not _HAS_WX:
        return None
    for w in wx.GetTopLevelWindows():
        if "PCB" in w.__class__.__name__:
            return w
    app = wx.GetApp()
    return app.GetTopWindow() if app else None


def _jsonable(v):
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if hasattr(v, "x") and hasattr(v, "y"):           # VECTOR2I / wxPoint
        try:
            return {"x": int(v.x), "y": int(v.y)}
        except Exception:                             # noqa: BLE001
            pass
    return repr(v)


# ───────────────────────── RPC 操作面 ─────────────────────────
def _op_ping(_a):
    return {"pong": True, "pid": os.getpid(), "gui_mode": _GUI_MODE,
            "has_wx": _HAS_WX, "kicad": pcbnew.GetBuildVersion(),
            "board_loaded": _live_board() is not None}


def _op_open(args):
    """守护形态: 把一块板载入常驻内存 (此后跨调用长存)。"""
    global _BOARD
    path = args["path"]

    def work():
        global _BOARD
        _BOARD = pcbnew.LoadBoard(path)
        _BOARD.BuildConnectivity()
        return {"opened": True, "path": path,
                "footprints": len(list(_BOARD.GetFootprints()))}
    return _run(work)


def _op_board_summary(_a):
    def work():
        b = _live_board()
        if b is None:
            return {"loaded": False}
        tracks = list(b.GetTracks())
        vias = [t for t in tracks if isinstance(t, pcbnew.PCB_VIA)]
        return {"loaded": True, "filename": b.GetFileName(),
                "footprints": len(list(b.GetFootprints())),
                "tracks": len(tracks), "vias": len(vias),
                "nets": b.GetNetCount(), "zones": len(list(b.Zones()))}
    return _run(work)


def _eval_last_expr(code, ns):
    """执行代码并回传值: 单表达式直 eval; 多语句执前段、回传末尾表达式;
    末尾非表达式则回 ns['result'] (若有)。"""
    import ast
    try:
        return eval(code, ns)                         # noqa: S307
    except SyntaxError:
        pass
    tree = ast.parse(code)
    if tree.body and isinstance(tree.body[-1], ast.Expr):
        head = ast.Module(body=tree.body[:-1], type_ignores=[])
        exec(compile(head, "<live>", "exec"), ns)     # noqa: S102
        tail = ast.Expression(tree.body[-1].value)
        return eval(compile(tail, "<live>", "eval"), ns)  # noqa: S307
    exec(code, ns)                                    # noqa: S102
    return ns.get("result")


def _op_eval(args):
    """一即一切: 进程内执行表达式/语句, ns 含 pcbnew/wx/board/frame/state。"""
    code = args.get("code", "")

    def work():
        ns = dict(_NS)
        ns.update({"pcbnew": pcbnew, "wx": wx, "board": _live_board(),
                   "frame": _find_frame(), "state": _NS})
        return _jsonable(_eval_last_expr(code, ns))
    return _run(work, timeout=float(args.get("timeout", 300.0)))


def _op_refresh(_a):
    def work():
        b = _live_board()
        if b is not None:
            b.BuildConnectivity()
        fr = _find_frame()
        if fr is not None and hasattr(fr, "Refresh"):
            fr.Refresh()
        return {"refreshed": True}
    return _run(work)


def _op_save(args):
    path = args.get("path")

    def work():
        b = _live_board()
        if b is None:
            return {"saved": False, "reason": "no board"}
        target = path or b.GetFileName()
        pcbnew.SaveBoard(target, b)
        return {"saved": True, "path": target}
    return _run(work)


_OPS = {"ping": _op_ping, "open": _op_open, "board_summary": _op_board_summary,
        "eval": _op_eval, "refresh": _op_refresh, "save": _op_save}


# ───────────────────────── HTTP 层 ─────────────────────────
class _Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _auth_ok(self):
        return (not _TOKEN) or \
            self.headers.get("Authorization", "") == f"Bearer {_TOKEN}"

    def do_GET(self):                                 # noqa: N802
        if self.path in ("/health", "/ping"):
            self._send(200, {"ok": True, "gui_mode": _GUI_MODE,
                             "ops": sorted(_OPS)})
        else:
            self._send(404, {"ok": False, "error": "GET only /health"})

    def do_POST(self):                                # noqa: N802
        if not self._auth_ok():
            self._send(401, {"ok": False, "error": "unauthorized"})
            return
        try:
            n = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:                        # noqa: BLE001
            self._send(400, {"ok": False, "error": f"bad json: {e}"})
            return
        fn = _OPS.get(payload.get("op"))
        if fn is None:
            self._send(404, {"ok": False, "error": f"unknown op: {payload.get('op')}",
                             "ops": sorted(_OPS)})
            return
        try:
            self._send(200, {"ok": True, "op": payload["op"],
                             "result": fn(payload.get("args", {}))})
        except Exception as e:                        # noqa: BLE001
            self._send(500, {"ok": False, "op": payload.get("op"),
                             "error": str(e), "traceback": traceback.format_exc()})

    def log_message(self, *_a):                       # 静默
        pass


def _make_server() -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((HOST, PORT), _Handler)
    _NS["_httpd"] = httpd
    return httpd


# ───────────────────────── 两种启动入口 ─────────────────────────
def run_daemon(board: str | None = None, port: int | None = None):
    """守护形态入口 (headless): 载板入常驻内存, 主进程跑 HTTP, 阻塞常驻。"""
    global _BOARD, PORT, _GUI_MODE
    _GUI_MODE = False
    if port:
        PORT = port
    if board:
        _BOARD = pcbnew.LoadBoard(board)
        _BOARD.BuildConnectivity()
    httpd = _make_server()
    _server_started.set()
    httpd.serve_forever()


def _start_thread_server() -> bool:
    """GUI 形态: 后台线程跑 HTTP (幂等)。"""
    if _server_started.is_set() or _NS.get("_thread"):
        return False
    t = threading.Thread(target=lambda: (_server_started.set(),
                                         _make_server().serve_forever()),
                         name="dao-live-rpc", daemon=True)
    _NS["_thread"] = t
    t.start()
    return _server_started.wait(timeout=5.0)


# ── GUI Action Plugin 规约: 被 import 即注册 + 拉起常驻服务 (GUI 形态) ──
if _HAS_WX and __name__ != "__main__":
    try:
        class _DaoLivePlugin(pcbnew.ActionPlugin):
            def defaults(self):
                self.name = "DAO Live Fusion Server"
                self.category = "DAO"
                self.description = "进程内活体融合内核 (常驻 RPC)"
                self.show_toolbar_button = False

            def Run(self):
                globals()["_GUI_MODE"] = True
                _start_thread_server()

        _DaoLivePlugin().register()
        _GUI_MODE = True
        _start_thread_server()
    except Exception:                                 # noqa: BLE001
        pass


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=None)
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args()
    run_daemon(board=a.board, port=a.port)
