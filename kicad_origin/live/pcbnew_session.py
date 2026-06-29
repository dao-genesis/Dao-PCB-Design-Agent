"""
pcbnew_session — 宿主侧常驻 pcbnew 工人管理器 (进程内嫁接的对接面)

把 KiCad-python 内的 pcbnew_worker 当作一个**长驻会话**驱动: 启动一次工人,
之后 load 一块板、多次查询 (stats/footprints/nets/connectivity/bbox) 全部走
同一进程同一张已加载的板 —— 替代"每次操作 spawn 一个新 python 再 LoadBoard"
的固定开销, 这正是用户要的"深层融合/嫁接", 提升效率与稳定性。

"道法自然": KiCad python 不在则 available()=False, 调用方据此优雅降级,
绝不抛异常崩溃。每次调用带挂钟超时 (读取线程 + 队列), 工人卡死不拖垮宿主。
"""
from __future__ import annotations

import json
import subprocess
import threading
import queue
from pathlib import Path
from typing import Any, Dict, Optional

from kicad_origin.origin.env import find_kicad_python

# 与 pcbnew_worker._RPC 一致: 工人响应行的唯一前缀 (隔离 pcbnew C 层 stdout 噪声)
_RPC = "\x01RPC "


def pcbnew_session_available() -> bool:
    """KiCad python 是否可用 (能否起 pcbnew 工人)。"""
    return find_kicad_python() is not None


class PcbnewSession:
    """常驻 pcbnew 工人会话。用作上下文管理器或显式 start()/close()。"""

    def __init__(self, *, default_timeout: float = 150.0) -> None:
        self._proc: Optional[subprocess.Popen] = None
        self._q: "queue.Queue[str]" = queue.Queue()
        self._reader: Optional[threading.Thread] = None
        self._rid = 0
        self.default_timeout = default_timeout
        self.version: Optional[str] = None

    # ── 生命周期 ──────────────────────────────────────────────
    def start(self) -> "PcbnewSession":
        kpy = find_kicad_python()
        if kpy is None:
            raise RuntimeError("KiCad python not found — pcbnew worker "
                               "unavailable")
        worker = str(Path(__file__).resolve().parent / "pcbnew_worker.py")
        self._proc = subprocess.Popen(
            [str(kpy), "-u", worker],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self._reader = threading.Thread(target=self._pump, daemon=True)
        self._reader.start()
        hello = self._read(timeout=30)        # 启动握手
        if not (hello and hello.get("ok")):
            self.close()
            raise RuntimeError("pcbnew worker failed to start")
        self.version = hello.get("result", {}).get("version")
        return self

    def _pump(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            # 只收带 RPC 前缀的行; pcbnew LoadBoard 等吐到 stdout 的噪声丢弃
            idx = line.find(_RPC)
            if idx >= 0:
                self._q.put(line[idx + len(_RPC):].strip())

    def _read(self, timeout: float) -> Optional[Dict[str, Any]]:
        try:
            return json.loads(self._q.get(timeout=timeout))
        except queue.Empty:
            return None

    def call(self, method: str, timeout: Optional[float] = None,
             **params: Any) -> Dict[str, Any]:
        """发一条 RPC 并等结果; 超时则杀工人并报错 (不挂起宿主)。"""
        if self._proc is None or self._proc.poll() is not None:
            raise RuntimeError("pcbnew worker not running")
        self._rid += 1
        rid = self._rid
        req = json.dumps({"id": rid, "method": method, "params": params})
        assert self._proc.stdin
        self._proc.stdin.write(req + "\n")
        self._proc.stdin.flush()
        resp = self._read(timeout=timeout or self.default_timeout)
        if resp is None:
            self.kill()
            raise TimeoutError("pcbnew worker '%s' 超时 (>%ss), 已杀进程"
                               % (method, timeout or self.default_timeout))
        if not resp.get("ok"):
            raise RuntimeError("pcbnew worker '%s' 失败: %s"
                               % (method, resp.get("error")))
        return resp.get("result", {})

    # ── 便捷封装 (薄壳) ───────────────────────────────────────
    def ping(self) -> Dict[str, Any]:
        return self.call("ping", timeout=10)

    def load(self, path: str, timeout: Optional[float] = None) -> Dict[str, Any]:
        return self.call("load", timeout=timeout, path=path)

    def stats(self) -> Dict[str, Any]:
        return self.call("stats")

    def bbox(self) -> Dict[str, Any]:
        return self.call("bbox")

    def footprints(self) -> Dict[str, Any]:
        return self.call("footprints")

    def nets(self) -> Dict[str, Any]:
        return self.call("nets")

    def connectivity(self) -> Dict[str, Any]:
        return self.call("connectivity")

    def save(self, path: str) -> Dict[str, Any]:
        return self.call("save", path=path)

    def symbol_methods(self, symbol: str) -> Dict[str, Any]:
        return self.call("eval", symbol=symbol, timeout=10)

    # ── 收尾 ──────────────────────────────────────────────────
    def kill(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.stdin.write(
                    json.dumps({"id": -1, "method": "shutdown"}) + "\n")
                self._proc.stdin.flush()
                self._proc.wait(timeout=5)
            except Exception:
                self.kill()
        self._proc = None

    def __enter__(self) -> "PcbnewSession":
        return self.start()

    def __exit__(self, *exc: Any) -> None:
        self.close()
