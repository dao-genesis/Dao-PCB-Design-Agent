"""native_live — 进程内活体融合内核的 Agent 侧门面 (对等操作活着的 KiCad)。

道法自然 · 守一: 这是"母"。它
  1. 把 `_live_server.py` 安插进 KiCad 用户 Action Plugin 目录 (GUI 启动即常驻);
  2. 起 pcbnew GUI (可无头 Xvfb) 并按需打开一块板;
  3. 经 localhost HTTP JSON-RPC 连上进程内内核, 驱动那个**活着的编辑器**;
  4. 用完优雅收场。

与旧 `native_*` 无头子进程之别: 那是无状态、每步重载; 这是**有状态、免重载、
握活板、能调用户点得到与点不到的一切**。旧 40 原语可渐次改打给此活内核。

反臆造: 所有断言取自活内核回传的真实活板状态, 非本地臆测。
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from kicad_origin.origin.env import find_kicad_python

HERE = Path(__file__).resolve().parent
SERVER_SRC = HERE / "_live_server.py"


def _user_plugin_dir() -> Path:
    """KiCad 9 GUI 形态的 Action Plugin 目录 (仅 depth-2 GUI 驻留用)。

    经真 GUI (KiCad 9.0.9 / Ubuntu) 实测, pcbnew 扫描并加载的是
    <documents>/scripting/plugins 即 ~/.local/share/kicad/9.0/scripting/plugins;
    <config>/plugins 不被扫描。
    """
    env = os.environ.get("KICAD_USER_PLUGIN_DIR")
    if env:
        return Path(env)
    return Path.home() / ".local" / "share" / "kicad" / "9.0" / "scripting" / "plugins"


def install_plugin(plugin_dir: Optional[Path] = None) -> Path:
    """把进程内内核安插进 GUI 插件目录 (幂等覆盖), 返回落地路径。"""
    dst_dir = Path(plugin_dir) if plugin_dir else _user_plugin_dir()
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / "dao_live_server.py"
    shutil.copyfile(SERVER_SRC, dst)
    return dst


@dataclass
class LiveSession:
    """一次活体会话: 起常驻 pcbnew 进程 (内核) + 连 + 驱动活板 + 收场。

    默认 daemon 形态 (headless, 稳): 起一个常驻 python 进程 import pcbnew,
    把板载入内存长存, 全 SWIG 面可达。gui=True 则改起 pcbnew GUI 驻留 (depth-2)。
    """
    board: Optional[str] = None
    port: int = 8137
    token: str = ""
    gui: bool = False
    headless: bool = True
    pcbnew_bin: str = "pcbnew"
    _proc: Optional[subprocess.Popen] = field(default=None, repr=False)
    _base: str = field(default="", repr=False)

    # ── 生命周期 ──
    def start(self, ready_timeout: float = 90.0) -> "LiveSession":
        self._base = f"http://127.0.0.1:{self.port}"
        env = dict(os.environ)
        env["DAO_LIVE_PORT"] = str(self.port)
        if self.token:
            env["DAO_LIVE_TOKEN"] = self.token
        env.setdefault("HOME", str(Path.home()))

        if self.gui:
            install_plugin()
            cmd: List[str] = (["xvfb-run", "-a"] if self.headless else [])
            cmd += [self.pcbnew_bin]
            if self.board:
                cmd += [str(self.board)]
        else:
            kpy = find_kicad_python() or "python3"
            cmd = [str(kpy), str(SERVER_SRC), "--port", str(self.port)]
            if self.board:
                cmd += ["--board", str(self.board)]

        self._proc = subprocess.Popen(
            cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None)
        self._wait_ready(ready_timeout)
        return self

    def _wait_ready(self, timeout: float):
        deadline = time.time() + timeout
        last = None
        while time.time() < deadline:
            if self._proc and self._proc.poll() is not None:
                raise RuntimeError(
                    f"pcbnew exited early (code {self._proc.returncode})")
            try:
                with urllib.request.urlopen(self._base + "/health", timeout=3) as r:
                    if r.status == 200:
                        return
            except Exception as e:                   # noqa: BLE001
                last = e
            time.sleep(1.0)
        raise TimeoutError(f"live kernel not ready in {timeout}s (last: {last})")

    def close(self):
        if self._proc and self._proc.poll() is None:
            try:
                if hasattr(os, "killpg"):
                    os.killpg(os.getpgid(self._proc.pid), signal.SIGTERM)
                else:
                    self._proc.terminate()
                self._proc.wait(timeout=15)
            except Exception:                        # noqa: BLE001
                try:
                    self._proc.kill()
                except Exception:                    # noqa: BLE001
                    pass

    def __enter__(self):
        return self.start()

    def __exit__(self, *_exc):
        self.close()

    # ── RPC ──
    def rpc(self, op: str, timeout: float = 130.0, **args) -> Dict[str, Any]:
        body = json.dumps({"op": op, "args": args}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(self._base + "/rpc", data=body,
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return json.loads(e.read())

    def ping(self) -> Dict[str, Any]:
        return self.rpc("ping")

    def summary(self) -> Dict[str, Any]:
        return self.rpc("board_summary")

    def eval(self, code: str, timeout: float = 130.0) -> Any:
        r = self.rpc("eval", timeout=timeout, code=code, timeout_inner=timeout)
        if not r.get("ok"):
            raise RuntimeError(f"live eval failed: {r.get('error')}\n"
                               f"{r.get('traceback', '')}")
        return r.get("result")

    def refresh(self) -> Dict[str, Any]:
        return self.rpc("refresh")

    def save(self, path: Optional[str] = None) -> Dict[str, Any]:
        return self.rpc("save", path=path)
