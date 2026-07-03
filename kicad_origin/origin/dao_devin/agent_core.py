"""agent_core — Agent 本源认证链 + 额度/计划面 (移植自 devin-remote Visurf/Windsurf 核)。

L3 · 把「本来把 VS Code 改造成 Devin Desktop 的那个本源」的 Agent 底层链接搬进 KiCad:

忠实移植自:
  * devin-remote/addons/rt-flow-app/app/src/main/assets/engine/devin-core.js
    (手机版与桌面 core/dao-vsix/src/extension.ts 的 devinLogin/devinFetchQuota 同源复刻)
  * devin-remote/core/rt-flow/devin_cloud.js (端点契约)

与 L1 devin_cloud.login 的分别 (为何是「更深的本源」):
  * L1 只做两跳 (windsurf 密码登录 → app.devin.ai post-auth 取 org)。
  * L3 是 Agent 真源五步链: windsurf 密码登录 → WindsurfPostAuth(sessionToken) →
    Devin post-auth(org) → RegisterUser(apiKey/windsurfKey/apiServerUrl) →
    GetUserStatus(计划/额度) + billing 美金余额。这条链拿到的 apiKey/windsurfKey 才是
    Agent 推理层 (codeium/windsurf server) 认的钥, 是「Agent 底层链接」的真钥面。

反臆造:
  * HTTP 全经 devin_cloud.json_request (ensure_ascii 中文防截断 · set_transport 可注入桩)。
  * 端点/字段名逐一对应源 (devin-core.js 行号见各函数 docstring), 不臆造新接口。
  * 额度取不到时 overageKnown=False 显式标注, 绝不把「未知」抹成 $0 (源踩坑①)。
"""
from __future__ import annotations

import math
import re
import time
import uuid as _uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from . import devin_cloud as dc


# ── 端点常量 (源 devin-core.js:83-94, 与桌面同源) ────────────────────────────
WINDSURF = "https://windsurf.com"
APP = "https://app.devin.ai"
URL_LOGIN = WINDSURF + "/_devin-auth/password/login"
URL_POSTAUTH = (WINDSURF +
                "/_backend/exa.seat_management_pb.SeatManagementService/WindsurfPostAuth")
URL_DEVIN_POST_AUTH = APP + "/api/users/post-auth"
URL_REGISTER = ("https://register.windsurf.com/"
                "exa.seat_management_pb.SeatManagementService/RegisterUser")
URL_GET_USER_STATUS: List[str] = [
    "https://server.codeium.com/exa.seat_management_pb.SeatManagementService/GetUserStatus",
    "https://server.self-serve.windsurf.com/exa.seat_management_pb.SeatManagementService/GetUserStatus",
    "https://windsurf.com/_route/api_server/exa.seat_management_pb.SeatManagementService/GetUserStatus",
]

_Q_TTL_MS = 2000  # 源 devin-core.js:159 _Q_TTL — 吸收撞点重复


@dataclass
class AgentAuth:
    """Agent 真源五步链的完整产出 (较 L1 Auth 多 sessionToken/apiKey/windsurfKey/quota)。"""
    ok: bool = False
    error: str = ""
    auth1: str = ""
    user_id: str = ""
    org_id: str = ""
    org_name: str = ""
    org_slug: str = ""
    session_token: str = ""
    api_key: str = ""
    windsurf_key: str = ""
    api_server_url: str = ""
    account_id: str = ""
    quota: Optional[Dict[str, Any]] = None

    def to_devin_auth(self) -> dc.Auth:
        """降解为 L1 devin_cloud.Auth (供既有 Cloud 读取函数复用)。"""
        return dc.Auth(auth1=self.auth1, user_id=self.user_id, org_id=self.org_id,
                       org_bare=self.org_id[4:] if self.org_id.startswith("org-") else self.org_id,
                       org_name=self.org_name)


# ── HTTP 薄封装 (复用 devin_cloud 传输, 归一回 {status, json, text, error}) ──
def _post(url: str, headers: Dict[str, str], body: Any,
          timeout_ms: Optional[int] = None) -> Dict[str, Any]:
    r = dc.json_request("POST", url, headers, body or {}, timeout_ms)
    return {"status": r["status"], "json": r["json"] or {}, "text": r["text"]}


