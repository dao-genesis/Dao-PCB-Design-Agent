# 道直连器 (Dao Connector)

> **道法自然 · 无为而无不为 · 玄之又玄, 众妙之门**
>
> 任意 agent · 任意用户 · 任意电脑 — 一行打通嘉立创EDA Pro 之底层之码.
>
> 用户五感可观: agent 之所行, 在 EDA DevTools console / events.jsonl / SSE 流, 三处皆见.

---

## 〇、道之总纲

```text
任意 agent (Claude/GPT/Cursor/Windsurf/任意 LLM)
     │
     ├── MCP stdio JSON-RPC ──────┐
     ├── HTTP REST /v1/* ─────────┤
     ├── OpenAI tool schema ──────┤
     └── Python SDK (DaoConnector)│
                                  ▼
                       ┌─────────────────────────┐
                       │     道直连器 (Dao)       │
                       │   ┌─────────────────┐   │
                       │   │ env_finder      │ ◀─── 跨机自动发现 (注册表/默认路径)
                       │   ├─────────────────┤   │
                       │   │ dao_connector   │ ◀─── 一键自驾 (locate→spawn→connect)
                       │   ├─────────────────┤   │
                       │   │ tools_registry  │ ◀─── 17 个高层工具 + JSON Schema
                       │   ├─────────────────┤   │
                       │   │ observer        │ ◀─── pre/post 钩子 (五感可观)
                       │   └─────────────────┘   │
                       │            │             │
                       │   BusTransport (CDP+总线)│
                       └────────────┼────────────┘
                                    │
                                    ▼
                       嘉立创EDA Pro renderer
                       (eda 沙箱内任意 API)
```

**道之三诀**:

1. **直连**: 不需要扩展, 不需要登录, 不需要 UI 操作 — `--remote-debugging-port=9222` 即通.
2. **代行**: agent 调一句, EDA 内任一类任一方法皆可达.
3. **可观**: 用户在 EDA DevTools / events.jsonl / SSE 流 三处皆见.

---

## 一、三块基石

### 1.1 `core/env_finder.py` — 跨机自动发现

**职责**: 任意电脑、任意安装路径都能定位嘉立创EDA本机环境.

**11 字段**:

| 字段 | 用途 |
|------|------|
| `lceda_exe` | lceda-pro.exe 主进程 |
| `lceda_home` | exe 所在目录 |
| `lceda_resources` | resources/app |
| `lceda_app_js` | resources/app/app.js (2.3MB 主进程) |
| `lceda_assets_dir` | resources/app/assets (22 资源目录) |
| `lceda_elib` | assets/db/lceda-std.elib (380MB 标准库) |
| `lceda_api_dir` | assets/pro-api/{version} |
| `lceda_user_root` | ~/Documents/LCEDA-Pro |
| `lceda_web_db` | ~/Documents/LCEDA-Pro/database/web.db (41MB) |
| `lceda_backup_dir` | 用户工程备份目录 |
| `jlc_assistant_exe` | 嘉立创下单助手 |

**发现策略** (优先级):

1. 缓存 `~/.lceda_dao/found.json`
2. 环境变量 `LCEDA_HOME` / `JLC_ASSISTANT_HOME` / `LCEDA_USER_ROOT`
3. Windows 注册表 (`HKCU\Software\嘉立创EDA`, `App Paths`)
4. 默认安装位置扫描 (`D:\lceda-pro` / `C:\Program Files` / 等)
5. PATH (`shutil.which("lceda-pro")`)
6. 多用户机器 fallback: 扫所有 `C:\Users\*\Documents\LCEDA-Pro`

**用法**:

```bash
python lceda_cli.py dao-find             # 报告
python lceda_cli.py dao-find --refresh   # 忽略缓存重扫
python lceda_cli.py dao-find --json      # JSON 输出
```

### 1.2 `core/dao_connector.py` — 一键自驾

**5 步流程** (auto):

