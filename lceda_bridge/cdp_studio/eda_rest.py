#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""eda_rest — 嘉立创EDA Pro 账号/工程生命周期的 REST 绑定(与 eda_api 的编辑器内 extapi 互补)。

道并行而不相悖:本源是两层:
  · 账号层(本模块):工程的增删查改、文件夹、团队、用户 —— 走同源 REST `/api/*`,
    用浏览器已登录的 cookie 直连 pro.lceda.cn(Python 直发,绕过浏览器 Service Worker)。
  · 编辑器层(eda_api.py):工程/文档打开后,经 CDP 调 `window._EXTAPI_ROOT_` 操作原理图/PCB 图元。

为何分两层:editor 页的 `_EXTAPI_ROOT_.dmt_Project.createProject` 在本上下文是空操作
(其 getAllProjectsUuid 只反映"当前已打开工程"),真正的账号级工程 CRUD 由 REST 承载。

cookie 来源:从正在运行的编辑器页经 CDP `Network.getCookies` 实时抓取(登录态已由冷启动固化)。

用法:
    from eda_rest import EdaRest
    r = EdaRest()                       # 自动从 CDP 抓取登录 cookie
    r.list_projects()                   # → [{uuid,name,path,...}, ...]
    r.create_project("我的工程")        # → {uuid, name, path, ...}
    r.get_user(); r.get_teams(); r.get_folders()

依赖:仅标准库 + dao_eda_cdp_driver(同目录,用于抓 cookie)。
环境变量:DAO_CDP_PORT(默认 29229)
"""
import json
import os
import re
import ssl
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dao_eda_cdp_driver as d

BASE = "https://pro.lceda.cn"
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Dao-Agent"


class RestError(RuntimeError):
    pass


def get_cookies(port=None, host_url=BASE + "/"):
    """从运行中的编辑器页抓取 cookie,返回 Cookie 头字符串。"""
    ws = d.connect_editor(port or d.CDP_PORT)
    ws.cmd("Network.enable", {}, timeout=3)
    res = ws.cmd("Network.getCookies", {"urls": [host_url]}, timeout=10)
    cookies = (res or {}).get("result", {}).get("cookies", [])
    return "; ".join("%s=%s" % (c["name"], c["value"]) for c in cookies), cookies


class EdaRest:
    def __init__(self, port=None, cookie_header=None):
        self.port = port or d.CDP_PORT
        if cookie_header is None:
            cookie_header, cookies = get_cookies(self.port)
            self._csrf = next((c["value"] for c in cookies if c["name"] == "oshwhub_csrf"), "")
        else:
            self._csrf = ""
        self.cookie = cookie_header
        self._ctx = ssl.create_default_context()

    # --- 底层 ---
    def api(self, method, path, body=None, timeout=30):
        url = path if path.startswith("http") else BASE + path
        headers = {
            "Cookie": self.cookie,
            "Accept": "application/json, text/plain, */*",
            "User-Agent": _UA,
            "Referer": BASE + "/editor",
        }
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json;charset=UTF-8"
            if self._csrf:
                headers["X-CSRF-Token"] = self._csrf
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=timeout, context=self._ctx) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, dict) and payload.get("success") is False:
            raise RestError("%s %s -> %s" % (method, path, payload.get("message") or payload))
        return payload

    def result(self, method, path, body=None, timeout=30):
        """返回 payload['result'](API 统一包了 {success,code,result})。"""
        p = self.api(method, path, body, timeout)
        return p.get("result", p) if isinstance(p, dict) else p

    # --- 用户 / 团队 / 文件夹 ---
    def get_user(self):
        return self.result("GET", "/api/user")

    def get_teams(self):
        return self.result("GET", "/api/teams")

    def get_folders(self):
        return self.result("GET", "/api/folder/getUserFolderAllData")

    # --- 工程生命周期 ---
    def list_projects(self, page=1, page_size=4000):
        r = self.result("GET", "/api/projects?page=%d&pageSize=%d" % (page, page_size))
        return r.get("lists", r) if isinstance(r, dict) else r

    def create_project(self, name, public=False, introduction="", owner_uuid=None):
        if owner_uuid is None:
            owner_uuid = self.get_user()["uuid"]
        path_slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "project"
        body = {
            "name": name, "public": public, "user_uuid": owner_uuid,
            "cbb_project": False, "introduction": introduction, "content": "",
            "default_sheet": "", "project_path": "%s/%s" % (self.get_user()["username"], path_slug),
            "mode": 1,
        }
        return self.result("POST", "/api/v4/projects/add", body)

    # 注:删除端点尚未测绘(/api/projects/{uuid} 存在但 DELETE 返回 405,需抓 GUI 真实请求确认),
    # 暂不提供 delete_project 以免误删;后续在实战中补齐。


if __name__ == "__main__":
    r = EdaRest()
    u = r.get_user()
    print("user:", u.get("username"), u.get("uuid"))
    ps = r.list_projects()
    print("projects: %d" % len(ps))
    for p in ps[:10]:
        print("  -", p["uuid"][:12], p["name"])
