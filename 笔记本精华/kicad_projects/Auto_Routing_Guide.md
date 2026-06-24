# 智能小车PCB自动布线指南

## 🎯 优化完成 - 准备自动布线

### v4.0版本优化要点

✅ **已完成的优化**:
1. **网络定义完整** - 所有24个网络都已定义
2. **元器件布局优化** - 为自动布线调整了最佳位置
3. **引脚网络分配** - 每个焊盘都分配了正确的网络
4. **PCB层叠结构** - 定义了标准的双层板结构

## 📋 网络连接表

| 网络名称 | 功能 | 连接元器件 |
|----------|------|------------|
| `+5V` | 电源正极 | 电源输入、Nano、传感器、电机 |
| `GND` | 电源地 | 所有地线连接 |
| `RST` | 复位信号 | 复位开关到Nano |
| `PWR_LED` | 电源指示 | 电阻R1到LED_PWR |
| `STATUS_LED` | 状态指示 | 电阻R2到LED_STATUS |
| `D8` | 数字引脚8 | 控制状态LED |
| `SENSOR1_SIG` | 传感器1信号 | 模拟输入 |
| `SENSOR2_SIG` | 传感器2信号 | 模拟输入 |
| `MOTOR_L_PWM` | 左电机PWM | 电机控制 |
| `MOTOR_L_DIR` | 左电机方向 | 电机控制 |
| `MOTOR_R_PWM` | 右电机PWM | 电机控制 |
| `MOTOR_R_DIR` | 右电机方向 | 电机控制 |

## 🔧 KiCad自动布线设置指南

### 第一步：打开PCB编辑器
1. 在KiCad中打开 `KICAD_optimized_v4.kicad_pcb`
2. 确认所有元器件都已正确加载
3. 检查网络连接是否正确显示

### 第二步：设计规则检查 (DRC)
```
1. 菜单: Tools → Design Rules Checker
2. 点击 "Run DRC" 
3. 解决所有错误和警告
4. 确保网络连接正确
```

### 第三步：设置布线规则
进入 `File → Board Setup → Design Rules`:

#### 🔗 网络类别设置
```
Default (默认):
- Track Width: 0.25mm (一般信号)
- Via Size: 0.8mm / 0.4mm drill

Power (电源):
- Track Width: 0.5mm (电源线)
- Via Size: 0.8mm / 0.4mm drill
- 包含网络: +5V, GND
```

#### 📏 布线规则
```
Minimum Track Width: 0.2mm
Minimum Via Size: 0.6mm
Minimum Drill: 0.3mm
Minimum Clearance: 0.2mm
```

### 第四步：自动布线器选择

#### 选项1：KiCad内置自动布线器 (简单)
```
1. 菜单: Tools → External Tools → FreeRouting
2. 如果没有安装，需要先下载FreeRouting
3. 导出.dsn文件进行布线
```

#### 选项2：使用FreeRouting (推荐)
```
1. 菜单: File → Export → Specctra DSN
2. 保存为 smart_car_v4.dsn
3. 在FreeRouting中打开DSN文件
4. 运行自动布线
5. 导出.ses文件
6. 在KiCad中导入: File → Import → Specctra Session
```

#### 选项3：使用插件自动布线器
```
1. 安装KiCad-Router插件
2. 或使用外部布线器如Altium、TopRouter
```

## ⚙️ 推荐自动布线参数

### FreeRouting参数设置
```
General Settings:
- Board: Double-sided
- Layer Count: 2
- Via Costs: Medium
- Trace Costs: Low

Routing Settings:
- Pass Count: 100
- Optimization: 50 passes
- Via Optimization: Enable
- Post Route Optimization: Enable

Via Rules:
- Minimum Via: 0.6mm
- Preferred Via: 0.8mm
- Maximum Via: 1.2mm
```

### 布线优先级设置
```
High Priority Networks:
1. GND (地网络)
2. +5V (电源网络)
3. PWR_LED, STATUS_LED (LED控制)

Medium Priority:
4. RST (复位信号)
5. Motor control signals
6. Sensor signals

Low Priority:
7. Unused pins
```

## 🎯 布线策略建议

### 1. 电源网络优先
- 先布GND网络，尽量使用填充
- +5V使用较宽的走线 (0.5mm)
- 避免电源走线过长

### 2. 信号完整性
- 数字信号尽量走直线
- 避免90度转角，使用45度或圆弧
- 高频信号远离晶振区域

### 3. 地平面处理
- 底层大面积铺地
- 顶层局部铺地填充空隙
- 确保良好的地回路

### 4. 机械考虑
- 避开安装孔周围
- 保持边缘距离
- 考虑元器件高度

## 📝 自动布线步骤清单

### 预处理检查 ✅
- [ ] 所有元器件都有正确的封装
- [ ] 网络连接表完整
- [ ] DRC检查通过
- [ ] 设计规则设置正确

### 布线执行 🔄
- [ ] 导出DSN文件
- [ ] 在FreeRouting中设置参数
- [ ] 运行自动布线
- [ ] 检查布线结果
- [ ] 手动调整问题区域

### 后处理优化 🔧
- [ ] 导入布线结果
- [ ] 运行DRC检查
- [ ] 添加铜填充
- [ ] 最终DRC验证
- [ ] 生成制造文件

## 🚨 常见问题解决

### 问题1：布线无法完成100%
```
解决方案:
1. 调整元器件位置
2. 增加通孔数量
3. 手动预布一些关键信号
4. 适当放宽设计规则
```

### 问题2：布线密度过高
```
解决方案:
1. 优化元器件布局
2. 使用更小的过孔
3. 减少不必要的连接
4. 考虑四层板设计
```

### 问题3：电源网络布线困难
```
解决方案:
1. 优先布电源和地
2. 使用星形供电
3. 增加电源焊盘
4. 使用铜填充代替走线
```

## 🎯 最终验证步骤

### 1. 电气验证
```bash
- DRC检查: 0 errors, 0 warnings
- 网络连接: 100%完成
- 孤立焊盘: 0个
```

### 2. 机械验证
```bash
- 安装孔位置正确
- 元器件无干涉
- PCB尺寸符合要求
```

### 3. 制造准备
```bash
- Gerber文件生成
- 钻孔文件生成
- 装配图生成
- BOM清单准备
```

## 🚀 下一步操作

1. **立即开始**: 在KiCad中打开 `KICAD_optimized_v4.kicad_pcb`
2. **设置规则**: 按照本指南配置设计规则
3. **执行布线**: 使用推荐的参数进行自动布线
4. **优化调整**: 根据结果进行必要的手动调整
5. **验证完成**: 确保所有检查都通过

---

**提示**: v4.0版本已经为自动布线做了最佳优化，按照本指南操作应该能获得良好的布线结果！

**版本**: v4.0  
**适用**: KiCad 8.0+  
**状态**: 准备就绪 🚀







