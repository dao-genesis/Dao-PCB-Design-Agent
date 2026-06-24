# PCBBrain · AI代理导引书

> "道生一，一生二，二生三，三生万物" — 本系统之架构，法自此。
>
> **一句话定义**：自然语言/模板名 → 自动生成可下单 PCB（.kicad_pcb + Gerber + BOM + iBoM + JLCPCB 下单 URL）的全闭环代码化 PCB 设计大脑。

---

## 一、万法归宗 · 唯一入口

AI 代理写脚本/调工具时，**首选此三路**，余皆内部实现：

| 场景 | 入口 | 示例 |
| --- | --- | --- |
| **Python 脚本内** | `from pcb_core import PCB` | `PCB.pipeline("stm32f103c6_dot_matrix")` |
| **Windsurf / Claude MCP** | MCP 工具调用 | `run_pipeline(template="ams1117_power")` |
| **命令行 / 他机脚本** | HTTP `:9906` | `POST /api/pipeline  {"template": "ams1117_power"}` |

**勿直接 import**：`pcb_guardian`/`pcb_dao`/`pcb_intent`/`pcb_wugan`/`pcb_advisor`/`pcb_user_sense` — 它们是 `pcb_server.py` HTTP 路由的实现层，精华已由 `pcb_core.PCB` 吸收；除非你在扩展 HTTP API，否则用 `pcb_core`。

---

## 二、PCB 类 · 核心 API（pcb_core.py）

```python
from pcb_core import PCB

PCB.list_templates()                # 列 21 个 DNA 模板 (dict)
PCB.design(template)                # DNA → .kicad_pcb + 自动布线
PCB.drc(template)                   # DRC 检查 (native API / CLI 降级)
PCB.gerber(template)                # Gerber 导出 (11层)
PCB.bom(template, qty=5)            # BOM + LCSC + 成本报告
PCB.ibom(template)                  # 交互式 HTML BOM
PCB.pipeline(template)              # 全闭环: DNA→PCB→DRC→Gerber→iBoM→JLCPCB
PCB.sense(template)                 # 五感健康报告
PCB.check_risks(template)           # 7条风险规则预判 (吸收自 guardian)
PCB.parse_intent(description)       # 自然语言 → DNA 推荐 (吸收自 dao)
PCB.alternatives(component)         # 国产替代推荐
PCB.env()                           # 环境检测 (KiCad/freerouting/Java/pcbnew)
```

---

## 三、六层架构

```
┌──────────────────────────────────────────────────────────────┐
│  L6  交付                 JLCPCB 下单包: BOM.csv + CPL.csv + Gerber.zip  │
├──────────────────────────────────────────────────────────────┤
│  L5  门面 (三面一体)      pcb_core.PCB | pcb_mcp (16工具) | pcb_server (HTTP:9906)│
├──────────────────────────────────────────────────────────────┤
│  L4  流水线              pcb_pipeline.PCBPipeline (6阶段) + pcb_brain.PCBBrain (CLI)│
├──────────────────────────────────────────────────────────────┤
│  L3  五感认知            pcb_eye (视听嗅味触) / pcb_wugan (无感聚合) / pcb_guardian (风险)│
├──────────────────────────────────────────────────────────────┤
│  L2  软件控制            kicad_arm (pcbnew/CLI/GUI四重协议) + kicad_native (1211 API)│
├──────────────────────────────────────────────────────────────┤
│  L1  代码化设计          circuit_dna (21模板 DNA) + pcb_ibom + pcb_jlcpcb │
├──────────────────────────────────────────────────────────────┤
│  L0  基础设施            _pcb_bootstrap (UTF-8/日志/路径/env缓存)         │
└──────────────────────────────────────────────────────────────┘
```

**任何模块开头都应 `import _pcb_bootstrap`**（若未直接 import 其他入口模块），以触发：
- Windows 控制台 UTF-8 (SetConsoleOutputCP 65001 + env PYTHONIOENCODING + stdout/stderr reconfigure)
- `sys.path` 自动注入 pcb_brain 目录
- 日志格式统一
- KiCad/freerouting/Java/pcbnew 环境一次探测全局缓存

