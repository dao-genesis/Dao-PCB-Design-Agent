# 本源架构 · 深用 KiCAD 一切, 而非从零重造

> 道理 (用户锚定): 像高斯深用 VS Code 底层、Cursor 立于 VS Code 之上, 我们**深用 KiCAD 一切本源**,
> 在其上做 PCB 全流程闭环 —— 而**不从零重造它已有的轮子**。为学者日益, 为道者日损。

## 〇、本源全量逆流 · 唯一事实源 (一劳永逸)

> 承嘉立创EDA Pro 之 EXTAPI 同法 (`lceda_bridge/cdp_studio/extapi_full_catalog.json`),
> 把 **KiCAD 9 本源整张声明面** 一次性逆流到位, 作后续一切深度融合的唯一事实源,
> 杜绝零敲碎打、臆造接口名。**反者道之动** — 接口名一律取自运行期真实 SWIG 符号。

```bash
python -m kicad_origin.origin.native_catalog            # 生成目录+参考
python -m kicad_origin.origin.native_catalog --verify   # live 交叉核对+端到端烟测
```

产物 (`kicad_origin/_native/`):

| 文件 | 内容 |
|------|------|
| `KICAD_NATIVE_CATALOG.json` | 机器/Agent 唯一事实源: 三层能力面 (pcbnew/cli/ipc) 全量结构化 |
| `KICAD_NATIVE_REFERENCE.md` | 按域分组的人类可读全表 |

三层能力面 (KiCad 9.0.9 实测规模):

| tier | 入口 | 规模 (9.0.9) | 取法 |
|------|------|------|------|
| ① pcbnew SWIG | `kicad_origin/origin/_pcbnew_probe.py` | **164 类 / 7913 方法 / 302 自由函数 / 852 常量** | KiCad python 子进程内 introspection, 每方法带真实 C++ 签名 |
| ② kicad-cli | `native_catalog.cli_surface` | **34 叶子命令** (含描述+全选项) | 递归 `--help` 子命令树 |
| ③ IPC (kipy) | `native_catalog.ipc_surface` | 视构建而定 (deb 9.0.9 未带) | 探测 `import kipy` |

> live 交叉核对: 目录采样的类/方法/函数/常量回到运行期逐一核对存在性 (0 missing),
> 并跑端到端烟测 (建板→加件→落盘→重载) — 证明目录非臆造、本源真可操作。

### 〇.1 本源操作层 · 给人用 → 给 Devin 用 (`native_ops.py`)

> 目录是"知"，操作层是"行"。把 KiCad 本来给人图形化操作的产线/校验能力, 编排成我
> 自己可程序化驱动的统一操作面 —— 真把这些工具用起来、调起来、火起来。一切命令路径/
> 选项 **catalog-backed** (取自上节唯一事实源, 不臆造 flag; 不在目录中即拒跑)。

```python
from kicad_origin.origin.native_ops import NativeOps
ops = NativeOps()
ops.board_summary("x.kicad_pcb")               # pcbnew 只读板态势
ops.drc("x.kicad_pcb", "drc.json")             # 真 DRC 引擎 + 解析违规
rep = ops.fab_package("x.kicad_pcb", "out/")   # 一键闭到可投产 (gerber/drill/pos/pdf/3D + zip)
```

```bash
python -m kicad_origin.origin.native_ops x.kicad_pcb out/   # CLI 一键全流程
```

实测 (示例板 `_st20_fab/ams1117_power_inlined.kicad_pcb`): 一条命令产出 16 件 gerber/
钻孔/贴片 + PDF + STEP 3D + DRC 报告 + 可投厂 zip, 全链路 ok。

### 〇.2 本源布线编排 · Specctra 往返 (`native_route.py`)

> 反者道之动: KiCad 自家**不带**自动布线器, 官方本源路径是经 Specctra DSN/SES 与外部
> 布线器 (freerouting) 往返 —— 即 GUI 里「导出 DSN / 导入 SES」之事。故不再从零造 A*
> 轮子, 而把这条本源往返编排成可程序化一步: 导出 DSN(原生 `ExportSpecctraDSN`) →
> freerouting 无头布线 → 导入 SES(原生 `ImportSpecctraSES`) → 落盘。

```python
from kicad_origin.origin.native_route import NativeRouter
rep = NativeRouter().route("in.kicad_pcb", "out.kicad_pcb")
# rep.unrouted_before / unrouted_after / tracks_added
```

实测 (2 件 0805 + 1 网的连通板): `unrouted 1 → 0`, 自动落 1 条走线, 全链路 ok。
freerouting/java 缺失时降级为 `router_unavailable` (DSN 已就绪可手工布线), 不崩。
启用自动布线: 设 `FREEROUTING_JAR` 或置 jar 于 `~/freerouting.jar` + 装 java。

### 〇.3 网表驱动建板 + 全闭环 (`native_build.py`)

> 补上游: 用真封装库取件、放置、按网连 pad、画板框, 产出**有连通待布线**的板; 再接
> 布线 + 制造, 合成一条 `spec → 建板 → 布线 → 出 fab` 的全闭环 —— 把 KiCad 整条本源
> 真跑起来、火起来。取件找不到即报错 (反臆造, 不静默替换)。

```python
from kicad_origin.origin.native_build import full_flow
rep = full_flow(spec, "out/")   # spec: {components:[{ref,lib,fp,x,y}], nets:{N:[[ref,pad]]}}
```

实测 (3 件 0805/0805C + 2 网 spec): build 3 器件 3 网 unrouted 3 → route 0 (+5 走线)
→ fab 出可投厂 zip, **全闭环 ok**。

### 〇.4 原生网表驱动 · 真上游接入 (`native_netlist.py`)

> 反者道之动: native_build 仍从手写 spec 起手 —— 非真上游。设计真本源在**原理图**:
> `kicad-cli sch export netlist` 落为 KiCad 原生网表 (S-expr)。本层直接吃这份网表:
> 解析器件 (ref/value/封装) 与网 (名/节点), **栅格自动布局**转成 native_build spec,
> 接全闭环 —— 合成 `原理图 → 网表 → 建板 → 布线 → 出 fab` 的真闭环。
> 反臆造: 网表未分配封装的器件如实报缺 (`missing_footprints`), 不静默编造; 可经
> `fp_map`(ref→"lib:fp") 显式补封装 (即 KiCad "分配封装"那一步) 后再建。

```python
from kicad_origin.origin.native_netlist import (
    parse_netlist, netlist_from_schematic, build_from_netlist)
nl, net = netlist_from_schematic("design.kicad_sch")   # 真上游: 图→原生网表
rep = build_from_netlist(net, "out/", fp_map={"U1": "Package_QFP:LQFP-48_7x7mm_P0.5mm"})
```

实测: 仓库物流车真原理图 → 50 件/62 网 (封装未分配 → 如实报 50 缺, **反臆造**);
风扇控制器真原理图 → 6 件含封装 → 可建板; 完整 fixture (3×0805 + 4 网) →
build unrouted 2 → route 0 (+4 走线) → fab zip, **全闭环 ok**。

### 〇.5 DRC 驱动自愈环 · 以真 DRC 为裁判 (`native_heal.py`)

> 无为而无不为: 不臆测板哪里错, 以 KiCad **真 DRC 引擎**为唯一裁判 —— 跑
> `kicad-cli pcb drc` 出违规, 按类归因, 施本源对策, 再跑 DRC 看收敛, 迭代至止。
> 间距类违规 (courtyards_overlap/clearance/shorting/solder_mask_bridge/silk_*)
> 根多为器件挨太近 → `_heal_worker respace` (pcbnew 真挪件, 按最大包络+gap 栅格拉开
> + 重画板框); 飞线未布 → `NativeRouter` 闭合。反臆造: 诊断全取自真 DRC, 修不动的
> 违规如实留报告, 不假装清零。

```python
from kicad_origin.origin.native_heal import NativeHealer
rep = NativeHealer().heal("bad.kicad_pcb", "healed.kicad_pcb", max_passes=4)
```

实测 (3×0805 堆叠成板 → 真 DRC 24 违规 + 2 飞线): respace 化解全部间距类, route 闭飞线
→ **24→0 违规 / 2→0 飞线, 1 pass 收敛**, ok。

### 〇.6 参数化本源器件库 · 朴散则为器 (`native_lib.py`)

> 朴散则为器: 反复手写 `{ref,lib,fp,x,y}` 是"散"; 把常用器件 (电阻/电容/排针) 连同
> **封装变体** (0402/0603/0805) 与**引脚→信号映射**抽象为一枚 `ComponentPrimitive`,
> 即"器", 一次定义处处实例化。本源在: 封装是真 `.kicad_mod` (S-expr), 本层用 `sexpr`
> 基座**直接读真焊盘名** → ① 校验所选封装在真库存在 ② 校验引脚映射焊盘名确属该封装
> (拼错焊盘如实报 unknown)。反臆造: 封装/焊盘不实即报, 不静默替换。

