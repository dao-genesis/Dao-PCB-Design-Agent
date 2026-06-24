# 实战 — 1500W 图腾柱无桥PFC 全链路落地

> **反者道之动** — 从开源复刻出发，站在巨人肩上，利用嘉立创一切之资，打通设计→制造→调试全链路
> **道法自然 无为而无不为** — 每一步都有明确动作，不依赖记忆，不产生决策疲劳

---

## 〇、嘉立创全生态速查

| 平台 | 用途 | 入口 |
|------|------|------|
| **嘉立创EDA** | 原理图+PCB设计 | https://lceda.cn / 本地客户端 |
| **oshwhub** | 开源硬件复刻 | https://oshwhub.com |
| **LCSC** | 元器件采购 (2.5M+料号) | https://www.lcsc.com |
| **嘉立创PCB** | PCB打样/批量 | https://www.jlcpcb.com |
| **嘉立创SMT** | PCBA贴片焊接 | https://smt.jlc.com |
| **嘉立创激光钢网** | 钢网+治具 | https://www.jlc-laser.com |
| **嘉立创3D打印** | 外壳/结构件 | https://www.jlc-3dp.cn |
| **嘉立创CNC** | 散热器/金属件 | https://www.jlc-cnc.com |
| **嘉立创CAM** | Gerber审查 | https://www.jlccam.com |

---

## 一、开源复刻起点 (最快路径)

### ⭐ 核心参考：3KW碳化硅图腾柱PFC (oshwhub)

| 属性 | 值 |
|------|-----|
| **链接** | https://oshwhub.com/leichaolin/3kw-totem-pole-pfc-with-silicon- |
| **功率** | 3000W (设计3500W) |
| **输入** | AC 110V~270V, 20A max |
| **输出** | DC 350V~430V, 20A max |
| **效率** | 98.5% |
| **拓扑** | 图腾柱无桥PFC (CCM) |
| **主控** | CW32 + IVCC1102 双主控 |
| **开关管** | SiC MOSFET (碳化硅) |
| **驱动** | 负压驱动 |
| **协议** | GPL 3.0 开源 |
| **EDA** | 嘉立创EDA专业版 (可直接复制工程) |

**操作步骤**：
```
1. 浏览器打开上述链接
2. 点击右上角「克隆工程」→ 自动导入嘉立创EDA专业版
3. 工程包含：完整原理图 + PCB + BOM + 3D模型
4. 重命名：1500W_TotemPole_PFC_v1
```

### 备选参考

| 项目 | 链接 | 特点 |
|------|------|------|
| 三相双向SiC无桥图腾柱 | https://oshwhub.com/monnina/san-xiang-shuang-xiang-SiCwu-qia | 三相AC-DC, 研究级 |
| TI UCC28070 PFC参考设计 | TI官网搜索 | 模拟控制, 参考电路成熟 |

---

## 二、本项目工程资料结构

```
实战/
├── 无桥PFC电气原理图及工程资料包.zip
└── 无桥PFC电气原理图及工程资料包/
    └── 无桥PFC电气原理图及工程资料包/
        ├── 01_论文图纸/          ← 彩图+矢量原理图 (PDF/PNG/SVG)
        ├── 02_论文文档/          ← 设计说明 + 论文章节
        ├── 03_BOM与连接表/       ← BOM.csv + 网络连接表.csv
        └── 04_工程源文件/
            ├── KiCad工程/        ← .kicad_pro + .kicad_sch (框架级)
            ├── EasyEDA源文件/    ← JSON结构定义 (5模块/19网络)
            ├── Altium导入准备/   ← 网表CSV
            └── SPICE仿真初稿/
```

**现状**：KiCad原理图为框架级(文本标注+网络标签)，需补充完整符号/封装。
**策略**：不从零画，从oshwhub复刻成熟设计→修改适配→投产。

---

## 三、BOM → LCSC 元器件映射

> 在嘉立创EDA中搜索器件时，优先选择 **Basic/Preferred** 分类（免换料费）

### 3.1 输入保护与EMI滤波