```python
from core.dao_connector import DaoConnector

with DaoConnector().auto() as dao:
    info = dao.eda.dmt_Project.getCurrentProjectInfo()
    ver = dao.eda.sys_Environment.getEditorVersion()
```

内部:

1. **locate()** — 调 env_finder
2. **ensure_eda(spawn=True)** — EDA 未运行则启动 `lceda-pro.exe --remote-debugging-port=9222`
3. **ensure_bridge(spawn=False)** — 仅 mode="http" 时启动 :9907
4. **connect(mode="bus")** — 注入 BusTransport (CDP+_MSG_BUS2_EXTAPI_)
5. **diagnose()** — 沙箱探测 (`eda` 类列表 + 总线状态)

**3 种 mode**:

- `bus`  ── BusTransport (CDP+总线, 推荐, 无需扩展) ★
- `http` ── HttpTransport (走 :9907, 需 EDA 内装 lceda-bridge.eext)
- `cdp`  ── CdpTransport (主 page Runtime.evaluate, eda 不可见, 仅 DOM)

### 1.3 `core/tools_registry.py` — 工具注册中心

**31 个高层语义工具** (按 domain) — 17 API-level + 9 UI-level + 5 flow-level (反者):

| Domain | 工具名 | 副作用 | 描述 |
|--------|--------|--------|------|
| environment | `eda.environment.info` | read | ★ 编辑器版本/在线模式/客户端类型/Pro 判定 |
| project | `eda.project.current` | read | ★ 当前打开工程详细信息 |
| project | `eda.project.list` | read | 所有工程列表 |
| project | `eda.project.open` | interactive | 按 UUID 打开工程 |
| document | `eda.document.list` | read | 当前工程内文档列表 |
| document | `eda.document.active` | read | 当前激活文档信息 |
| component | `eda.component.search` | read | 关键字搜索元件库 |
| pcb | `eda.pcb.drc` | write | DRC 设计规则检查 |
| pcb | `eda.pcb.export_gerber` | destructive | 导出 Gerber 制造文件 |
| sch | `eda.sch.netlist` | read | 导出原理图网表 |
| bom | `eda.bom.export` | read | 导出 BOM 物料清单 |
| system | `eda.system.notify` | interactive | 在 EDA 内弹消息 (用户能看到) |
| system | `eda.system.console_log` | write | 在 EDA DevTools 输出 |
| system | `eda.system.call` | write | (高级) 调任意 `eda.<class>.<method>(args)` |
| system | `eda.system.eval` | destructive | (高级) 沙箱内执行 JS [需 bus] |
| system | `eda.system.introspect` | read | (自省) 列 eda 顶层对象/方法 [需 bus] |
| dao | `eda.dao.diagnose` | read | 道直连器自诊断 |
| ui | `eda.ui.narrate` | interactive | 顶部弹 toast 横幅 (用户可见) |
| ui | `eda.ui.screenshot` | read | ★ 截 EDA 画面存档 (供 agent 视觉反馈) |
| ui | `eda.ui.click_at` | interactive | 按坐标点击 (真 CDP Input.dispatchMouseEvent) |
| ui | `eda.ui.click_text` | interactive | ★ 点含某文字的按钮 (不需 agent 算坐标) |
| ui | `eda.ui.drag` | interactive | 鼠标拖拽 (PCB 移元件/SCH 拉框) |
| ui | `eda.ui.scroll` | interactive | 滚轮 (画布缩放/翻页) |
| ui | `eda.ui.type` | interactive | 键盘逐字输入 (Input.dispatchKeyEvent) |
| ui | `eda.ui.hotkey` | interactive | 快捷键组合 (Ctrl+S/F2/Esc) |
| ui | `eda.ui.find` | read | ★ 扫视屏上可点元素 (agent 视觉地图) |

**每个工具携带**:

- `name` / `description` (中文给 LLM 看)
- `input_schema` (JSON Schema, 严格定义参数)
- `side_effect` (read/write/interactive/destructive)
- `visibility` (silent/log/toast/highlight, observer 用)
- `handler` (Callable, 内部用 `_try_paths` 候选链兜底)
- `to_mcp()` / `to_openai()` 双格式输出