```python
from kicad_origin.origin.native_lib import standard_library
lib = standard_library()                 # R/C/Header_2x10 皆经真库校验
rep = lib.build_from_primitives(
    [{"name": "R", "ref": "R1", "x": 10, "y": 10, "variant": "0603"}, ...],
    nets, "out/")                         # 实例 → spec → 全闭环
```

实测: R/C 读真封装 2 焊盘、Header_2x10 读真封装 20 焊盘, 校验全 ok; ghost 焊盘"9"如实
报 unknown; 5 件 (含 0805/0603/20脚 3 变体) + 2 网 → route 4→0 (+9 走线) → fab zip,
**全闭环 ok**。

### 〇.7 本源全流程一体化 · 一条道贯之 (`native_flow.py`)

> 三生万物: 把已逆流各本源层 (网表 `native_netlist`、器件库 `native_lib`、建板
> `native_build`、布线 `native_route`、真 DRC 自愈 `native_heal`、制造 `native_ops`)
> 贯成一条道 —— 喂入任一真上游 (原生 `.net` / `.kicad_sch` / spec), 一气呵成产出**经真
> DRC 检过**的可投厂工件。与 `full_flow` 别: ① 统一吃多源上游 ② 建板与投厂间插入**以真
> DRC 为裁判的自愈闸** (先 heal 再 fab, 不投违规板)。反臆造: 缺封装如实溯源 (`_origin`),
> 自愈以真 DRC 判收敛。

```python
from kicad_origin.origin.native_flow import run_flow
rep = run_flow("design.net", "out/")     # netlist → 建板 → 自愈闸 → 布线 → 投厂
```

实测 (divider.net, 3 件/4 网): build (2 飞线) → heal (DRC 0 违规 / 飞线 2→0) → fab zip,
`_origin` 如实溯源 (3 件全可放, 0 缺封装), **全流程 ok**。

### 〇.8 本源物料与装配 (`native_bom.py` / `native_assembly.py`)

> 制板出 gerber 只是裸板; **采购**要 BOM、**贴片**要坐标、**评审**要 3D 实体。
> - `native_bom`: 两条本源路径取 BOM —— ① `from_board` 经子进程 (`_bom_worker`) 用 pcbnew
>   读每枚封装真 ref/value/footprint, 按 (value, footprint) 归并 (KiCad "Grouped By Value"
>   同义, 引脚号自然序 R2<R10); ② `from_schematic` 经 `kicad-cli sch export bom` 直出真
>   原理图 BOM。读不到即报错, 不编行。
> - `native_assembly`: 把贴片坐标 (`export_pos`) + 3D STEP/GLB (`pcb export step|glb`,
>   catalog-backed) + BOM 一并打成**装配包 zip**。

```python
from kicad_origin.origin.native_bom import NativeBom
from kicad_origin.origin.native_assembly import NativeAssembly
NativeBom().from_board("board.kicad_pcb")            # 真板 → 归并 BOM
NativeAssembly().assemble("board.kicad_pcb", "out/") # pos+step+glb+bom → zip
```

实测: 真板 4 件 → BOM 归并 (R1+R2 同值合 qty2 / R10 异值另起, 3 物料/4 总数); 真原理图
simple_fan_controller → `sch export bom` 出 5 行 (330R ×2 归并); 装配包 zip 含
positions.csv+board.step+board.glb+bom.csv, **全产出 ok**。

### 〇.9 本源覆铜与层叠 (`native_zone.py` / `native_stackup.py`)

> 信号走线只是骨架; **覆铜回流地**靠 zone pour、**高速/多层**靠层叠。皆用 pcbnew 真改板。
> - `native_zone`: 子进程 (`_layer_worker` op=pour) 用本源 `pcbnew.ZONE` + `ZONE_FILLER`
>   为指定铜层+网络铺一块覆盖板框 (Edge.Cuts 包络 + margin) 的覆铜区, **真浇灌**后落盘,
>   重载实测每区填充面积 (mm²)。网络/铜层不存在即报错, 绝不乱接网 (反臆造)。
> - `native_stackup`: 子进程 (op=stackup) 用 `BOARD.SetCopperLayerCount` 真升降层数
>   (2→4→6, 须 >=2 偶数), 落盘后重载实测启用铜层名回报。

```python
from kicad_origin.origin.native_zone import NativeZone
from kicad_origin.origin.native_stackup import NativeStackup
NativeZone().pour("b.kicad_pcb", "o.kicad_pcb",
                  zones=[{"layer": "F.Cu", "net": "GND"},
                         {"layer": "B.Cu", "net": "GND"}])
NativeStackup().set_copper_layers("b.kicad_pcb", "o.kicad_pcb", 4)
```

实测: 真板双面铺 GND → 两区均 is_filled, 填充面积 366/389 mm² (真浇灌非估算);
未知网络 `NOPE`/未知层 `In9.Cu`/奇数层 3 均如实拒做; 2→4 层后启用铜层
`['F.Cu','In1.Cu','In2.Cu','B.Cu']`。

### 〇.10 本源器件库批量逆流 (`native_libscan.py`)

> `native_lib` 手工预置三两枚原语是"点"; 真库里躺着 **155 个 `.pretty` 封装库**(数千封装)
> 与 **223 个 `.kicad_sym` 符号库**。本层把这整面真库逆流为可检索索引, 并据真焊盘把成族
> 封装 (同名不同尺寸的 R/C/L/LED…) **批量萃取**为多变体 `ComponentPrimitive`。
> 全程读真文件: 封装名来自真 `.kicad_mod`、焊盘名直读真 S-expr、符号名来自真 `.kicad_sym`;
> 萃取后**逐变体对真焊盘校验**, 焊盘对不上的变体剔除, 绝不臆造不存在的器件。

```python
from kicad_origin.origin.native_libscan import NativeLibScan
s = NativeLibScan()
s.find_footprints(r"^R_0805_\d+Metric$", lib_pattern=r"^Resistor_SMD$")
lib, report = s.augment_standard_library()   # standard_library 之上真库扩充
# report = {'R_SMD':17, 'C_SMD':13, 'L_SMD':11, 'LED_SMD':9} —— 皆真库校验通过
```

实测: 索引 155 封装库 / 223 符号库; 从真库萃取 R/C/L/LED 四族共 **50 个校验通过的变体**
(R_SMD 17 / C_SMD 13 / L_SMD 11 / LED_SMD 9), 每枚 `validate().ok` 真焊盘核对通过;
不命中模式 / 焊盘对不上均如实拒收。

### 〇.11 真原理图几何直驱 (`native_schematic.py`)

> `native_netlist` 从原理图只取连接 (网表), 摆位却退化成机械栅格 —— 丢了设计者在原理图上
> "R 挨着 LED、C 靠着 IC"的空间意图 (人法地)。本层**直读真 .kicad_sch 的 symbol 几何**
> (lib_id / at[x,y,rot] / Reference / Value / Footprint), 把原理图坐标等比规整映射到目标板
> (保相对排布), 作摆位种子; 连接仍走 `native_netlist` 真网表。几何来自原理图、网表来自原理图,
> 二者皆真。缺封装件如实列报告, 原理图无连线则 nets 真为 0 (反臆造, 绝不臆造连接)。

```python
from kicad_origin.origin.native_schematic import NativeSchematic
ns = NativeSchematic()
ns.read("design.kicad_sch")                 # [SchSymbol(ref,lib_id,value,fp,x,y,rot), ...]
lay = ns.layout("design.kicad_sch", board_w=60, board_h=40)   # 几何映射摆位
ns.build("design.kicad_sch", "out/")         # 摆位+真网表 → native_build 全闭环
```

实测: 真 `simple_fan_controller.kicad_sch` → 读出 6 件 (R1/R2/D1/D2/SW1/C1) 真几何;
布局保设计者排布 (R 在左、D/C 在右; R1 在 R2 上), 等比缩进 60×40 板; 缺封装 0;
该图未画连线, 故 `nets=0` 如实回报 (非 bug, 是真相); 全闭环建板+布线出真 board。

### 〇.12 本源拼板 (`native_panel.py`)

> 单板是"一"; 投厂按单位面积出片, 要把它阵列成 n×m 拼板加工艺边 (一生二二生三)。不靠手摆,
> 而用 KiCad 本源 `BOARD_ITEM.Duplicate()` 把源板每一件 (封装/走线/过孔/覆铜/图元) 真复制
> 平移到各格 (源板占首格), 末了在 `Edge.Cuts` 加整面外框 + `rail_mm` 工艺边。子进程
> (`_panel_worker.py`) 在 pcbnew 内完成, 落盘后**重载实测**封装总数与外框尺寸 (反臆造)。

