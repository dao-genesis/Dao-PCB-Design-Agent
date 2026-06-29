# HANDOFF — PCB设计Agent 交接文档

> **道法自然 · 无为而无以为 · 为而不争**
>
> 此文档为后续 Agent / 开发者接手之入口。读此一文档，即可知全貌、可推进。

---

## 一句话

**PCB设计Agent** 是一个以"AI代码化PCB"为核心理念的闭环系统：
收到任何PCB设计需求 → **先复刻oshwhub已有** → 改板适配 → DRC → Gerber → 打样下单 → 焊接 → 烧录 → 验证。
21个DNA模板覆盖STM32/ESP32/无人机/可穿戴/电源/通信/电机等全品类。

---

## 快速开始

```python
# Python — 统一门面
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

# MCP (Windsurf集成)
python pcb_mcp.py                                # stdio模式
python pcb_mcp.py test                           # 自检16工具

# 验证
python pcb_core.py                               # 统一门面自检
python _pcb_bootstrap.py                         # 基础设施自检
python _verify_all.py                            # 全量验证 (23项)
python _verify_all.py --full                     # +21模板pipeline (44项)

# 原理图道
python -m schematic_dao build warehouse_logistics_vehicle
```

---

## 双引擎架构

| 引擎 | 视角 | 核心数据 | 输出 | 入口 |
|------|------|---------|------|------|
| **pcb_brain** | PCB 布局优先 | `circuit_dna.DNA` (21模板) | `.kicad_pcb` / Gerber / BOM / iBoM | `from pcb_core import PCB` |
| **schematic_dao** | 原理图优先 | `SchematicProject` | SVG/PDF/PNG/MD/CSV/.kicad_sch | `python -m schematic_dao build <name>` |

> 两引擎可串联: SchematicProject (论文级) → DNA (布局级) → PCB打样下单

---

## 六层架构

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

---

## 四大子系统

### ① pcb_brain/ — PCB布局引擎

| 文件 | 大小 | 职责 |
|------|------|------|
| `circuit_dna.py` | 128KB | 21个DNA模板 (数据层, 无依赖) |
| `kicad_arm.py` | 58KB | PCB生成/BFS v4布线/DRC/Gerber |
| `kicad_native.py` | 38KB | KiCad 9 pcbnew桥 (153封装/225符号) |
| `pcb_eye.py` | 21KB | DRC/BOM/Gerber验证 |
| `pcb_jlcpcb.py` | 38KB | BOM/CPL/成本/LCSC 170+料号 |
| `pcb_ibom.py` | 22KB | 交互式HTML BOM |
| `pcb_pipeline.py` | 27KB | 全闭环流水线 |
| `pcb_core.py` | 25KB | 统一门面API + 风险预判 + 意图解析 |
| `pcb_brain.py` | 24KB | CLI入口 |
| `pcb_mcp.py` | 47KB | MCP服务器 (16工具) |
| `pcb_server.py` | 102KB | HTTP服务器 (:9906) |
| `pcb_advisor.py` | 18KB | 设计顾问 |
| `pcb_dao.py` | 19KB | 道之PCB |
| `pcb_guardian.py` | 21KB | 守护者 |
| `pcb_intent.py` | 18KB | 意图解析 |
| `pcb_kibot.py` | 17KB | KiBot集成 |
| `pcb_self_loop.py` | 19KB | 自闭环 |
| `pcb_user_sense.py` | 31KB | 用户感知 |
| `pcb_wugan.py` | 39KB | 无感自动化 |
| `agent_sense.py` | 16KB | 远程Agent扩展 |
| `_pcb_bootstrap.py` | 10KB | UTF-8/路径/日志/环境 (全局根基) |
| `_verify_all.py` | 9KB | 全量验证 (23项→44项) |

### ② schematic_dao/ — 原理图道

| 文件 | 职责 |
|------|------|
| `schematic_dao.py` | SchematicProject 核心类 |
| `pipeline.py` | 原理图→四件套流水线 |
| `render_svg.py` | SVG渲染 (论文级原理图) |
| `render_kicad.py` | KiCad工程生成 |
| `render_kicad_export.py` | KiCad导出 |
| `render_bom.py` | BOM生成 |
| `render_docs.py` | 文档生成 |
| `render_showcase.py` | HTML展示 |
| `render_png.py` | PNG渲染 |
| `render_altium.py` | Altium兼容 |
| `render_easyeda.py` | 嘉立创EDA兼容 |
| `_kicad_lib.py` | KiCad符号库解析 |
| `_layout_zones.py` | 布局分区 |
| `projects/warehouse_logistics_vehicle.py` | 仓库物流车 (50元件/40网络/14模块) |

