# ☯ DAO-KiCad Agent 桥接文档 (复制即接入)

> 把本文档整体发给任意 Agent (Devin / Copilot / Claude / 本地 Agent / 自研 Agent 均可),
> 它即可通过 HTTP 直连 DAO-KiCad 底层引擎, 全方位调度一切本源工具:
> 原理图/PCB 渲染 → 网表 → 建板(封装自愈) → freerouting 自动布线 → DRC/ERC → 制造输出,
> 以及一键全闭环管线。无为而无不为。

## 0. 启动底层桥 (若尚未运行)

```bash
cd <本仓库>/dao_kicad
PYTHONPATH=$PWD:$PWD/.. python3 -m bridge.ide_server --port 9931
# 或直接安装 vscode-dao-kicad 插件, 打开主页时自动拉起
```

前置: 机器装有 KiCad ≥8 (Linux/Windows/macOS 均自动探测 kicad-cli) 与 Java (布线用)。

## 1. 自发现 (Agent 第一步)

```
GET http://127.0.0.1:9931/api/health        → {"ok":true,"kicad":"9.0.9","cli":"..."}
GET http://127.0.0.1:9931/api/capabilities  → 全部工具的机器可读 schema
GET http://127.0.0.1:9931/api/doc           → 本文档
```

health 不通 = 桥未启动, 按第 0 节启动; `kicad: null` = 该机未装 KiCad。

## 2. 工具总表

| 端点 | 方法 | 入参 (JSON) | 说明 |
|---|---|---|---|
| `/api/tree` | GET | `?root=目录` | 发现 KiCad 工程 (sch/pcb/net) |
| `/api/render/sch` | GET | `?path=x.kicad_sch` | 原理图 → SVG |
| `/api/render/pcb` | GET | `?path=x.kicad_pcb&layers=F.Cu,...` | 板图 → SVG |
| `/api/netlist` | POST | `{sch, out?}` | 原理图 → 网表 |
| `/api/build` | POST·job | `{netlist, out, layers?=2, project_dir?}` | 网表 → 摆放好的板 (含封装自愈) |
| `/api/route` | POST·job | `{pcb, out?, passes?=10, timeout?}` | freerouting 自动布线 |
| `/api/drc` | POST | `{pcb}` | DRC 校验 |
| `/api/erc` | POST | `{sch}` | ERC 校验 |
| `/api/fab` | POST·job | `{pcb, out}` | Gerber + 钻孔 + 贴片 CSV |
| `/api/auto` | POST·job | `{sch\|netlist, out?, layers?, passes?, timeout?, fab?}` | **一键全闭环**: 网表→建板→布线→DRC[→制造] |
| `/api/job` | GET | `?id=job号` | 轮询任务 `{done, stage?, result?}` |

标注 `job` 的端点立即返回 `{"job":"<id>"}`; 轮询 `/api/job?id=` 直至 `done:true`,
期间 `stage` 字段给出实时阶段 (netlist/build/route/drc/fab)。

## 3. 长链路示例 (完整闭环, 任何 Agent 照抄可用)

```bash
B=http://127.0.0.1:9931
# 发现工程
curl "$B/api/tree?root=/usr/share/kicad/demos/ecc83"
# 一键闭环 (原理图直入, 含制造输出)
JOB=$(curl -s $B/api/auto -d '{"sch":"/usr/share/kicad/demos/ecc83/ecc83-pp.kicad_sch","fab":true}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["job"])')
# 轮询至完成
watch -n2 "curl -s '$B/api/job?id=$JOB'"
# 结果: {"done":true,"result":{"ok":true,"clean":true,"pcb":"...","steps":{...}}}
```

分步链路 (需要中途决策时): `netlist → build(job) → route(job) → drc → fab(job)`,
每步出参即下步入参 (`net`/`pcb` 路径), DRC 不干净可调 `passes`/`timeout` 重布。

## 4. 约定与边界

- 桥默认只绑 `127.0.0.1` (本机 Agent 直连); 远程接入请自行加隧道/反代与鉴权。
- 所有路径为**桥所在机器**上的绝对路径。
- 错误恒以 JSON 返回 `{"ok":false,"error":"..."}`, HTTP 400/404/500; 任务失败时
  `result.steps` 保留每一阶段的完整输出用于归因。
- 支持 Content-Length 与 chunked 两种请求体; 响应含 CORS 头, 网页端可直接 fetch。

*道法自然 · 无为而无不为*
