"""devin_cloud — Devin Cloud 云端客户端 (忠实移植自 devin-remote/core/dao-vsix)。

出处: devin-remote/core/dao-vsix/rtflow/devin_cloud.js (v3.50.64)。端点与请求契约
逐函数照搬其已实测确证者, 不臆造新接口:

  * 登录:   POST windsurf.com/_devin-auth/password/login {email,password} → token
            再 POST app.devin.ai/api/users/post-auth (Bearer token) → org_id
  * 鉴权头: {Authorization: Bearer <auth1>, x-cog-org-id: <orgId>}
  * 列会话: GET app.devin.ai/api/org-<bare>/v2sessions[?limit=]  (回落 /api/sessions)
  * 会话详: GET app.devin.ai/api/sessions/<devinId>
  * 建会话: POST app.devin.ai/api/sessions {user_message, prompt, ...}
  * 续消息: POST api.devin.ai/v1/session/<id>/message {message}  (Bearer apk_ API Key)
  * 事件流: GET app.devin.ai/api/events/devin-<id>/stream  (回落 /events/first-load/<id>)
  * 额度:   GET app.devin.ai/api/<orgId>/billing/status
  * 知识库: GET app.devin.ai/api/org-<bare>/learning/all
  * 剧本:   GET app.devin.ai/api/org-<bare>/playbooks
  * 密钥:   GET app.devin.ai/api/org-<bare>/secrets
  * Git:    GET app.devin.ai/api/organizations/<orgId>/git-connections-metadata

反臆造纪律 (照搬 dao-vsix 原注释里的实测教训):
  * 续消息公开 API 仅认 Devin API Key (apk_...); 会话登录态 auth1 被拒 403 → 缺
    API Key 时不臆造成功, 直接回报需配置 (对应 devin_cloud.js sendMessage)。
  * 请求体非 ASCII 一律转义 (ensure_ascii=True), 否则服务端每隔一字截断中文。
  * 429/5xx 退避重试 (遵从 Retry-After), 而非当作请求已失败上抛。
"""
from __future__ import annotations

import json
import os
import random
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# ── 软编码配置 (唯变所适 · 对应 devin_cloud.js CFG) ────────────────────────────
@dataclass
class Config:
    login_url: str = "https://windsurf.com/_devin-auth/password/login"
    api_base: str = "https://app.devin.ai/api"
    v1_base: str = "https://api.devin.ai/v1"
    api_key: str = ""  # Devin 官方 API Key (apk_...); 续写消息所需
    ua: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) dao-kicad-devin-cloud"
    auth_ttl_ms: int = 12 * 60 * 60 * 1000  # 登录态缓存 12h
    req_timeout_ms: int = 30000
    stream_timeout_ms: int = 90000
    max_retries: int = 3          # 瞬态网络错误重试
    retry_base_ms: int = 500      # 指数退避基数 500/1000/2000ms
    rate_limit_max_retries: int = 6  # HTTP 429 重试
    retry_max_delay_ms: int = 30000


CFG = Config()


def configure(**opts: Any) -> Config:
    """就地覆写软编码配置 (对应 devin_cloud.js configure)。"""
    for k, v in opts.items():
        if hasattr(CFG, k):
            setattr(CFG, k, v)
    return CFG


# ── 登录态缓存落盘位置 (对应 DC_AUTH_CACHE) ──────────────────────────────────
def _dao_home() -> Path:
    root = os.environ.get("DAO_HOME")
    return Path(root) if root else (Path.home() / ".dao")


def _auth_cache_path() -> Path:
    return _dao_home() / "devin-auth-cache.json"


def ensure_dir(d: Path) -> None:
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def read_json(file: Path, fallback: Any) -> Any:
    try:
        return json.loads(file.read_text("utf-8"))
    except (OSError, ValueError):
        return fallback


def write_json(file: Path, obj: Any) -> None:
    try:
        ensure_dir(file.parent)
        file.write_text(json.dumps(obj, ensure_ascii=False, indent=2), "utf-8")
    except OSError:
        pass


# ── 低层 HTTP (可注入 transport 以便单测不触网) ──────────────────────────────
# transport(method, url, headers, body_bytes, timeout_s) -> (status, headers_dict, body_bytes)
Transport = Callable[[str, str, Dict[str, str], Optional[bytes], float],
                     Tuple[int, Dict[str, str], bytes]]

_TRANSPORT: Optional[Transport] = None


