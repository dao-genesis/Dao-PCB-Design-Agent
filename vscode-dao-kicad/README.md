# DAO KiCad — 归一 PCB 工作台 (VS Code 插件)

把 KiCad 的所有板块桥接进 IDE 单网页主页: 项目浏览 · 原理图/PCB 查看 ·
网表→板构建 · freerouting 自动布线 · DRC/ERC · Gerber/钻孔/贴片制造输出 ·
☯ 一键闭环管线 · 🤖 AI 智能体 (OpenAI 兼容第三方 API 接入 + 工具调度)。
用户无需打开 KiCad GUI — 全部经 `dao_kicad/bridge/ide_server.py` REST 桥调
本仓库的 daokicad 引擎与 `kicad-cli` 完成。

## 架构

```
VS Code Webview (media/home.html 单网页主页)
        │ fetch (localhost REST)
dao_kicad/bridge/ide_server.py  ← 插件自动拉起
        │
daokicad 引擎 (LiveKiCad) + kicad-cli + freerouting
```

## 使用

1. 机器需装 KiCad 9 (kicad-cli) 与本仓库 (dao_kicad)。
2. 安装插件: `code --install-extension dao-kicad-0.1.0.vsix`
   (打包: `cd vscode-dao-kicad && npm run package`)。
3. 命令面板运行 **DAO KiCad: 打开归一主页**。插件自动检测工作区里的
   dao_kicad 引擎并在 127.0.0.1:9931 拉起桥接服务(可在设置里改
   `daoKicad.enginePath` / `daoKicad.python` / `daoKicad.port`)。
4. 主页左侧切换板块, 顶栏输入文件路径, 执行即可。构建/布线/制造为
   后台任务, 页面轮询直至完成。

## REST API (供任何单网页 IDE / Devin Desktop 复用)

| 端点 | 说明 |
|---|---|
| `GET /api/health` | 服务与 KiCad 状态 |
| `GET /api/tree?root=` | 递归发现 .kicad_pro 项目 |
| `GET /api/render/sch?path=` | 原理图 → SVG |
| `GET /api/render/pcb?path=&layers=` | PCB → SVG |
| `POST /api/netlist {sch}` | 原理图 → 网表 |
| `POST /api/build {netlist,out,layers,project_dir}` | 网表 → 板 (job) |
| `POST /api/route {pcb,passes,timeout}` | freerouting 布线 (job) |
| `POST /api/drc {pcb}` / `POST /api/erc {sch}` | 检查 |
| `POST /api/fab {pcb,out}` | Gerber/钻孔/贴片 (job) |
| `POST /api/auto {sch\|netlist,out,layers,passes,timeout,fab}` | 一键全闭环: 网表→建板→布线→DRC[→制造] (job·带 stage 进度) |
| `GET /api/job?id=` | 轮询后台任务 `{done,stage?,result?}` |
| `GET /api/capabilities` | 全部工具机器可读 schema (Agent 自发现) |
| `GET /api/doc` | Agent 接入文档 (复制即接入) |

## Agent 接入 (任意 Agent 直连底层)

把 `dao_kicad/bridge/AGENT_BRIDGE.md` 整体发给任意 Agent (Devin/Copilot/本地 Agent),
它即可经 HTTP 全方位调度 KiCad 底层与全闭环管线; 或让 Agent 直接
`GET /api/doc` 自取。
