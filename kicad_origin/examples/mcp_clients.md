# MCP 客户端配置 — 任意 LLM agent 直连 KiCad

`kicad_origin` 内建一个 MCP server (Model Context Protocol, JSON-RPC over stdio),
暴露 23 个 KiCad 工具. 任何支持 MCP 的 LLM 客户端均可一键直连.

## 启 server

```bash
# 方式 1: 顶层 CLI
python -m kicad_origin mcp

# 方式 2: 子模块
python -m kicad_origin.dao.mcp

# 方式 3: dao 子命令
python -m kicad_origin dao serve
```

server 在 stdin 读 JSON-RPC, stdout 写响应; 反馈 / 日志走 stderr 与
`%TEMP%/kicad_origin_mcp/mcp_*.jsonl`, 不污染协议通道.

## 列工具 schema (无需启 server)

```bash
python -m kicad_origin dao tools
# 或
python -m kicad_origin.dao.mcp --list-tools
```

输出 23 个工具的 JSON Schema, 字段全自描述, agent 无需文档.

---

## Claude Desktop

`~/.claude/mcp_servers.json` (macOS / Linux) 或
`%APPDATA%\Claude\mcp_servers.json` (Windows):

```json
{
  "mcpServers": {
    "kicad-origin": {
      "command": "python",
      "args": ["-m", "kicad_origin.dao.mcp"]
    }
  }
}
```

重启 Claude Desktop, 在 chat 内问 "搜符号 STM32H743" 即可看到 23 个工具
被自动调用.

---

## Cline (VS Code 插件)

`.cline/mcp.json`:

```json
{
  "mcpServers": {
    "kicad-origin": {
      "command": "python",
      "args": ["-m", "kicad_origin.dao.mcp"],
      "env": {}
    }
  }
}
```

---

## Cursor

`Settings → Features → MCP Servers`, 添加:

```text
Name:    kicad-origin
Command: python -m kicad_origin.dao.mcp
```

---

## Cascade (Windsurf)

Cascade 通过 `~/.codeium/windsurf/mcp_config.json` 加载:

```json
{
  "mcpServers": {
    "kicad-origin": {
      "command": "python",
      "args": ["-m", "kicad_origin.dao.mcp"]
    }
  }
}
```

---

## 自定义 Python agent (无需 LLM)

```python
import json, subprocess, sys

p = subprocess.Popen(
    ["python", "-m", "kicad_origin.dao.mcp"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True,
)

def call(msg):
    p.stdin.write(json.dumps(msg) + "\n"); p.stdin.flush()
    return json.loads(p.stdout.readline())

# 1. 握手
print(call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05"}}))

# 2. 列工具
print(call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}))

# 3. 搜符号
print(call({"jsonrpc": "2.0", "id": 3,
            "method": "tools/call",
            "params": {"name": "kicad_search_symbol",
                       "arguments": {"query": "STM32", "limit": 5}}}))

p.stdin.close()
```

---

## 23 工具速查

| 类别       | 工具                          | 摘要 |
|------------|-------------------------------|------|
| **状态**   | kicad_status                  | 五脉 + 索引 + 板 总状态 |
|            | kicad_env                     | KiCad 安装路径 / 版本 |
|            | kicad_connect                 | 探活 IPC; 可自动启用 |
| **库**     | kicad_search_symbol           | 22386 符号模糊搜 |
|            | kicad_search_footprint        | 15179 封装模糊搜 |
|            | kicad_get_footprint           | 单封装 pads/courtyard/3D |
| **板**     | kicad_open                    | 加载 .kicad_pcb (可同时 GUI) |
|            | kicad_save                    | 保存当前板 |
|            | kicad_new_board               | 新建空板 (11 标准层) |
|            | kicad_close                   | 关闭当前板 |
| **元件**   | kicad_list_footprints         | 列所有元件 |
|            | kicad_list_nets               | 列所有 net |
|            | kicad_get_footprint_info      | 单元件详情 |
|            | kicad_move_footprint          | 移动 (mm) |
|            | kicad_rotate_footprint        | 旋转 (度) |
|            | kicad_set_value               | 改 Value |
|            | kicad_remove_footprint        | 删除元件 |
| **校验**   | kicad_run_drc                 | 6 规则 DRC |
| **制造**   | kicad_export_gerber           | 11 层 RS-274X |
|            | kicad_export_excellon         | PTH/NPTH 钻孔 |
|            | kicad_export_fab              | 一键: DRC+Gerber+Excellon |
| **可见**   | kicad_snapshot                | 截屏 KiCad 窗口 |
|            | kicad_history                 | 本会话动作回放 |

---

> "玄之又玄, 众妙之门." — 一个 server, 任意 agent 入门, 即得 KiCad 全境.