```python
from kicad_origin.origin.native_panel import NativePanel
rep = NativePanel().panelize("board.kicad_pcb", "panel.kicad_pcb",
                             cols=3, rows=2, gap_mm=2.0, rail_mm=5.0)
rep.fp_after        # = fp_before * cols * rows
rep.panel_bbox_mm   # 整面外框尺寸 (重载实测)
```

实测: 3 件单板 (39.8×11.2mm) → 3×2 拼板 = **18 件**, 整面 133.5×34.4mm (含 5mm 工艺边);
2×1 条板 = 6 件; `1×1` (非拼板) 与 `cols=0` 均如实拒做。

### 〇.13 双板逆差分 (`native_diff.py`)

> 不断实践验证: 每做一步操作 (布线/自愈/拼板…) 都该能问"它到底改了什么"。本层用 KiCad 本源
> 以 Reference 锚定比对两板封装 (added/removed/moved/changed), 以网名比对网表 (added/
> removed), 统计走线/过孔/覆铜数量增量与外框尺寸。子进程 (`_diff_worker.py`) 在 pcbnew 内
> **真读两文件**比对 (反臆造, 不臆测差异)。

```python
from kicad_origin.origin.native_diff import NativeDiff
rep = NativeDiff().diff("before.kicad_pcb", "after.kicad_pcb")
rep.fp_added; rep.fp_moved; rep.nets_added   # 增量明细
rep.identical                                 # 封装/网表/走线计数全无变化 → True
```

实测: 同板自比 → `identical=True` (common=3); 改板 (R2 移 +20mm、加 R3、加 SIG 网) →
`fp_added=['R3']`、`fp_moved` 含 R2 位移 20mm、`nets_added` 含 SIG; 删 C1 → `fp_removed`
含 C1、`nets_removed` 含 GND。

### 〇.14 一键可投厂审查 (`native_audit.py`)

> 执一以为天下牧: 前面各层各司其职 (建板/布线/自愈/拼板/差分…), 投厂前要"执一"——一次性
> 回答"这板能不能投"。本层不造新轮子, 而是**调度既有本源层**汇成裁决: `board_summary`
> (pcbnew 实测板况) + `drc` (kicad-cli 真 DRC) + `from_board` (真板 BOM)。裁决规则透明可查,
> 每条 blocker 如实列出 (反臆造, 绝不替用户拍板"差不多能投")。

```python
from kicad_origin.origin.native_audit import NativeAudit
rep = NativeAudit().audit("board.kicad_pcb", "out/")
rep.ready          # bool: 无阻断项 且 DRC 违规=0
rep.blockers       # ["未布线 2", "DRC 违规 3", ...] 透明列报
rep.markdown()     # 人类可读审查单 (并落盘 out/audit.json + audit.md)
```

阻断规则: 无封装 / 无 Edge.Cuts 板框 / 未布线 / DRC 违规 / DRC 未连接 任一非零即 not-ready。
实测: 未布线板 → `ready=False` blockers `[未布线 2, DRC 未连接 2]` (DRC 违规 0, BOM 2 行 3 件);
缺板文件如实报错; 布通后 (未布线 0 且未连接 0) → `ready=True`, blockers 空。

### 〇.15 参数化板框 + 安装孔 (`native_outline.py`)

> 反者道之动: 板框与安装孔本是人在 GUI 里一笔一笔手绘的活, 但落到本源它们只是板文件里的
> `PCB_SHAPE` (Edge.Cuts) 与 `PAD_ATTRIB_NPTH` 焊盘。本层把"给人画的外形"改造成可编程下发:
> 矩形/圆角矩形板框 (圆角=4 直边+4 角弧)、四角自动或显式坐标打安装孔, 经子进程
> (`_outline_worker.py`) 在 pcbnew 内重画落盘, 再**重载实测**外框尺寸/边数/孔数 (反臆造)。

```python
from kicad_origin.origin.native_outline import NativeOutline
rep = NativeOutline().apply("in.kicad_pcb", "out.kicad_pcb",
                            width_mm=50, height_mm=30,
                            shape="rounded", corner_r_mm=3,
                            hole_dia_mm=3.2)   # 四角自动 4 孔
rep.size_mm   # 重载实测外框包围盒 [w,h]
rep.edge_items  # 矩形=1; 圆角=8 (4 边+4 弧)
rep.holes     # NPTH 安装孔数 (重载实测)
```

实测: 50×30 矩形 + 四角 Ø3.2 → `edge_items=1, holes=4, size≈[50,30]`;
40×40 圆角 r=5 居中 + 中心 Ø4 孔 → `edge_items=8, holes=1`; 尺寸非正/缺板文件如实报错。

### 〇.16 连接感知自动布局 (`native_place.py`)

> 反者道之动: 摆放元件本是人盯着飞线一个个拖的活, 但它本质是个**可度量的优化**——让相连焊盘
> 靠拢、总连线最短。本层以布局界标准指标 HPWL (各网焊盘包围盒半周长之和) 为度量, 经子进程
> (`_place_worker.py`) 在 pcbnew 内做 barycentric 收敛 (每件拉向相连焊盘质心) + 防重叠分离,
> `fixed` 位号 (连接器/定位件) 锚定不动; 落盘后**重载实测** HPWL 前后值与剩余重叠 (反臆造)。

```python
from kicad_origin.origin.native_place import NativePlace
rep = NativePlace().place("in.kicad_pcb", "out.kicad_pcb", fixed=["J1"])
rep.hpwl_before_mm, rep.hpwl_after_mm   # 重载实测总连线长
rep.reduction_mm, rep.improved          # 严格变短即 improved
rep.overlaps                            # 收尾分离后剩余重叠对数 (期望 0)
```

实测: 4 连杆链路打散在四角 (HPWL≈385mm) → 布局后 ≈44mm (降 ~89%), `improved=True`、
`overlaps=0`; `fixed=["R1"]` 时 R1 坐标重载后逐位不变; 缺板文件如实报错。

### 〇.17 板图可视化证明 (`native_render.py`)

> 不断实践验证: 每做一步 (建板/布局/布线/打孔…) 都该能"亲眼"核对, 而非只信数字。本层用 KiCad
> 本源 `kicad-cli pcb render` (3D PNG, 顶/底) 与 `pcb export svg` (2D 叠层图) 真引擎出图,
> 全程 catalog 背书 (命令不在本源目录即拒跑), 出图后**逐一实测文件存在且非空** (反臆造, 不臆称
> "渲染成功")——给我和用户一份每步皆可视的证据链。

```python
from kicad_origin.origin.native_render import NativeRender
rep = NativeRender().render("board.kicad_pcb", "out/")
rep.images   # {"top": ".../top.png", "bottom": ..., "svg": ".../board.svg"}
rep.sizes    # 各产物字节数 (实测 > 0)
rep.ok       # 至少一张图成功落盘且非空
```

实测: 示例板 → top/bottom PNG + 2D SVG 全部落盘非空 (`ok=True`); `sides=[]` 仅出 SVG;
缺板文件如实报错 `ok=False`、`images={}`。

### 〇.18 参数化丝印文字/标记 (`native_silk.py`)

> 反者道之动: 板号/版本/Logo/批次/极性记号本是人在 GUI 里逐个敲的丝印, 但落到本源它们只是
> F.SilkS/B.SilkS 上的 `PCB_TEXT`。本层经子进程 (`_silk_worker.py`) 用本源 `PCB_TEXT` 批量盖字
> (位置/字号/线宽/角度/镜像可控, 底层 B.SilkS 默认自动镜像), 落盘后**重载实测**各丝印层文字计数
> (反臆造, 不臆称"已盖")。

```python
from kicad_origin.origin.native_silk import NativeSilk
rep = NativeSilk().stamp("in.kicad_pcb", "out.kicad_pcb", texts=[
    {"text": "DAO-PCB v1", "x": 5, "y": 5, "size_mm": 1.5},
    {"text": "REV A", "x": 5, "y": 40, "layer": "B.SilkS"},
])
rep.added, rep.silk_texts_f, rep.silk_texts_b   # 重载实测各层文字数
```

实测: 顶层 2 条 + 底层 1 条 → `added=3, silk_texts_f=2, silk_texts_b=1`; 空白文字自动跳过;
texts 为空 / 缺板文件如实报错 `ok=False`。

### 〇.19 接地过孔缝合 (`native_stitch.py`)

