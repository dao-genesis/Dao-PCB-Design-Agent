# 仓库车间物流车控制系统设计 电气原理图工程资料包

> 项目代号: `warehouse_logistics_vehicle`  ·  版本: v1.0
> 创建: 2024-06-13  ·  更新: 2026-04-27
> 由 [`schematic_dao`](../../schematic_dao/) 自动生成 — 一份道, 多重源文件

---

## 项目规格

- **电源输入**: 12V DC (锂电池供电)
- **主控**: STM32G030K8T6 (LQFP-32, ARM Cortex-M0+ @ 64MHz)
- **电机驱动**: L298N(XBLW) 双H桥, 2A/通道
- **无线通信**: 蓝牙 UART (HC-05/HC-04)
- **显示**: OLED 0.96" I2C (SSD1306)
- **传感器**: HC-SR04 超声波 + 红外循迹×2 + 站点红外 + 压力
- **电池监测**: ADC 分压采样 (R28 100K / R29 2K)
- **调试**: SWD (PA13/PA14) + 5V 程序下载
- **外形**: PCB 双面板 100×80mm (建议)

## 统计

- 模块: **14** 个
- 元器件: **50** 个 (引脚总数 **182**)
- 电气网络: **40** 条
- 元件分组: actuator, connector, display, indicator, input, mcu, passive, power, protection, sensor, wireless

---

## 资料包结构

### 01_论文图纸

- `warehouse_logistics_vehicle_规范矢量版.svg`
- `warehouse_logistics_vehicle_彩图版.svg`
- `warehouse_logistics_vehicle_KiCad真原理图.pdf`
- `warehouse_logistics_vehicle_KiCad真原理图.svg`

### 02_论文文档

- `warehouse_logistics_vehicle_电气原理图设计说明.md`
- `warehouse_logistics_vehicle_论文正文插入版.md`

### 03_BOM与连接表

- `warehouse_logistics_vehicle_BOM清单.csv`
- `warehouse_logistics_vehicle_网络连接表.csv`
- `warehouse_logistics_vehicle_KiCad原生BOM.csv`
- `warehouse_logistics_vehicle_python_bom.xml`

### 04_工程源文件

- `warehouse_logistics_vehicle.kicad_pro`
- `warehouse_logistics_vehicle.kicad_sch`
- `README_KiCad工程说明.txt`
- `warehouse_logistics_vehicle.net`
- `warehouse_logistics_vehicle_erc.json`
- `warehouse_logistics_vehicle_erc.report.txt`
- `warehouse_logistics_vehicle.dxf`
- `一键打开KiCad工程.cmd`
- `一键打开原理图.cmd`
- `warehouse_logistics_vehicle_easyeda_source.json`
- `Altium_工程导入准备说明.txt`
- `warehouse_logistics_vehicle_网络连接表.csv`


---

## 后续工程化路径

1. **EDA 二次完善**: 在 KiCad / Altium / EasyEDA 内为每个元件绑定真实符号 + 封装
2. **ERC 检查**: 通过 ERC 后再进入 PCB 阶段
3. **PCB 布局布线**: 遵守去耦/晶振/电源/差分对四条黄金规则
4. **DRC 检查**: 0 错误后导出 Gerber + BOM + CPL
5. **打样下单**: jlcpcb.com 或嘉立创EDA一键下单
6. **焊接 + 调试**: 对照 BOM 备料, 逐模块通电验证

---

*文档由 `schematic_dao.pipeline.generate_pack()` 自动生成*
