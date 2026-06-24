# PCBBrain · 文件索引

> 详见 [`_AGENT_GUIDE.md`](./_AGENT_GUIDE.md) 之架构总览

## 代码文件 (按职责分组)

### L0 · 基础设施

- `_pcb_bootstrap.py` — UTF-8修复 / 路径 / 日志 / 环境探测缓存 (所有模块之根)

### L1 · 数据 & 代码化 DNA

- `circuit_dna.py` — 21个 DNA 模板 (STM32/ESP32/RP2040/无人机/可穿戴/工业/LoRa/蓝牙…)

### L2 · 软件控制

- `kicad_arm.py` — 四重协议 (native→pcbnew API→CLI→pywinauto) + freerouting/BFS 布线
- `kicad_native.py` — pcbnew 9.0 原生桥 (1211 API) + 封装/符号索引

### L3 · 感知与规划

- `pcb_eye.py` — 五感 (视/听/嗅/味/触)
- `pcb_wugan.py` — 六感聚合 (+ 无感/心斋) · HTTP `/api/wugan`/`/api/xinzhai`
- `pcb_guardian.py` — 7+ 条风险规则引擎 · HTTP `/api/guardian`
- `pcb_intent.py` — 项目文件意图扫描 · HTTP `/api/intent`
- `pcb_dao.py` — 三态置信意图解析 · HTTP `/api/dao/*`
- `pcb_advisor.py` — 关键字推荐 + LLM 对话 · HTTP `/api/recommend`/`/api/chat`
- `pcb_user_sense.py` — 用户五感需求管道 · HTTP `/api/user_sense`
- `agent_sense.py` — 远程 :9904 agent 五感扩展客户端

### L4 · 流水线 & 制造交付

- `pcb_pipeline.py` — 6阶段全闭环流水线 + 便携JRE下载 + MCP自注册
- `pcb_ibom.py` — 交互式 HTML BOM
- `pcb_jlcpcb.py` — LCSC 料号库 / BOM.csv / CPL.csv / 成本报告 / 下单URL
- `pcb_kibot.py` — KiBot CI/CD 集成 (可选)
- `pcb_self_loop.py` — 自我闭环实践引擎 (独立进程长跑)

### L5 · 三面门面

- `pcb_core.py` — **Python 脚本入口 (万法归宗)**
- `pcb_mcp.py` — **MCP 工具入口** (stdio + fastmcp + HTTP)
- `pcb_server.py` — **HTTP 服务** :9906 (代码 API + 用户 UI)
- `pcb_brain.py` — **CLI 入口** (`python pcb_brain.py ...`)

## 验证 / 测试

- `_verify_all.py` — 全量自检 (Layer 1/3/4 快速 + `--full` 跑 21 模板 pipeline)
- `_verify_all_run.txt` — 最新基线通过记录 (23/23, 有 KiCad 环境)
- `_test_mcp_stdio.py` — MCP stdio 协议回归
- `_test_real_pads.py` / `_read_pads.py` — 实焊盘验证
- `_probe_agent.py` — 远程 agent 探针

## 资源文件

- `freerouting.jar` — 世界级自动布线引擎 (5 MB)
- `jre/` — 便携式 JRE 17 (pcb_pipeline 自动下载安装)
- `requirements.txt` — Python 依赖清单

## 运行输出

- `output/` — 所有 pipeline 产物根目录
- `logs/` — 日志归档 (含历史 skidl_legacy / freerouting / verify 运行记录)
- `drone_schematic_complete.py` / `.net` — SKiDL 完整原理图(无人机)演示

## 文档

- `_AGENT_GUIDE.md` — AI 代理导引书 (一眼明道)
- `_INDEX.md` — 本文件

## 已知遗留 (可清/可归档)

- `skidl.log` / `skidl.erc` — 已归档至 `logs/skidl_legacy.*`
- `output/*_YYYYMMDD_HHMMSS/` — 历史运行目录（多为空），可批量清理保留最新一次

---

_21 个 Python 主模块 + 1 个 JRE + 3 个测试 + 若干报告 = 完整闭环代码化 PCB 系统_