> 反者道之动: EMI/散热缝合过孔本是人在 GUI 里沿网格一个个 ctrl+点出来的, 落到本源只是绑定某网码的
> `PCB_VIA`。本层经子进程 (`_stitch_worker.py`) 在区域 (板框/封装包围盒/显式 region) 内按 `pitch_mm`
> 网格放 THROUGH 过孔并绑定目标网 (默认 GND), 按"clearance + 过孔半径 + 焊盘自身半径"自动跳过会与
> 其他网短接/重载改网的点, 落盘后**重载实测**目标网过孔数 (反臆造; 目标网不存在即拒跑, 不臆造网)。
> 配合 native_zone 覆铜即成真正接地网。

```python
from kicad_origin.origin.native_stitch import NativeStitch
rep = NativeStitch().stitch("in.kicad_pcb", "out.kicad_pcb",
                            net="GND", pitch_mm=5, region=[5, 5, 45, 45])
rep.added, rep.vias_on_net, rep.vias_total   # 重载实测: 落点全在 GND
```

实测: 40×40 区域 pitch 5 → 全部落点重载后均在 GND (`vias_on_net==added`); pitch 越细过孔越多;
目标网不存在 / 缺板文件如实报错 `ok=False`。

### 〇.20 元件际间距/重叠检测 (`native_courtyard.py`)

> 反者道之动: 装配阶段元件会不会"打架"本是人在 GUI 里放大了肉眼比对 courtyard 框, 但落到本源每件
> courtyard 只是 F.CrtYd/B.CrtYd 上一圈 `SHAPE_POLY_SET`。本层经子进程 (`_courtyard_worker.py`) 取每件
> 本源 courtyard 多边形两两做 `BooleanIntersection` 求**真实相交面积** (非包围盒近似), 面积 > eps 即判
> 重叠报出 (反臆造: 缺 courtyard 的件如实列入 missing, 不臆造为 0 重叠)。与铜层 DRC 互补的装配几何检查。

```python
from kicad_origin.origin.native_courtyard import NativeCourtyard
rep = NativeCourtyard().check("board.kicad_pcb")
rep.overlap_count, rep.overlaps, rep.missing   # overlaps:[{a,b,area_mm2}]
rep.clean   # 无重叠且检测成功
```

实测: 间隔摆放 2 件 → `overlap_count=0`、`clean=True`; 近乎叠放 (dx=0.3mm) → 报 1 处重叠并给真实
相交面积 (≈5.76 mm²); 缺板文件如实报错 `ok=False`。

### 〇.21 制造图尺寸标注 (`native_dimension.py`)

> 反者道之动: 制造图上的板宽/孔距/间距标注本是人在 GUI 里一根根拉出来的, 但落到本源它们只是
> Dwgs.User 上的 `PCB_DIM_ALIGNED`。本层经子进程 (`_dimension_worker.py`) 用本源 PCB_DIM_ALIGNED
> 下发对齐标注 (毫米/精度可控), `auto_board=True` 时按板框包围盒自动加"板宽/板高"两道, 落盘后
> **重载实测** Dwgs.User 标注计数与各自量得值 (反臆造: 数值取自 KiCad 量算 `GetMeasuredValue` 而非手填)。

```python
from kicad_origin.origin.native_dimension import NativeDimension
rep = NativeDimension().annotate("in.kicad_pcb", "out.kicad_pcb", auto_board=True)
rep.added, rep.dims_on_layer, rep.values   # values 为重载后 KiCad 量得的真实 mm
```

实测: 显式 40mm 跨距 → 量得 ≈40.0; `auto_board` 在 50×30 板上自动加两道 → 量得 ≈30 与 ≈50;
dims 空且未启用 auto_board / 缺板文件如实报错 `ok=False`。

### 〇.22 装配视觉基准点 (`native_fiducial.py`)

> 反者道之动: 贴片机视觉对位用的 fiducial 本是人从库里拖一个封装手放上去的, 但落到本源它只是一个
> F.Cu 露铜 + F.Mask 开窗的圆形焊盘。本层经子进程 (`_fiducial_worker.py`) 直接用本源 FOOTPRINT+PAD
> 造基准点 (铜径/开窗径可控, 经 `LocalSolderMaskMargin` 控阻焊余量), 支持顶/底层, 落盘后**重载实测**
> 真正加进去的基准点数与各自阻焊余量 (反臆造)。

```python
from kicad_origin.origin.native_fiducial import NativeFiducial
rep = NativeFiducial().place("in.kicad_pcb", "out.kicad_pcb", fiducials=[
    {"x": 5, "y": 5, "copper_mm": 1, "mask_mm": 2}])
rep.fiducials, rep.mask_margins_mm   # 重载实测: 余量 = (mask-copper)/2
```

实测: 顶层 2 个 (铜1/窗2) → `fiducials=2`、阻焊余量均 0.5mm; 底层 (铜1.5/窗3) → 余量 0.75mm;
`mask_mm<=copper_mm` / 空输入 / 缺板文件如实报错 `ok=False`。

### 〇.23 锡膏钢网开孔调优 (`native_paste.py`)

> 反者道之动: 钢网(stencil)开孔为防连锡/补锡量本是人在 GUI 里逐焊盘改 paste margin 的, 但落到本源它
> 只是每个 SMD `PAD` 的 `LocalSolderPasteMargin`(绝对/每边) 与 `LocalSolderPasteMarginRatio`(按尺寸
> 比例)。本层经子进程 (`_paste_worker.py`) 对全部(或按封装 ref 过滤的) SMD 焊盘批量下发余量/比例,
> 落盘后**重载实测**被调焊盘数与实际回读值 (反臆造)。

```python
from kicad_origin.origin.native_paste import NativePaste
rep = NativePaste().tune("in.kicad_pcb", "out.kicad_pcb",
                         margin_mm=-0.05, ratio=-0.1, refs=["U1"])
rep.tuned, rep.sample_margin_mm, rep.sample_ratio   # 重载回读
```

实测: 全板 6 个 SMD 焊盘下发 margin=-0.05/ratio=-0.1 → `tuned=6`、回读 -0.05/-0.1; `refs=["R1"]`
过滤后 `tuned` 收窄且 < 全板; margin 与 ratio 全缺 / 缺板文件如实报错 `ok=False`。

### 〇.24 网类驱动 (`native_netclass.py`)

> 反者道之动: 网类(线宽/间距/过孔尺寸)与"哪些网归哪类"本是人在板设置对话框里点出来的, 但落到本源它
> 只是 `NET_SETTINGS` 里的一组 `NETCLASS` 与一串模式→类的绑定。本层经子进程 (`_netclass_worker.py`)
> 声明式建/改网类、按网名(或模式)绑网, `SynchronizeNetsAndNetClasses` 后落盘, **重载后对每条真实网
> 逐一解析其生效网类与实际线宽/间距/过孔** (反臆造) —— 这是 DRC 与自动布线的根。

```python
from kicad_origin.origin.native_netclass import NativeNetclass
rep = NativeNetclass().apply("in.kicad_pcb", "out.kicad_pcb",
    classes=[{"name": "PWR", "track_mm": 0.5, "via_dia_mm": 0.9}],
    assignments=[{"pattern": "VCC", "class": "PWR"}])
rep.class_of("VCC"), rep.nets   # 重载实测每条网生效网类与参数
```

实测: 建 PWR(track 0.5/clr 0.25/via 0.9) 并绑 VCC → 重载 `reload_classes` 含 PWR、VCC 生效类=PWR 且
线宽 0.5/过孔 0.9; 未绑的 GND 仍为 Default(0.2); classes 与 assignments 全空 / 缺板文件如实报错。

### 〇.25 阻焊控制 (`native_mask.py`)

> 反者道之动: 过孔是否被阻焊盖住(tenting)、焊盘开窗放多大本是人在 GUI 里逐个勾/改的, 但落到本源
> 过孔蒙盖只是 `PCB_VIA` 的前/后 `TentingMode`, 焊盘开窗只是 `PAD` 的 `LocalSolderMaskMargin`。本层经
> 子进程 (`_mask_worker.py`) 对全部过孔批量设蒙盖模式(`tented`/`not_tented`/`from_rules`)、对(可按封装
> ref 过滤的)焊盘批量设开窗余量, 落盘后**重载实测**过孔蒙盖态与焊盘开窗余量 (反臆造)。

```python
from kicad_origin.origin.native_mask import NativeMask
rep = NativeMask().apply("in.kicad_pcb", "out.kicad_pcb",
                         via_tenting="tented", pad_mask_mm=0.05)
rep.vias_tented, rep.sample_pad_mask_mm   # 重载实测
```

实测: 缝合 25 过孔后全设 `tented` → 重载 `vias_tented=25`(=全部); `not_tented`+`pad_mask_mm=0.05`
→ 6 焊盘开窗余量回读 0.05; 非法模式 / 无参 / 缺板文件如实报错 `ok=False`。