def _get(url: str, headers: Dict[str, str],
         timeout_ms: Optional[int] = None) -> Dict[str, Any]:
    r = dc.json_request("GET", url, headers, None, timeout_ms)
    return {"status": r["status"], "json": r["json"] or {}, "text": r["text"]}


def _uuid4() -> str:
    return str(_uuid.uuid4())


# ── 计划/额度解析 (源 devin-core.js:222-257) ────────────────────────────────
def billing_dollars(b: Optional[Dict[str, Any]]) -> float:
    """源 devin-core.js:222 billingDollars — 可用美金 = max(0,available)+max(0,overage), 封顶 1000。"""
    if not isinstance(b, dict):
        return 0.0
    avail = b.get("available_credits")
    ovg = b.get("overage_credits")
    avail = avail if isinstance(avail, (int, float)) and math.isfinite(avail) else 0
    ovg = ovg if isinstance(ovg, (int, float)) and math.isfinite(ovg) else 0
    d = max(0.0, float(avail)) + max(0.0, float(ovg))
    return min(1000.0, round(d * 100) / 100.0)


def _gi(d: Dict[str, Any], *keys: str) -> int:
    for k in keys:
        v = d.get(k) if isinstance(d, dict) else None
        if v is not None:
            try:
                return int(v)
            except (ValueError, TypeError):
                pass
    return 0


def _gs(d: Dict[str, Any], *keys: str) -> str:
    for k in keys:
        v = d.get(k) if isinstance(d, dict) else None
        if v is not None:
            return str(v)
    return ""


def parse_plan_status(j: Dict[str, Any]) -> Dict[str, Any]:
    """源 devin-core.js:230 parsePlanStatus — GetUserStatus → 归一计划/额度。"""
    us = j.get("userStatus") or j.get("user_status") or {}
    ps = (us.get("planStatus") or us.get("plan_status")
          or j.get("planStatus") or j.get("plan_status") or j)
    pi = (ps.get("planInfo") or ps.get("plan_info")
          or us.get("planInfo") or us.get("plan_info") or {})
    weekly = _gi(ps, "weeklyQuotaRemainingPercent", "weekly_quota_remaining_percent")
    daily = _gi(ps, "dailyQuotaRemainingPercent", "daily_quota_remaining_percent")
    if (not ps.get("dailyQuotaRemainingPercent")
            and not ps.get("daily_quota_remaining_percent") and weekly > 0):
        daily = weekly
    return {
        "planName": _gs(pi, "planName", "plan_name"),
        "teamsTier": _gs(pi, "teamsTier", "teams_tier"),
        "planStart": _gs(ps, "planStart", "plan_start"),
        "planEnd": _gs(ps, "planEnd", "plan_end"),
        "wPct": weekly, "dPct": daily,
        "availablePromptCredits": _gi(ps, "availablePromptCredits", "available_prompt_credits"),
        "availableFlowCredits": _gi(ps, "availableFlowCredits", "available_flow_credits"),
        "_source": "GetUserStatus",
    }


def fetch_overage_dollars(auth1: str, org_id: str) -> Optional[float]:
    """源 devin-core.js:249 fetchOverageDollars — billing/status 取美金余额 (失败回 None)。"""
    if not auth1 or not org_id:
        return None
    bare = re.sub(r"^org-", "", org_id)
    br = _get(APP + "/api/org-" + bare + "/billing/status",
              {"Authorization": "Bearer " + auth1, "x-cog-org-id": org_id})
    if br["status"] == 200 and br["json"]:
        return billing_dollars(br["json"])
    return None


