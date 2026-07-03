# ☯ Dao KiCad AI IDE · 反向接入文档 (Agent Access)

> 本文档供云端 Agent (Devin Cloud 等) 读取, 直连并原生操作这套 KiCad AI IDE:
> 看项目全貌 / 驱动活板 / 调用 KiCad 工具 / 跑 agent 对话回合。

## 接入信息

```
URL:   http://127.0.0.1:8323
Token: <token>
Auth:  Authorization: Bearer <token>   (/api/health 免鉴权)
```

公网接入: 本机执行 `cloudflared tunnel --url http://127.0.0.1:8323` 即得公网 URL, 端点/鉴权不变。

## 端点

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 活性探测 (免鉴权) → `{"ok":true,"service":"dao-kicad-ai-ide"}` |
| GET | `/api/state` | **项目全貌** (先看这个再动手): 板况/DRC/流程/产物/git/动作日志 |
| GET | `/api/state.md` | 同上, Markdown 一页 (text/markdown) |
| GET | `/api/tools` | KiCad 工具清单 (OpenAI function-call schema) |
| POST | `/api/tool` | `{"name":"kicad_board_summary","args":{}}` 调任一工具 |
| POST | `/api/eval` | `{"code":"len(board.GetFootprints())"}` 活板进程内执行 (board 已绑定) |
| POST | `/api/chat` | `{"text":"把 C11 移到 (79,30)","conversation":"conv-…"?}` 跑一整回合 agent loop |
| GET | `/api/conversations` | 对话列表 |
| GET | `/api/doc` | 本文档 |

## Quickstart (curl)

```bash
curl -s http://127.0.0.1:8323/api/health
curl -s -H "Authorization: Bearer <token>" http://127.0.0.1:8323/api/state
curl -s -H "Authorization: Bearer <token>" -X POST http://127.0.0.1:8323/api/eval \
     -d '{"code":"len(board.GetFootprints())"}'
```

## Python SDK (零依赖)

```python
import json, urllib.request
URL, TOKEN = "http://127.0.0.1:8323", "<token>"
def api(method, path, body=None, t=180):
    req = urllib.request.Request(URL + path,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer " + TOKEN,
                 "Content-Type": "application/json"}, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=t).read())

print(api("GET", "/api/state"))                       # 先看全貌
print(api("POST", "/api/eval", {"code": "board.GetFileName()"}))
print(api("POST", "/api/chat", {"text": "报告当前板况"}))
```

## 约定

* 一切回值 JSON: 成功 `{"ok":true,...}`, 失败 `{"ok":false,"error":"..."}`。
* `/api/chat` 为同步整回合 (含多轮工具调用), 回 `content` + `steps` 轨迹; 长任务
  请调大超时 (工具步可能触活板/DRC)。
* 每次工具调用自动追记项目动作日志 → 之后 `/api/state` 的 journal 可见 (史料闭环)。

*道法自然 · 无为而无不为*