def set_transport(fn: Optional[Transport]) -> None:
    """注入自定义传输层 (单测/离线用)。传 None 恢复默认 urllib。"""
    global _TRANSPORT
    _TRANSPORT = fn


def _ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _urllib_transport(method: str, url: str, headers: Dict[str, str],
                      body: Optional[bytes], timeout_s: float
                      ) -> Tuple[int, Dict[str, str], bytes]:
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s, context=_ssl_ctx()) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:  # 4xx/5xx: 取回响应体供上层判读
        return e.code, dict(e.headers or {}), e.read() or b""


_TRANSIENT = ("econnreset", "econnrefused", "etimedout", "timeout", "eai_again",
              "enotfound", "epipe", "ehostunreach", "enetunreach", "reset",
              "socket", "tls", "ssl", "temporarily")


def _is_transient(e: Exception) -> bool:
    m = str(getattr(e, "reason", "") or e).lower()
    return any(t in m for t in _TRANSIENT)


def _is_retryable_status(status: int, method: str) -> bool:
    if status == 429:
        return True
    if status in (502, 503, 504):
        return method.upper() in ("GET", "HEAD")
    return False


def _retry_delay_ms(headers: Dict[str, str], attempt: int) -> int:
    cap = CFG.retry_max_delay_ms
    ra = (headers or {}).get("retry-after") or (headers or {}).get("Retry-After")
    if ra:
        try:
            secs = int(str(ra).strip())
            return min(max(0, secs) * 1000, cap)
        except ValueError:
            pass
    base = CFG.retry_base_ms * (2 ** attempt)
    return min(base + random.randint(0, CFG.retry_base_ms), cap)


def raw_request(method: str, url: str, headers: Dict[str, str],
                body: Optional[bytes], timeout_ms: Optional[int] = None
                ) -> Tuple[int, Dict[str, str], bytes]:
    """善行无辙迹: 瞬态错误指数退避重试; 429/5xx 遵从 Retry-After 退避重试。"""
    transport = _TRANSPORT or _urllib_transport
    timeout_s = (timeout_ms or CFG.req_timeout_ms) / 1000.0
    hdrs = {"User-Agent": CFG.ua, "Accept": "application/json"}
    hdrs.update(headers or {})
    max_net = max(0, CFG.max_retries)
    max_rl = max(0, CFG.rate_limit_max_retries)
    last_exc: Optional[Exception] = None
    for attempt in range(max(max_net, max_rl) + 1):
        try:
            status, rheaders, buf = transport(method, url, hdrs, body, timeout_s)
            if _is_retryable_status(status, method) and attempt < max_rl:
                time.sleep(_retry_delay_ms(rheaders, attempt) / 1000.0)
                continue
            return status, rheaders, buf
        except Exception as e:  # noqa: BLE001 — 需按瞬态与否分流
            last_exc = e
            if attempt >= max_net or not _is_transient(e):
                break
            time.sleep((CFG.retry_base_ms * (2 ** attempt)) / 1000.0)
    raise last_exc if last_exc else RuntimeError("raw_request failed")


def json_request(method: str, url: str, headers: Optional[Dict[str, str]] = None,
                 body: Any = None, timeout_ms: Optional[int] = None
                 ) -> Dict[str, Any]:
    """发送 JSON 请求, 回 {status, json, text, headers}。

    body 非 ASCII 一律转义 (ensure_ascii=True) —— 对应 dao-vsix asciiSafeJson,
    否则服务端每隔一字截断中文 (踩坑 5)。
    """
    h = dict(headers or {})
    payload: Optional[bytes] = None
    if body is not None:
        text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=True)
        payload = text.encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    status, rheaders, buf = raw_request(method, url, h, payload, timeout_ms)
    text = buf.decode("utf-8", "replace")
    parsed: Any = None
    try:
        parsed = json.loads(text)
    except ValueError:
        parsed = None
    return {"status": status, "json": parsed, "text": text, "headers": rheaders}


# ── 鉴权 ─────────────────────────────────────────────────────────────────────
@dataclass
class Auth:
    auth1: str = ""
    user_id: str = ""
    org_id: str = ""
    org_bare: str = ""
    org_name: str = ""
    email: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.auth1 and self.org_id)


