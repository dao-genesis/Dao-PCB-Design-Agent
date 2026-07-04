# ☯ DAO LCEDA · 外接 Agent 接管文档 (AGENT_API.md)

> 本文档是"MD 通道": 任何外接 Agent(Devin/Copilot/自研)只需读完本文,
> 即可全方位接管 VS Code 插件底层, 驱动嘉立创EDA 从零到出产的全链路。
> 原生"第三方 API 通道"与本通道同源: 全部经本地桥 `http://127.0.0.1:9940`。

## 0. 体系一图

```
外接 Agent ──(本文档 MD 通道 / 原生 HTTP 通道)──▶ 桥 :9940 ──CDP──▶ 嘉立创EDA
VS Code 插件(vscode-dao-lceda): 中间面板 /panel · 左侧 /api/tree · 对话 /api/agent
```

- 桥仅监听 127.0.0.1, 零第三方依赖(纯 Python 标准库)。
- EDA 需带 CDP 启动(Web 版 :29229 / 桌面版 :29230), 桥自动发现目标。

## 1. 端点总览

| 端点 | 方法 | 作用 |
|---|---|---|
| `/api/health` | GET | 桥/CDP 目标状态 |
| `/api/frame` | GET | 最新画面 JPEG(呈现面) |
| `/api/input` | POST | 鼠标/键盘/字符注入(执行面) |
| `/api/verb` | POST | 官方 `_EXTAPI_ROOT_` 动词直调(反馈面) |
| `/api/eval` | POST | 页内 JS 求值(高阶, 仅本机) |
| `/api/tree` | GET | 工程树(左侧文件树数据源) |
| `/api/chat` | POST | 极简同步问答(旧通道, 保留兼容) |
| `/api/tools` | GET | **机器可读工具目录**(高阶工具清单+参数) |
| `/api/agent` | POST | **Copilot 式编排**: 自然语言或直调工具 → 异步作业 |
| `/api/agent/<job>` | GET | 轮询作业进度(步骤流式) |

## 2. 原生第三方 API 通道 (推荐)

### 2.1 发现能力

```bash
curl -s localhost:9940/api/tools
# → {"ok":true,"tools":[{"tool":"pcb.autoroute","params":{},"desc":"原生自动布线并轮询至稳定"},…]}
```

### 2.2 直调工具(异步作业)

```bash
curl -s -X POST localhost:9940/api/agent \
  -d '{"tool":"device.search","args":{"keyword":"STM32F103C8T6"}}'
# → {"ok":true,"reply":"已直调工具 device.search","job":"<jid>"}
curl -s localhost:9940/api/agent/<jid>
# → {"ok":true,"job":{"status":"done","steps":[{"tool":"device.search","status":"done","result":[…]}]}}
```

### 2.3 自然语言编排

```bash
curl -s -X POST localhost:9940/api/agent -d '{"text":"全链路"}'
# 编排: pcb.layout → pcb.outline → pcb.autoroute → pcb.pour → pcb.drc → fab.outputs
```

### 2.4 底层动词直调(与工具层并存)

```bash
curl -s -X POST localhost:9940/api/verb \
  -d '{"ns":"dmt_Project.getCurrentProjectInfo","args":[],"timeout":40}'
```

## 3. 高阶工具目录(dao_tools 沉淀·实战验证)

| 工具 | 参数 | 说明(含实战缺陷结论) |
|---|---|---|
| `project.info` | — | 当前工程信息 |
| `project.create` | name?, desc? | 建工程; **createProject 不切上下文 → 已内置 openProject 修正** |
| `device.search` | keyword | 元件库检索; **只收关键字一个参数(多传分页参数返回空)·返回形 list/分页两种 → 均已归一** |
| `sch.place` | uuid, libraryUuid, x, y, designator? | 确定性放件(create 8 参真实签名 + getState_PrimitiveId) |
| `sch.wire` | componentId, netmap{pin:net} | 连接即命名; **斜线/浮点端点必失败 → 已内置轴对齐取整** |
| `sch.save` | — | 保存原理图 |
| `pcb.sync` | — | 原理图→PCB 同步(importChanges + GUI 应用修改兜底) |
| `pcb.layout` | pitch? | 网络亲和布局(连通度排序+贪心近邻, 实测过孔 21→8) |
| `pcb.outline` | margin? | 按引脚包络自动板框 |
| `pcb.autoroute` | — | 原生自动布线(GUI Route→Auto Routing→Run + 铜线数稳定判据) |
| `pcb.pour` | margin? | 双面 GND 覆铜 + Shift+B 重建 |
| `pcb.drc` | — | DRC(长动词, 桥透传 ≤120s 超时) |
| `fab.outputs` | prefix? | Gerber/BOM/贴片坐标(blob→base64→落盘) |
| `canvas.image` | — | 画布渲染图 |

## 4. MD 通道操作范式(给外接 Agent 的最短配方)

1. `GET /api/health` 确认桥活; 不活则 `python3 bridge_server.py`(EDA 需已带 CDP 启动并登录)。
2. `GET /api/tools` 拿目录 → 按 §3 组合调用 `/api/agent`。
3. 长链路(布线/覆铜/出产)一律走异步作业, 1.5s 间隔轮询 `/api/agent/<job>`。
4. 电路描述与工具解耦: 参照 `project_bluepill.py` 的 `CIRCUIT`(BOM+netmap)格式,
   逐件 `device.search → sch.place → sch.wire`, 再 `全链路` 一键收尾。
5. 出错即缺陷线索: 把 `steps[].error` 原文沉淀, 修 dao_tools 而非绕过。

## 5. Python SDK(零依赖)

```python
import json, time, urllib.request
B = "http://127.0.0.1:9940"
def api(p, body=None, t=90):
    d = json.dumps(body).encode() if body else None
    return json.load(urllib.request.urlopen(urllib.request.Request(
        B+p, data=d, headers={"Content-Type": "application/json"}), timeout=t))
def agent(text=None, tool=None, args=None, wait=600):
    r = api("/api/agent", {"text": text} if text else {"tool": tool, "args": args or {}})
    if not r.get("job"):
        return r
    for _ in range(int(wait / 1.5)):
        j = api("/api/agent/" + r["job"])["job"]
        if j["status"] != "running":
            return j
        time.sleep(1.5)
agent(text="当前工程信息")
```

*道法自然 · 无为而无不为*
