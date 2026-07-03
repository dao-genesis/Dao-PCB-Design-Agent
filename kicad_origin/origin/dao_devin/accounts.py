"""accounts — 多账号池 (WAM · 反向注入 · 一键切号) 的最小 Python 实现。

移植自 devin-remote/core/dao-vsix 的 wam.* 账号管理 (Windsurf Account Manager) 的
核心数据面: 账号池落盘、当前活动号、健康/黑名单、按需登录取号。UI 侧的
「浏览器多实例/IDE 内路由多实例」在桌面 dao-vsix 里靠反代实现; 在 KiCad 里我们
只需要「哪个号是当前活动号 + 用它的 auth1 驱动 Devin Cloud」, 故此处只落数据面与
选号策略, 不搬反代。

反臆造: 账号凭据只落用户本机 ~/.dao (与 dao-vsix 同域), 明文 token 不写入仓库。
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import devin_cloud as dc


def _accounts_path() -> Path:
    return dc._dao_home() / "devin-accounts.json"


@dataclass
class Account:
    email: str
    password: str = ""          # 仅落用户本机 ~/.dao; 支持改用 token 免密
    token: str = ""             # 可选: 直接给 auth1 (反向注入·免登录)
    org_id: str = ""
    org_name: str = ""
    label: str = ""             # 展示名
    disabled: bool = False      # 黑名单/停用
    added_at: int = 0

    def redacted(self) -> Dict[str, Any]:
        """脱敏视图 (面板展示用): 不外泄 password/token 明文。"""
        d = asdict(self)
        d["password"] = "***" if self.password else ""
        d["token"] = (self.token[:6] + "…") if self.token else ""
        return d


@dataclass
class Pool:
    accounts: List[Account] = field(default_factory=list)
    active_email: str = ""

    def find(self, email: str) -> Optional[Account]:
        key = str(email).lower()
        for a in self.accounts:
            if a.email.lower() == key:
                return a
        return None


def load_pool() -> Pool:
    raw = dc.read_json(_accounts_path(), {})
    accs = [Account(**{k: v for k, v in a.items() if k in Account.__dataclass_fields__})
            for a in (raw.get("accounts") or [])]
    return Pool(accounts=accs, active_email=raw.get("active_email", ""))


def save_pool(pool: Pool) -> None:
    dc.write_json(_accounts_path(), {
        "accounts": [asdict(a) for a in pool.accounts],
        "active_email": pool.active_email,
    })


def add_account(email: str, password: str = "", token: str = "",
                label: str = "") -> Pool:
    """加入账号 (幂等: 同 email 覆盖凭据)。第一个加入的自动成为活动号。"""
    pool = load_pool()
    existing = pool.find(email)
    if existing:
        if password:
            existing.password = password
        if token:
            existing.token = token
        if label:
            existing.label = label
    else:
        pool.accounts.append(Account(email=email, password=password, token=token,
                                     label=label or email, added_at=int(time.time())))
    if not pool.active_email:
        pool.active_email = email
    save_pool(pool)
    return pool


def remove_account(email: str) -> Pool:
    pool = load_pool()
    pool.accounts = [a for a in pool.accounts if a.email.lower() != str(email).lower()]
    if pool.active_email.lower() == str(email).lower():
        pool.active_email = pool.accounts[0].email if pool.accounts else ""
    save_pool(pool)
    return pool


def switch_account(email: str) -> Pool:
    """一键切号: 把活动号切到 email (对应 wam.switchAccount)。"""
    pool = load_pool()
    if not pool.find(email):
        raise ValueError(f"账号池无此号: {email}")
    pool.active_email = email
    save_pool(pool)
    return pool


def set_disabled(email: str, disabled: bool) -> Pool:
    pool = load_pool()
    a = pool.find(email)
    if a:
        a.disabled = disabled
        save_pool(pool)
    return pool


def list_accounts() -> List[Dict[str, Any]]:
    """脱敏账号列表 (面板展示)。"""
    pool = load_pool()
    out = []
    for a in pool.accounts:
        v = a.redacted()
        v["active"] = a.email.lower() == pool.active_email.lower()
        out.append(v)
    return out


def ensure_account_auth(email: str, force: bool = False) -> Dict[str, Any]:
    """按需为某账号取 auth (对应 dao-vsix ensureAccountAuth): 优先用直给的 token
    (反向注入·免登录), 否则用池内密码登录。取号落 devin_cloud 的登录态缓存。"""
    pool = load_pool()
    a = pool.find(email)
    if not a:
        return {"ok": False, "error": f"账号池无此号: {email}"}
    if a.disabled:
        return {"ok": False, "error": f"账号已停用: {email}"}
    if a.token:
        # 反向注入: 直接以给定 auth1 组装 (org 通过 post-auth 补全)
        org_resp = dc.json_request("POST", dc.CFG.api_base + "/users/post-auth",
                                   {"Authorization": "Bearer " + a.token}, {})
        od = org_resp["json"] or {}
        org_id = od.get("org_id") or od.get("orgId") or a.org_id or ""
        if not org_id:
            return {"ok": False, "error": f"token post-auth 无 org_id (HTTP {org_resp['status']})"}
        return {"ok": True, "auth": dc.Auth(
            auth1=a.token, org_id=org_id,
            org_bare=org_id[4:] if org_id.startswith("org-") else org_id,
            org_name=od.get("org_name") or a.org_name or "", email=email)}
    if not a.password:
        return {"ok": False, "error": f"账号无密码且无 token, 无法取号: {email}"}
    return dc.get_auth(email, a.password, force=force)


def active_auth(force: bool = False) -> Dict[str, Any]:
    """取当前活动号的 auth。"""
    pool = load_pool()
    if not pool.active_email:
        return {"ok": False, "error": "账号池为空 / 未设活动号"}
    return ensure_account_auth(pool.active_email, force=force)


def fleet_overview() -> Dict[str, Any]:
    """全池概览: 逐号取 auth + accountOverview, 任一失败降级不毁整份 (无为·大成若缺)。"""
    pool = load_pool()
    out: List[Dict[str, Any]] = []
    for a in pool.accounts:
        entry: Dict[str, Any] = {"email": a.email, "label": a.label or a.email,
                                 "active": a.email.lower() == pool.active_email.lower(),
                                 "disabled": a.disabled}
        if a.disabled:
            entry["overview"] = None
            entry["error"] = "disabled"
            out.append(entry)
            continue
        try:
            r = ensure_account_auth(a.email)
            if r.get("ok"):
                entry["overview"] = dc.account_overview(r["auth"])
            else:
                entry["overview"] = None
                entry["error"] = r.get("error")
        except Exception as e:  # noqa: BLE001
            entry["overview"] = None
            entry["error"] = str(e)
        out.append(entry)
    return {"active_email": pool.active_email, "accounts": out}