def _fetch_quota_raw(api_key: str, windsurf_key: str, auth1: str,
                     org_id: str, api_server_url: str = "") -> Optional[Dict[str, Any]]:
    """源 devin-core.js:180 _devinFetchQuotaRaw — GetUserStatus 多端点回退 + billing 兜底。"""
    status_key = api_key if (api_key and not api_key.startswith("cog_")) else (windsurf_key or "")
    if status_key:
        tries: List[str] = []
        if api_server_url:
            tries.append(re.sub(r"/+$", "", api_server_url)
                         + "/exa.seat_management_pb.SeatManagementService/GetUserStatus")
        for u in URL_GET_USER_STATUS:
            if u not in tries:
                tries.append(u)
        metadata = {"ideName": "windsurf", "ideVersion": "1.99.0", "extensionName": "windsurf",
                    "extensionVersion": "1.99.0", "apiKey": status_key, "sessionId": _uuid4(),
                    "requestId": "1", "locale": "en", "os": "windows"}
        for u in tries:
            r = _post(u, {"Connect-Protocol-Version": "1", "X-Api-Key": status_key},
                      {"metadata": metadata})
            if 200 <= r["status"] < 300 and r["json"]:
                ps = parse_plan_status(r["json"])
                od = fetch_overage_dollars(auth1, org_id)
                if od is not None:
                    ps["overageDollars"] = od
                    ps["overageKnown"] = True
                    ps["overageTs"] = int(time.time() * 1000)
                else:
                    ps["overageKnown"] = False
                return ps
            if r["status"] in (401, 400):
                break
    # 回退: Devin billing (源 devin-core.js:206)
    if auth1 and org_id:
        bare = re.sub(r"^org-", "", org_id)
        br = _get(APP + "/api/org-" + bare + "/billing/status",
                  {"Authorization": "Bearer " + auth1, "x-cog-org-id": org_id})
        if br["status"] == 200 and br["json"]:
            d = billing_dollars(br["json"])
            has = (br["json"].get("has_subscription_or_credits") is True
                   or br["json"].get("is_subscription_valid") is True or d > 0)
            return {"planName": "Trial", "dPct": 100 if has else 0, "wPct": 100 if has else 0,
                    "overageActive": d > 0, "overageDollars": d, "overageKnown": True,
                    "overageTs": int(time.time() * 1000), "_source": "devin_billing"}
    return None


_q_cache: Dict[str, Dict[str, Any]] = {}


def _q_key(api_key: str, windsurf_key: str, auth1: str, org_id: str) -> str:
    sk = api_key if (api_key and not api_key.startswith("cog_")) else (windsurf_key or "")
    return (auth1 or "") + "|" + (org_id or "") + "|" + sk


def fetch_quota(api_key: str, windsurf_key: str, auth1: str, org_id: str,
                api_server_url: str = "", force: bool = False) -> Optional[Dict[str, Any]]:
    """源 devin-core.js:165 devinFetchQuota — 2s TTL 缓存吸收撞点重复; 仅缓存成功值。"""
    key = _q_key(api_key, windsurf_key, auth1, org_id)
    if not force:
        c = _q_cache.get(key)
        if c and (int(time.time() * 1000) - c["ts"]) < _Q_TTL_MS and c["data"]:
            return dict(c["data"])
    data = _fetch_quota_raw(api_key, windsurf_key, auth1, org_id, api_server_url)
    if data:
        _q_cache[key] = {"ts": int(time.time() * 1000), "data": data}
    return dict(data) if data else None