### 〇.26 焊盘-覆铜连接 (`native_thermal.py`)

> 反者道之动: 焊盘落在覆铜里是直接实连(散热好/难焊)、走热焊盘辐条(可焊/有阻抗)、还是干脆不连, 本是
> 人在 GUI 焊盘属性里逐个选的, 但落到本源它只是 `PAD` 的 `LocalZoneConnection` 与
> `LocalThermalSpokeWidthOverride`。本层经子进程 (`_thermal_worker.py`) 对(可按封装 ref 过滤的)焊盘
> 批量设连接模式(`full`/`thermal`/`none`/`tht_thermal`)与辐条宽, 落盘后**重载逐焊盘实测**其本地覆铜
> 连接模式与辐条宽 (反臆造) —— 这是地/电源平面散热与可焊性的根。

```python
from kicad_origin.origin.native_thermal import NativeThermal
rep = NativeThermal().apply("in.kicad_pcb", "out.kicad_pcb",
                            connection="thermal", spoke_mm=0.4)
rep.pads_matched, rep.sample_spoke_mm   # 重载实测
```

实测: 全板 6 焊盘设 `thermal`+辐条 0.4 → 重载 `pads_matched=6`(=全部)、辐条回读 0.4; `refs=["R1"]`
+`full` 后命中数收窄且 >0; 非法连接模式 / 缺板文件如实报错 `ok=False`。
> 注: `LocalThermalGapOverride` 在 9.0.9 SWIG 为 `optional<int>` 绑定异常(拒收 int), 故本层只下发
> 连接模式与辐条宽两项可靠量, 不臆造热焊盘间隙。

### 〇.27 本源分组 (`native_group.py`)

> 反者道之动: 把一个功能块(电源/某子电路)的若干封装框成一组便于整体搬动/复用, 本是人在 GUI 里框选
> 再 Ctrl+G 的, 但落到本源它只是一个 `PCB_GROUP` 持有若干成员引用。本层经子进程 (`_group_worker.py`)
> 按封装 ref 把成员聚成命名 `PCB_GROUP` 挂到板上, 落盘后**重载实测**组数与各组成员数 (反臆造) ——
> 这是"可复用功能块"的本源载体。

```python
from kicad_origin.origin.native_group import NativeGroup
rep = NativeGroup().apply("in.kicad_pcb", "out.kicad_pcb", groups=[
    {"name": "PWR", "refs": ["U1", "C1"]},
    {"name": "SIG", "refs": ["R1", "R2"]}])
rep.groups_added, rep.reload_groups   # 重载实测组数/成员
```

实测: 3 封装板建 `SIG`(R1,R2) 与 `PWR`(C1) 两组 → 重载 `reload_groups` 含两组、成员数分别 2/1;
空 groups / refs 无命中 / 缺板文件如实报错 `ok=False`。

### 〇.28 禁布区/规则区 (`native_keepout.py`)

> 反者道之动: 天线净空、连接器下方、安装孔周边那些"此处不许铺铜/走线/打孔"的禁区, 本是人在 GUI 里画
> 规则区再逐项勾"不允许"的, 但落到本源它只是一个 `SetIsRuleArea(True)` 的 `ZONE` 带几个 `DoNotAllow*`
> 开关。本层经子进程 (`_keepout_worker.py`) 按矩形+层+禁止项批量造规则区, 落盘后**重载实测**规则区数与
> 各禁止项 (反臆造) —— 这是布线/铺铜避让的本源约束。

```python
from kicad_origin.origin.native_keepout import NativeKeepout
rep = NativeKeepout().apply("in.kicad_pcb", "out.kicad_pcb", areas=[
    {"layer": "F.Cu", "rect": [5, 5, 20, 20]},
    {"layer": "B.Cu", "rect": [30, 5, 45, 20], "no_pads": True}])
rep.areas_added, rep.reload_rule_areas, rep.areas   # 重载实测
```

实测: F.Cu+B.Cu 两禁布区 → 重载 `reload_rule_areas=2`、各区禁止项(notrack/novia/nopour)回读为真、
B.Cu 区 `no_pads` 回读为真; 空 areas / 非法层名 / 缺板文件如实报错 `ok=False`。
> 两点本源脾性(顺之不硬来): ① 9.0.9 SWIG 对规则区 `SetZoneName` 会令 `SaveBoard` 段错迫, 故不赋名;
> ② 一次性给多个新建规则区同存会内存损坏, 故**每加一个即 save→load**, 让下个区构建在已持久化的板上。

### 〇.29 显式铜线段布线 (`native_track.py`)

> 反者道之动: 自动布线(native_route)固然省事, 但电源大电流走线、阻抗可控线、跨接补线这些"我就要这根
> 线走这里、这么宽"的诉求, 本是人在 GUI 里一段段画的, 落到本源它只是若干 `PCB_TRACK` 各持
> start/end/width/layer/net。本层经子进程 (`_track_worker.py`) 按坐标批量落铜段, 落盘后**重载实测**
> 新增段数、全板段总长与各段属性 (反臆造) —— 这是"精确可控布线"的本源原子。

```python
from kicad_origin.origin.native_track import NativeTrack
rep = NativeTrack().apply("in.kicad_pcb", "out.kicad_pcb", tracks=[
    {"start": [40, 40], "end": [50, 40], "width_mm": 0.5, "net": "GND"},
    {"start": [50, 40], "end": [50, 50], "width_mm": 0.3, "layer": "B.Cu"}])
rep.added_segments, rep.total_len_mm, rep.tracks   # 重载实测
```

实测: 两段(F.Cu/GND 0.5mm + B.Cu 0.3mm) → 重载 `added_segments=2`、`total_len_mm=20.0`、各段
线宽/层/网回读一致; 空 tracks / 板上无此网名 / 缺板文件如实报错 `ok=False`。
> 本源脾性(实测记录, 不臆造): 线段端点若**物理叠合到某焊盘**, KiCad 载入期连通性会按该焊盘的网改写线
> 段网(故文件里写 `(net 1 GND)` 也可能重载成相邻焊盘的 VCC) —— 精确布线时应让线走在目标焊盘上或空旷处。

### 〇.30 显式过孔下放 (`native_via.py`)

> 反者道之动: 层间换层、缝合地(stitching)、散热过孔阵列这些"我就要在这点钻个孔连通两层"的诉求, 本是人
> 在 GUI 里一个个点的, 落到本源它只是若干 `PCB_VIA` 各持 position/drill/diameter/net/层对。本层经子进程
> (`_via_worker.py`) 按坐标批量落通孔, 落盘后**重载实测**新增过孔数与各孔钻径/外径/网 (反臆造) —— 这是
> "层间互连"的本源原子, 与 〇.29 `native_track` 的"同层走线"互补, 合成完整的精确布线面。

```python
from kicad_origin.origin.native_via import NativeVia
rep = NativeVia().apply("in.kicad_pcb", "out.kicad_pcb", vias=[
    {"at": [40, 40], "drill_mm": 0.4, "diameter_mm": 0.8, "net": "GND"},
    {"at": [45, 40], "drill_mm": 0.3, "diameter_mm": 0.6}])
rep.added_vias, rep.vias   # 重载实测
```

实测: 两通孔(GND 0.4/0.8mm + 裸孔 0.3/0.6mm) → 重载 `added_vias=2`、各孔钻径/外径/网回读一致; 空 vias /
板上无此网名 / 尺寸非法(钻径≥外径) / 缺板文件如实报错 `ok=False`。

### 〇.31 显式多边形覆铜 (`native_zonefill.py`)

> 反者道之动: 分割电源面(split plane)、局部接地岛、大电流铜皮、避开某区的异形铺铜这些"我就要这块形状
> 的铜浇在这层这网上"的诉求, 本是人在 GUI 里一笔一笔画多边形的, 落到本源它只是若干 `pcbnew.ZONE` 各持
> outline(多边形角点)/layer/net/priority, 再交 `ZONE_FILLER` 真填充。本层经子进程 (`_zonefill_worker.py`)
> 按**任意多边形轮廓**批量铺铜浇灌, 落盘后**重载实测**新增覆铜区数与各区填充面积/角点/是否已填 (反臆造)。
> 与 〇.9 `native_zone` 互补: native_zone 是"覆盖整块板框的整面铺满", native_zonefill 是"任意形状的局部铺"。

```python
from kicad_origin.origin.native_zonefill import NativeZoneFill
rep = NativeZoneFill().apply("in.kicad_pcb", "out.kicad_pcb", zones=[
    {"outline": [[5, 5], [50, 5], [50, 15], [5, 15]],
     "layer": "F.Cu", "net": "GND"}])
rep.added_zones, rep.zones   # 重载实测
```

