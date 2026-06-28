"""WsTransport — 经 WebSocket 桥驱动嘉立创EDA 的 transport.

与 http_transport / cdp_transport 同构: callable(path, args) -> Any。
但不同于 HttpTransport (其 fetch 在 EDA 扩展沙箱内被 Mixed-Content 拦截),
本 transport 走 `lceda_ws_bridge` 的 WebSocket 通道 —— 这是扩展沙箱里唯一可用的
本地通道, 故生命周期/文档类 eda.* (createProject 等) 也能在此正常 resolve。

用法:
    from core.sdk import EDA
    from core.ws_transport import WsTransport

    eda = EDA(WsTransport())          # 自动起 WS 桥, 等扩展连上
    print(eda.sys_Environment.getEditorVersion())
    print(eda.dmt_Project.getCurrentProjectInfo())   # L4 会挂, L2 正常返回

前置: 嘉立创EDA 已安装并启用 lceda-bridge 扩展 (勾选「外部交互」权限),
      扩展会自动扫描 9930-9939 端口连接本桥。
"""
from __future__ import annotations

import time
from typing import Any

import lceda_ws_bridge


class WsTransport:
    def __init__(
        self,
        autostart: bool = True,
        wait_connect_s: float = 60.0,
        timeout: float = 30.0,
    ) -> None:
        self.timeout = timeout
        if autostart and lceda_ws_bridge.BRIDGE.port is None:
            lceda_ws_bridge.serve_in_background()
        if wait_connect_s > 0:
            deadline = time.time() + wait_connect_s
            while time.time() < deadline and not lceda_ws_bridge.is_connected():
                time.sleep(0.2)

    @property
    def connected(self) -> bool:
        return lceda_ws_bridge.is_connected()

    def __call__(self, path: str, args: list[Any]) -> Any:
        return lceda_ws_bridge.call(path, *(args or []), timeout=self.timeout)

    def run_code(self, code: str) -> Any:
        return lceda_ws_bridge.run_code(code, timeout=self.timeout)