**逃生口**: 三件法宝让 agent 自我修正

- `eda.system.call` — 调任意已知 dot-path
- `eda.system.eval` — 沙箱执行任意 JS
- `eda.system.introspect` — 列出 eda 类与方法 (动态自学习)

---

## 二、三协议外露

### 2.1 MCP server (stdio JSON-RPC)

按 **MCP 2024-11-05 spec**, 不依赖 `mcp` pip 包.

**支持 method**:

- `initialize` ← 握手
- `notifications/initialized` ← 客户端 notify
- `tools/list` ← 列工具
- `tools/call` ← 调用 (懒加载道直连器)
- `ping`

**启动**:

```bash
python lceda_cli.py mcp                   # stdio
# 或
python -m core.mcp_server
```

**生成客户端配置**:

```bash
python lceda_cli.py mcp-config --target claude   > claude_desktop_config.json
python lceda_cli.py mcp-config --target cursor   > .cursor/mcp.json
python lceda_cli.py mcp-config --target windsurf > .windsurf/mcp.json
```

输出示例:

```json
{
  "mcpServers": {
    "lceda-dao": {
      "command": "python",
      "args": ["-m", "core.mcp_server"],
      "cwd": "<.../lceda_bridge>",
      "env": {"PYTHONIOENCODING": "utf-8"}
    }
  }
}
```

**懒加载**: server 启动时不连 EDA, 第一次 `tools/call` 才 `DaoConnector.auto()`. 用户能看到 EDA 窗口弹出 (`spawn=True`).

### 2.2 HTTP REST (五端点)

`lceda_bridge_server.py serve` 监听 `:9907`, 在已有传统桥之上加:

| 路径 | 方法 | 用途 |
|------|------|------|
| `/v1/info` | GET | 服务器信息: name/version/tools_count/sessions |
| `/v1/tools` | GET | 工具列表 (MCP schema 格式) |
| `/v1/openai` | GET | 工具列表 (OpenAI tool calling 格式) |
| `/v1/exec` | POST | `{name, arguments}` → ExecResult |
| `/v1/events` | GET | text/event-stream — SSE 实时事件流 |

**任意 LLM 调用**:

```bash
curl http://127.0.0.1:9907/v1/tools | jq '.tools[] | .name'

curl -X POST http://127.0.0.1:9907/v1/exec \
  -H 'Content-Type: application/json' \
  -d '{"name": "eda.environment.info", "arguments": {}}'

# 实时事件流
curl -N http://127.0.0.1:9907/v1/events
```

### 2.3 Python SDK

```python
from core.dao_connector import DaoConnector
from core import tools_registry

with DaoConnector().auto() as dao:
    # 方式 1: 走 EDA 代理 (动态属性链)
    info = dao.eda.sys_Environment.getEditorVersion()

    # 方式 2: 走工具注册中心 (有 schema 校验 + observer 钩子)
    out = tools_registry.execute(dao.transport, "eda.project.current", {})
    print(out.to_dict())
```

---

## 三、五感可观

### 3.1 events.jsonl 持久化

`~/.lceda_dao/events.jsonl` ─ 每次工具调用前后写两行:

```json
{"seq":1,"ts":1777547820.12,"type":"tool.pre","tool":"eda.project.current",...}
{"seq":2,"ts":1777547820.45,"type":"tool.post","tool":"eda.project.current","ok":true,"duration_ms":328.5,...}
```

查看:

```bash
python lceda_cli.py events            # 最近 20 条
python lceda_cli.py events -n 100     # 最近 100 条
python lceda_cli.py events --stats    # 按工具聚合统计
```

### 3.2 EDA 内 console.log (DevTools 可见)

`TransportObserver` 在 BusTransport 模式下, 每次调用前后:

```javascript
console.log("[Agent] → eda.project.current(params=[])")
console.log("[Agent] ✓ eda.project.current in 328.5ms")
```

用户在嘉立创EDA Pro 中: **F12 → Console** 即可见.

### 3.3 SSE 实时流

任意 web 客户端订阅 `/v1/events`, 收 `exec.pre` / `exec.post` / `exec.error` 事件:

```javascript
const es = new EventSource('http://127.0.0.1:9907/v1/events');
es.addEventListener('exec.pre', e => console.log('PRE:', JSON.parse(e.data)));
es.addEventListener('exec.post', e => console.log('POST:', JSON.parse(e.data)));
```

---

## 四、任意 agent 接入指南

### Claude Desktop

```bash
python lceda_cli.py mcp-config --target claude
# 把输出的 JSON 放进:
#   Windows: %APPDATA%\Claude\claude_desktop_config.json
#   macOS:   ~/Library/Application Support/Claude/claude_desktop_config.json
# 重启 Claude Desktop, 即可在对话里看到 17 个 lceda-dao 工具.
```

### Cursor

```bash
python lceda_cli.py mcp-config --target cursor
# 放进 ~/.cursor/mcp.json
```

### Windsurf

```bash
python lceda_cli.py mcp-config --target windsurf
# 放进 ~/.windsurf/mcp.json (或 IDE 的 MCP 设置面板)
```

### Cline (VSCode 扩展)

```bash
python lceda_cli.py mcp-config --target cline
# Cline 的 MCP 设置 → 粘贴
```

### OpenAI / GPT (function calling)

```python
import requests, openai

# 1. 拉工具 schema
schema = requests.get('http://127.0.0.1:9907/v1/openai').json()['tools']

# 2. 给 GPT
resp = openai.chat.completions.create(
    model="gpt-4o", tools=schema,
    messages=[{"role":"user","content":"看下当前嘉立创工程信息"}],
)

# 3. 执行 tool call
for call in resp.choices[0].message.tool_calls:
    name = call.function.name.replace('_', '.')   # OpenAI 已转义 .
    args = json.loads(call.function.arguments)
    res = requests.post('http://127.0.0.1:9907/v1/exec',
                        json={'name': name, 'arguments': args}).json()
    # 返结果给下一轮 GPT
```

### 任意 LLM (curl/wget)

```bash
# 列工具
curl http://127.0.0.1:9907/v1/tools

# 执行
curl -X POST http://127.0.0.1:9907/v1/exec -H 'Content-Type: application/json' \
  -d '{"name":"eda.environment.info","arguments":{}}'
```

### Python (本地脚本)

```python
from core.dao_connector import DaoConnector
with DaoConnector().auto() as dao:
    print(dao.eda.dmt_Project.getCurrentProjectInfo())
```

---

## 五、CLI 速查

```bash
python lceda_cli.py drive [--mode bus] [--smoke] [--hold]   # 一键自驾
python lceda_cli.py mcp                                     # 启 MCP server
python lceda_cli.py mcp-config --target claude              # 输出客户端配置
python lceda_cli.py tools [--mcp|--openai|--json]           # 列工具
python lceda_cli.py dao-status [--json]                     # 道直连器状态
python lceda_cli.py dao-find [--refresh] [--json]           # 跨机环境扫描
python lceda_cli.py events [-n N] [--stats]                 # 操作日志
```

---

## 六、smoke 见证

```bash
python tests\smoke_dao.py
```

输出:

```text
================================================================
  smoke_dao — 道直连器全链路端到端 (6 块基石)
================================================================
  [1] env_finder           ✅ 4 项
  [2] dao_connector        ✅ 3 项
  [3] tools_registry       ✅ 6 项
  [4] observer             ✅ 3 项
  [5] mcp_server (stdio)   ✅ 4 项
  [6] HTTP server /v1/*    ✅ 4 项
  ✅ 全部 24 项验证通过 — 道既已通
```

---

## 七、★ 反者道之动 — UI-level 真模拟用户操作

