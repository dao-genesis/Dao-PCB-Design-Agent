# PCB设计 — 架构与资源总览

> **PCBBrain**: AI代码化PCB设计闭环系统 — 21个DNA模板, 16个MCP工具, 全链路自动化
> **schematic_dao**: 原理图道 — 一份 SchematicProject → PFC同款四件套资料包
> **核心入口**: `from pcb_core import PCB` 或 `python -m schematic_dao build <project>`
> **操作手册**: [`_AGENT_GUIDE.md`](./_AGENT_GUIDE.md) · [`schematic_dao/_AGENTS.md`](./schematic_dao/_AGENTS.md)

---

## 双引擎并行 (PCB 与 原理图)

| 引擎 | 视角 | 核心数据 | 输出 | 入口 |
|------|------|---------|------|------|
| [`pcb_brain/`](./pcb_brain/) | PCB 布局优先 | `circuit_dna.DNA` (21模板) | `.kicad_pcb` / Gerber / BOM / iBoM | `from pcb_core import PCB` |
| [`schematic_dao/`](./schematic_dao/) | 原理图优先 | `SchematicProject` | SVG/PDF/PNG/MD/CSV/.kicad_sch | `python -m schematic_dao build <name>` |

> 两引擎可串联: SchematicProject (论文级) → DNA (布局级) → PCB打样下单

---

## 系统架构

```
用户需求 (自然语言/模板名)
    │
    ▼
┌─────────────────────────────────────────────────┐
│  pcb_core.py — 统一门面 (万法归宗)              │
│  PCB.quick("描述") / PCB.pipeline("模板")       │
└──────────┬──────────────────────────────────────┘
           │
    ┌──────┼──────────────────────┐
    ▼      ▼                      ▼
 意图解析  风险预判              全闭环流水线
 (parse_  (check_    ┌──────────────────────────┐
  intent)  risks)    │ pcb_pipeline.py (6阶段)  │
                     │ DNA→PCB→DRC→Gerber→BOM→  │
                     │ iBoM→JLCPCB下单包        │
                     └──────────────────────────┘
                        │  │  │  │  │
              ┌─────────┘  │  │  │  └──────┐
              ▼            ▼  ▼  ▼         ▼
         circuit_dna  kicad_arm pcb_eye pcb_jlcpcb
         (21模板)    (引擎)    (感知)   (生产)
```

## 模块依赖图 (真实import关系)

```
_pcb_bootstrap.py          ← Layer 0: UTF-8/路径/日志/环境 (全局根基)
    ↑
circuit_dna.py (128KB)     ← Layer 1: 21个DNA模板 (数据层, 无依赖)
    ↑
kicad_arm.py (58KB)        ← Layer 2: PCB生成/BFS v4布线/DRC/Gerber (引擎层)
    ↑
pcb_eye.py (21KB)          ← Layer 3: DRC/BOM/Gerber验证 (感知层)
pcb_jlcpcb.py (38KB)       ← Layer 3: BOM/CPL/成本/LCSC 170+料号 (生产层)
pcb_ibom.py (22KB)         ← Layer 3: 交互式HTML BOM
    ↑
pcb_pipeline.py (27KB)     ← Layer 4: 全闭环流水线 (编排层)
    ↑
pcb_core.py                ← Layer 5: 统一门面API + 风险预判 + 意图解析
pcb_brain.py (24KB)        ← Layer 5: CLI入口
pcb_mcp.py (47KB)          ← Layer 5: MCP服务器 (16工具)
pcb_server.py (102KB)      ← Layer 5: HTTP服务器 (:9906)

可选:
kicad_native.py (38KB)     ← KiCad 9 pcbnew桥 (153封装库/225符号库)
agent_sense.py (16KB)      ← 远程Agent扩展 (:9904)
```

## EDA工具链

