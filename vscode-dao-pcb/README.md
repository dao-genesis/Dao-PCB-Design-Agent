# DAO PCB — 归一工作台 (KiCad + 嘉立创EDA 双线合一)

> 道并行而不相悖 · 无为而无不为 · 道法自然

把 PCB 项目的两条核心路线 —— **KiCad**(`vscode-dao-kicad`)与**嘉立创EDA**(`vscode-dao-lceda`)——
在 **Devin Desktop 基底**(dao-ai-base)之上合并为一个插件, 三合一结构与
devin-remote 的 dao-one(二合一 + Proxy Pro)同构:

```
Devin Desktop 基底 (dao-ai-base: Cascade 三模式 · windsurf 垫片)
        │
Proxy Pro 同源模式层 (pcb-mode: 四态提示词隔离/替换)
  ⌨ native — 字节级直通, 原生编程体验分毫不动
  ☯ dao    — 帛书《老子》+《阴符经》道魂整体隔离/替换
  ☯ kicad  — 道魂 + KiCad 领域 SP + 36 工具目录 (MCP dao-kicad)
  ☯ lceda  — 道魂 + EDA 领域 SP + CDP 桥工具目录 (MCP lceda-dao)
        │
归一主页 (网页套网页 · dao-vsix /shell 同构)
  ☯ KiCad 标签  → dao_kicad ide_server (9931) 单网页工作台
  ⚡ 嘉立创EDA 标签 → lceda bridge_server (9940) 归一外壳
  ⚙ 模式 标签   → 四态可视化切换
```

## 双桥并行

| 桥 | 端口 | 事实源 | MCP |
|---|---|---|---|
| KiCad | 9931 | `dao_kicad/bridge/ide_server.py` | `dao-kicad` (`bridge/mcp_server.py`) |
| 嘉立创EDA | 9940 | `lceda_bridge/vscode_lceda/bridge_server.py` | `lceda-dao` (`core/mcp_server.py`) |

插件激活即自动发现工作区内引擎/桥并拉起, 双路 MCP 注册进
`~/.codeium/windsurf/mcp_config.json` —— 领域工具与官方编程工具**并列平权、原生注入**,
Cascade / Devin Local / Devin Cloud 三模式全部原生 function-calling 直达两套引擎底层。

## 模式切换

- 状态栏 ☯ 药丸: 一键循环 `native → dao → kicad → lceda`;
- 命令 `DAO PCB: 选择模式`: 快速面板直选;
- 归一主页「⚙ 模式」标签: 可视化四态卡片。

模式持久化于 `~/.dao-pcb/mode.json`; 注入策略为**每会话首条注入全量 SP, 其后轻量标记**
(agent:epoch 粒度), 领域工具目录从活桥实时刷新、桥未起时用同源兜底目录。

## 测试

```bash
node test/pcb-mode.test.js   # 13 项四态塑形单测, 纯 node 可跑
```

## 与旧插件的关系

`vscode-dao-kicad` 与 `vscode-dao-lceda` 保留为两条路线的单体形态(可独立装);
本插件为归一交付本体, 二者的桥/引擎/工具注册表即本插件的事实源, 不重复造。