| Ref | 名称 | 关键参数 | LCSC搜索关键词 | 封装建议 | 备注 |
|-----|------|----------|----------------|----------|------|
| F1 | 保险丝 | T25A 250VAC | `fuse 25A 250V` | 5×20mm PCB座 / 板载 | 慢断型, 陶瓷管 |
| MOV1 | 压敏电阻 | 470V (14D471K) | `varistor 471K 14D` | 径向引线 | 并联L-N |
| NTC1 | NTC限流器 | 5Ω/15A | `NTC 5R 15A inrush` | 径向引线 | 稳态需旁路 |
| K1 | 旁路继电器 | ≥250VAC ≥25A | `relay 250VAC 25A` | PCB继电器 | 母线建立后导通 |
| Lcm | 共模电感 | 2×2mH ≥20A | `common mode choke 2mH 20A` | 大环形/UU | 按EMI测试调整 |
| Cx | X电容 | 0.47µF/275VAC X2 | `X2 capacitor 0.47uF 275V` | 方块引线 | 安规件 |
| Cy1/Cy2 | Y电容 | 2.2nF Y1/Y2 | `Y capacitor 2.2nF Y1` | 圆片/方块 | 接PE, 注意漏电流 |

### 3.2 主功率级

| Ref | 名称 | 关键参数 | LCSC搜索关键词 | 封装建议 | 备注 |
|-----|------|----------|----------------|----------|------|
| Q1/Q2 | 高频SiC MOSFET | 650V/40mΩ | `SiC MOSFET 650V 40mohm` | TO-247-3/4 | **关键器件**: IMW120R045M1 / C3M0040120K / SCT3040KL |
| Q3/Q4 | 工频同步整流 | 650V/低Rds(on) | `SiC MOSFET 650V` 或 Si超结 | TO-247 | 低频换向, Si超结MOS也可 |
| L1 | 升压电感 | ~450µH ≥25A | 定制件或搜 `PFC inductor` | 大磁芯绕制 | **需按纹波/饱和重新核算** |
| Cbus1/2 | 母线电容 | 470µF/450V | `electrolytic 470uF 450V` | 径向引线 35×50mm | 注意纹波电流额定 |
| Rbleed | 泄放电阻 | 220kΩ/2W | `resistor 220K 2W` | 金属膜 | 掉电安全 |
| CS1 | 电流采样 | ≥25A | `hall sensor 25A` 或 `current transformer` | PCB贴装/穿心 | 霍尔/互感器优先 |

### 3.3 驱动与控制

| Ref | 名称 | 关键参数 | LCSC搜索关键词 | 封装建议 | 备注 |
|-----|------|----------|----------------|----------|------|
| U1/U2 | 隔离驱动器 | 高速/隔离 | `isolated gate driver SiC` | SOIC-16 / 宽体 | UCC21520 / Si8233 / ACPL-332J |
| U5 | PFC控制器 | 电压外环+电流内环 | `PFC controller UCC28070` 或 MCU | DIP/TSSOP | 数字控制: STM32G4 / TMS320F280 |
| U6 | 辅助电源 | 400V→15V/5V | `flyback controller` + 变压器 | — | VIPer系列 / TNY系列 |
| Rg1~4 | 栅极电阻 | 按驱动器定 | `resistor 10R 0805` | 0805 | 控制开关速度 |

### 3.4 采样与保护

| Ref | 名称 | 关键参数 | LCSC搜索关键词 | 封装 | 备注 |
|-----|------|----------|----------------|------|------|
| Rv1~3 | 高压分压 | MΩ级串联 | `resistor 1M 1206 1%` | 1206 | 多颗串联分压, 注意耐压 |
| NTC_T | 温度检测 | 10kΩ B=3950 | `NTC 10K 3950` | 径向 | OTP保护 |
| 运放/比较器 | OCP/OVP/UVLO | 高速 | `comparator LM393` | SOIC-8 | 保护环路 |

---

## 四、嘉立创EDA → PCB → 投产 全链路

### Phase 1: 原理图 (嘉立创EDA专业版)

