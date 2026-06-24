1500W 图腾柱式无桥 PFC KiCad 工程说明

1. 文件用途
本文件夹提供毕业设计后续工程化绘制的 KiCad 工程雏形，包含项目文件 bridgeless_pfc.kicad_pro 和示意级原理图 bridgeless_pfc.kicad_sch。
该工程用于继续整理正式原理图，不等同于可直接投产 PCB 文件。

2. 当前工程包含的模块
- AC 输入保护：F1、MOV1、NTC1、K1；
- EMI 滤波：Lcm、Cx、Cy1、Cy2；
- 图腾柱式无桥 PFC 主功率：Q1~Q4、L1、Cbus；
- 采样信号：VIN_S、VBUS_S、IL_S、ZCD；
- 驱动信号：GH、GL、GDH、GDL；
- 保护信号：UVLO、OVP、OCP、OTP、FAULT；
- 辅助电源：+15V、+5V/+3.3V。

3. 继续做 AD / KiCad 工程时必须补充
- 最终器件型号与封装；
- 引脚编号和符号库；
- 高压安全间距、爬电距离和 PCB 热设计；
- 驱动电源隔离方案；
- 电流采样具体实现方式；
- EMI 滤波器实测优化参数。

4. 重要校核
1500W、85VAC 低压输入工况下输入电流约为 18A，输入保险丝、共模电感、软启动器件、PCB 铜箔宽度都不能按小功率电源处理。