实测: 覆盖两 GND 焊盘的矩形轮廓 → 重载 `added_zones=1`、`is_filled=True`、填充面积 373mm²(真浇灌非估算,
连通网才留铜); 空 zones / 轮廓<3角点 / 板上无此网名 / 未知铜层 / 缺板文件如实报错 `ok=False`。
> 本源脾性(实测记录, 不臆造): 多边形若**未覆盖该网任何焊盘**, KiCad 填充期按孤岛移除, `is_filled=True`
> 但 `filled_area_mm2=0` —— 局部铺铜须让轮廓压住目标网的焊盘/走线方留铜, 这是连通性本源, 非 bug。

### 〇.32 显式圆弧布线 (`native_arc.py`)

> 反者道之动: RF/微波线、阻抗可控的平滑弯、泪滴过渡、规避直角的美观弯角这些"我就要这里走一段弧"的诉求,
> 本是人在 GUI 里一段段画弧的, 落到本源它只是若干 `pcbnew.PCB_ARC` 各持 start/mid/end 三点 + width/layer/net
> (三点定弧: 起点 + 弧上中间点 + 终点唯一确定一段圆弧)。本层经子进程 (`_arc_worker.py`) 按三点批量落弧,
> 落盘后**重载实测**新增弧数与各弧半径/圆心角/弧长/线宽/层/网 (反臆造) —— 这是"曲线布线"的本源原子,
> 与 〇.29 `native_track` 的"直线段"互补成"直+弧"的完整同层走线面。

```python
from kicad_origin.origin.native_arc import NativeArc
rep = NativeArc().apply("in.kicad_pcb", "out.kicad_pcb", arcs=[
    {"start": [40, 40], "mid": [47.071, 42.929], "end": [50, 50],
     "width_mm": 0.4, "layer": "F.Cu", "net": "GND"}])
rep.added_arcs, rep.arcs   # 重载实测
```

实测: 四分之一圆弧(圆心(40,50)/半径10mm) → 重载 `added_arcs=1`、`radius_mm≈10`、`angle_deg≈90`、
`length_mm≈15.708`、线宽/层/网回读一致; 空 arcs / 缺三点之一 / 线宽≤0 / 板上无此网名 / 未知铜层 /
缺板文件如实报错 `ok=False`。

### 〇.33 通用图形图元 (`native_graphic.py`)

> 反者道之动: 丝印图形、Logo 轮廓、机械标记、装配图辅助线、User 层批注、图形化禁布框这些"画给人看
> 或给制造看"的几何, 本是人在 GUI 里一笔一笔画的, 但落到本源它们只是任意层上的 `pcbnew.PCB_SHAPE`
> —— 线段/圆/矩形/多边形(可填充)。本层经子进程 (`_graphic_worker.py`) 在任意层批量落图元, 落盘后**重载
> 实测**(按 UUID 与落盘前比对, 只认本次新增, 不把板框等既有图元算进来) 各图元类型/层/线宽/半径/长度/
> 是否填充/多边形角点数 (反臆造)。与 〇.29/〇.32 (铜层走线)、〇.x `native_outline` (Edge.Cuts 板框)、
> `native_silk` (文字) 分工互补 —— 本层是"画形"的本源原子。

```python
from kicad_origin.origin.native_graphic import NativeGraphic
rep = NativeGraphic().apply("in.kicad_pcb", "out.kicad_pcb", shapes=[
    {"type": "segment", "start": [0, 0], "end": [10, 0], "layer": "F.SilkS"},
    {"type": "circle", "center": [20, 20], "radius_mm": 5, "layer": "F.SilkS"},
    {"type": "rect", "start": [0, 30], "end": [15, 40], "layer": "Dwgs.User"},
    {"type": "poly", "points": [[0, 50], [10, 50], [5, 60]], "filled": True}])
rep.added_shapes, rep.shapes   # 重载实测(仅本次新增)
```

实测: 线段/圆(r=5)/矩形/填充三角形四件 → 重载 `added_shapes=4`、圆 `radius_mm≈5`、三角形
`filled=True` 且 `points=3`、各层名回读一致; 空 shapes / 线宽≤0 / 未知层 / 未知类型 / 圆缺半径 /
多边形<3角点 / 缺板文件如实报错 `ok=False`。

### 〇.34 受控拆铜 (`native_ripup.py`)

> 反者道之动: 落铜有 〇.29~〇.33 一族, 那"拆"呢? 重布线、改网络归属、清空某层重来这些诉求, 本是人在
> GUI 里框选删除的, 但落到本源它只是按筛选条件对 `board` 上的 `PCB_TRACK`/`PCB_ARC`/`PCB_VIA`/`ZONE`
> 调 `board.Remove()`。本层经子进程 (`_ripup_worker.py`) 按 nets/layers/types 三维筛选受控拆除, 落盘后
> **重载实测**各类删除数与剩余数 (反臆造, 不臆称已删)。这是布线迭代的**逆原子** —— 让"改"成为可程序化
> 驱动的闭环 (落→拆→再落)。

```python
from kicad_origin.origin.native_ripup import NativeRipup
rep = NativeRipup().apply("in.kicad_pcb", "out.kicad_pcb",
                          nets=["GND"], types=["track", "arc"])
rep.removed_total, rep.removed, rep.remaining   # 重载实测 {track,arc,via,zone}
```

实测: 板上播 2 条 GND F.Cu 走线 + 1 段 GND F.Cu 弧 + 1 个 GND 过孔 + 1 条 B.Cu 走线后, 按
`nets=[GND] types=[track,arc]` 拆 → 重载 `removed={track:2,arc:1,via:0}`、过孔与 B.Cu 走线尚存;
单 `types=[via]` 只拆过孔; 单 `layers=[B.Cu]` 只拆该层; 未知类型 / 板上无此网名如实报错 `ok=False`;
空命中 (如 `nets=[VCC]` 无铜) `removed_total=0` 但 `ok=True` 不崩。

### 〇.35 显式封装变换 (`native_move.py`)

> 反者道之动: native_place 是"盯着飞线自收敛"的**自动**布局; 但很多时候人**明确知道**某件该怎么摆 ——
> "连接器贴板边定到 (x,y)、这排电容整体右移 2mm、这颗芯片转 90°、这件翻到背面"。这类确定性意图本是人在
> GUI 里精确拖拽/输入坐标的, 落到本源它只是 `FOOTPRINT.SetPosition / SetOrientationDegrees / Flip`。
> 本层经子进程 (`_move_worker.py`) 按 ref 逐件施变换 (x,y 绝对定位 / dx,dy 相对平移 / rotate_deg 设角 /
> flip 翻面), 落盘后**重载实测**各件真实坐标/角度/所在面 (反臆造)。与 〇.x `native_place` 互补 ——
> 一个"自动找好", 一个"我说了算"。

```python
from kicad_origin.origin.native_move import NativeMove
rep = NativeMove().apply("in.kicad_pcb", "out.kicad_pcb", moves=[
    {"ref": "J1", "x": 5, "y": 20},              # 绝对定位
    {"ref": "C1", "dx": 2, "rotate_deg": 90},    # 相对平移 + 转 90°
    {"ref": "U2", "flip": True}])                # 翻到背面
rep.moved, rep.footprints   # 重载实测
```

实测: R1 绝对定位 (25,35)+转 90° → 重载读回 `x=25,y=35,orientation=90,flipped=False`; C1 相对 (+5,-3)
自 (40,10) → `(45,7)` 且 `flip=True` 落 `B.Cu`; 空 moves / 板上无此 ref / 缺板文件如实报错 `ok=False`。

### 〇.36 全链路实测闭合: 自取布线器, 纯代码 → 可投产 (`env.ensure_freerouting` + `test_native_endtoend`)

> 反者道之动: 三主线讲了这么多原子与编排, 但"纯代码生成可投产 PCB"这条道**到底跑没跑通**? 此前
> `native_route`/`native_flow` 的端到端断言因 VM 无 freerouting jar 而**全程 skip** —— 等于这条最关键
> 的链从未被真正走过一遍。KiCad 自家**不带**自动布线器, 这正是"官方缺失、需我们自行补齐"的本源缺口。
> `env.ensure_freerouting()` 把缺口闭合: 缺 jar 时按官方 release 自取 freerouting 1.9.0 (与既有
> `-de/-do/-mp` CLI 约定一致) 落到候选位; `NativeRouter(auto_provision=True)` 据此让整条
> build→route→fab 开箱即通。下载失败则降级 `router_unavailable` 不崩 (无为而无不为)。