# ── Agent 真源五步登录链 (源 devin-core.js:104 devinLogin) ───────────────────
def agent_login(email: str, password: str, retry: int = 0) -> AgentAuth:
    """源 devin-core.js:104 devinLogin — 五步链:
    email+password → auth1 → sessionToken → orgId → apiKey → quota。
    429 指数退避重试 (≤3 次, 对应源 retry 分支)。
    """
    if not email or not password:
        return AgentAuth(ok=False, error="email and password required")

    # Step1: windsurf 密码登录 → auth1
    r1 = _post(URL_LOGIN, {"Origin": WINDSURF, "Referer": WINDSURF + "/account/login"},
               {"email": email, "password": password})
    if r1["status"] == 429 and retry < 3:
        time.sleep((2 ** retry) * 2.0)
        return agent_login(email, password, retry + 1)
    j1 = r1["json"]
    auth1 = j1.get("token") or j1.get("auth1_token")
    if r1["status"] != 200 or not auth1:
        detail = j1.get("detail") or j1.get("error") or j1.get("message") or ("HTTP %d" % r1["status"])
        return AgentAuth(ok=False, error="登录失败: " + str(detail))
    user_id = j1.get("user_id") or ""

    # Step2: WindsurfPostAuth → sessionToken (+accountId)
    r2 = _post(URL_POSTAUTH, {"Origin": WINDSURF, "Referer": WINDSURF + "/profile",
                              "Connect-Protocol-Version": "1", "X-Devin-Auth1-Token": auth1},
               {"auth1_token": auth1})
    j2 = r2["json"]
    session_token = j2.get("sessionToken") or j2.get("session_token") or ""
    if r2["status"] != 200 or not session_token:
        return AgentAuth(ok=False, error="PostAuth 失败: "
                         + str(j2.get("error") or j2.get("code") or j2.get("message") or "no_session"))

    # Step3: Devin post-auth → orgId/orgName/orgSlug
    r3 = _post(URL_DEVIN_POST_AUTH, {"Authorization": "Bearer " + auth1}, {})
    org_id, org_name, org_slug = _extract_org(r3["json"])
    if not org_id:
        return AgentAuth(ok=False, error="Devin PostAuth: 无 orgId")

    # Step4: RegisterUser → apiKey/apiServerUrl
    r4 = _post(URL_REGISTER, {"Connect-Protocol-Version": "1"},
               {"firebase_id_token": session_token})
    j4 = r4["json"]
    api_key = j4.get("api_key") or j4.get("apiKey") or session_token
    api_server_url = j4.get("api_server_url") or j4.get("apiServerUrl") or ""
    windsurf_key = api_key if (api_key and not api_key.startswith("cog_")) else ""

    # Step5: 额度 (非阻断)
    quota = None
    try:
        quota = fetch_quota(api_key, windsurf_key, auth1, org_id, api_server_url)
    except Exception:
        quota = None

    return AgentAuth(ok=True, auth1=auth1, user_id=user_id, org_id=org_id, org_name=org_name,
                     org_slug=org_slug, session_token=session_token, api_key=api_key,
                     windsurf_key=windsurf_key, api_server_url=api_server_url,
                     account_id=j2.get("accountId") or "", quota=quota)


def _extract_org(j3: Dict[str, Any]) -> tuple:
    """源 devin-core.js:126-131 — org 对象/顶层多字段名兜底 + 正则扫 org?id。"""
    org = j3.get("org") or {}
    org_id = org.get("org_id") or j3.get("org_id") or j3.get("orgId") or ""
    org_name = org.get("org_name") or j3.get("org_name") or j3.get("orgName") or ""
    org_slug = org.get("org_slug") or j3.get("org_slug") or j3.get("orgSlug") or ""
    if not org_id and isinstance(org, dict):
        for k, v in org.items():
            if re.search(r"org.?id", k, re.I):
                org_id = str(v)
                break
    return org_id, org_name, org_slug


def hydrate_auth1(auth1: str) -> AgentAuth:
    """源 devin-core.js:305 hydrateAuth1 — 用已有 auth1 补全 org + 额度 (无需邮密)。"""
    if not auth1:
        return AgentAuth(ok=False, error="无 auth1")
    r3 = _post(URL_DEVIN_POST_AUTH, {"Authorization": "Bearer " + auth1}, {})
    org_id, org_name, org_slug = _extract_org(r3["json"])
    if not org_id:
        return AgentAuth(ok=False, error="auth1 无效或已过期")
    quota = None
    try:
        quota = fetch_quota("", "", auth1, org_id)
    except Exception:
        quota = None
    return AgentAuth(ok=True, auth1=auth1, org_id=org_id, org_name=org_name,
                     org_slug=org_slug, user_id=r3["json"].get("user_id") or "", quota=quota)


def auth1_alive(auth1: str, org_id: str) -> bool:
    """源 devin-core.js:325 auth1Alive — billing/status 200 即令牌仍活。"""
    if not auth1 or not org_id:
        return False
    bare = re.sub(r"^org-", "", org_id)
    br = _get(APP + "/api/org-" + bare + "/billing/status",
              {"Authorization": "Bearer " + auth1, "x-cog-org-id": org_id})
    return br["status"] == 200


def clear_quota_cache() -> None:
    _q_cache.clear()