---

## 四、流水线六阶（pcb_pipeline.PCBPipeline）

```
[道] Stage 1: DNA选择 + auto_layout 布局
[一] Stage 2: .kicad_pcb 生成 + auto_route (freerouting → BFS 兜底)
[二] Stage 3: DRC (native pcbnew → kicad-cli 降级)
[三] Stage 4: Gerber 导出 (6-11 层)
[万物] Stage 5: iBoM + JLCPCB (并行: HTML BOM + BOM.csv + CPL.csv)
[归根] Stage 6: 汇总报告 (pipeline_report.json)
```

---

## 五、模块定位速查

### 五-甲 · 核心闭环 (必须)
| 模块 | 大小 | 职责 |
| --- | ---: | --- |
| `_pcb_bootstrap.py` | 10 KB | 道生一 · 基础设施根基 |
| `circuit_dna.py` | 126 KB | 21 个 DNA 模板 (数据层) |
| `kicad_arm.py` | 57 KB | KiCad 软件控制臂 |
| `kicad_native.py` | 37 KB | pcbnew 9.0 原生桥 (1211 API) |
| `pcb_ibom.py` | 22 KB | 交互式 HTML BOM |
| `pcb_jlcpcb.py` | 37 KB | LCSC 料号 + 成本 + 下单 |
| `pcb_eye.py` | 21 KB | 五感感知 (视听嗅味触) |
| `pcb_pipeline.py` | 27 KB | 全闭环流水线 |
| `pcb_core.py` | 25 KB | **万法归宗 API 门面** |
| `pcb_mcp.py` | 47 KB | MCP 16 工具 (stdio/fastmcp/http) |
| `pcb_brain.py` | 24 KB | CLI 入口 (`python pcb_brain.py ...`) |

### 五-乙 · HTTP 服务实现层 (pcb_server.py 之用)
| 模块 | 大小 | 职责 |
| --- | ---: | --- |
| `pcb_server.py` | 100 KB | Flask 服务 :9906 (代码 API + 用户 UI) |
| `pcb_advisor.py` | 18 KB | `/api/recommend`·`/api/chat` — LLM 对话 |
| `pcb_intent.py` | 18 KB | `/api/intent` — 项目意图扫描 |
| `pcb_guardian.py` | 21 KB | `/api/guardian` — 风险规则引擎 |
| `pcb_dao.py` | 19 KB | `/api/dao/*` — 三态置信意图解析 |
| `pcb_wugan.py` | 39 KB | `/api/wugan`·`/api/xinzhai` — 六感+心斋 |
| `pcb_user_sense.py` | 31 KB | `/api/user_sense` — 用户五感需求 |
| `pcb_self_loop.py` | 19 KB | 自我闭环实践引擎 (独立进程) |
| `pcb_kibot.py` | 17 KB | KiBot CI/CD 集成 (可选) |
| `agent_sense.py` | 16 KB | 远程 agent :9904 五感扩展 |

### 五-丙 · 验证 / 测试
| 文件 | 职责 |
| --- | --- |
| `_verify_all.py` | 全量自检 (Layer1/3/4 快速, `--full` 跑 21 模板 pipeline) |
| `_test_mcp_stdio.py` | MCP stdio 协议单元测试 |
| `_test_real_pads.py` / `_read_pads.py` | 实焊盘验证 |
| `_probe_agent.py` | 远程 agent 探针 |

---

## 六、环境矩阵