```python
from kicad_origin.origin.env import ensure_freerouting
ensure_freerouting()                 # 缺则自取 freerouting.jar (官方缺失, 我们补齐)
from kicad_origin.origin.native_flow import run_flow
rep = run_flow({                     # 纯代码声明的稳压小板 (4 件 / 4 网)
    "size_mm": [30, 22],
    "components": [{"ref": "U1", "lib": "Package_TO_SOT_SMD", "fp": "SOT-23", ...}, ...],
    "nets": {"VIN": [["U1", "3"], ["C1", "1"]], "GND": [...], ...},
}, "out/", heal=True, route=True, fab=True)
```

实测 (VM, KiCad 9.0.9 + freerouting 1.9.0): 纯代码 spec → 建板 4 件/5 网/5 未布线 → 自愈闸 pass0
freerouting 真布线 **未布线 5→0、落 14 条铜走线**、pass1 **DRC 0 违规 / 0 未连**收敛 → 投厂真出
**27 件 Gerber(全层)+ 钻孔 .drl + gerbjob + 贴装 csv + STEP 3D + 制造 PDF**, `drc.json` 实测
`violations=[] unconnected=[]`。`test_native_endtoend` 把这条链固化: 布线器缺位优雅跳过, 在位即真跑真
断言 (反臆造取自重载与真 DRC); 另含不联网的 `ensure_freerouting` 兜底逻辑断言 (已在位即返回, 绝不触网)。

### 〇.37 三主线同进: 净类深控 + 规模化实跑 + 组合方法论 (`_build_worker` netclass · `native_recipe`)

> 道并行不相背驰。承 〇.36 的全链闭合, 三主线同步再进一步, 皆 VM 真跑、反臆造实测:

**主线一 (深度接入 KiCad 底层) — netclass 差异化布线。** 此前 `_build_worker` 只会建"等宽"
板, 对布线器毫无规则深控。补齐: spec 增 `netclasses` 段, 经 `NET_SETTINGS.SetNetclasses`
+ `SetNetclassPatternAssignment` 把每网指派到带 `track_width/clearance/diff_pair_*` 的净类。
关键本源认知: **KiCad 9 把净类存进 `.kicad_pro` 项目文件而非 `.kicad_pcb`** —— `SaveBoard`
连带写出 `.kicad_pro`, `LoadBoard` 又随邻接项目文件读回 effective 净类, 故 DSN 导出/freerouting
全程 honor。实测稳压小板设 Power 类 0.8mm: 重载 `GetEffectiveNetClass('VOUT').GetTrackWidth()`
**=0.8mm**, 布线后电源网 VIN/VOUT/GND 落 **0.8mm 粗铜**、信号 FB 仍 **0.2mm 细铜** —— 对布线器
的深控由 spec 一路贯到铜箔。指派到不存在的网**如实报错**, 不静默 (反臆造)。

**主线二 (纯代码全栈) — 规模化实跑。** 把 〇.36 的 4 件小板扩到 **12 件真实 MCU 板** (SOIC-8
MCU + 3 去耦 + 4 电阻 + 2 LED + SOT-23 三极管 + 排针, 12 网): 纯代码 spec → 建板 **22 未布线**
→ freerouting **22→0 全布通** → DRC **0 违规/0 未连** → 重载实测 **58 条 track / 12 封装** → 投厂
真出 **27 件 Gerber + 钻孔 + STEP + PDF + 贴装 csv**。证全链非玩具, 可扩到工程规模板。

**主线三 (工具协同方法论) — `native_recipe` 组合层。** spec 仍是手抄扁平字典, 同类子电路
(去耦/分压/LED 指示/排针引出) 反复手抄易错。沉淀: 纯 Python 的 `Recipe` 累加器 + 参数化积木
`decoupling/voltage_divider/led_indicator/pin_header`, 叠加时自动合并同名网、ref 冲突即报错,
`.spec()` 吐出 `native_build` 直接可吃的字典 (净类指派到未声明网亦报错)。于是"画一块板"从手抄
升维为"组合积木"。**零 KiCad 依赖 → CI 全测**; 末附 router_only 集成把组合出的板真送 `full_flow`
端到端落地。

```python
from kicad_origin.origin import native_recipe as rcp
from kicad_origin.origin.native_build import full_flow
r = rcp.Recipe()
rcp.pin_header(r, "J1", {"1":"VCC","2":"IO1","3":"FB","4":"GND"}, at=(3,6))
rcp.decoupling(r, "C1", "VCC", "GND", at=(12,5))
rcp.voltage_divider(r, "R1","R2", high="VCC", mid="FB", low="GND", at=(20,6))
rcp.led_indicator(r, "R3","D1", drive="IO1", gnd="GND", at=(12,14))
r.netclass("Power", ["VCC","GND"], track_width_mm=0.6, clearance_mm=0.25)
full_flow(r.spec("board.kicad_pcb", size_mm=[34,24]), "out/")  # 组合 → 可投产
```

### 〇.38 接地平面闭环: 双面 GND 铺铜 + 避异网缝合过孔 (`native_flow` ground 阶 · `_stitch_worker` 防短路)

> 反者道之动: 〇.37 把链跑通, 但一上真实接地平面就**暴露真问题**——单面 B.Cu GND 铺铜因 SMD 焊盘
> 全在 F.Cu、无缝合过孔, DRC 报 `isolated_copper`(整片地铜悬空)。真练方知缺口, 这正是道法自然。

**接地平面闭环 (融进 `native_flow.run_flow` 的可选 ground 阶)。** spec 增可选 `ground` 段, 仅当
存在时触发, 落于 heal/route 之后、fab 之前: 由 `size_mm` 内缩 `inset_mm` 得轮廓 (避板框
`copper_edge_clearance`), **双面 (F.Cu+B.Cu) 浇 GND 铜** → **缝合过孔**把两面地平面 + 各 GND 焊盘
缝成一体, 化解 isolated_copper。无 `size_mm` 则如实跳过 (不臆造板框)。

```python
spec["ground"] = {"net": "GND", "layers": ["F.Cu", "B.Cu"],
                  "inset_mm": 0.5, "stitch": {"pitch_mm": 5}}
run_flow(spec, "out/", heal=True, route=True, fab=True)  # 自动多一道 ground 阶
```

**避异网缝合 (`_stitch_worker` 深修, 主线一)。** 初版缝合过孔只避**异网焊盘**, 不避**异网走线/过孔**
—— freerouting 布线非确定, 某次 FB 走线恰穿过网格过孔点 → DRC 报 `shorting_items`(GND 与 FB 短路)。
补齐: 收集所有异网走线段 (点到线段距离平方, 整数 nm 无溢出) + 异网过孔, 候选过孔点距任一异网铜
< `clearance + via_r + 半宽` 即跳过。实测稳压小板: 双面铺铜 (F.Cu 540 / B.Cu 609 mm²) + **16 颗
GND 缝合过孔** → 投厂真 DRC **0 违规 / 0 未连**。golden 测试重载实测每颗 GND 过孔到异网走线的距离
≥ clearance (反臆造, 不靠 DRC 兜底而直接量距)。

### 〇.39 净类深控贯到铜箔实证: 净类宽度经 freerouting 真 honor (主线一 · 反臆造)

> 〇.36 的 netclass 只验到落 `.kicad_pro` + 重载读回 effective 轨宽 (纸面层)。本节把它推到铜箔:
> **净类宽度是否被真布线器执行?** 不臆测, 直接量。

**DSN 真带净类规则。** `pcbnew.ExportSpecctraDSN` 把每个净类导成 `(class <name> <nets...> (rule (width W) (clearance C)))`——实测 `Diff` 净类 (track_width 0.25 / clearance 0.2) 落为 `(class Diff USB_DM USB_DP ... (rule (width 250) (clearance 200)))`。freerouting 据此布线。

**布线后逐网量实测。** 两连接器引出 USB 差分对 (USB_DP/USB_DM, 归 Diff 净类 0.25mm) + 电源/地 (默认窄轨)。`route` 后重载, 逐网收 `PCB_TRACK` 宽度: **USB_DP/USB_DM = 0.25mm** (净类宽被布线器真 honor), GND < 0.25 (默认网不受 Diff 类波及)。golden 测试 `test_netclass_width_honored_by_real_router` 锁此不变量 (router_only)。

**诚实边界 (反臆造, 不夸大)。** 净类**宽度/间距**贯通到铜 (已证); 但真正的**耦合差分布线** (DP/DM 全程平行、维持恒定 gap) freerouting 1.9.0 经典 DSN 路径**不**单独编码差分配对指令, 两网按同宽独立布线而非耦合走线。即"差异化宽度"已落地, "耦合等距差分"仍是上游布线器局限——此处如实记录, 不充作已有能力。

### 〇.40 大型系统板端到端 + 平面法布线四能力 (`native_route.skip_nets` · 铺铜 solid · 缝合孔-孔避让 · plane-first DSN)