### ③ kicad_origin/ — KiCad本源逆向

纯Python KiCad工程数据读写，不依赖KiCad安装:

| 子包 | 职责 |
|------|------|
| `origin/` | S-expr解析、版本适配、环境探测、单位 |
| `pcb/` | board/footprint/pad/track/zone/net/geometry/inline |
| `engine/` | DRC、Gerber、Excellon (纯Python) |
| `lib/` | 符号库/封装库索引、镜像、读取 |
| `dao/` | 道之桥 (bridge/dao/feedback/mcp) |
| `ziran/` | 自然交互 (launcher/senses/window/workflow/input/apps) |
| `live/` | KiCad活体直连 (ipc/connector/daoji/do/gui/cli/config) |
| `app/` | pcbnew兼容层 |
| `examples/` | 快速入门、自动出图、JLC就绪、活体控制台 |

### ④ lceda_bridge/ — 嘉立创EDA直连

五层穿透嘉立创EDA，不重新发明EDA，逆向连入:

| 层 | 内容 |
|---|---|
| L1 | 独立脚本 (环境侦察/列出工程/导出BOM/注入原理图/DRC/改属性) |
| L2 | 嘉立创扩展 (extension.json + iframe桥) |
| L3 | 文件直读 (.eprj=SQLite / .elib=SQLite / .epro=ZIP) |
| L4 | CDP自动化 (Chrome DevTools Protocol) |
| L5 | 云端API |
| core/ | 31个核心模块 (anatomy/bridge/observer/ui_director/knowledge_graph/...) |

---

## 21个DNA模板

| 模板 | 描述 | 元件 | 成本 | 分类 |
|------|------|------|------|------|
| `stm32f103c6_dot_matrix` | STM32F103C6+LED点阵 | 17 | ~¥12 | stm32 |
| `esp32_servo_wifi` | ESP32 WiFi+舵机 | 16 | ~¥28 | esp32 |
| `drone_flight_controller` | STM32F405+IMU+4PWM飞控 | 38 | ~¥65 | drone |
| `drone_aerial_h743` | 航拍级H743+双IMU (ArduPilot) | 68 | ~¥67 | drone |
| `smartwatch_core` | nRF52840+心率+IMU可穿戴 | 28 | ~¥50 | wearable |
| `rp2040_minimal` | RP2040 Pico兼容 USB-C | 21 | ~¥25 | rp2040 |
| `stm32g031_minimal` | STM32G031低成本M0+ | 15 | ~¥8 | stm32 |
| `stm32h743_core` | STM32H743 480MHz高性能 | 21 | ~¥65 | stm32 |
| `gd32f103_minimal` | GD32F103国产STM32平替 | 17 | ~¥10 | stm32 |
| `esp32s3_rs485_can` | ESP32-S3+RS485+CAN工业 | 23 | ~¥55 | communication |
| `ch32v003_minimal` | CH32V003 RISC-V (¥0.5芯片) | 12 | ~¥3 | risc-v |
| `w5500_ethernet` | W5500 SPI以太网 100Mbps | 14 | ~¥18 | communication |
| `motor_driver_dual` | TB6612双H桥电机驱动 | 10 | ~¥10 | motor |
| `usb_c_pd_trigger` | CH224K USB-C PD取电 | 13 | ~¥8 | power |
| `lora_sx1276_gateway` | SX1276 LoRa 433MHz | 11 | ~¥22 | wireless |
| `nrf52840_ble5` | nRF52840 BLE5.0/Zigbee | 13 | ~¥32 | wireless |
| `ams1117_power` | AMS1117-3.3V稳压模块 | 4 | ~¥2 | power |
| `industrial_power` | 12V→5V/3.3V/1.8V三路电源 | 18 | ~¥22 | power |
| `led_indicator` | 三色LED指示灯组 | 8 | ~¥2 | indicator |
| `safety_protection` | TVS+ESD+保险丝+看门狗 | 16 | ~¥18 | protection |
| `lcd_tft_43` | 4.3寸TFT+触摸+DVP摄像头 | 17 | ~¥28 | display |