def auth_headers(auth: Auth, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    h = {"Authorization": "Bearer " + auth.auth1, "x-cog-org-id": auth.org_id}
    if extra:
        h.update(extra)
    return h


def login(email: str, password: str) -> Dict[str, Any]:
    """两跳登录: windsurf 密码登录取 token → app.devin.ai post-auth 取 org_id。"""
    resp = json_request("POST", CFG.login_url, {}, {"email": email, "password": password})
    if resp["status"] != 200 or not resp["json"]:
        return {"ok": False, "error": f"login HTTP {resp['status']}: {resp['text'][:160]}"}
    j = resp["json"]
    auth1 = j.get("token") or j.get("access_token")
    if not auth1:
        return {"ok": False, "error": "登录响应无 token"}
    user_id = j.get("user_id") or j.get("userId") or ""
    org_resp = json_request("POST", CFG.api_base + "/users/post-auth",
                            {"Authorization": "Bearer " + auth1}, {})
    od = org_resp["json"] or {}
    org_id = od.get("org_id") or od.get("orgId") or ""
    if not org_id:
        return {"ok": False, "error": f"post-auth 无 org_id (HTTP {org_resp['status']})"}
    return {
        "ok": True,
        "auth": Auth(auth1=auth1, user_id=user_id, org_id=org_id,
                     org_bare=org_id[4:] if org_id.startswith("org-") else org_id,
                     org_name=od.get("org_name") or od.get("orgName") or "", email=email),
    }


def get_auth(email: str, password: str, force: bool = False) -> Dict[str, Any]:
    """登录态缓存: email→auth, 12h 内复用, 过期或 force 时重登。"""
    cache = read_json(_auth_cache_path(), {})
    key = str(email).lower()
    hit = cache.get(key)
    now = int(time.time() * 1000)
    if not force and hit and hit.get("auth1") and now - hit.get("ts", 0) < CFG.auth_ttl_ms:
        return {"ok": True, "cached": True, "auth": Auth(
            auth1=hit["auth1"], user_id=hit.get("userId", ""), org_id=hit["orgId"],
            org_bare=hit.get("orgBare", ""), org_name=hit.get("orgName", ""), email=email)}
    r = login(email, password)
    if r["ok"]:
        a: Auth = r["auth"]
        cache[key] = {"auth1": a.auth1, "userId": a.user_id, "orgId": a.org_id,
                      "orgBare": a.org_bare, "orgName": a.org_name, "ts": now}
        write_json(_auth_cache_path(), cache)
    return r


def clear_auth_cache(email: Optional[str] = None) -> None:
    cache = read_json(_auth_cache_path(), {})
    if email:
        cache.pop(str(email).lower(), None)
    else:
        cache = {}
    write_json(_auth_cache_path(), cache)


# ── Cloud 读取 ───────────────────────────────────────────────────────────────
def _as_array(j: Any, *keys: str) -> List[Any]:
    if isinstance(j, list):
        return j
    if not isinstance(j, dict):
        return []
    for k in keys:
        if isinstance(j.get(k), list):
            return j[k]
    return []


def list_sessions(auth: Auth, limit: Optional[int] = None) -> Dict[str, Any]:
    url = CFG.api_base + "/org-" + auth.org_bare + "/v2sessions"
    if limit:
        url += "?limit=" + str(limit)
    r = json_request("GET", url, auth_headers(auth), None, 60000)
    if r["status"] == 200:
        arr = _as_array(r["json"], "result", "sessions", "data")
        if arr or (isinstance(r["json"], dict) and (r["json"].get("result") or r["json"].get("sessions"))):
            return {"ok": True, "sessions": arr}
    r = json_request("GET", CFG.api_base + "/sessions", auth_headers(auth), None, 60000)
    if r["status"] == 200:
        return {"ok": True, "sessions": _as_array(r["json"], "result", "sessions", "data")}
    return {"ok": False, "sessions": [], "error": f"list sessions HTTP {r['status']}"}


def get_session_detail(auth: Auth, devin_id: str) -> Dict[str, Any]:
    r = json_request("GET", CFG.api_base + "/sessions/" + devin_id, auth_headers(auth))
    return r["json"] or {} if r["status"] == 200 else {}


def create_session(auth: Auth, prompt: str, opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """发起新 Devin Cloud 对话。app.devin.ai 内部 API 校验字段为 user_message,
    prompt 同带以兼容内部/公开两套契约 (对应 devin_cloud.js createSession)。"""
    opts = opts or {}
    payload: Dict[str, Any] = {"user_message": str(prompt or ""), "prompt": str(prompt or "")}
    if opts.get("title"):
        payload["title"] = opts["title"]
    if opts.get("tags"):
        payload["tags"] = opts["tags"]
    if opts.get("playbookId"):
        payload["playbook_id"] = opts["playbookId"]
    if opts.get("repos"):
        payload["repos"] = opts["repos"]
    if opts.get("sessionSecrets"):
        payload["session_secrets"] = opts["sessionSecrets"]
    if opts.get("idempotencyKey"):
        payload["idempotency_key"] = opts["idempotencyKey"]
    r = json_request("POST", CFG.api_base + "/sessions", auth_headers(auth), payload)
    if r["status"] in (200, 201):
        j = r["json"] or {}
        return {"ok": True, "devinId": j.get("devin_id") or j.get("session_id") or j.get("id"),
                "isNewSession": j.get("is_new_session"), "createdAt": j.get("created_at"), "raw": j}
    return {"ok": False, "status": r["status"],
            "error": f"createSession HTTP {r['status']}: {(r['text'] or '')[:160]}"}


def send_message(auth: Auth, devin_id: str, message: str,
                 opts: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """向已有对话追加用户消息。公开 API 仅认 Devin API Key (apk_...); 缺则不臆造成功
    (对应 devin_cloud.js sendMessage 的 403 实测教训)。"""
    opts = opts or {}
    api_key = opts.get("apiKey") or CFG.api_key or ""
    if not api_key:
        return {"ok": False, "status": 0,
                "error": "续写消息需配置 Devin API Key (apk_...); 会话登录态不被公开 API 接受。"
                         "请设置 CFG.api_key 或 opts['apiKey'] 后重试。"}
    r = json_request("POST", CFG.v1_base + "/session/" + devin_id + "/message",
                     {"Authorization": "Bearer " + api_key, "User-Agent": CFG.ua},
                     {"message": str(message or "")})
    ok = 200 <= r["status"] < 300
    return {"ok": ok, "status": r["status"], "raw": r["json"], "text": (r["text"] or "")[:200],
            "error": None if ok else f"sendMessage HTTP {r['status']}: {(r['text'] or '')[:160]}"}


def get_event_stream(auth: Auth, devin_id: str) -> Dict[str, Any]:
    """事件流 (SSE/ndjson/json 混合) → 去重排序事件数组。/events 要求 devin- 前缀。"""
    eid = "devin-" + str(devin_id or "").replace("devin-", "", 1) if str(devin_id).startswith("devin-") \
        else "devin-" + str(devin_id or "")
    url = CFG.api_base + "/events/" + eid + "/stream"
    resp_text: Optional[str] = None
    for attempt in range(3):
        try:
            status, _h, buf = raw_request("GET", url,
                                          auth_headers(auth, {"Accept": "text/event-stream"}),
                                          None, CFG.stream_timeout_ms)
            if status == 200:
                resp_text = buf.decode("utf-8", "replace")
                break
        except Exception:  # noqa: BLE001
            pass
        if attempt < 2:
            time.sleep(1.5 * (attempt + 1))
    if resp_text is None:
        r = json_request("GET", CFG.api_base + "/events/first-load/" + eid, auth_headers(auth))
        if r["status"] != 200:
            return {"events": [], "ok": False, "reason": "fetch-failed", "status": r["status"]}
        return {"events": _as_array(r["json"], "result", "events"), "ok": True, "reason": "first-load", "status": 200}
    return {"events": _parse_event_stream(resp_text), "ok": True, "reason": "stream", "status": 200}


def _parse_event_stream(raw: str) -> List[Dict[str, Any]]:
    """解析混合 SSE/ndjson/JSON 流, 按 event_id 去重, 按 created_at_ms 排序。"""
    merged: Dict[str, Dict[str, Any]] = {}

    def add(ev: Any) -> None:
        if not isinstance(ev, dict) or not ev.get("type"):
            return
        key = ev.get("event_id") or f"{ev.get('type')}-{ev.get('timestamp')}-{ev.get('created_at_ms')}"
        merged.setdefault(str(key), ev)

    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        payload = s[5:].strip() if s.startswith("data:") else s
        if not payload or payload == "[DONE]" or payload[0] not in "{[":
            continue
        try:
            obj = json.loads(payload)
        except ValueError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("result"), list):
            for e in obj["result"]:
                add(e)
        else:
            add(obj)
    events = list(merged.values())
    events.sort(key=lambda e: e.get("created_at_ms") or 0)
    return events


def list_knowledge(auth: Auth) -> Dict[str, Any]:
    r = json_request("GET", CFG.api_base + "/org-" + auth.org_bare + "/learning/all", auth_headers(auth))
    return {"ok": True, "learnings": _as_array(r["json"], "learnings")} if r["status"] == 200 \
        else {"ok": False, "learnings": []}


def list_playbooks(auth: Auth) -> Dict[str, Any]:
    r = json_request("GET", CFG.api_base + "/org-" + auth.org_bare + "/playbooks", auth_headers(auth))
    return {"ok": True, "playbooks": _as_array(r["json"], "playbooks")} if r["status"] == 200 \
        else {"ok": False, "playbooks": []}


def list_secrets(auth: Auth) -> Dict[str, Any]:
    r = json_request("GET", CFG.api_base + "/org-" + auth.org_bare + "/secrets", auth_headers(auth))
    return {"ok": True, "secrets": _as_array(r["json"], "secrets")} if r["status"] == 200 \
        else {"ok": False, "secrets": []}


def get_git_connections(auth: Auth) -> Dict[str, Any]:
    r = json_request("GET", CFG.api_base + "/organizations/" + auth.org_id + "/git-connections-metadata",
                     auth_headers(auth))
    if r["status"] != 200:
        return {"ok": False, "connections": []}
    conns = r["json"] if isinstance(r["json"], list) else _as_array(r["json"], "connections")
    return {"ok": True, "connections": conns}


def get_billing(auth: Auth) -> Dict[str, Any]:
    r = json_request("GET", CFG.api_base + "/" + auth.org_id + "/billing/status", auth_headers(auth))
    return {"ok": True, "billing": r["json"]} if r["status"] == 200 and r["json"] else {"ok": False, "billing": None}


def message_limit_int(max_credits: Any) -> Optional[int]:
    """归一为服务端可接受的整数 max_credits (≥1); 低于 1 或非数 → None。"""
    try:
        i = int(float(max_credits))
    except (TypeError, ValueError):
        return None
    return i if i >= 1 else None


def set_message_limit(auth: Auth, max_credits: Any) -> Dict[str, Any]:
    imc = message_limit_int(max_credits)
    if imc is None:
        return {"ok": False, "status": 0, "belowMin": True}
    r = json_request("POST", CFG.api_base + "/org-" + auth.org_bare + "/billing/usage/limits",
                     auth_headers(auth), {"max_credits": imc})
    return {"ok": r["status"] in (200, 201, 204), "status": r["status"], "sent": imc}


def get_message_limit(auth: Auth) -> Dict[str, Any]:
    r = json_request("GET", CFG.api_base + "/org-" + auth.org_bare + "/billing/usage/limits", auth_headers(auth))
    if r["status"] == 200 and isinstance(r["json"], dict):
        j = r["json"]
        v = j.get("max_acu_limit")
        if not isinstance(v, (int, float)):
            v = j.get("max_credits")
        if not isinstance(v, (int, float)) and isinstance(j.get("limits"), dict):
            v = j["limits"].get("max_credits")
        return {"ok": True, "maxCredits": v if isinstance(v, (int, float)) else None}
    return {"ok": False, "maxCredits": None}


def billing_balance(billing: Any) -> Optional[float]:
    """从 billing 提取可用余额(美元); None = 无法判定 (禁止据此做破坏性清理)。"""
    if not billing:
        return None
    b = billing.get("billing") if isinstance(billing, dict) and isinstance(billing.get("billing"), dict) else billing
    if not isinstance(b, dict):
        return None

    def num(*keys: str) -> Optional[float]:
        for k in keys:
            v = b.get(k)
            if isinstance(v, (int, float)):
                return float(v)
        return None

    avail = num("available_credits", "availableCredits")
    overage = num("overage_credits", "overageCredits")
    dollars = (avail or 0) + max(0, overage or 0)
    if b.get("has_subscription_or_credits") is True or b.get("is_subscription_valid") is True:
        return dollars if dollars > 0 else 9999
    if b.get("has_subscription_or_credits") is False:
        return dollars
    if avail is not None or overage is not None:
        return dollars
    return None


# ── 会话状态分类 (对话追踪用 · 五态细分) ─────────────────────────────────────
def classify_session(s: Optional[Dict[str, Any]]) -> str:
    """running/awaiting/blocked/finished/idle 五态。权威实时状态在
    latest_status_contents; user_action_required 非空=真·等待用户输入 (最高优先)。"""
    s = s or {}
    lsc = s.get("latest_status_contents") or {}
    enum_v = str(lsc.get("enum") or "").lower()
    reason = str(lsc.get("reason") or "").lower()
    uar = lsc.get("user_action_required")
    status = str(s.get("status") or "").lower()
    act = str(s.get("activity_status") or "").lower()
    cur = str(s.get("current_activity") or "").lower()

    if uar not in (None, "", False):
        return "awaiting"
    terminal = enum_v == "finished" or any(t in status for t in
                                           ("suspended", "expired", "exited", "archived", "deleted"))
    if terminal:
        return "finished"
    blob = " ".join((enum_v, reason, status, act, cur))
    if any(t in blob for t in ("out_of_quota", "usage_limit", "insufficient", "overage",
                               "credit", "billing", "exceeded", "quota")):
        return "blocked"
    if any(t in blob for t in ("error", "failed", "stuck", "crash")):
        return "blocked"
    if any(t in blob for t in ("await", "waiting_for_user", "waiting_for_input",
                               "needs_input", "user_input", "ask_user", "blocked_on_user")):
        return "awaiting"
    if "blocked" in blob:
        return "blocked"
    if any(t in blob for t in ("running", "working", "in_progress", "streaming", "active",
                               "started", "resumed", "busy", "thinking", "executing",
                               "coding", "planning", "testing")):
        return "running"
    return "running" if (enum_v or status) else "idle"


def is_active_class(cls: str) -> bool:
    return cls in ("running", "awaiting", "blocked")


def _sess_id(s: Dict[str, Any]) -> Any:
    return s.get("devin_id") or s.get("session_id") or s.get("id")


def account_overview(auth: Auth) -> Dict[str, Any]:
    """账号本源概览: 会话(着重) + 知识库/剧本/密钥/Git/额度 简要。大成若缺: 任一
    子端点失败不毁整份概览 (对应 devin_cloud.js accountOverview 的 allSettled)。"""
    def _safe(fn: Callable[[], Dict[str, Any]], fb: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return fn()
        except Exception:  # noqa: BLE001
            return fb

    sessions = _safe(lambda: list_sessions(auth), {"sessions": []})
    knowledge = _safe(lambda: list_knowledge(auth), {"learnings": []})
    playbooks = _safe(lambda: list_playbooks(auth), {"playbooks": []})
    secrets = _safe(lambda: list_secrets(auth), {"secrets": []})
    git = _safe(lambda: get_git_connections(auth), {"connections": []})
    billing = _safe(lambda: get_billing(auth), {"billing": None})
    ss = sessions.get("sessions") or []
    classed = [classify_session(s) for s in ss]
    return {
        "email": auth.email,
        "orgId": auth.org_id,
        "sessions": [{
            "devinId": _sess_id(s),
            "title": s.get("title") or s.get("name") or "(未命名)",
            "status": s.get("status") or s.get("activity_status") or "",
            "statusClass": classify_session(s),
            "createdAt": s.get("created_at"),
            "updatedAt": s.get("updated_at"),
            "tags": s.get("tags") or [],
        } for s in ss],
        "counts": {
            "sessions": len(ss),
            "running": classed.count("running"),
            "awaiting": classed.count("awaiting"),
            "blocked": classed.count("blocked"),
            "knowledge": len(knowledge.get("learnings") or []),
            "playbooks": len(playbooks.get("playbooks") or []),
            "secrets": len(secrets.get("secrets") or []),
            "gitConnections": len(git.get("connections") or []),
        },
        "billing": billing.get("billing"),
    }


def list_running_sessions(auth: Auth) -> Dict[str, Any]:
    """返回所有活跃·需关注会话 (running/awaiting/blocked), 各带 statusClass。"""
    r = list_sessions(auth, 100)
    active = []
    for s in (r.get("sessions") or []):
        lsc = s.get("latest_status_contents") or {}
        cls = classify_session(s)
        if is_active_class(cls):
            active.append({
                "devinId": _sess_id(s),
                "title": s.get("title") or s.get("name") or "(未命名)",
                "status": str(lsc.get("enum") or s.get("status") or s.get("activity_status") or "")
                + (f"({lsc.get('reason')})" if lsc.get("reason") else ""),
                "reason": lsc.get("reason") or "",
                "statusClass": cls,
            })
    return {"ok": r.get("ok", False), "sessions": active}
