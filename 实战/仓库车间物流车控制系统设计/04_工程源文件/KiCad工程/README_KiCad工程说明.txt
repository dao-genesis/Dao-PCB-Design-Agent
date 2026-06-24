仓库车间物流车控制系统设计 — KiCad 工程说明 (schematic_dao 真原理图)

1. 文件用途
本文件夹为 `warehouse_logistics_vehicle` 项目的真 KiCad 原理图工程, 含:
  - warehouse_logistics_vehicle.kicad_pro — 工程文件
  - warehouse_logistics_vehicle.kicad_sch — 真原理图 (含 KiCad 标准库符号 + 全局网络标签)
  - 配套 PDF/SVG (由 kicad-cli sch export 自动导出, 见 ../../01_论文图纸/)

道法自然: 不画 wire, 全部走线交由 KiCad 通过同名 global_label 自动连接.
打开 KiCad, 即可见每个元件的真实符号 + 引脚旁的网络标签.

2. 项目规格
- 电源输入: 12V DC (锂电池供电)
- 主控: STM32G030K8T6 (LQFP-32, ARM Cortex-M0+ @ 64MHz)
- 电机驱动: L298N(XBLW) 双H桥, 2A/通道
- 无线通信: 蓝牙 UART (HC-05/HC-04)
- 显示: OLED 0.96" I2C (SSD1306)
- 传感器: HC-SR04 超声波 + 红外循迹×2 + 站点红外 + 压力
- 电池监测: ADC 分压采样 (R28 100K / R29 2K)
- 调试: SWD (PA13/PA14) + 5V 程序下载
- 外形: PCB 双面板 100×80mm (建议)

3. 模块清单 (共 14 个)
- [power_chain] 12V转5V转3.3V稳压电路 — 元件: U11, U12, C20, C21, C22, C23
- [battery_adc] 电池电压ADC采集 — 元件: R28, R29
- [ultrasonic] 超声波传感器接口 — 元件: U1
- [oled] OLED显示屏接口 — 元件: OLED1, R25, R26
- [reset] 复位单片机复位电路 — 元件: RESET1, R5, C5, C6
- [mcu_core] 单片机引脚分配电路 — 元件: U2
- [motor_l298n] L298N电机驱动电路 — 元件: U14, D2, D3, D4, D5, D6
- [swd] 程序下载电路 — 元件: PH-00015_SWD, R3, R4
- [sys_led] 系统指示灯电路 — 元件: LED6, R22
- [bluetooth] 蓝牙模块驱动电路 — 元件: BT1, LED5, R20
- [keys] 按键控制电路 — 元件: KEY1, KEY2, KEY3, KEY4, R23, R23B
- [pressure] 压力采集接口 — 元件: PH-00015_PRESS, R27
- [ir_trace] 红外循迹模块 — 元件: IR_TRACE_L, IR_TRACE_R
- [ir_station] 站点红外探头接口 — 元件: IR_STATION

4. 元件总数: 50 个
   网络总数: 40 条
   引脚总数: 182 个

5. 工程化路径
   - 在 KiCad 内打开 .kicad_sch 即可见原理图全貌
   - 元件位置可手动整理 (本工程使用算法布局, 仅保证可读)
   - 同名 global_label 已电气等效, 可直接 ERC / 生成网表
   - 进入 PCB 阶段: File → New PCB → Import netlist
   - 后续可逐元件绑定真实封装、添加 PWR_FLAG、运行 ERC

6. 配套 BOM 与网络连接表
   - 元器件 BOM 清单: ../../03_BOM与连接表/warehouse_logistics_vehicle_BOM清单.csv
   - 原理图网络连接表: ../../03_BOM与连接表/warehouse_logistics_vehicle_网络连接表.csv

—— schematic_dao 自动生成 vv1.0 ——