```
操作路径:
1. 克隆oshwhub开源工程 → 嘉立创EDA云端
2. 对照本项目BOM (03_BOM与连接表/) 校验器件
3. 修改适配:
   - 功率降额: 3KW参考→1.5KW实际 (电感/电容/保险丝重新选型)
   - 控制器: 如需UCC28070模拟控制, 替换数字主控部分
   - 辅助电源: 按实际VCC需求调整
4. 运行ERC → 0 Error
5. 导出网表: 文件→导出→网表
```

### Phase 2: PCB布局布线

```
高压PCB黄金规则 (1500W/400VDC 强制):
┌─────────────────────────────────────────────────┐
│ 1. 爬电距离: 强弱电间距 ≥ 6.4mm (400VDC, B组)  │
│ 2. 铜厚: 内层2oz, 外层2oz (大电流走线)         │
│ 3. 线宽: 20A走线 ≥ 5mm (外层2oz)               │
│ 4. SW_HF节点: 最短最紧凑, 远离采样线            │
│ 5. 隔离沟槽: 高低压间开槽 + 安规距离            │
│ 6. 散热: 功率器件大面积铜皮 + 过孔阵列          │
│ 7. EMI: 共模电感靠近输入, Y电容靠近PE           │
└─────────────────────────────────────────────────┘

嘉立创EDA操作:
1. 原理图→设计→更新/导入PCB
2. 板框: 建议 150×100mm (双面, 4层优选)
3. 布局: 功率回路优先, 信号回路其次
4. 布线: 手动布大电流, 自动布信号线
5. 铺铜: 顶层PGND, 底层PGND, 过孔阵列连通
6. DRC: 设计→设计规则检查 → 0 Error
7. 3D预览: 检查元件间距/高度
```

### Phase 3: 制造文件导出

```
Gerber导出:
  嘉立创EDA → 制造 → PCB制板文件(Gerber) → 导出

BOM导出 (JLCPCB格式):
  嘉立创EDA → 制造 → 物料清单(BOM) → 导出Excel
  格式: Designator | Footprint | LCSC Part# | Quantity

CPL导出 (贴片坐标):
  嘉立创EDA → 制造 → 贴片坐标 → 导出CSV
```

### Phase 4: 下单制造

#### 4a. PCB打样 (嘉立创PCB)
```
https://www.jlcpcb.com → 立即下单 → 上传Gerber.zip

推荐参数 (高压电源板):
  层数:        4层 (推荐) 或 2层
  板材:        FR4 TG155 (高Tg耐温)
  厚度:        1.6mm
  铜厚:        外层2oz, 内层1oz
  颜色:        绿色 (最便宜)
  表面处理:    HASL无铅 或 ENIG沉金
  最小线宽:    6mil
  最小孔径:    0.3mm
  阻焊桥:      0.1mm
  数量:        5片 (首版验证)
  ≈ ¥50~80 (4层5片)
```

#### 4b. SMT贴片 (可选, 小批量)
```
https://smt.jlc.com → 上传Gerber + BOM + CPL

注意:
  - 大功率器件(TO-247 SiC MOSFET)需手工焊
  - SMT适合小元件: 电阻/电容/IC/驱动器
  - Basic件免换料费, Extended件收¥3/种
```

#### 4c. 钢网 (手工焊必备)
```
https://www.jlc-laser.com → 上传Gerber
  框架钢网: ≈¥40
  无框钢网: ≈¥20
  配合锡膏+热风枪回流
```

#### 4d. 散热器 (CNC/3D打印)
```
SiC MOSFET散热方案:
  - 铝散热器: 嘉立创CNC定制, 3天交货
  - 3D打印风道: 嘉立创3D打印
  - 或淘宝成品散热器 (TO-247专用)
```

---

## 五、LCSC器件快速搜索脚本

> 利用pcb_brain已有的LCSC搜索能力, 批量查询