| 工具 | 位置 | 用途 |
|------|------|------|
| KiCad 9.0 | `D:\KICAD` (台式机) | PCB生成/DRC/Gerber — **AI核心工具** |
| 嘉立创EDA | `D:\lceda-pro` / `Z:\嘉立创EDA\lceda-pro` | 国产EDA, 一键打板 |
| Altium Designer | `D:\ad\Altium.Designer.22.11.1\` | AD22完整版 |
| Keil IDE | `D:\Keil_v5` | STM32开发 |
| Proteus | `D:\proteus` | 仿真 (台式机) |

## 用户项目

| 项目 | 位置 | 说明 |
|------|------|------|
| 嘉立创初版 | `D:\电路设计嘉立创\` | 2024-09, 台式机最早PCB设计 |
| STM32点阵控制 | `D:\keil代码\stm32\` | STM32F103C6, 串口控制LED点阵, **已验证** |
| ESP32 WiFi舵机 | `D:\电路代码\sketch_sep3b.ino` | ESP32+WebServer, HTTP控制舵机 |
| AD课程作业 | `Z:\adpcbexample\PCB_Project_1homework\` | 含BOM+Gerber, 真实打板级 ✅ |
| AD台式机工程 | `D:\ad\ad_project\` | AD22原理图+PCB工程 |
| 无人机飞控 | `pcb_brain/circuit_dna.py` | 38元件, STM32F405+IMU, DNA已集成 |

## DNA模板一览 (21个)

| 模板 | 描述 | 元件 | 成本 | 分类 |
|------|------|------|------|------|
| `stm32f103c6_dot_matrix` | STM32F103C6+LED点阵 | 17 | ~¥12 | stm32 |
| `esp32_servo_wifi` | ESP32 WiFi+舵机 | 16 | ~¥28 | esp32 |
| `drone_flight_controller` | STM32F405+IMU+4PWM飞控 | 38 | ~¥65 | drone |
| `drone_aerial_h743` | **航拍级H743+双IMU (ArduPilot)** | 68 | ~¥67 | drone |
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

> 完整模板详情: `python pcb_core.py` 或 `PCB.list_templates_detail()`

## 落地路径

> 详见 [`docs/全链路实现方案.md`](./docs/全链路实现方案.md)

- **P-2 📐 schematic_dao 原理图道** — `python -m schematic_dao build <project>` → 一键生成 PFC 同款四件套资料包 (论文图/文档/BOM/网表/工程源文件). 当前已注册项目: `warehouse_logistics_vehicle` (仓库车间物流车控制系统设计) → [**详见 `schematic_dao/_AGENTS.md`**](./schematic_dao/_AGENTS.md)
- **P-1 🌉 嘉立创底层直连** — `lceda_bridge/` 五层穿透 (独立脚本→扩展→iframe桥→文件→云端). 反者道之动, 让 Python/Windsurf 直接驱动嘉立创EDA → [**详见 `lceda_bridge/README.md`**](./lceda_bridge/README.md)
- **P0 🔥 实战: 1500W图腾柱PFC** — oshwhub复刻3KW SiC PFC → 降额1.5KW → 嘉立创EDA全链路 → PCB打样+SMT → 调试验证 → [**详见 `实战/README.md`**](./实战/README.md)
- **P1 嘉立创主线** — oshwhub复刻STM32F103C6板 → 嘉立创EDA改板 → Gerber打样(5片≈¥20) → 焊接 → 烧录`main.c`
- **P2 ESP32舵机板** — oshwhub复刻ESP32最小系统 → 加舵机电路 → 打样 → WiFi HTTP验证
- **P3 无人机飞控** — `python pcb_brain.py full drone_flight_controller` → 全链路自动交付
- **P4 仓库物流车控制系统** — `python -m schematic_dao build warehouse_logistics_vehicle` → 50元件/40网络/14模块 已生成 → [**详见 `实战/仓库车间物流车控制系统设计/`**](./实战/仓库车间物流车控制系统设计/)

## 开源参考

> 详见 [`docs/线上资源参考.md`](./docs/线上资源参考.md) (2026-04-08 综合调研)

| 项目 | 状态 | 集成方式 |
|------|------|----------|
| [SKiDL](https://github.com/devbisme/skidl) | ✅ 已集成 | `circuit_dna.py` (支持KICAD9) |
| [freerouting](https://github.com/freerouting/freerouting) | ✅ 已集成 | `kicad_arm.auto_route_freerouting()` |
| [InteractiveHtmlBom](https://github.com/openscopeproject/InteractiveHtmlBom) | ✅ 已集成 | `pcb_ibom.py` |
| [kicad-jlcpcb-tools](https://github.com/Bouni/kicad-jlcpcb-tools) | ✅ 已集成 | `pcb_jlcpcb.py` |
| [kicad-tools](https://github.com/rjwalters/kicad-tools) | 🔜 **P0待集成** | A\*布线/LLM布局/Pure Python DRC/制造商规则 |
| [KiCAD-MCP-Server](https://github.com/mixelpixx/KiCAD-MCP-Server) | 📖 参考 | 122工具/JLCPCB API 2.5M+零件/Tool Router |
| [kicad-mcp-python](https://github.com/Finerestaurant/kicad-mcp-python) | 🔜 P2待评估 | KiCad官方IPC-API替代pcbnew |

## 待办

- [ ] **P0**: `pip install kicad-tools` → 集成A\*布线/LLM布局/Pure Python DRC到pipeline
- [ ] **P1**: 参考KiCAD-MCP-Server的JLCSearch API增强`pcb_jlcpcb.py` (2.5M+零件库)
- [ ] **P2**: 等`kicad-python` IPC-API稳定后替代`kicad_native.py`
- [ ] **P3**: 升级SKiDL至KICAD9 netlist生成
- [ ] 清理重复副本: `Z:\github\AI _PCB设计\`, `Z:\道\道生一\一生二\PCB设计\`
- [ ] 清理空STUB: `Z:\adpcbexample\PCB_Project_1homework1\`, `homework2\`
- [ ] 清理 `output/` 旧文件

---

*位置: `V:\道\道生一\一生二\PCB设计\` | 操作手册: [`_AGENT_GUIDE.md`](./_AGENT_GUIDE.md)*
