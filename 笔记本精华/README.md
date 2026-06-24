# 📁 项目模板说明

这个目录包含了各种SKiDL项目模板，帮助您快速开始新的PCB设计项目。

## 🎯 可用模板

### 1. **新项目模板.py** ⭐
- **用途**: 通用项目起始模板
- **包含**: 基础电路结构、LED控制、电源管理
- **特点**: 完整的注释、错误处理、自动化输出

### 2. **即将添加的模板**:
- `微控制器项目模板.py` - MCU核心电路
- `电源管理模板.py` - 电源转换电路  
- `传感器接口模板.py` - 传感器连接电路
- `通信接口模板.py` - UART/SPI/I2C接口

## 🚀 使用方法

### 快速开始
```bash
# 1. 复制模板到项目目录
cp templates/新项目模板.py projects/我的新项目.py

# 2. 编辑项目信息
# 修改文件中的PROJECT_NAME、AUTHOR等变量

# 3. 运行项目
cd projects
python 我的新项目.py
```

### 自定义步骤
1. **修改项目信息**:
   ```python
   PROJECT_NAME = "我的LED控制器"
   PROJECT_VERSION = "1.0.0" 
   AUTHOR = "张三"
   DESCRIPTION = "基于Arduino的LED控制电路"
   ```

2. **调整电路参数**:
   ```python
   VCC_VOLTAGE = 12.0  # 改为12V电源
   LED_CURRENT = 30e-3  # 改为30mA LED
   ```

3. **添加元件**:
   ```python
   # 在define_components()函数中添加
   components['switch'] = Part('Switch', 'SW_Push',
                               ref='SW1',
                               footprint='Button_Switch_THT:SW_PUSH_6mm')
   ```

4. **修改连接**:
   ```python
   # 在connect_circuit()函数中添加连接
   switch[1] += mcu['D2']  # 按钮连接到D2引脚
   switch[2] += gnd       # 另一端接地
   ```

## 📋 模板功能特性

### ✅ 包含的功能
- **自动计算**: LED限流电阻自动计算
- **错误处理**: 完善的异常处理机制
- **设计检查**: 自动DRC检查
- **多种输出**: 网表、ERC报告、BOM清单
- **中文注释**: 详细的中文说明

### 🎨 文件输出
```
output/
└── 项目名/
    ├── 项目名.net      # KiCad网表文件
    ├── 项目名.erc      # 电气规则检查报告
    └── 项目名_bom.txt  # 物料清单
```

## 🔧 配置说明

### KiCad库路径
确保在根目录的`config.py`中配置了正确的KiCad路径:
```python
KICAD_PATHS = [
    "C:/Program Files/KiCad/8.0/share/kicad/symbols",
    "C:/Program Files/KiCad/8.0/share/kicad/footprints",
]
```

### 元件库选择
模板使用标准的KiCad库:
- `Device` - 基础元件 (R, C, L, LED等)
- `MCU_Module` - 微控制器模块
- `Connector` - 连接器
- `Switch` - 开关按钮

## 🎓 学习建议

### 新手建议
1. 从`新项目模板.py`开始
2. 逐步修改参数，观察变化
3. 理解每个函数的作用
4. 学会查看ERC报告

### 进阶技巧
1. 创建自定义组件函数
2. 使用Python循环生成重复电路
3. 实现参数化设计
4. 添加仿真支持

## 🔍 故障排除

### 常见问题
1. **符号库找不到**: 检查config.py配置
2. **网表生成失败**: 检查元件连接是否正确
3. **ERC错误**: 查看未连接的引脚

### 调试技巧
```python
# 添加调试信息
print(f"元件 {part.ref}: {len(part.pins)} 个引脚")
print(f"网络 {net.name}: {len(net.pins)} 个连接")
```

## 📚 参考资源

- [SKiDL官方文档](https://devbisme.github.io/skidl/)
- [KiCad符号库](https://kicad.github.io/symbols/)
- [项目主README](../README.md)

---

**💡 提示**: 每次创建新项目时，建议复制模板并重命名，而不是直接修改模板文件。
















