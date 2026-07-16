# 冷启动 · Dao-PCB-Design-Agent（Windows · 后端优先 · 零 GUI）

> 一条命令从裸 Windows VM 到全链路就绪：KiCad + Devin Desktop + 归一 VSIX + 双桥 + 双 MCP。
> 幂等设计：产物存在即跳过，复跑近零成本。

```powershell
powershell -ExecutionPolicy Bypass -File coldstart\up.ps1            # 全链路
powershell -ExecutionPolicy Bypass -File coldstart\up.ps1 -Status    # 只看现状
powershell -ExecutionPolicy Bypass -File coldstart\up.ps1 -RunOnly   # 已装机, 仅启双桥
```

## 阶段 / 产物（存在即跳过）

| 阶段 | 产物 | 说明 |
|---|---|---|
| 1 KiCad | `C:\Program Files\KiCad\9.0\bin\kicad-cli.exe` | NSIS `/S /allusers` 静默装（已实测） |
| 2 Devin Desktop | `%LOCALAPPDATA%\Programs\Devin\bin\devin-desktop.cmd` | Inno `/VERYSILENT` 用户级静默装 |
| 3 归一 VSIX | `vscode-dao-pcb\dao-pcb.vsix` + `dao.dao-pcb` 已装 | `npx @vscode/vsce package` + `--install-extension` |
| 4 双桥 | `127.0.0.1:9931 /api/health` · `127.0.0.1:9940 /api/health` | wrapper 启动，健康即跳过 |

## 环境变量

- `DAO_PCB_TOKEN` — 桥鉴权（Bearer）
- `DAO_KICAD_PORT`(9931) / `LCEDA_BRIDGE_PORT`(9940)
- `DAO_CDP_PORTS`(29229) — LCEDA 桥附着的 Chrome CDP 端口
- `DAO_PREFER_LOCAL_EDA`(0) — Server 2022 上本地 LCEDA Pro 安装器不可用，固定走 Web+CDP

## 已趟过的坑（改动前必读）

1. **embedded Python**：Devin VM 内置 `C:\devin\python\python.exe` 是嵌入式发行版，`python312._pth`
   会忽略 `PYTHONPATH` 与 cwd —— 桥/MCP 必须经 `coldstart\run_*.py` wrapper（先注入 `sys.path` 再 `runpy`）。
2. **KiCad 静默装要等**：`/S` 全程 3-6 分钟且无输出，必须 `-Wait` 后校验 `kicad-cli.exe` 存在，过早探测会误判失败。
3. **LCEDA Pro 桌面安装器**：在 Windows Server 2022 上确认弹窗后静默退出，不可用；固定 Web 版 `https://pro.lceda.cn/editor` + CDP。
4. **JLC passport 登录**：数据中心 IP 会被风控静默拦截（点登录无响应）；账号态需借用户侧网络出口（DAO Bridge / VPS 代理）。
5. **CDP 目标选择**：passport 登录页 `redirectUrl` 参数含 `lceda`，必须按 host 过滤（`bridge_server.py` 已修复, PR #5）。
6. **Devin Desktop 登录**：OAuth 回跳 `devin://`，无法后端注入，仅此一步需 GUI（浏览器输账密 → Open 回跳）。
7. **MiMo API**：模型名必须用 `mimo-v2.5`，`mimo` 会 400。

## MCP（stdio）

```powershell
python coldstart\run_kicad_mcp.py   # dao-kicad · 36 tools
python coldstart\run_lceda_mcp.py   # lceda-dao · 44 tools
```

## 验证清单

```powershell
& "C:\Program Files\KiCad\9.0\bin\kicad-cli.exe" version                        # 9.0.9
curl.exe -H "Authorization: Bearer %DAO_PCB_TOKEN%" http://127.0.0.1:9931/api/health
curl.exe -H "Authorization: Bearer %DAO_PCB_TOKEN%" http://127.0.0.1:9940/api/health
cd vscode-dao-pcb && node test\pcb-mode.test.js                                 # 13 项
```