> **"上善若水. 水善利万物而不争, 处众人之所恶, 故几于道."**
>
> 前 17 个 API-level 工具是"内功" — 直调 `eda.<class>.<method>(...)`, 快但跳过 UI, 用户看不见.
>
> 本章 9 个 UI-level 工具是"招式" — 走 CDP Input 真鼠标键盘, 用户在 EDA 窗口内看见鼠标轨迹 · 菜单弹开 · 按钮被点 · 字符出现.
>
> "以其终不自为大, 故能成其大" — 不被用户疑为黑箱, 故可被信。

### 7.1 六原语 (损之又损, 至于无为)

一切复杂 UI 动作皆由事六原语合成, 定于 `core/ui_director.py`:

| 原语 | 底层 CDP method | 说明 |
|------|------|------|
| `move_to(x, y)` | Input.dispatchMouseEvent (mouseMoved) | 虚拟光标 CSS transition + 真鼠标事件 |
| `click(x, y)` | Input.dispatchMouseEvent (mousePressed/mouseReleased) | 高亮目标 + 慢动作点击 |
| `drag(x1,y1,x2,y2)` | press → 多帧 mouseMoved → release | 6 帧拖动 (默 480ms) |
| `scroll(x, y, dy)` | Input.dispatchMouseEvent (mouseWheel) | 画布缩放/滚动 |
| `type_text(text)` | Input.dispatchKeyEvent (char) | 逐字 60ms, 用户可见输入 |
| `press(key)` | Input.dispatchKeyEvent (keyDown/keyUp) | F1..F12, Enter, Esc, 方向键等 28 个特殊键 |

### 7.2 9 个 UI 工具 (供 agent 调用)

| 工具 | 语义 | 示例参数 |
|------|------|------|
| `eda.ui.narrate` | 顶部弹 toast 横幅 | `{text:"打开元件面板"}` |
| `eda.ui.screenshot` | 截 EDA 画面存档 | `{}` |
| `eda.ui.click_at` | 点坐标 (真鼠标事件) | `{x:800, y:24}` |
| `eda.ui.click_text` | ★ 点含某文字的按钮 | `{text:"打开"}` |
| `eda.ui.drag` | 拖拽 | `{x1:100,y1:100, x2:300,y2:200}` |
| `eda.ui.scroll` | 滚轮 | `{x:600,y:400, delta_y:-100}` |
| `eda.ui.type` | 键盘输入文字 | `{text:"电阻"}` |
| `eda.ui.hotkey` | 快捷键 | `{keys:["ctrl","s"]}` |
| `eda.ui.find` | ★ 扫视屏上可点元素 (视觉地图) | `{contains:"导出"}` |

★ 表示最常用: `find` 取得视觉地图, `click_text` 不需 agent 算坐标.

### 7.3 五感反馈 (用户三处皆见)

```text
agent 一调 (例: eda.ui.click_text {text:"保存"}):
  ├─ 视-1: 横幅 toast "🤖 即将: 点 UI 文字"   (1.5秒自消)
  ├─ 视-2: 虚拟光标慊动作移到目标        (600ms CSS transition)
  ├─ 视-3: 目标按钮红框高亮                 (800ms outline)
  ├─ 视-4: 鼠标点击脚本 (虚拟光标缩小脉冲)
  ├─ 听:   winsound.MessageBeep (interactive 类响 1 声)
  ├─ 检:   ~/.lceda_dao/screenshots/<时间>_pre_eda_ui_click_text.png
  └─ 记:   ~/.lceda_dao/events.jsonl tool.pre + tool.post 两行
```

### 7.4 启动可观 (auto() → 欢迎/告别)

```python
with DaoConnector().auto() as dao:    # user_visible=True 默认开
    # 1. 连上后自动弹: "🤖 道直连器已就位 · agent 接管中" (3.5秒)
    # 2. 作业...
    dao.ui_director.click_text("另存为")
    dao.ui_director.type_text("my_pcb_v2")
    dao.ui_director.press("Enter")
# 退出时自动弹: "👋 agent 退场, 道隐无名"
```

