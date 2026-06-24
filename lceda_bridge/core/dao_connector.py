"""道直连器 (DaoConnector) — 一键自驾打通全链路.

道法自然: 自动定位 → 自动启动 → 自动握手 → 自动持守.
任意 agent / 任意用户 / 任意电脑, 一行可达 EDA 之内.

工作流:
    1. locate()           env_finder 跨机扫描
    2. ensure_eda()       lceda-pro 未运行则启动 (--remote-debugging-port)
    3. ensure_bridge()    lceda_bridge_server :9907 未运行则启动 (子进程)
    4. connect()          BusTransport 注入 + diagnose
    5. (持守, 可被 with-context 自动释放)

用法:
    from core.dao_connector import DaoConnector

    # 最简 — 一行到 eda
    with DaoConnector().auto() as dao:
        info = dao.eda.dmt_Project.getCurrentProjectInfo()
        ver = dao.eda.sys_Environment.getEditorVersion()

    # 显式分步 (用于诊断)
    dao = DaoConnector()
    env = dao.locate()                  # 跨机定位
    proc = dao.ensure_eda(spawn=True)   # 启动 EDA
    dao.ensure_bridge(spawn=True)       # 启动桥
    dao.connect(mode="bus")             # 走 CDP+总线
    print(dao.diagnose())

mode 选项:
    "bus"  ── BusTransport (CDP+_MSG_BUS2_EXTAPI_, 推荐) ★
    "http" ── HttpTransport (走 :9907, 需扩展已装并启动桥接)
    "cdp"  ── CdpTransport (主 page Runtime.evaluate, eda 不可见)
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.error import URLError
from urllib.request import urlopen

from . import env_finder
from .cdp_transport import (
    BusTransport,
    CdpTransport,
    LaunchedEDA,
    cdp_available,
    cdp_diagnose,
    cdp_tcp_listening,
    launch_eda_with_cdp,
    list_targets,
    list_targets_via_browser_ws,
)
from .http_transport import HttpTransport
from .sdk import EDA

# UI 层 (反者道之动): 延迟 import, 避免忪依赖
if False:  # TYPE_CHECKING
    from .ui_director import UIDirector
    from .narrator import Narrator
    from .observer import EdaObserver


# ──────────────────────────────────────────────────────────
# 默认配置
# ──────────────────────────────────────────────────────────
DEFAULT_CDP_PORT = 9222
DEFAULT_BRIDGE_PORT = 9907
DEFAULT_FRAME_IDX = 1


@dataclass
class DaoState:
    """道直连器状态快照."""
    located: bool = False
    eda_running: bool = False
    eda_spawned_by_us: bool = False
    eda_proc: Optional[subprocess.Popen] = None
    eda_launched: Optional[LaunchedEDA] = None   # ★ v4.0.2 含 browser_ws_url
    browser_ws_url: Optional[str] = None          # ★ v4.0.2 ws-only 入口 (lceda-pro 屏 HTTP)
    bridge_running: bool = False
    bridge_spawned_by_us: bool = False
    bridge_proc: Optional[subprocess.Popen] = None
    connected: bool = False
    transport_mode: Optional[str] = None  # "bus" | "http" | "cdp"
    cdp_port: int = DEFAULT_CDP_PORT
    bridge_port: int = DEFAULT_BRIDGE_PORT
    frame_idx: int = DEFAULT_FRAME_IDX
    sandbox_diagnose: Optional[dict] = None
    timeline: list[dict] = field(default_factory=list)  # 各步骤事件

    def event(self, kind: str, **data) -> None:
        self.timeline.append({"ts": time.time(), "kind": kind, **data})


# ──────────────────────────────────────────────────────────
# 工具
# ──────────────────────────────────────────────────────────
def _port_listening(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ping(url: str, timeout: float = 2.0) -> bool:
    try:
        with urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 400
    except (URLError, OSError, TimeoutError):
        return False


# ──────────────────────────────────────────────────────────
# 道直连器
# ──────────────────────────────────────────────────────────
class DaoConnector:
    """嘉立创EDA 全链路自驾连接器."""

    def __init__(
        self,
        cdp_port: int = DEFAULT_CDP_PORT,
        bridge_port: int = DEFAULT_BRIDGE_PORT,
        frame_idx: int = DEFAULT_FRAME_IDX,
        on_event: Optional[Callable[[str, dict], None]] = None,
        user_visible: bool = True,  # ★ 五感可观开关 (默认开)
    ):
        self.state = DaoState(
            cdp_port=cdp_port,
            bridge_port=bridge_port,
            frame_idx=frame_idx,
        )
        self.env: Optional[env_finder.EnvLocations] = None
        self.transport: Optional[Any] = None
        self.eda: Optional[EDA] = None
        self.on_event = on_event
        self.user_visible = user_visible
        # 道之辅佐 (auto() 中延迟创建, 需 BusTransport)
        self.ui_director: Optional[Any] = None     # UIDirector
        self.narrator: Optional[Any] = None        # Narrator
        self.observer: Optional[Any] = None        # EdaObserver
        # ★ 反者道之动 — 道流 (六柱合一, agent-native)
        self.flow: Optional[Any] = None            # DaoFlow
        self._closed = False

    # ── 事件 ───────────────────────────────────────────
    def _emit(self, kind: str, **data) -> None:
        self.state.event(kind, **data)
        if self.on_event:
            try:
                self.on_event(kind, data)
            except Exception:
                pass

    # ── 1. 定位 ───────────────────────────────────────
    def locate(self, force_refresh: bool = False) -> env_finder.EnvLocations:
        self.env = env_finder.force_refresh() if force_refresh else env_finder.discover()
        self.state.located = self.env.is_complete()
        self._emit("located", complete=self.state.located, missing=self.env.missing())
        return self.env

    # ── 2. EDA 进程 ────────────────────────────────────
    def is_eda_running(self) -> bool:
        """EDA 已开 CDP? — v4.0.2 改用 TCP 探测 (lceda-pro 屏 HTTP /json/version)."""
        return cdp_tcp_listening(self.state.cdp_port)

    def ensure_eda(
        self,
        spawn: bool = True,
        wait_seconds: float = 60.0,
        extra_args: Optional[list[str]] = None,
        isolated_user_data: bool = False,
    ) -> Optional[LaunchedEDA]:
        """确保 EDA 已运行且开启 CDP.

        ★ v4.0.2 用户无为无感:
          - 不管已运行 / 我们启, 均返 LaunchedEDA (we_started_it 区分).
          - 启时加 --no-proxy-server (绕 clash/v2ray) + 捕 stderr 拿 browser_ws_url.
          - 已运行时尝试 HTTP /json/version 拿 ws URL; 拿不到则 browser_ws_url=None
            (此时只能通过 HTTP 路径, 但 lceda-pro 已屏; 建议 kill+restart 让我们抓 stderr).

        ★ 兵无常势 v4.0.3:
          extra_args:         附加命令行 (如 ['--no-sandbox'])
          isolated_user_data: 自动加 --user-data-dir=<TEMP>/lceda-pro-dao
                              用于"不扰原 EDA, 另启独立实例 (开 9222)"之径.
                              典型: 用户当前 EDA 没带 CDP 调试端口, 不想杀.
        """
        if self.is_eda_running():
            self.state.eda_running = True
            # 已运行 — 尝试拿 browser_ws_url (HTTP 可能已屏 → None)
            launched = launch_eda_with_cdp(
                exe=(self.env.lceda_exe if self.env else ""),
                debug_port=self.state.cdp_port,
                wait_seconds=1.0,  # 仅探测, 不启
            )
            self.state.eda_launched = launched
            self.state.browser_ws_url = launched.browser_ws_url if launched else None
            self._emit(
                "eda_already_running",
                port=self.state.cdp_port,
                browser_ws_url=self.state.browser_ws_url,
                ws_captured=bool(self.state.browser_ws_url),
            )
            return launched
        if not spawn:
            self._emit("eda_not_running", spawn=False)
            return None
        if not self.env or not self.env.lceda_exe:
            self.locate()
        if not self.env or not self.env.lceda_exe:
            raise RuntimeError(
                "未找到 lceda-pro.exe — 请先安装嘉立创EDA Pro, 或设置环境变量 LCEDA_HOME"
            )
        # ★ 组装 extra_args
        final_extra: list[str] = list(extra_args or [])
        user_data_dir: Optional[str] = None
        if isolated_user_data:
            import tempfile
            user_data_dir = str(Path(tempfile.gettempdir()) / "lceda-pro-dao")
            Path(user_data_dir).mkdir(parents=True, exist_ok=True)
            # 仅当未显式提供时加
            if not any(a.startswith("--user-data-dir") for a in final_extra):
                final_extra.append(f"--user-data-dir={user_data_dir}")
        self._emit(
            "eda_spawning",
            exe=self.env.lceda_exe,
            port=self.state.cdp_port,
            user_data_dir=user_data_dir,
            extra_args=final_extra,
        )
        launched = launch_eda_with_cdp(
            exe=self.env.lceda_exe,
            debug_port=self.state.cdp_port,
            wait_seconds=wait_seconds,
            no_proxy=True,       # ★ 绕 system proxy
            capture_stderr=True, # ★ 抓 browser ws UUID
            extra_args=final_extra or None,
        )
        self.state.eda_running = True
        self.state.eda_launched = launched
        self.state.eda_spawned_by_us = launched.we_started_it if launched else False
        self.state.eda_proc = launched.proc if launched else None
        self.state.browser_ws_url = launched.browser_ws_url if launched else None
        self._emit(
            "eda_spawned",
            port=self.state.cdp_port,
            pid=(launched.pid if launched else None),
            browser_ws_url=self.state.browser_ws_url,
            ws_captured=bool(self.state.browser_ws_url),
        )
        return launched

    # ── 3. 桥服务器 ────────────────────────────────────
    def is_bridge_running(self) -> bool:
        return _http_ping(f"http://127.0.0.1:{self.state.bridge_port}/ping")

    def ensure_bridge(self, spawn: bool = True, wait_seconds: float = 10.0) -> Optional[subprocess.Popen]:
        """确保 lceda_bridge_server :9907 已运行."""
        if self.is_bridge_running():
            self.state.bridge_running = True
            self._emit("bridge_already_running", port=self.state.bridge_port)
            return None
        if not spawn:
            self._emit("bridge_not_running", spawn=False)
            return None
        # 找 server.py 路径 (与本模块同目录的上一级)
        bridge_py = Path(__file__).resolve().parent.parent / "lceda_bridge_server.py"
        if not bridge_py.exists():
            raise FileNotFoundError(f"找不到桥脚本: {bridge_py}")
        self._emit("bridge_spawning", script=str(bridge_py), port=self.state.bridge_port)
        # 子进程启动
        env = os.environ.copy()
        env.setdefault("PYTHONIOENCODING", "utf-8")
        creationflags = 0
        if sys.platform == "win32":
            creationflags = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        proc = subprocess.Popen(
            [sys.executable, str(bridge_py), "serve"],
            cwd=str(bridge_py.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
            creationflags=creationflags,
        )
        # 轮询 ping
        deadline = time.time() + wait_seconds
        while time.time() < deadline:
            if self.is_bridge_running():
                self.state.bridge_running = True
                self.state.bridge_spawned_by_us = True
                self.state.bridge_proc = proc
                self._emit("bridge_spawned", port=self.state.bridge_port, pid=proc.pid)
                return proc
            time.sleep(0.3)
        proc.terminate()
        raise RuntimeError(f"桥服务器启动后 {wait_seconds}s 内 :{self.state.bridge_port} 仍未响应")

    # 4. 握手
    def connect(self, mode: str = "bus", timeout: float = 30.0) -> EDA:
        """注入 transport 并返回 EDA 实例.

        ★ v4.0.2: bus/cdp 模式优先走 state.browser_ws_url (ws-only),
        lceda-pro 屏 HTTP /json/list 时唯一通路.
        """
        if mode == "bus":
            if not self.is_eda_running():
                raise RuntimeError(f"EDA 未启动调试端口 {self.state.cdp_port}, 请先 ensure_eda(spawn=True)")
            cdp = CdpTransport.connect(
                debug_port=self.state.cdp_port,
                timeout=timeout,
                browser_ws_url=self.state.browser_ws_url,  # ★ ws-only
            )
            bus = BusTransport(cdp, frame_idx=self.state.frame_idx, timeout=timeout)
            self.transport = bus
            self.eda = EDA(bus)
            self.state.transport_mode = "bus"
            self._emit(
                "connected",
                mode="bus",
                frame_idx=self.state.frame_idx,
                via_browser_ws=bool(self.state.browser_ws_url),
            )
        elif mode == "http":
            if not self.is_bridge_running():
                raise RuntimeError(f"桥未启动 :{self.state.bridge_port}, 请先 ensure_bridge(spawn=True)")
            http = HttpTransport(server=f"http://127.0.0.1:{self.state.bridge_port}", timeout=timeout)
            self.transport = http
            self.eda = EDA(http)
            self.state.transport_mode = "http"
            self._emit("connected", mode="http", port=self.state.bridge_port)
        elif mode == "cdp":
            if not self.is_eda_running():
                raise RuntimeError(f"EDA 未启动调试端口 {self.state.cdp_port}")
            cdp = CdpTransport.connect(
                debug_port=self.state.cdp_port,
                timeout=timeout,
                browser_ws_url=self.state.browser_ws_url,  # ★ ws-only
            )
            self.transport = cdp
            self.eda = EDA(cdp)
            self.state.transport_mode = "cdp"
            self._emit("connected", mode="cdp", via_browser_ws=bool(self.state.browser_ws_url))
        else:
            raise ValueError(f"未知 mode: {mode}, 应为 'bus' | 'http' | 'cdp'")
        self.state.connected = True
        return self.eda

    # 5. 自驾全程
    def auto(
        self,
        mode: str = "bus",
        spawn_eda: bool = True,
        spawn_bridge: bool = False,
        timeout: float = 60.0,
        isolated_user_data: bool = False,
        extra_args: Optional[list[str]] = None,
    ) -> "DaoConnector":
        """一行到 eda — locate + ensure_eda + (ensure_bridge) + connect.

        ★ v4.0.3: isolated_user_data=True 用独立 user-data-dir 启第二实例
        (不扰原 EDA, 适用 "用户已开 EDA 但未启 CDP" 之境).
        """
        self.locate()
        if mode in ("bus", "cdp"):
            self.ensure_eda(
                spawn=spawn_eda,
                wait_seconds=timeout,
                isolated_user_data=isolated_user_data,
                extra_args=extra_args,
            )
        if mode == "http" or spawn_bridge:
            self.ensure_bridge(spawn=spawn_bridge or (mode == "http"))
        self.connect(mode=mode, timeout=timeout)
        # 沙箱诊断 (BusTransport 才有意义)
        if mode == "bus":
            try:
                self.state.sandbox_diagnose = self.transport.diagnose()  # type: ignore[union-attr]
                self._emit("sandbox_diagnosed", **(self.state.sandbox_diagnose or {}))
            except Exception as e:
                self._emit("sandbox_diagnose_failed", error=str(e))
        # ★ 反者道之动 — 起道流 (六柱合一)
        if mode == "bus":
            try:
                from .dao_flow import DaoFlow
                self.flow = DaoFlow(self.transport)
                # 也挂 transport._dao_flow 让 tools_registry 复用同一实例
                self.transport._dao_flow = self.flow
                self._emit("flow_ready", kg_methods=self.flow.kg.stats().get("total_methods"))
            except Exception as e:
                self._emit("flow_init_failed", error=str(e))
        # ★ 启 UI 层 (五感可观) — BusTransport 才可以
        if self.user_visible and mode == "bus":
            try:
                self._enable_user_visible_layer()
            except Exception as e:
                self._emit("user_visible_failed", error=str(e))
        return self

    # 五感可观层 (UI Director + Narrator + Observer)
    def _enable_user_visible_layer(self) -> None:
        """创建 UIDirector + Narrator + EdaObserver, 三者锦上添花使用户可观."""
        from .ui_director import UIDirector, UIConfig
        from .narrator import Narrator, NarratorConfig, attach_to_observer
        from .observer import EdaObserver, ObserverHooks

        # 1. UIDirector — 鼠标键盘原语
        self.ui_director = UIDirector(self.transport, config=UIConfig())
        self.ui_director.install_overlay()
        # 缓存到 transport 供 tools_registry 复用
        self.transport._ui_director = self.ui_director

        # 2. Narrator — 五感反馈
        self.narrator = Narrator(self.ui_director, config=NarratorConfig())

        # 3. Observer — 永久日志 (EDA 内可见性由 narrator 提供, 见 step 4)
        self.observer = EdaObserver(
            eda_visible=False,  # 走 narrator → ui.narrate, 不走 _try_eda_log 旧路径
            hooks=ObserverHooks(),
        )
        # 挂到 transport, 让 tools_registry.execute 自动取
        self.transport._observer = self.observer

        # 4. narrator 接入 observer (链式) — 每次工具调用都 toast
        attach_to_observer(self.narrator, self.observer)

        # 5. 欢迎横幅 — 用户看见 道直连器已就位
        self.narrator.banner("🤖 道直连器已就位 · agent 接管中", ms=3500)
        self.ui_director.beep("info")

        self._emit("user_visible_enabled", ui=True, narrator=True, observer=True)

    # 6. 诊断
    def diagnose(self) -> dict:
        """综合诊断报告 — 不抛错, 给出全景.

        ★ v4.0.2: cdp_diagnose 重新出 (区分 tcp/http/ws 三层).
        若有 browser_ws_url 也会通过它走 ws 目标发现.
        """
        if self.env is None:
            self.locate()
        # HTTP 目标 (lceda-pro 屏则空)
        http_targets = list_targets(self.state.cdp_port)
        # ws 目标 (有 browser_ws_url 时才走)
        ws_targets: list = []
        if self.state.browser_ws_url:
            try:
                ws_targets = list_targets_via_browser_ws(self.state.browser_ws_url, timeout=3.0)
            except Exception:
                ws_targets = []
        return {
            "platform": (self.env.platform if self.env else "?"),
            "env": self.env.as_dict() if self.env else None,
            "eda_running": self.is_eda_running(),
            "cdp_port": self.state.cdp_port,
            "cdp": cdp_diagnose(self.state.cdp_port),
            "browser_ws_url": self.state.browser_ws_url,
            "cdp_targets_http": http_targets,   # HTTP /json/list 结果 (屏则空)
            "cdp_targets_ws": ws_targets,       # ws Target.getTargets 结果 (真实)
            "bridge_running": self.is_bridge_running(),
            "bridge_port": self.state.bridge_port,
            "transport_mode": self.state.transport_mode,
            "connected": self.state.connected,
            "spawned_by_us": {
                "eda": self.state.eda_spawned_by_us,
                "bridge": self.state.bridge_spawned_by_us,
            },
            "sandbox": self.state.sandbox_diagnose,
            "timeline": self.state.timeline[-20:],
        }

    # ── 7. 释放 ────────────────────────────────────────
    def close(self, terminate_spawned: bool = False) -> None:
        if self._closed:
            return
        self._closed = True
        # ★ 道流退 (effect_stream 后台线程)
        if self.flow is not None:
            try:
                self.flow.close()
            except Exception:
                pass
        # 道隐无名 — 告别横幅
        if self.narrator is not None:
            try:
                self.narrator.banner("👋 agent 退场, 道隐无名", ms=2000)
            except Exception:
                pass
        if self.ui_director is not None:
            try:
                self.ui_director.close()
            except Exception:
                pass
        # 关闭 transport
        if self.transport is not None:
            close_fn = getattr(self.transport, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
        self._emit("closed", terminate_spawned=terminate_spawned)
        if not terminate_spawned:
            return
        # 仅当我们启动的, 才停 (尊重用户已运行实例)
        if self.state.bridge_spawned_by_us and self.state.bridge_proc is not None:
            try:
                self.state.bridge_proc.terminate()
            except Exception:
                pass
        if self.state.eda_spawned_by_us and self.state.eda_proc is not None:
            try:
                # EDA 一般不强终止 (用户可能正在操作)
                pass
            except Exception:
                pass

    # ── 上下文 ─────────────────────────────────────────
    def __enter__(self) -> "DaoConnector":
        return self

    def __exit__(self, *exc) -> None:
        self.close(terminate_spawned=False)


# ──────────────────────────────────────────────────────────
# 模块级便捷函数
# ──────────────────────────────────────────────────────────
def auto(
    mode: str = "bus",
    spawn_eda: bool = True,
    spawn_bridge: bool = False,
    timeout: float = 60.0,
    user_visible: bool = True,
    isolated_user_data: bool = False,
    extra_args: Optional[list[str]] = None,
) -> DaoConnector:
    """道法自然 — 一行返回已就位的 DaoConnector.

    ★ v4.0.3: isolated_user_data=True → 不扰原 EDA, 用独立 user-data-dir 启第二实例.
    """
    return DaoConnector(user_visible=user_visible).auto(
        mode=mode,
        spawn_eda=spawn_eda,
        spawn_bridge=spawn_bridge,
        timeout=timeout,
        isolated_user_data=isolated_user_data,
        extra_args=extra_args,
    )


def diagnose() -> dict:
    """不连接, 只读取本机各组件状态 (env/eda/bridge)."""
    return DaoConnector().diagnose()


# ──────────────────────────────────────────────────────────
# CLI 直跑
# ──────────────────────────────────────────────────────────
def _cli(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "diagnose":
        rep = diagnose()
        print(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
        return 0
    if cmd == "drive":
        # 一键自驾 (含启动 EDA)
        spawn = "--no-spawn" not in argv
        mode = "bus"
        for a in argv[1:]:
            if a.startswith("--mode="):
                mode = a.split("=", 1)[1]
        try:
            with DaoConnector().auto(mode=mode, spawn_eda=spawn) as dao:
                print("✅ 道直连器已就位")
                print(json.dumps(dao.diagnose(), ensure_ascii=False, indent=2, default=str))
            return 0
        except Exception as e:
            print(f"❌ 道直连器启动失败: {e}", file=sys.stderr)
            return 2
    print(f"未知命令: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
