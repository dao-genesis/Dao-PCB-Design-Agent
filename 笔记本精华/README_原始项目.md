# 🔧 AI辅助PCB设计项目

> 使用代码化方式进行PCB设计的完整工作流程探索

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![SKiDL](https://img.shields.io/badge/SKiDL-2.0.1-green.svg)](https://github.com/devbisme/skidl)
[![KiCad](https://img.shields.io/badge/KiCad-8.0-orange.svg)](https://www.kicad.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 📋 项目简介

本项目探索使用代码化方式进行PCB设计，类似于OpenSCAD之于3D建模。通过集成多种现代PCB设计工具链，实现从电路设计到PCB制造的全自动化流程。

### 🎯 核心目标

- ✅ **代码驱动设计**: 使用Python等编程语言描述电路
- ✅ **版本控制友好**: 所有设计文件可纳入Git管理
- ✅ **自动化流程**: 从电路图到PCB布局的自动化
- ✅ **多工具集成**: SKiDL、Atopile、KiCad等工具链整合

## 🏆 主要成果

### 🚁 无人机飞控PCB
- **43个元器件**完整集成
- **74.7%自动化**连接率
- STM32F405主控 + MPU-6050 IMU
- 4路电机PWM控制
- 完整电源管理系统
- **生产就绪状态** ✅

### 🚗 智能车项目
- ATmega328P主控
- L298N双电机驱动
- HC-SR04超声波传感器
- 完整通信接口(UART/I2C/SPI)
- **100%构建成功率** ✅

## 📁 项目结构

```
AI_PCB设计/
├── 📄 README.md                    # 项目主文档
├── 📄 requirements.txt              # Python依赖
├── 📄 config.py                     # 项目配置
│
├── 📂 projects/                     # 主要项目源码
│   ├── drone_flight_controller_skidl.py
│   ├── smart_car_skidl.py
│   └── ...更多项目
│
├── 📂 drone_pcb_project/            # 无人机飞控完整项目
│   ├── FINAL_PROJECT_SUMMARY.md
│   ├── run_complete_workflow.py
│   └── drone_flight_controller.kicad_pcb
│
├── 📂 KICAD/                        # KiCad项目集合
│   ├── Atopile/smart-car/          # Atopile智能车项目
│   ├── KICAD_optimized_v4.kicad_pcb
│   └── ...其他KiCad项目
│
├── 📂 completed_projects/           # 完成项目输出
│   ├── *.net                       # 网表文件
│   ├── *.erc                       # 电气规则检查报告
│   └── *.csv                       # 物料清单
│
├── 📂 examples/                     # 示例和演示
│   └── demos/                      # 演示脚本
│
├── 📂 libraries/                    # 自定义元件库
│   ├── basic_circuit_lib_sklib.py
│   └── ...其他库文件
│
├── 📂 templates/                    # 项目模板
│   ├── 新项目模板.py
│   └── README.md
│
├── 📂 docs/                         # 文档中心
│   ├── reports/                    # 项目报告
│   ├── guides/                     # 使用指南
│   ├── jitx/                       # JITX相关文档
│   └── environment/                # 环境配置文档
│
├── 📂 configs/                      # 配置文件
│   ├── network/                    # 网络配置
│   ├── ato.yaml                    # Atopile配置
│   └── slm.toml                    # Stanza配置
│
├── 📂 tools/                        # 工具脚本
│   ├── eprj_analyzer.py
│   └── ...其他工具
│
├── 📂 scripts/                      # 自动化脚本
│   └── organize_files.ps1
│
├── 📂 utils/                        # 工具函数
│   └── circuit_tools.py
│
├── 📂 html_downloads/               # HTML文档
├── 📂 analysis_output/              # 分析输出
├── 📂 extracted_data/               # 提取数据
├── 📂 archived_files/               # 归档文件
│
├── 📂 jitx_projects/                # JITX项目
├── 📂 stanza_tests/                 # Stanza测试
├── 📂 KICADlizi/                    # KiCad练习项目
└── 📂 output/                       # 构建输出
```

## 🚀 快速开始

### 环境要求

- **Python**: 3.11+
- **KiCad**: 8.0+
- **操作系统**: Windows/Linux/MacOS

### 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/yourusername/AI_PCB设计.git
cd AI_PCB设计

# 2. 安装Python依赖
pip install -r requirements.txt

# 3. 安装KiCad (如果尚未安装)
# 访问 https://www.kicad.org/download/

# 4. 配置环境
python config.py
```

### 运行示例

```bash
# SKiDL基础示例
python projects/simple_led.py

# 无人机飞控完整工作流
cd drone_pcb_project
python run_complete_workflow.py

# Atopile智能车项目
cd KICAD/Atopile/smart-car
ato build
```

## 🛠️ 技术栈

### 主要工具

| 工具 | 版本 | 用途 | 状态 |
|------|------|------|------|
| **SKiDL** | 2.0.1 | 电路设计主力 | ✅ 完全配置 |
| **Atopile** | latest | 声明式电路设计 | ✅ 集成完成 |
| **KiCad** | 8.0+ | PCB布局和输出 | ✅ 完全集成 |
| **JITX** | 3.31.2 | 高级设计探索 | ⚠️ 实验性 |

### Python包

```
skidl==2.0.1
matplotlib==3.8.4
schemdraw==0.21
numpy==1.26.4
graphviz==0.21
kinet2pcb==1.1.2
kinparse==1.2.4
```

## 📚 学习路径

### 第1周：基础入门
1. 阅读 `docs/environment/` 中的环境配置指南
2. 运行 `projects/` 中的简单示例
3. 理解SKiDL基本语法

### 第2周：实践项目
1. 使用 `templates/新项目模板.py` 创建项目
2. 学习网表生成和ERC报告
3. 完成LED控制电路

### 第3-4周：进阶应用
1. 研究无人机飞控项目
2. 学习自动化布局流程
3. 掌握KiCad集成

### 长期目标
1. 创建自定义元件库
2. 开发自动化工具
3. 参与社区贡献

## 📖 文档资源

- 📘 [环境部署指南](docs/environment/环境部署最终总结.md)
- 📙 [SKiDL快速入门](docs/guides/)
- 📗 [无人机项目总结](drone_pcb_project/FINAL_PROJECT_SUMMARY.md)
- 📕 [智能车项目文档](KICAD/Atopile/SMART_CAR_PROJECT_SUMMARY.md)
- 📓 [JITX使用指南](docs/jitx/JITX_使用指南.md)

## 🎯 项目特色

### 1. 完整的工作流程
从电路设计 → 网表生成 → PCB布局 → 制造输出

### 2. 多工具对比
并行探索SKiDL、Atopile、JITX，全面评估各工具优劣

### 3. 实际应用导向
不仅是理论学习，而是可以实际生产的项目

### 4. 详尽的文档
每个阶段都有完整的总结报告和使用指南

### 5. 自动化优先
最大程度减少手工操作，提高设计效率

## 🤝 贡献指南

欢迎贡献！请：

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启Pull Request

## 📊 项目统计

- **项目总数**: 15+
- **代码文件**: 100+
- **文档页数**: 50+
- **元器件库**: 500+
- **成功率**: 85%+

## 🔗 相关链接

- [SKiDL官方文档](https://devbisme.github.io/skidl/)
- [Atopile官网](https://atopile.io/)
- [KiCad官网](https://www.kicad.org/)
- [项目Wiki](docs/)

## 📝 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 👥 作者

- 项目创建者 - [@yourusername](https://github.com/yourusername)

## 🙏 致谢

- SKiDL开发团队
- KiCad社区
- Atopile团队
- 所有贡献者

---

**⭐ 如果这个项目对您有帮助，请给个星标支持！**

**📧 有问题或建议？[提交Issue](https://github.com/yourusername/AI_PCB设计/issues)**
