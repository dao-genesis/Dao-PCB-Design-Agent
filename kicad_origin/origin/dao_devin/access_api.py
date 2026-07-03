"""access_api — 反向接入层: 本地 HTTP API, 供云端 Agent 原生接入本 KiCad AI IDE。

道法自然 · 参照 DAO Bridge / Devin Remote 插件同一逻辑: 本体一切功能确保之上,
再暴一个**带鉴权的本地 HTTP + JSON 面**并附自足文档 — 任何云端 Agent 读一遍文档
即可原生操作这套系统 (看全貌 / 驱活板 / 调工具 / 起对话), 无需用户手工搭桥。
可外挂内网穿透 (cloudflared tunnel 一行命令) 即成公网可达。

端点 (除 /api/health 外均需 Authorization: Bearer <token>):

  GET  /api/health         → 活性 (免鉴权)
  GET  /api/state          → 项目全貌 (project_state.snapshot)
  GET  /api/state.md       → 全貌 Markdown (一页读懂)
  GET  /api/tools          → 工具清单 (OpenAI function-call schema)
  POST /api/tool           → {"name","args"} 调任一注册工具
  POST /api/eval           → {"code"} 活板进程内执行 pcbnew 代码
  POST /api/focus          → {"refs":[…]} 画布选中+高亮+缩放定位 (AI 的光标)
  POST /api/save           → 保存活板 (Ctrl+S 内化)
  POST /api/chat           → {"text","conversation"?} 跑一整回合 agent loop
  GET  /api/conversations  → 对话列表
  GET  /api/doc            → 本接入文档 (Markdown, 自足)

零第三方依赖 (纯 stdlib http.server) → GUI 内/无头/CI 皆可起。token 自动生成并
持久化 ~/.dao/access-token (亦可显式传入)。

反臆造: 所有回值取自 bridge 的真实回传; 鉴权失败 401 明示, 不静默。
"""
from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional

from . import devin_cloud as dc
from . import project_state

API_VERSION = "1"
_TOKEN_FILE = "access-token"


def load_or_create_token(path: Optional[Path] = None) -> str:
    """token 持久化 ~/.dao/access-token (无则生成)。"""
    p = path or (dc._dao_home() / _TOKEN_FILE)
    if p.exists():
        t = p.read_text("utf-8").strip()
        if t:
            return t
    t = "dao-kicad-" + secrets.token_hex(16)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(t, "utf-8")
    return t


def render_access_doc(url: str = "http://127.0.0.1:8323",
                      token: str = "<token>") -> str:
    """自足接入文档 (Markdown): 云端 Agent 读一遍即可原生接入。"""
    return f"""# ☯ Dao KiCad AI IDE · 反向接入文档 (Agent Access)

> 本文档供云端 Agent (Devin Cloud 等) 读取, 直连并原生操作这套 KiCad AI IDE:
> 看项目全貌 / 驱动活板 / 调用 KiCad 工具 / 跑 agent 对话回合。

## 接入信息

```
URL:   {url}
Token: {token}
Auth:  Authorization: Bearer {token}   (/api/health 免鉴权)
```

公网接入: 本机执行 `cloudflared tunnel --url {url}` 即得公网 URL, 端点/鉴权不变。

## 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 活性探测 (免鉴权) → `{{"ok":true,"service":"dao-kicad-ai-ide"}}` |
| GET | `/api/state` | **项目全貌** (先看这个再动手): 板况/DRC/流程/产物/git/动作日志 |
| GET | `/api/state.md` | 同上, Markdown 一页 (text/markdown) |
| GET | `/api/tools` | KiCad 工具清单 (OpenAI function-call schema) |
| POST | `/api/tool` | `{{"name":"kicad_board_summary","args":{{}}}}` 调任一工具 |
| POST | `/api/eval` | `{{"code":"len(board.GetFootprints())"}}` 活板进程内执行 (board 已绑定) |
| POST | `/api/focus` | `{{"refs":["R2","C11"]}}` 画布选中+高亮+缩放定位 (AI 的光标, 用户实时可见) |
| POST | `/api/save` | 保存活板到其文件 (Ctrl+S 内化, 无需触 GUI) |
| POST | `/api/chat` | `{{"text":"把 C11 移到 (79,30)","conversation":"conv-…"?}}` 跑一整回合 agent loop |
| GET | `/api/conversations` | 对话列表 |
| GET | `/api/doc` | 本文档 |

## Quickstart (curl)

```bash
curl -s {url}/api/health
curl -s -H "Authorization: Bearer {token}" {url}/api/state
curl -s -H "Authorization: Bearer {token}" -X POST {url}/api/eval \\
     -d '{{"code":"len(board.GetFootprints())"}}'
```

## Python SDK (零依赖)

```python
import json, urllib.request
URL, TOKEN = "{url}", "{token}"
def api(method, path, body=None, t=180):
    req = urllib.request.Request(URL + path,
        data=json.dumps(body).encode() if body else None,
        headers={{"Authorization": "Bearer " + TOKEN,
                 "Content-Type": "application/json"}}, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=t).read())

print(api("GET", "/api/state"))                       # 先看全貌
print(api("POST", "/api/eval", {{"code": "board.GetFileName()"}}))
print(api("POST", "/api/chat", {{"text": "报告当前板况"}}))
```

## 约定

* 一切回值 JSON: 成功 `{{"ok":true,...}}`, 失败 `{{"ok":false,"error":"..."}}`。
* `/api/chat` 为同步整回合 (含多轮工具调用), 回 `content` + `steps` 轨迹; 长任务
  请调大超时 (工具步可能触活板/DRC)。
* 每次工具调用自动追记项目动作日志 → 之后 `/api/state` 的 journal 可见 (史料闭环)。

*道法自然 · 无为而无不为*
"""


