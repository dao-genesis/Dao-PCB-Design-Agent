"""bridge — 半原生 Devin Desktop 的门面: 把 Devin Cloud + 账号池 + 模型路由 + 活体
内核 (native_live) 归一成 KiCad 面板可直接调用的一组高层操作。

守一之母 (native_live) 是「活着的 KiCad 编辑器」。本 bridge 让一个 Devin Cloud 对话
能**直驱这块活板**:
  * 对话/账号/追踪面 → 走 devin_cloud + accounts (纯云端, 无 KiCad 依赖);
  * 「让 Agent 动手改板」面 → 走 native_live.LiveSession 的 eval/summary (进程内活板);
  * 模型路由面 → 走 dao_proxy (第三方渠道)。

本模块**零 wx / 零 pcbnew 依赖** → CI 纯测 (网络经 devin_cloud.set_transport 注入桩)。
panel.py 只做 wx UI, 一切业务落此。

反臆造: 活板动作的结果一律取自 LiveSession 回传的真实活板状态, 不本地臆测。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import accounts, agent_core, dao_proxy
from . import devin_cloud as dc


def _agent_auth_dict(a: "agent_core.AgentAuth") -> Dict[str, Any]:
    """AgentAuth → 面板可 JSON 化 (不暴露密码, apiKey 尾截防泄)。"""
    if not a.ok:
        return {"ok": False, "error": a.error}
    return {"ok": True, "userId": a.user_id, "orgId": a.org_id, "orgName": a.org_name,
            "orgSlug": a.org_slug, "hasApiKey": bool(a.api_key),
            "hasWindsurfKey": bool(a.windsurf_key), "apiServerUrl": a.api_server_url,
            "quota": a.quota}


@dataclass
class BridgeState:
    auth: Optional[dc.Auth] = None
    active_devin_id: str = ""


class DevinKiCadBridge:
    """面板业务门面。live_factory 可注入 (默认惰性起 native_live.LiveSession)。"""

    def __init__(self, live_factory: Optional[Any] = None) -> None:
        self.state = BridgeState()
        self._live_factory = live_factory
        self._live = None  # 活体会话句柄 (惰性)

    # ── 账号面 ────────────────────────────────────────────────────────────
    def add_account(self, email: str, password: str = "", token: str = "",
                    label: str = "") -> Dict[str, Any]:
        accounts.add_account(email, password=password, token=token, label=label)
        return {"ok": True, "accounts": accounts.list_accounts()}

    def list_accounts(self) -> List[Dict[str, Any]]:
        return accounts.list_accounts()

    def switch_account(self, email: str) -> Dict[str, Any]:
        accounts.switch_account(email)
        self.state.auth = None  # 迫使下次取号重解析
        return {"ok": True, "active": email}

    def remove_account(self, email: str) -> Dict[str, Any]:
        accounts.remove_account(email)
        return {"ok": True, "accounts": accounts.list_accounts()}

    def ensure_auth(self, force: bool = False) -> Dict[str, Any]:
        """确保当前活动号已取号 (auth 缓存进 state)。"""
        if self.state.auth and self.state.auth.ok and not force:
            return {"ok": True, "auth": self.state.auth, "cached": True}
        r = accounts.active_auth(force=force)
        if r.get("ok"):
            self.state.auth = r["auth"]
        return r

    # ── 对话追踪面 ────────────────────────────────────────────────────────
    def overview(self) -> Dict[str, Any]:
        r = self.ensure_auth()
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
        return {"ok": True, "overview": dc.account_overview(self.state.auth)}

    def running_sessions(self) -> Dict[str, Any]:
        r = self.ensure_auth()
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error"), "sessions": []}
        return dc.list_running_sessions(self.state.auth)

    def session_events(self, devin_id: str) -> Dict[str, Any]:
        r = self.ensure_auth()
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error"), "events": []}
        return dc.get_event_stream(self.state.auth, devin_id)

    # ── 对话窗口面 ────────────────────────────────────────────────────────
    def new_session(self, prompt: str, opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        r = self.ensure_auth()
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
        res = dc.create_session(self.state.auth, prompt, opts)
        if res.get("ok"):
            self.state.active_devin_id = res.get("devinId") or ""
        return res

    def send(self, message: str, devin_id: str = "",
             opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        r = self.ensure_auth()
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
        did = devin_id or self.state.active_devin_id
        if not did:
            return {"ok": False, "error": "无活动对话 (先 new_session 或指定 devin_id)"}
        return dc.send_message(self.state.auth, did, message, opts)

    # ── 模型路由面 ────────────────────────────────────────────────────────
    def proxy_presets(self) -> List[Dict[str, str]]:
        return dao_proxy.list_presets()

    def proxy_channels(self) -> List[Dict[str, Any]]:
        return dao_proxy.list_channels()

    def proxy_add(self, **kw: Any) -> Dict[str, Any]:
        dao_proxy.add_channel(**kw)
        return {"ok": True, "channels": dao_proxy.list_channels()}

    def proxy_route(self, name: Optional[str] = None) -> Dict[str, Any]:
        return dao_proxy.resolve_route(name)

    def proxy_chat(self, messages: List[Dict[str, Any]], name: Optional[str] = None,
                   model: str = "", **opts: Any) -> Dict[str, Any]:
        """经活动渠道打真模型 (三协议归一)。底层 dao_proxy.chat → proxy_adapters。"""
        return dao_proxy.chat(messages, name=name, model=model, **opts)

    # ── Agent 本源面 (L3 · Windsurf/Visurf 真源认证链) ─────────────────────
    def agent_login(self, email: str, password: str) -> Dict[str, Any]:
        """Agent 真源五步链登录 (windsurf→sessionToken→org→apiKey→额度)。
        较 add_account 的两跳更深: 产出 apiKey/windsurfKey (Agent 推理层认的钥)。"""
        a = agent_core.agent_login(email, password)
        return _agent_auth_dict(a)

    def agent_hydrate(self, auth1: str) -> Dict[str, Any]:
        """用已有 auth1 补全 org+额度 (无需邮密)。源 hydrateAuth1。"""
        return _agent_auth_dict(agent_core.hydrate_auth1(auth1))

    def agent_quota(self, force: bool = False) -> Dict[str, Any]:
        """当前活动号的 Agent 额度/计划 (GetUserStatus + billing 美金余额)。"""
        r = self.ensure_auth(force=force)
        if not r.get("ok"):
            return {"ok": False, "error": r.get("error")}
        au = self.state.auth
        q = agent_core.fetch_quota("", "", au.auth1, au.org_id, force=force)
        return {"ok": q is not None, "quota": q}

    # ── 活体内核面 (让 Agent 直驱活板) ────────────────────────────────────
    def live(self):
        """惰性取活体会话。默认起 native_live.LiveSession(headless daemon)。"""
        if self._live is not None:
            return self._live
        if self._live_factory is not None:
            self._live = self._live_factory()
            return self._live
        from kicad_origin.origin.native_live import LiveSession  # 延迟导入 (KiCad 依赖)
        self._live = LiveSession().start()
        return self._live

    def live_summary(self) -> Dict[str, Any]:
        try:
            return {"ok": True, "summary": self.live().summary()}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def live_eval(self, code: str) -> Dict[str, Any]:
        """在活板进程内执行 (Agent 的手): 回传真实活板回值。"""
        try:
            return {"ok": True, "result": self.live().eval(code)}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)}

    def close(self) -> None:
        if self._live is not None:
            try:
                self._live.close()
            except Exception:  # noqa: BLE001
                pass
            self._live = None
