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