class _Handler(BaseHTTPRequestHandler):
    server_version = "DaoKiCadAIIDE/" + API_VERSION

    # ── util ──
    def _send(self, code: int, body: Any, ctype: str = "application/json") -> None:
        raw = (body if isinstance(body, (bytes, str)) else
               json.dumps(body, ensure_ascii=False))
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _authed(self) -> bool:
        tok = getattr(self.server, "dao_token", "")
        got = self.headers.get("Authorization", "")
        return bool(tok) and got == "Bearer " + tok

    def _body(self) -> Dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return {}

    def log_message(self, *_a: Any) -> None:  # 静音默认 stderr 日志
        pass

    @property
    def bridge(self) -> Any:
        return getattr(self.server, "dao_bridge")

    # ── 路由 ──
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            self._send(200, {"ok": True, "service": "dao-kicad-ai-ide",
                             "version": API_VERSION})
            return
        if not self._authed():
            self._send(401, {"ok": False, "error": "鉴权失败 (Bearer token)"})
            return
        try:
            if path == "/api/state":
                self._send(200, self.bridge.project_state())
            elif path == "/api/state.md":
                self._send(200, self.bridge.project_state_markdown(),
                           "text/markdown")
            elif path == "/api/tools":
                self._send(200, {"ok": True, "tools": self.bridge.ai_tools()})
            elif path == "/api/conversations":
                self._send(200, {"ok": True,
                                 "conversations": self.bridge.ai_conversations()})
            elif path == "/api/doc":
                info = getattr(self.server, "dao_info", {})
                self._send(200, render_access_doc(info.get("url", ""),
                                                  getattr(self.server, "dao_token", "")),
                           "text/markdown")
            else:
                self._send(404, {"ok": False, "error": "无此端点: %s" % path})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"ok": False, "error": "%s: %s" % (type(e).__name__, e)})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if not self._authed():
            self._send(401, {"ok": False, "error": "鉴权失败 (Bearer token)"})
            return
        body = self._body()
        try:
            if path == "/api/tool":
                r = self.bridge.registry().dispatch(
                    body.get("name", ""), body.get("args") or {})
                self.bridge.journal(body.get("name", "?"),
                                    body.get("args", ""), actor="remote")
                self._send(200, r)
            elif path == "/api/eval":
                r = self.bridge.live_eval(body.get("code", ""))
                self.bridge.journal("kicad_eval", body.get("code", ""),
                                    actor="remote")
                self._send(200, r)
            elif path == "/api/focus":
                r = self.bridge.live_focus(body.get("refs") or [])
                self.bridge.journal("kicad_focus", body.get("refs", ""),
                                    actor="remote")
                self._send(200, r)
            elif path == "/api/save":
                r = self.bridge.live_save()
                self.bridge.journal("kicad_save", "", actor="remote")
                self._send(200, r)
            elif path == "/api/chat":
                cid = body.get("conversation", "")
                if not cid:
                    c = self.bridge.ai_new_conversation(
                        channel=body.get("channel", ""))
                    cid = c["conversation"]["id"]
                r = self.bridge.ai_send(cid, body.get("text", ""))
                r["conversation_id"] = cid
                self._send(200, r)
            else:
                self._send(404, {"ok": False, "error": "无此端点: %s" % path})
        except Exception as e:  # noqa: BLE001
            self._send(500, {"ok": False, "error": "%s: %s" % (type(e).__name__, e)})


class AccessServer:
    """反向接入 HTTP 服务 (daemon 线程内跑, start/stop 幂等)。"""

    def __init__(self, bridge: Any, host: str = "127.0.0.1", port: int = 8323,
                 token: str = "") -> None:
        self.bridge = bridge
        self.host = host
        self.port = port
        self.token = token or load_or_create_token()
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> Dict[str, Any]:
        if self._httpd is not None:
            return self.info()
        self._httpd = ThreadingHTTPServer((self.host, self.port), _Handler)
        self.port = self._httpd.server_address[1]  # port=0 → 实际端口
        self._httpd.dao_bridge = self.bridge  # type: ignore[attr-defined]
        self._httpd.dao_token = self.token  # type: ignore[attr-defined]
        self._httpd.dao_info = self.info()  # type: ignore[attr-defined]
        self._thread = threading.Thread(target=self._httpd.serve_forever,
                                        daemon=True)
        self._thread.start()
        return self.info()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
            self._thread = None

    def info(self) -> Dict[str, Any]:
        url = f"http://{self.host}:{self.port}"
        return {"ok": True, "running": self._httpd is not None, "url": url,
                "port": self.port, "token": self.token,
                "doc": url + "/api/doc", "health": url + "/api/health"}

    def write_conn_info(self, path: Optional[Path] = None) -> Path:
        """接入信息落盘 ~/.dao/kicad-access.json (供隧道侧/云端 Agent 零配置读取)。"""
        p = path or (dc._dao_home() / "kicad-access.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.info(), ensure_ascii=False, indent=2),
                     "utf-8")
        return p

    def write_doc(self, path: Path) -> Path:
        """把接入文档落盘 (供分发给云端 Agent / 提交进知识库)。"""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(render_access_doc(self.info()["url"], self.token), "utf-8")
        return p


def write_state_and_doc(project_dir: Path, server: Optional[AccessServer] = None) -> Dict[str, str]:
    """一键刷新: 项目全貌落盘 + (如服务在跑) 接入文档落盘。"""
    out = project_state.write_state(project_dir)
    if server is not None:
        out["access_doc"] = str(server.write_doc(
            Path(project_dir) / "AGENT_ACCESS.md"))
    return out