| 依赖 | 角色 | 缺失时 |
| --- | --- | --- |
| **KiCad 9.0** (`D:\KICAD` / `C:\Program Files\KiCad\9.0\`) | pcbnew API + kicad-cli | 降级文件直写，无 DRC/Gerber |
| **Java 17+** (自动下载 jre/) | freerouting 自动布线 | BFS 兜底（Level3，可能有 clearance 违规） |
| **freerouting.jar** (`./freerouting.jar`) | 世界级自动布线 | BFS 兜底 |
| Python 3.11 | 配 KiCad 9 ABI | Python 3.12 ABI 不匹配 → pcbnew DLL 失败 |
| fastmcp (可选) | MCP 高阶封装 | 降级 stdio JSON-RPC（内置实现） |
| flask | pcb_server HTTP | 无 HTTP API |

> 本机若无 KiCad，pipeline 仍可跑（文件直写 + mock Gerber），19/23 检测项通过。

---

## 七、常见 AI 代理任务速查

### 任务 A: 用户一句话 → 完整 PCB
```python
from pcb_core import PCB
intent = PCB.parse_intent("我想做一个WiFi控制的温湿度监测器")
# → {"template": "esp32_servo_wifi", ...}
result = PCB.pipeline(intent["template"])
# → gerber.zip + BOM.csv + iBoM.html + 下单URL
```

### 任务 B: 检查当前环境
```python
from pcb_core import PCB
PCB.env()      # dict
PCB.env_text() # 一行摘要
```

### 任务 C: 风险预判（早于 DRC）
```python
from pcb_core import PCB
PCB.check_risks("esp32_servo_wifi")
# → 7 条规则: 去耦/bulk/晶振/I2C上拉/LED限流/锂电保护/MCU复位
```

### 任务 D: 扩展新 DNA 模板
编辑 `circuit_dna.py`，在 `CircuitDNA._TEMPLATES` 加入新 `DNA(...)` 实例。**勿在 pcb_core 里改数据**。

### 任务 E: 扩展新 MCP 工具
编辑 `pcb_mcp.py`，加 `_new_tool()`；同时更新 `_run_fastmcp()` / `_run_stdio()` 两处注册表。

---

## 八、回归测试

```bash
python _verify_all.py          # 快速自检 (~10s)
python _verify_all.py --full   # 全量 (21 模板 × pipeline, ~60s)
```

**目标**: `总计: 23 项 | ✅23 ⚠️0 ❌0 | ✅ 全部通过` (需 KiCad 装好)。

本机无 KiCad 时应为 `19 ✅ / 4 ⚠️ / 0 ❌`（pcbnew/CLI/封装库/符号库四项降级警告，不算失败）。

### PowerShell 终端乱码之治

若于 pwsh 管道中见中文 mojibake（`鈫?` 等），以下前缀令 pwsh 按 UTF-8 读子进程：

```powershell
[Console]::OutputEncoding = [Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
$env:PYTHONIOENCODING = 'utf-8'
python _verify_all.py
```

此非代码问题——Python 输出本已 UTF-8（由 `_pcb_bootstrap.py` 三重保障），乱乃 pwsh 从管道读子进程时默认 GBK 解码所致。

---

## 九、勿碰禁区 · 慎终如始

- **勿删 `output/` 下含文件的目录**（含 `self_loop.jsonl` / BOM.csv / CPL.csv / pipeline_report.json — 皆运行痕迹）
- **勿直改 `circuit_dna.py` 的 `Comp` / `DNA` dataclass 定义** — 它被 21 个模板实例化，破坏即连锁
- **勿并发改 `mcp_config.json`** — 用 `pcb_pipeline.auto_register_mcp()` 安全注册
- **慎改 `kicad_arm.py` 的四重协议顺序** (native → pcbnew API → CLI → pywinauto) — 降级链是健壮性之本

---

## 十、哲学 · 为何如此

- **道生一**: `_pcb_bootstrap.py` 是唯一根基，一处定义，万处复用
- **一生二**: `circuit_dna` (数据) + `kicad_arm` (行为) — 静动分离
- **二生三**: `pcb_eye` 五感补全感知维度
- **三生万物**: `pcb_core` / `pcb_mcp` / `pcb_server` 三面门面对外释放能力
- **归根**: `pcb_pipeline` 的 Stage 6 将一切化为 `pipeline_report.json` + 下单 URL

> "无之以为用" — `pcb_core` 是空门面，真作为在底层
> "有之以为利" — `circuit_dna` 的 21 模板是真数据，承载全部可制造性

---

_最后更新_: 2026-04-19 · _维护者_: PCBBrain 核心 · _回归基线_: `_verify_all_run.txt`
