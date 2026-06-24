# schematic_dao — Agent 操作手册

> **原理图道**: 一份 `SchematicProject` 定义 → 多重源文件输出
> **位置**: `PCB设计/schematic_dao/`
> **输出范式**: 对标 [`实战/无桥PFC电气原理图及工程资料包/`](../实战/无桥PFC电气原理图及工程资料包/)

---

## 道之核心

**为学日益, 为道日损.** 工程上越简单的接口, 承载越多变化.

```
SchematicProject  ←  唯一真相源
       │
       ├── render_svg            →  规范矢量SVG (规范版+彩图版)
       ├── render_png            →  PNG 高保真位图 (经 Playwright 渲染)
       ├── render_bom            →  BOM清单CSV + 网络连接表CSV
       ├── render_kicad          →  真 .kicad_sch (含 KiCad 标准库符号 + global_label)
       ├── render_kicad_export   →  调 kicad-cli: PDF / SVG / PNG / DXF / netlist /
       │                              BOM CSV / Python BOM XML / ERC 报告
       ├── render_kicad_launcher →  生成 .cmd 一键打开 KiCad GUI
       ├── render_showcase       →  单页 _index.html — 一页见万象
       ├── render_easyeda        →  EasyEDA 工程JSON
       ├── render_altium         →  Altium 导入说明 + 网络表
       └── render_docs           →  设计说明MD + 论文正文插入版MD
```

**KiCad 底层闭环**: 真符号库提取 (`_kicad_lib.py`) → extends 内联展开 → 真原理图 →
kicad-cli 全套导出 → ERC 检查 → 一键 GUI 启动 → HTML 一页展示.

**已知关键陷阱** (踩过的坑, 留给未来):
- KiCad 9 嵌入 `lib_symbols` 不支持跨条目 `(extends)` — 必须把父类内联展开到子类
- KiCad 9 `(text)(effects)(justify ...)` 不接受 `center` — 用 `left/right/top/bottom` 或省略
- `_kicad_lib.gather_required_symbols()` 现返回 **单条目** 内联块, 父类不再单独出现

---

## 最快入口

```bash
# CLI
python -m schematic_dao list                                 # 列出全部已注册项目
python -m schematic_dao validate <project>                   # 校验项目数据模型
python -m schematic_dao build <project>                      # 一键生成完整资料包
python -m schematic_dao build <project> <custom_output_dir>  # 指定输出根目录
```

```python
# Python API
from schematic_dao import SchematicProject, generate_pack
from schematic_dao.projects.warehouse_logistics_vehicle import build_project

proj = build_project()
files = generate_pack(proj, "实战/仓库车间物流车控制系统设计/", clean=True)
```

---

## 数据模型 (5 个 dataclass)

| 类 | 职责 |
|---|---|
| `Pin` | 元件单引脚 (designator/name/role) |
| `Component` | 元件 — 含引脚、封装、BOM 元数据、分组 |
| `Net` | 网络 — 含节点列表、用途、设计注意、网络分类 |
| `Module` | 子电路块 — 含布局、配色、所属元件/网络/body |
| `SchematicProject` | 项目 — 元件 + 网络 + 模块 + 走线 + 图框 |

**位置参数顺序** (避免踩坑):
```python
Net(name, purpose, nodes, notes, net_class, color)
#    ↑1   ↑2     ↑3    ↑4    ↑5         ↑6
```

---

## 注册新项目 (3 步)

### 1. 写项目定义文件

`schematic_dao/projects/<your_project>.py`:

```python
from ..schematic_dao import SchematicProject, Component, Pin, Net, Module, ModuleLayout, WireHint, TitleBlock

def build_project() -> SchematicProject:
    proj = SchematicProject(
        name="my_project",
        title=TitleBlock(title_cn="我的项目", version="v1.0"),
        spec={"主控": "ESP32-S3"},
        description="...",
    )
    proj.components = [...]
    proj.nets = [...]
    proj.modules = [...]
    proj.wires = [...]
    return proj
```

### 2. 注册到 CLI

`schematic_dao/__main__.py`:

```python
_PROJECT_REGISTRY = {
    "my_project": (
        ".projects.my_project",
        "build_project",
        "实战/我的项目设计/",       # 默认输出位置
    ),
    ...
}
```

### 3. 一键生成

```bash
python -m schematic_dao validate my_project
python -m schematic_dao build my_project
```