---

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

---

## 验证状态 (2026-04-08)

| 维度 | 结果 |
|------|------|
| DNA模板 | **21个** |
| DRC零违规 | **21/21 ✅** |
| MCP工具 | **16/16 ✅** |
| BOM覆盖 | **21/21 ✅** (170+ LCSC料号) |
| pipeline | **21/21 ✅** |
| 全量验证 | **23/23 ✅** |
| 线上资源调研 | **2026-04-08 ✅** |

---

## EDA工具链

| 工具 | 位置 | 用途 |
|------|------|------|
| KiCad 9.0 | `D:\KICAD` (台式机) | PCB生成/DRC/Gerber — **AI核心工具** |
| 嘉立创EDA | `D:\lceda-pro` / `Z:\嘉立创EDA\lceda-pro` | 国产EDA, 一键打板 |
| Altium Designer | `D:\ad\Altium.Designer.22.11.1\` | AD22完整版 |
| Keil IDE | `D:\Keil_v5` | STM32开发 |
| Proteus | `D:\proteus` | 仿真 (台式机) |
| freerouting.jar | `pcb_brain/freerouting.jar` | PCB自动布线 (需JRE, 已排除上传) |

---

## 实战项目

### P0: 1500W图腾柱PFC
- oshwhub复刻3KW SiC PFC → 降额1.5KW → 嘉立创EDA全链路 → PCB打样+SMT
- `实战/无桥PFC电气原理图及工程资料包/`

### P4: 仓库车间物流车控制系统
- `python -m schematic_dao build warehouse_logistics_vehicle`
- 50元件/40网络/14模块 已生成
- `实战/仓库车间物流车控制系统设计/` (论文图/文档/BOM/工程源文件)

### 笔记本精华
- `drone_pcb/` — 无人机飞控PCB完整工作流 (SKiDL→KiCad→布线→验证)
- `kicad_projects/` — 风扇控制器/智能小车 KiCad工程
- `tools/` — 嘉立创.eprj解析工具链

### _JLC_READY/
- 21个模板的JLCPCB下单就绪包 (BOM/CPL/Gerber)

---

## 嘉立创EDA Pro 深融状态 (2026-06-29)

> **道法自然 · 反者道之动 · 逆流即深融**

### 已通 EXTAPI 完整能力 (701 methods / 93 namespaces)

| 维度 | API 数 | 关键能力 | 状态 |
|------|--------|----------|------|
| 工程管理 (dmt_*) | 78 | Project/Schematic/PCB/Board CRUD, 标签页控制 | **通** |
| 原理图 (sch_*) | 73 | 放件/连线/Net Flag(VCC/GND)/Net Port/Net Label/DRC | **通** |
| PCB (pcb_*) | 165 | 放件/布线/过孔/覆铜/DRC/网络/坐标转换/清除布线 | **通** |
| 设计规则 (pcb_Drc) | 45 | Net-class/差分对/等长组/规则配置/网间规则/区域规则/实时DRC | **通** |
| 层叠 (pcb_Layer) | 26 | 铜层数(2~32)/物理层叠/自定义层/可见性/锁定 | **通** |
| 制造数据 | 31 | Gerber/BOM/PnP/DSN/3D/DXF/IPC/ODB++/iBOM/Altium/TestPoint | **通** |
| 库 (lib_*) | 64 | Device/Footprint/Symbol/3DModel/CBB/Classification 搜索+CRUD | **通** |
| 系统 (sys_*) | 98 | 快捷键/面板/I18n/定时器/WebSocket/文件系统/格式转换 | **通** |
| 事件 | 18 | 鼠标/图元/网络/交叉选择/实时DRC 监听 | **通** |

### 全链路验证 (Linux VM)

```
build_capstone_full.py RESULT PASS
  place(3 components by LCSC) → wire(route-by-name) → pcb_route(2-layer via)
  → copper_pour(GND L1+L2) → DRC(total=0) → export(Gerber 8494/BOM 6739/PnP 6961 bytes)