```python
# 在 pcb_brain/ 目录下运行
import sys; sys.path.insert(0, '.')
from pcb_jlcpcb import JLCPCBManager

jlc = JLCPCBManager()

# 1500W PFC 关键器件搜索
search_list = [
    ("SiC MOSFET 650V",         "Q1/Q2 高频开关管"),
    ("SiC MOSFET 650V",         "Q3/Q4 工频整流"),
    ("isolated gate driver",    "U1/U2 隔离驱动"),
    ("PFC controller",          "U5 PFC控制器"),
    ("electrolytic 470uF 450V", "Cbus 母线电容"),
    ("varistor 471K",           "MOV1 压敏电阻"),
    ("X2 capacitor 0.47uF",    "Cx X电容"),
    ("NTC 5R 15A",              "NTC1 限流"),
    ("hall sensor 25A",         "CS1 电流采样"),
    ("fuse 25A 250V",           "F1 保险丝"),
]

for keyword, desc in search_list:
    print(f"\n{'='*60}")
    print(f"  {desc} → 搜索: {keyword}")
    print(f"  LCSC: https://www.lcsc.com/search?q={keyword.replace(' ', '+')}")
    print(f"  嘉立创: 在EDA器件库中搜索同关键词")
```

---

## 六、安全警告 ⚠️

```
╔══════════════════════════════════════════════════════════╗
║  本项目涉及 400VDC 高压, 致命风险!                      ║
║                                                          ║
║  1. 母线电容 400V 充满电后 可致命 — 操作前必须放电       ║
║  2. 泄放电阻 Rbleed 必须安装 — 掉电后自动放电           ║
║  3. 首次上电使用 调压器/隔离变压器 — 逐步升压            ║
║  4. 测量使用 差分探头 — 禁止普通示波器直接接高压侧       ║
║  5. PCB高低压隔离间距 ≥ 6.4mm — 违反此规则=安全隐患     ║
║  6. 焊接后 目检+万用表 — 确认无短路再上电                ║
║  7. 散热器必须安装 — SiC MOSFET 无散热器秒烧             ║
╚══════════════════════════════════════════════════════════╝
```

---

## 七、调试验证 (上电三层法)

### 层1: 冷检查 (不上电)
```
[ ] 万用表量 HV_BUS+ 与 PGND: 不短路 (>100kΩ, Rbleed)
[ ] 量 +15V 与 SGND: 不短路
[ ] 量 +5V 与 SGND: 不短路
[ ] 目检所有焊点: 无虚焊/连锡
[ ] SiC MOSFET散热器已安装并涂硅脂
[ ] 所有连接器方向正确
```

### 层2: 辅助电源验证 (低压上电)
```
[ ] 仅给辅助电源供电 (外部12V)
[ ] 量 +15V: 14.8~15.2V ✓
[ ] 量 +5V: 4.95~5.05V ✓
[ ] 量 +3.3V: 3.28~3.32V ✓
[ ] 控制器/驱动器芯片不发烫
```

### 层3: 主功率验证 (调压器逐步升压)
```
[ ] 接入调压器, 从0V开始
[ ] 升至30VAC → 观察电流, 应<1A (NTC限流)
[ ] 继电器动作后电流应下降
[ ] 逐步升至85VAC → 量 VBUS: 应约120VDC (未启动PFC)
[ ] 启动PFC控制 → VBUS应逐步升至设定值(~400VDC)
[ ] 加载 → 效率/波形验证
```

---

## 八、版本迭代规范

```
命名: 1500W_TotemPole_PFC_v{版本}_{日期}
  v0.1: oshwhub复刻, 未修改
  v0.2: 降额至1500W, 调整选型
  v1.0: 首版投产, DRC/ERC全通过
  v1.1: 首版回板修正
  v2.0: 功能验证通过, 优化EMI
```

---

## 九、与pcb_brain集成

本项目可作为第22个DNA模板集成到pcb_brain系统:

```python
# circuit_dna.py 新增模板 (未来)
"bridgeless_pfc_1500w": {
    "desc": "1500W图腾柱无桥PFC, SiC MOSFET, 400VDC输出",
    "category": "power",
    "components": 30,  # 约30个关键元件
    "cost": "~¥200",
    "modules": [
        "Input_Protection_EMI",
        "Power_Stage",
        "Gate_Driver",
        "Control_Sampling",
        "Protection_Aux"
    ]
}
```

---

*反者道之动, 弱者道之用 — 从开源复刻起步, 以最小代价获得最大工程经验*
*天下难事必作于易, 天下大事必作于细 — 每颗料号、每条走线、每个间距都不可轻视*

*文档版本: v1.0 | 2026-04-28 | 道之实战*
