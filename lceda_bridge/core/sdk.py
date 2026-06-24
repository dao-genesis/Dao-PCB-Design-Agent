"""嘉立创EDA Python SDK — 运行时代理.

不做代码生成. 用 __getattr__ 动态拦截任意 `eda.<class>.<method>(args)`,
转发给底层 transport (HTTP / CDP).

用法:
    from core.sdk import EDA
    from core import http_transport, cdp_transport

    # 用 HTTP 桥 (依赖 lceda_bridge_server + 已装扩展)
    eda = EDA(http_transport.HttpTransport())
    print(eda.sys_Environment.getEditorVersion())
    print(eda.dmt_Project.getCurrentProjectInfo())

    # 用 CDP 直连 (无需扩展, 启动 EDA 时加 --remote-debugging-port=9222)
    eda = EDA(cdp_transport.CdpTransport.connect())
    eda.sys_MessageBox.showInformationMessage("Hello from Python", "Title", "OK")

任何符合签名的 transport 都可: callable(path: str, args: list) -> Any
"""
from __future__ import annotations

from typing import Any, Callable, Protocol


class Transport(Protocol):
    def __call__(self, path: str, args: list[Any]) -> Any: ...


class _Caller:
    """中间链节点 — 拼接路径直到被调用 (变成实际 RPC) 或被深入访问."""

    __slots__ = ("_transport", "_path")

    def __init__(self, transport: Transport, path: str):
        self._transport = transport
        self._path = path

    def __getattr__(self, name: str) -> "_Caller":
        if name.startswith("_"):
            raise AttributeError(name)
        return _Caller(self._transport, f"{self._path}.{name}")

    def __call__(self, *args: Any) -> Any:
        return self._transport(self._path, list(args))

    def __repr__(self) -> str:
        return f"<eda.{self._path}>"


class EDA:
    """嘉立创EDA 顶层代理.

    eda.<className>.<methodName>(args...) 会变成 transport(<className>.<methodName>, [args]).
    """

    __slots__ = ("_transport",)

    def __init__(self, transport: Transport):
        self._transport = transport

    def __getattr__(self, name: str) -> _Caller:
        if name.startswith("_"):
            raise AttributeError(name)
        return _Caller(self._transport, name)

    def __repr__(self) -> str:
        return f"<EDA via {type(self._transport).__name__}>"

    # ── 便捷整路径调用 ──
    def call(self, path: str, *args: Any) -> Any:
        return self._transport(path, list(args))

    # ── 上下文 ──
    def __enter__(self) -> "EDA":
        return self

    def __exit__(self, *exc) -> None:
        close = getattr(self._transport, "close", None)
        if callable(close):
            close()