### 7.5 demo 与 smoke

```bash
# 实景演示 (要 EDA 或会自动启动)
python demos\ui_demo.py            # 8 步完整体验
python demos\ui_demo.py --slow     # 更慢节奏
python demos\ui_demo.py --no-clicks  # 仅 narrate / 截屏, 不点击

# 静态验证 (不需 EDA, 11 项)
python tests\smoke_dao_ui.py       # 11 项静态 + 湿测会自动 skip或跑
```

### 7.6 设计要点 (仅供深入)

* **不动 OS 真鼠标** — CDP Input 仅在 EDA 进程内虚拟, 不干扰用户真鼠标
* **虚拟光标 div** — z-index 2147483646, pointer-events:none, 不拦截点击
* **慊动作节奏** — move 600ms, click dwell 120ms, type 60ms/字: 让用户看清
* **虚拟光标不可选** — `--slow` 可调为 1200ms, `UIConfig.enable_cursor=False` 可全关

## 八、★★★ 反者道之动 — v4.0.0 agent-native (DaoFlow)

> **"曲则全, 柉则直, 洼则盈, 敝则新, 少则得, 多则惑."**
>
> v3.1 的 9 个 UI 工具是"招式" — 让 agent 模拟人. 但 agent 本不是人.
>
> 本章 6 柱 + 5 元工具 是"本然" — 让 agent 直读直写 V8 Object Graph.
>
> "以其终不自为大, 故能成其大" — 不拟人, 反能汇全力于本然.

详见 [MANIFESTO_REVERSAL.md](./MANIFESTO_REVERSAL.md).

### 8.1 六柱 (损之又损, 至于无为)

| 柱 | 文件 | 职 | 代替 |
|---|------|------|------|
| 镜 | `core/state_mirror.py` | EDA 全状态 → JSON | screenshot+OCR / find_clickables / viewport |
| 图 | `core/knowledge_graph.py` | 819 method 静态图 (TSDoc 合 入) | system.introspect / 试错 |
| 解 | `core/intent_resolver.py` | 意图(NL/JSON) → method+args | click_text / 手工选菜单 |
| 脉 | `core/causal_engine.py` | target_state → 寻路 → 执行 | 18 步手工规划 |
| 流 | `core/effect_stream.py` | 状态 diff → patch 推送 | 轮询 toast / 等加载 |
| 逆 | `core/reversible.py` | with-block 自动 snapshot + EDA undo 链 | 手动中断/重试 |

一柱 (`core/dao_flow.py`) 抱 六柱为天下式.

### 8.2 5 元工具 (代替 26 具象)

| 工具 | 作用 | 示例 |
|------|------|------|
| `eda.flow.snapshot` | 一次拿全状态 JSON | `flow.snapshot()` → `{env, project, documents, active, selection, viewport, panels, dom, ts}` |
| `eda.flow.search` | KG 语义搜 | `flow.search('open project')` → [{score:130, path:'dmt_Project.openProject',...}, ...] |
| `eda.flow.intend` | 意图 → method (不执行) | `flow.intend({do:'open',what:'project',target:'my_pcb'})` → ResolvedAction |
| `eda.flow.act` | intend + execute + state diff | `flow.act('list all projects')` → 一行抵 18 步 |
| `eda.flow.aim` | target_state 驱动 | `flow.aim({project_uuid:'abc'})` → plan + run |

### 8.3 跨代对比 (同一意图)

