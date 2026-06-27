# PCB设计 — Agent操作手册

> **万法归宗**: 一个`PCB`类, 一个`pcb_mcp.py`入口, 承载全部PCB设计能力
> **原理图道**: 一个`SchematicProject`类, 一个`schematic_dao`模块, 一份道生四件套
> **位置**: `PCB设计/pcb_brain/` (PCB布局)  ·  `PCB设计/schematic_dao/` (原理图论文级)

---

## 双引擎选择

| 我要... | 用哪个 |
|---|---|
| 直接出 `.kicad_pcb` / Gerber / SMT 下单包 | `pcb_brain` (`from pcb_core import PCB`) |
| 出论文级原理图 SVG/PDF + BOM + 网络表 + KiCad 工程雏形 | `schematic_dao` (`python -m schematic_dao build`) |
| 自然语言 → 选模板 → 自动出 PCB | `PCB.quick("描述")` |
| 拍照原理图 → 复刻为完整工程资料包 | `schematic_dao` 写 project 定义 → build |
| 同时要论文图和打样文件 | 先 `schematic_dao` 出设计文档 → 再 `pcb_brain` 出 Gerber |

---

## 最快入口

```python
# Python — 统一门面 (推荐)
from pcb_core import PCB

PCB.list_templates()                            # 21个DNA模板
PCB.design("esp32_servo_wifi")                  # 生成PCB
PCB.pipeline("stm32f103c6_dot_matrix")          # 全闭环: DNA→PCB→DRC→Gerber→BOM→下单包
PCB.parse_intent("WiFi温湿度监测器")             # 自然语言→模板
PCB.check_risks("drone_flight_controller")      # 风险预判
PCB.bom("smartwatch_core", qty=5)               # BOM+LCSC+成本
PCB.quick("我想做一个无人机飞控")                 # 一句话→完整交付物
```

```bash
# CLI
python pcb_brain.py list                         # 列出模板
python pcb_brain.py full <模板名>                # 完整流水线
python pcb_brain.py design <模板名>              # 快速设计
python pcb_brain.py status                       # 环境状态
python pcb_pipeline.py <模板名>                  # 独立流水线

# MCP (Windsurf集成)
python pcb_mcp.py                                # stdio模式
python pcb_mcp.py test                           # 自检16工具

# 验证
python pcb_core.py                               # 统一门面自检
python _pcb_bootstrap.py                         # 基础设施自检
python _verify_all.py                            # 全量验证 (23项)
python _verify_all.py --full                     # +21模板pipeline (44项)
```

---

## 架构 (六层)

```
Layer 0  _pcb_bootstrap.py    UTF-8/路径/日志/环境探测 (import即生效)
Layer 1  circuit_dna.py       21个DNA模板 (数据层, 128KB)
Layer 2  kicad_arm.py         PCB生成/BFS布线v4/DRC/Gerber (引擎层, 58KB)
Layer 3  pcb_jlcpcb.py        BOM/CPL/成本/LCSC 170+料号 (生产层)
         pcb_ibom.py          交互式HTML BOM
         pcb_eye.py           DRC/BOM/Gerber验证 (感知层)
Layer 4  pcb_pipeline.py      全闭环流水线 (编排层)
Layer 5  pcb_core.py          统一门面API — 万法归宗
         pcb_brain.py         CLI入口
         pcb_mcp.py           MCP服务器 (16工具, Windsurf直连)
         pcb_server.py        HTTP服务器 (:9906, Web UI)
可选     kicad_native.py      KiCad 9 pcbnew桥 (153封装库/225符号库)
         agent_sense.py       远程Agent扩展 (:9904)
```

## 流水线 (6阶段)

```
DNA选择 → .kicad_pcb生成 → DRC检查+自动修复 → Gerber导出 → iBoM+BOM → JLCPCB下单包
```

## MCP工具 (16个)