> 专注真正大规模长链路复杂 PCB: 以密集 QFP 大板为靠标一路实践, **让缺失能力在真板上暴露、再自补**, 三主线同进。反臆造: 一切布线/铺铜/DRC 皆重载或真 `kicad-cli` DRC 实测。

**驱动靠标 (STM32F103C8T6 开发板, 28 件 / 33 网)。** 纯代码经 `native_recipe` 积木拼装: LQFP-48 (0.5mm 脚距) MCU + USB Micro-B + 8MHz 晶振 + AMS1117 LDO + 去耦阵 + GPIO/UART/SWD 排针 + 复位/BOOT 键 + 电源/状态 LED, 90×68mm 双层。这块板把布线器逼到极限, 逐一逼出真问题:

**能力 ① `NativeRouter.skip_nets` —— 从 DSN 摘网 (宽地/电源交平面, 不硬布)。** LQFP 0.5mm 脚距上, 宽 GND 网以细线从周边焊盘逃逸在双层板上几无可能 (freerouting 首跑 90 未布线残 19, 皆电源/地)。产业标准做法: 宽地/电源交**双面铺铜平面 + 缝合过孔**独立承担, 不交布线器硬布。故新增 `skip_nets`: 布线前从 Specctra DSN 摘除指定网的 `(net ...)` 块并从 `(class ...)` 头去其网名——`_match_paren_end` 括号平衡扫描保证 DSN 语法不破, `_strip_nets_from_dsn` 返回真删网名。`route_passes`/`route_skip_nets` 经 `native_heal`/`native_flow` 贯到顶层编排。

**能力 ② 铺铜 `pad_connection=solid` —— 免热焊盘辐条不足。** 首次浇 GND 平面后真 DRC 冒 7 个 `starved_thermal` (热焊盘辐条不足)。`_zonefill_worker` 增 `SetPadConnection(ZONE_CONNECTION_FULL)`: 地/电源平面取实心满连, 焊盘直接并入铜面。`native_flow` ground 阶默认 `pad_connection="solid"`。实测: `starved_thermal` 归零。

**能力 ③ 缝合过孔孔-孔避让 —— 免 `hole_to_hole`。** 缝合过孔原只避异网焊盘/走线, 却会落在**同网 THT 焊盘** (如 J1 的 GND 直插脚) 钻孔旁 → `hole_to_hole` 违规。`_stitch_worker` 增: 收全板所有钻孔 (任意网, 含同网焊盘 + 过孔), 缝合点离任一钻孔中心 < `hole_clearance + 钻孔半径和` 即跳过。实测: `hole_to_hole` 归零。

**能力 ④ plane-first: 预浇平面经 DSN 落为 `(plane ...)`。** 实测: 布线**前**在 B.Cu 浇好的 GND 实心铺铜, 经 `ExportSpecctraDSN` 被导出为 `(plane GND (polygon B.Cu ...))`——布线器据此把每个 GND 脚自动打孔并入平面。此路把大板未布线从 85 降到 13 (信号/电源基本布通, 仅 QFP 电源环残留)。

**三修复实证 (大板)。** 上述 ①②③ 令大板真 DRC 违规 **9 → 3** (`starved_thermal`/`hole_to_hole` 两类彻底消除)。

**诚实边界 (反臆造, 关键)。** freerouting 1.9.0 **无法**把这块密集 28 件双层 QFP 板全布到 0 未连/0 违规: 无论 `skip_nets` 交平面还是 plane-first, MCU 的 **VDD 电源环** (脚 1/9/24/36/48) + USB + 个别长信号总有残留。这是**双层板 + 上游布线器**对细脚距 QFP 电源分配的真实上限——产业界这类板本就是**四层** (信号/GND/电源/信号) 或**人工扇出**。此处如实记录, **不伪造"全清"**。

**清板端到端固化 (`test_native_bigboard.py`)。** 取能被布线器全布的规模: 10 件多子系统电源板 (LDO + 去耦阵 + LED + 双排针 + 双面 GND 平面), 走 build → route(skip GND) → 双面实心铺铜 + 缝合 → fab, 重载实测 **DRC 0 违规 / 0 未连**, 26 件 Gerber + 钻孔 + STEP + PDF + 贴装真出。四能力另各有确定性/pcbnew/router 分层断言 (`skip_nets` 纯文本 CI 恒跑)。回归 467 passed / 5 skipped 无退化。

## 一、摸清本源: KiCAD 9.0.9 原生能力面 (VM 实测)

| 能力 | KiCAD 原生本源 | 取代我此前的"从零造" |
|------|---------------|----------------------|
| 板对象读写 | `pcbnew.LoadBoard/SaveBoard`, `BOARD`/`FOOTPRINT`/`PAD`/`PCB_TRACK`/`PCB_VIA` | (保留自研 `Board` 仅作轻量编辑, 落盘走 pcbnew) |
| 连通性/飞线 | `BOARD.GetConnectivity()` → `CONNECTIVITY_DATA` (真 ratsnest) | 我的 MST 猜测 |
| 设计规则 | `GetAllNetClasses()` / `GetDesignSettings()` (clearance/track/via) | Python 里散落的参数 |
| **自动布线** | `ExportSpecctraDSN` / `ImportSpecctraSES` + 生态 **Freerouting** | **`route_maze`/`route_maze2` (自研 A*) ← 弃** |
| DRC | `kicad-cli pcb drc` (真引擎) | 我的 Python DRC ← 早已弃 |
| 制造产出 | `kicad-cli pcb export` (Gerber/钻孔/贴片), `render` | — |

## 二、本源全流程闭环 (用户全方位操作链)

```
DNA 设计意图
  └─ inline 真焊盘 (KiCad 封装库)
       └─ spread_placement   ── courtyard 几何拉开 (我的工具, 暂留)
            └─ pinmap + netbind ── 命名引脚→脚号 + 绑网 (我的工具, 暂留; 本源化待办)
                 └─ ★ autoroute_freerouting ──────────────── 本源自动布线
                 │     pcbnew ExportSpecctraDSN → Freerouting(无头) → pcbnew ImportSpecctraSES
                 └─ kicad-cli pcb drc ──────────────────────── 本源真 DRC (唯一真理)
                      └─ kicad-cli pcb export ──────────────── 本源制造产出 (Gerber/钻孔/贴片)
```

核心新件: `kicad_origin/pcb/autoroute.py` (编排) + `kicad_origin/pcb/_specctra_helper.py`
(在 KiCad 自带 python 下跑的 pcbnew DSN/SES 帮手)。`design_loop --router freerouting` 即走本源链路。

## 三、保留 / 弃用 / 待本源化

- **弃用**: `route_maze` / `route_maze2` (自研 A* 布线) —— 本源 Freerouting 在密板上决定性更优 (见审计)。
  暂留作无 Java 环境的降级回退, 不再投入演进。
- **保留**: `spread_placement` (读真 F.CrtYd courtyard 几何拉开, KiCAD 无等价一键命令)、
  `pinmap`/`netbind` (从 DNA 逻辑意图→真实焊盘绑网, 这是"设计输入"层, 非重造 KiCAD)。
- **待本源化**: ① netbind 改用 pcbnew `NETINFO_ITEM`/`SetNetCode` 原生绑网;
  ② copper-to-edge 在 DSN 导出前设 `GetDesignSettings()` 边距, 让 Freerouting 避板框;
  ③ 制造产出接 `kicad-cli pcb export` 出 Gerber/钻孔/贴片, 闭到可投产。

## 四、环境依赖 (须固化进 blueprint, 否则快照不持久)

- KiCad 9.0.9 (含 pcbnew python): `C:\Program Files\KiCad\9.0`
- JRE 25 (Freerouting 需 class 69): 本会话置于 `C:\Users\Administrator\tools\jre25\...`
- Freerouting v2.2.4 jar: `C:\Users\Administrator\tools\freerouting-2.2.4.jar`
- `autoroute.py` 经 env 覆盖路径: `KICAD_PYTHON` / `JAVA_BIN` / `FREEROUTING_JAR`。
  **注意**: `tools/` 为本会话所置, 未来快照须由 blueprint 重新下载 JRE25 + freerouting.jar。

## 五、实测结论

本源 Freerouting 链路全库 16 板: **9/16 板 0 错且全导通**, 且把自研 A* 啃不动的密板
(gd32 17→全通、dot_matrix、w5500 25→全通) 决定性解决。余下失败均为**非布线问题**
(命名引脚未绑 / 大板 placement / 板框边距 / 预存封装钻孔), 各有本源对策, 逐一推进。

> 无为而无不为: 不与成熟引擎争布线之巧, 而善用其巧, 专注于其上之全流程闭环。