---

## 输出资料包结构 (PFC 同款四件套)

```
<output_root>/
├── README.md                                # 资料包总览
├── 01_论文图纸/
│   ├── {name}_规范矢量版.svg                # 黑白规范矢量
│   ├── {name}_彩图版.svg                    # 彩色填充矢量
│   ├── {name}_规范矢量版.png                # PNG @2x (Playwright 渲染)
│   └── {name}_彩图版.png
├── 02_论文文档/
│   ├── {name}_电气原理图设计说明.md         # 完整设计说明
│   └── {name}_论文正文插入版.md             # 精简论文章节
├── 03_BOM与连接表/
│   ├── {name}_BOM清单.csv                   # 按位号合并 (UTF-8 BOM)
│   └── {name}_网络连接表.csv
└── 04_工程源文件/
    ├── KiCad工程/
    │   ├── {name}.kicad_pro
    │   ├── {name}.kicad_sch                 # S-expr, 含标题栏+网络标签
    │   └── README_KiCad工程说明.txt
    ├── EasyEDA源文件/
    │   └── {name}_easyeda_source.json
    └── Altium导入准备/
        ├── Altium_工程导入准备说明.txt
        └── {name}_网络连接表.csv
```

---

## SVG 视觉风格

| 模块 box_style | 颜色 | 推荐用途 |
|---|---|---|
| `box` | 黑 #111 | MCU/逻辑核心 |
| `bluebox` | 蓝 #1463d8 | 电源/通信 |
| `redbox` | 红 #d92525 | 复位/警告 |
| `greenbox` | 绿 #148447 | 采样/指示灯 |
| `purplebox` | 紫 #6a35b1 | 显示/控制 |
| `orangebox` | 橙 #e57200 | 电机/功率 |
| `tealbox` | 青 #0a8a8a | 传感器 |
| `brownbox` | 棕 #8b4513 | 输入/按键 |

| 走线 style | 颜色/形态 | 推荐用途 |
|---|---|---|
| `wire` | 实线黑 | 电源/普通走线 |
| `sig` | 紫色虚线 | 信号采样 |
| `drv` | 蓝色虚线 | 驱动/通信总线 |
| `bus` | 绿色实线粗 | 多路电源/总线 |

---

## 校验规则 (proj.validate())

- ✅ 网络节点引用的元件必须存在
- ✅ 模块内引用的元件/网络必须存在
- ✅ 元件至少出现在一个网络上 (孤岛检测)
- ✅ WireHint 引用的模块必须存在

通过校验后再 build, 否则 `_VALIDATION.txt` 留底.

---

## 与 pcb_brain 的边界

| 维度 | schematic_dao | pcb_brain |
|---|---|---|
| 视角 | 原理图优先 (论文/工程文档) | PCB 布局优先 (Gerber/SMT) |
| 输出 | SVG/PDF/MD/CSV/.kicad_sch | .kicad_pcb/Gerber/BOM/iBoM |
| 数据 | `SchematicProject` (论文级) | `DNA` (布局级) |
| 工具 | 内置渲染 | KiCad CLI/freerouting |
| 适用 | 毕业设计/工程报告/方案评审 | 实物打样/SMT 量产 |

二者可串联: `SchematicProject` 可手工/半自动转 `DNA`, 进入 `pcb_brain` 流水线打样.

---

## 当前注册项目

| 项目 | 标题 | 输出位置 | 元件 | 网络 |
|---|---|---|---|---|
| `warehouse_logistics_vehicle` | 仓库车间物流车控制系统设计 | `实战/仓库车间物流车控制系统设计/` | 50 | 40 |

---

## 后续路线图

- [ ] PNG 渲染降级方案 (Pillow 直接绘图, 不依赖 Playwright)
- [ ] PDF 输出 (从 SVG 经 svglib + reportlab)
- [ ] 自动转 `pcb_brain.DNA` (SchematicProject → KiCad 布局级)
- [ ] LLM 辅助: 自然语言 → SchematicProject 草图
- [ ] 复刻 PFC 项目作为第二个验证标杆 (`bridgeless_pfc`)
- [ ] 真实 KiCad 符号绑定 (基于 KiCad 9 lib 路径)

---

*位置: `PCB设计/schematic_dao/` | 道直连器: `from schematic_dao import generate_pack`*