| 工具 | 功能 |
|------|------|
| `list_templates` | 列出21个DNA模板+成本 |
| `design_pcb` | DNA→.kicad_pcb+自动布线 |
| `get_bom` | BOM+LCSC料号+成本+下单URL |
| `run_drc` | DRC设计规则检查 |
| `export_gerber` | Gerber生产文件导出 |
| `pcb_sense` | 环境五感健康报告 |
| `find_alternative` | 国产/低成本替代查询 |
| `estimate_cost` | BOM+打样+SMT成本估算 |
| `check_design` | 设计规则建议 |
| `generate_order` | JLCPCB完整下单包 |
| `generate_ibom` | 交互式HTML BOM |
| `run_pipeline` | 全闭环流水线 |
| `search_footprint` | KiCad封装库搜索 (15179封装) |
| `search_symbol` | KiCad符号库搜索 (45963符号) |
| `parse_pcb` | PCB文件S-expr解析 |
| `kicad_sense` | KiCad Native健康报告 |

## DNA模板 (21个)

| 模板 | 描述 | 元件 | 成本 | 分类 |
|------|------|------|------|------|
| `stm32f103c6_dot_matrix` | STM32F103C6+LED点阵 | 17 | ~¥12 | stm32 |
| `esp32_servo_wifi` | ESP32 WiFi+舵机 | 16 | ~¥28 | esp32 |
| `drone_flight_controller` | STM32F405+IMU+4PWM | 38 | ~¥65 | drone |
| `drone_aerial_h743` | 航拍级H743+双IMU | 68 | ~¥67 | drone |
| `smartwatch_core` | nRF52840+心率+IMU | 28 | ~¥50 | wearable |
| `rp2040_minimal` | RP2040 Pico兼容 | 21 | ~¥25 | rp2040 |
| `stm32g031_minimal` | STM32G031低成本 | 15 | ~¥8 | stm32 |
| `stm32h743_core` | STM32H743 480MHz | 21 | ~¥65 | stm32 |
| `esp32s3_rs485_can` | ESP32-S3+RS485+CAN | 23 | ~¥55 | communication |
| `ch32v003_minimal` | CH32V003 RISC-V ¥0.5 | 12 | ~¥3 | risc-v |
| `gd32f103_minimal` | GD32F103国产平替 | 17 | ~¥10 | stm32 |
| 其余10个 | power/motor/wireless/display/protection | — | — | — |

## 环境依赖

| 工具 | 状态 | 说明 |
|------|------|------|
| Python 3.11 | ✅ | 系统版本 |
| freerouting.jar | ✅ | pcb_brain/freerouting.jar |
| Java JRE | ✅ | pcb_brain/jre/ (便携) |
| KiCad CLI | 按机器 | 台式机D:\KICAD\bin\kicad-cli.exe |
| pcbnew API | ❌ | KiCad 9=Py3.11, ABI限制, L2 CLI降级 |
| kicad-tools | 🔜 待装 | `pip install kicad-tools` — A\*布线/LLM布局/Pure Python DRC |

## 已知限制

- **pcbnew API**: KiCad 9捆绑Python 3.11但ABI不兼容系统环境, 已有L2 CLI降级。未来可通过`kicad-python` IPC-API替代
- **freerouting GUI**: v1.9.0需GUI(HeadlessException), BFS布线v4作为兜底 (21/21模板零违规)。`kicad-tools`内置A\*布线器可作为第三选项
- **UTF-8**: 已通过`_pcb_bootstrap.py`统一修复, 所有模块import即生效

## 集成路线图 (2026-04-08)

| 优先级 | 项目 | 行动 | 收益 |
|--------|------|------|------|
| P0 | `kicad-tools` | `pip install kicad-tools` → pipeline可选后端 | A\*布线替代BFS, LLM布局, Pure Python DRC |
| P1 | JLCPCB API | 参考KiCAD-MCP-Server的JLCSearch | 2.5M+零件库, 实时价格/库存 |
| P2 | `kicad-python` | 等PyPI稳定后替代kicad_native.py | 实时KiCad交互, 消除ABI限制 |
| P3 | SKiDL KICAD9 | `generate_netlist(tool=KICAD9)` | 原生KiCad 9 netlist |

> 详见 [`线上资源参考.md`](./线上资源参考.md)

## 验证状态 (2026-04-08)

| 维度 | 结果 |
|------|------|
| DNA模板 | **21个** |
| DRC零违规 | **21/21 ✅** |
| MCP工具 | **16/16 ✅** |
| BOM覆盖 | **21/21 ✅** (170+ LCSC料号) |
| pipeline | **21/21 ✅** |
| 全量验证 | **23/23 ✅** |
| 线上资源调研 | **2026-04-08 ✅** (GitHub/Tavily/Context7) |