```

### 深融新前沿 (本次推进)

| 前沿 | 签名/入口 | 实测 |
|------|-----------|------|
| **电源符号** | `createNetFlag('Power','VCC',x,y,rot,mirror)` | **VCC/GND/AnalogGND/ProtectGND 全通** |
| **网络端口** | `createNetPort('IN'/'OUT'/'BI',name,x,y,rot,mirror)` | **通 (netport-in/out/bi)** |
| **差分对** | `createDifferentialPair(name,posNet,negNet)` | **通 (落库,getAllDifferentialPairs 复读)** |
| **等长组** | `createEqualLengthNetGroup(name,nets,color)` | **通** |
| **设计规则** | `getCurrentRuleConfiguration()` → JLCPCB Capability 全量规则 | **通** |
| **逐网规则** | `getNetRules()/overwriteNetRules()` — Track/Spacing/Via 可写 | **通** |
| **Net-class** | `createNetClass(name,nets,color)` | **返回false不落库(疑似需编辑器上下文)** |
| **铜层管理** | `setTheNumberOfCopperLayers(count)` — 2~32偶数 | **通** |
| **物理层叠** | `getCurrentPhysicalStackingConfiguration()` | **通** |
| **Freerouting** | `getDsnFile()` + `importAutoRouteSesFile()` | **通 (DSN导出+SES回灌闭环)** |
| **扩展导出** | 3D/DXF/IPC-D356A/IPC-2581C/ODB++/iBOM/Altium/TestPoint | **通** |
| **社区资源** | `lib_Device.search/getByLcscIds` + Footprint/Symbol/3D/CBB | **通 (全品类搜索)** |
| **健壮登录** | `op_pwd_robust` + Aliyun 滑块验证码自动解 | **通 (cold_start 集成)** |

### 社区资源接入 (阳路)

```python
from eda_community import Community
c = Community()
c.full_search("ESP32")      # → 5 devices + 5 footprints + 5 symbols + 5 3D models
c.get_device_by_lcsc(["C7466","C14663"])  # LCSC 编号精确取件
c.search_cbb("buck converter")            # CBB 复用电路块
```

---

## 集成路线图

| 优先级 | 项目 | 行动 | 收益 |
|--------|------|------|------|
| P0 | `kicad-tools` | `pip install kicad-tools` → pipeline可选后端 | A*布线替代BFS, LLM布局, Pure Python DRC |
| P1 | JLCPCB API | 参考KiCAD-MCP-Server的JLCSearch | 2.5M+零件库, 实时价格/库存 |
| P2 | `kicad-python` IPC-API | 等PyPI稳定后替代kicad_native.py | 实时KiCad交互, 消除ABI限制 |
| P3 | SKiDL KICAD9 | `generate_netlist(tool=KICAD9)` | 原生KiCad 9 netlist |

---

## 已排除内容 (不在本仓库)

- `__pycache__/` — Python缓存
- `pcb_brain/logs/` — 运行日志
- `pcb_brain/output/` — 生成产物 (可重新生成)
- `pcb_brain/jre/` — 便携JRE (~200MB)
- `pcb_brain/freerouting.jar` — 布线器JAR (5MB, 可重新下载)
- `_live_session/` — 实时会话记录
- `_screencast/` — 截屏记录
- `schematic_dao/_test_out/` — 测试输出
- `lceda_bridge/dist/` — 构建产物
- `lceda_bridge/_recon_jlc/` — 侦察数据
- `*.zip` — 项目打包ZIP (5.5MB PFC资料包)
- `*.backup_*` — KiCad备份文件
- `*.log` — 日志文件

---

## 环境依赖

| 依赖 | 用途 |
|------|------|
| Python 3.11 | 运行时 |
| KiCad 9.0 | PCB/DRC/Gerber (台式机) |
| 嘉立创EDA Pro | 国产EDA (笔记本+台式机) |
| Java JRE | freerouting.jar运行 (便携, 已排除) |
| pywin32 | Windows COM (可选) |

```
# requirements.txt (pcb_brain/)
skidl>=1.2
kinet2pcb>=1.2
# 其他依赖按需安装
```

---

**大道至简 · 此器成矣 · 以御万法**

> 上善若水, 水善利万物而不争. 处众人之所恶, 故几于道.
> 反者道之动, 弱者道之用. 天下之物生于有, 有生于无.