```text
目标: 获取当前工程信息 (uuid + name + path)

╔══ v3.1 UI-level (拟人 18 工具) ══╗        ╔══ v4.0 DaoFlow (本然 1 工具) ══╗
║ 1. ui.screenshot()                 ║        ║ flow.act(                       ║
║ 2. ui.find('文件')                  ║        ║     'get current project info'  ║
║ 3. ui.click_text('文件')             ║  vs    ║ )                                ║
║ 4. sleep(300ms)                    ║        ║                                  ║
║ 5. ui.click_text('属性')             ║        ║ → dmt_Project.getCurrentProjectInfo ║
║ 6. ui.screenshot() + OCR           ║        ║ → 直接拿 JSON                    ║
║ 7. ui.press('Escape')               ║        ║                                  ║
║ ⏚ ~3-8 秒, 按钮文字变 → 全跌           ║        ║ ⏚ ~50-100ms, 不依赖 UI 焦点       ║
╚════════════════════════════════════╝        ╚═══════════════════════════════════╝
```

### 8.4 一行入道

```python
from core.dao_connector import DaoConnector
with DaoConnector().auto() as dao:
    flow = dao.flow                              # DaoFlow 已自动实例化
    print(flow.snapshot_summary())                # ~600 字中文摘要

    # 一句完成
    r = flow.act("get current project info")
    print(r['result'])                            # JSON

    # 目标驱动
    r = flow.aim({"active_doc_name": "sch1"})      # 自寻路

    # 可逆会话 (错亦无伤)
    with flow.session() as sess:
        sess.do("dmt_Project.deleteProject", [uuid], side_effect="destructive")
        # 招异常 → 自动 EDA undo 回滚
```

### 8.5 跨代兼容

* `dao.eda` — v1.0 Python SDK 全保留
* `dao.ui_director` / `dao.narrator` — v3.1 UI 拟人全保留 (需演示给人看时仍用)
* `dao.flow` — v4.0 ★ agent 默认走此路

道并行不悖. 26 具象 + 5 元 = 31 工具, 供任意场景选用.

### 8.6 demo 与 smoke

```bash
# 离线 demo (不需 EDA, 看反向之美)
python demos\flow_demo.py --offline

# 实景 demo (要 EDA 或会自启动)
python demos\flow_demo.py

# 静态验证 (22 项静态 + 湿测自动 skip或跑)
python tests\smoke_dao_flow.py
```

## 九、设计哲学

> **"道生一, 一生二, 二生三, 三生万物"**
>
> 道生一 ── 一份 `dao_connector.py` 入口
>
> 一生二 ── 在线 (CDP+总线 / HTTP 桥) + 离线 (anatomy/elib/eprj)
>
> 二生三 ── MCP / HTTP REST / Python SDK 三协议外露
>
> 三生万物 ── 17 工具 × 任意 agent × 任意机器 × 任意用户

> **"反者道之动, 弱者道之用. 天下万物生于有, 有生于无"**
>
> agent 之力, 不在堆砌, 而在: 跨机即得 (env_finder), 一键即通 (dao_connector), 不知即问 (introspect), 错亦无伤 (graceful fallback), 行皆可见 (observer).

> **"生而不有, 为而不恃, 长而不宰, 是谓玄德"**
>
> 道直连器: 不替换嘉立创, 不破坏数据, 不绕过协议; 仅把"已存在的本然"显出来 — 故道法自然.

---

## 十、跨机/任意用户/任意电脑保证

| 维度 | 实现 |
|------|------|
| **任意电脑** | env_finder 多策略发现 (注册表/默认路径/PATH/环境变量) |
| **任意用户** | 多用户机扫所有 `C:\Users\*\Documents\LCEDA-Pro` |
| **任意 agent** | MCP / HTTP REST / OpenAI schema / Python SDK 四协议 |
| **任意 LLM** | OpenAI tool schema 标准化 (name / description / parameters) |
| **任意版本** | tools_registry 用 `_try_paths` 候选链, EDA 升级 API 也可适配 |
| **零依赖** | MCP server 不依赖 `mcp` pip 包, 全 stdlib (Python ≥ 3.10) |

---

> **"知者不言, 言者不知. 塞其兑, 闭其门, 挫其锐, 解其纷, 和其光, 同其尘, 是谓玄同"**
>
> 道直连器之于嘉立创EDA Pro, 玄同也. 异名同谓.
