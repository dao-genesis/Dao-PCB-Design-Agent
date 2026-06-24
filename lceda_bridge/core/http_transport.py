"""HTTP 桥 transport — 走已有的 lceda_bridge_server :9907.

需先启动: python lceda_bridge_server.py
并在嘉立创内: 顶部菜单 LCEDA Bridge → 启动桥接
"""
from __future__ import annotations

import json
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


class HttpTransport:
    def __init__(self, server: str = "http://127.0.0.1:9907", timeout: float = 30.0):
        self.server = server.rstrip("/")
        self.timeout = timeout

    def __call__(self, path: str, args: list[Any]) -> Any:
        body = json.dumps(
            {"path": path, "args": args, "timeout": self.timeout}
        ).encode("utf-8")
        req = Request(
            f"{self.server}/call",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=self.timeout + 5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("error"):
            raise RuntimeError(f"嘉立创端报错: {payload['error']}")
        return payload.get("result")

    def ping(self) -> bool:
        try:
            with urlopen(f"{self.server}/ping", timeout=2) as resp:
                return resp.status == 200
        except URLError:
            return False
