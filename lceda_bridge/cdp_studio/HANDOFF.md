# 交接文档 · Dao-PCB-Design-Agent(嘉立创 EDA 深融)

> 道法自然 · 三道并行而不相悖:**阴**(逆向底层 API)、**阳**(正向整合社区/共享资源)、
> **全链路**(原理图意图 → 可制造产物)。本文供后续 Agent 接手后零摩擦继续推进。

## 0. 一分钟上手

- **桌面端零摩擦部署(干净机器一条命令)**：`python bootstrap_desktop.py --license <激活文件> --with-freerouting --verify`(幂等：下载客户端→解压→安放离线激活→拉起 CDP:29230 并等 `_EXTAPI_ROOT_` ns>0)。已部署过仅重起：`--launch-only --verify`。随后 `cd examples && PYTHONPATH=.. python3 run.py all --tries 5` 跑全链路板谱。详见 `DESKTOP_OFFLINE_FINDINGS.md` 末「一键复现部署」与「冷启动竞争」。

- 引擎:`lceda_bridge/cdp_studio/eda_flow.py`(类 `Flow`,封装全部能力,逆向自嘉立创 EDA Pro v3.2.148 的 `window._EXTAPI_ROOT_` 私有 RPC 总线)。
- 驱动:`dao_eda_cdp_driver.py` / `eda_api.py`(CDP 接到运行中的 Chrome,端口 `:29229`;编辑器在 `https://pro.lceda.cn/editor`)。
- 账号:`15606700905`(用户 `aiotvr`)。冷启动登录见 `cold_start.py`(已固化确定性登录,根治"GUI 合成键入吞密码前缀"——改用 CDP 向 React 受控组件注入)。
- 跑任一活体验证:`python build_capstone_full.py`(全能力大合龙,期望 `RESULT PASS`)。
- 仓库自动 PR 线路:阻断式 `Python syntax gate`(全仓 py_compile)+ main 分支保护 + 打 `dao-auto` 标签自动合并。**提交前务必 `python -m py_compile`**。

## 1. 能力全谱(全部 VM 活体验证 · 见对应 build_*.py)

### 原理图(SCH)
- `place_device_det(device,x,y,...)` — 确定性放件(逆 `sch_PrimitiveComponent.create(device,x,y,subPartName,rotation,mirror,addIntoBom,addIntoPcb)`)。同器件连放 5/5 精确。(#22)
- `route_by_name(net_map, stub=40)` — **连接即命名**:每脚一段短 stub 赋网名,互不接触的同名 stub 仍归一网 → **任意拓扑零交叉零融合**(物理拉线在跨侧/密集拓扑必融,本法是归一解)。(#24)
- 关键判据:嘉立创原理图**任意两线几何相交(含正交十字)即融合**。

### 阳 · 社区/共享资源
- `lib_search` / `device_by_lcsc` / `place_by_lcsc(lcsc_id,x,y)` — LCSC 编号 → 库记录 → 一行确定性落件。(#25)
- `footprint_search` / `symbol_search` / `model3d_search` / `cbb_search` / `classification_tree` — 嘉立创共享**封装/符号/3D/可复用电路块/分类目录**检索(`_resolve_lib` 统一库解析)。(#31)

### PCB
- `pcb_place_det(comp_id,x,y,rotation,layer)` / `pcb_layout_row(...)` — 确定性摆件(逆 `pcb_PrimitiveComponent.modify` 的 setState_X/Y/Rotation)。(#28)
- 网络绑在**器件引脚**(`getAllPinsByPrimitiveId` 每脚带 net/x/y),非自由焊盘。`pcb_pins_by_net()` 据此聚合。
- `pcb_route_net(net,layer,width,orthogonal,escape,via)` — 程序化铜布线(纯 extapi `pcb_PrimitiveLine.create`,无需板框/GUI)。
  - `escape!=0`:**避让走线**,引脚竖直逃逸到器件行外空走廊再水平贯通(signed:>0 行下、<0 行上)。(#26/#28)
  - `via=True`:走非顶层时每脚落过孔接顶层焊盘。
- `pcb_route_all(escape)` — 单层多网上下交替分侧。(#28)
- `pcb_route_layers(escape)` — **2 层过孔布线**:各网轮流顶/底层 + 各走逃逸走廊。两重正交自由度叠加(走廊灭 Pad-to-Track、分层灭两网相交)→ 任意交叉/共线拓扑零违规。(#30)
- `pcb_via(net,x,y,hole,diameter,via_type)` — 落过孔(hole/diameter 不可省)。
- `copper_pour` / `auto_ground_pour(net,layers,margin)` / `rebuild_pours()` — 程序化敷铜地平面。`auto_ground_pour` 从器件引脚取 bbox(实板自由焊盘为空);`rebuild_pours` 走 GUI 快捷键 Shift+B(extapi 无重建命令)算出实铜。GND 覆铜既铺实铜又经热焊盘连通同网引脚。(#33)

### DRC / 导出
- `drc_check(verbose)` / `drc_violations()` / `drc_summary()` — **API 直读**结构化违规树(更正旧论"明细唯 GUI 面板可得";v3.2.148 `pcb_Drc.check(strict,ui,includeVerboseError=true)` 直接返回)。(#27)
- `export_gerber/export_bom/export_pick_and_place/export_pdf/export_dsn` / `export_all(out_dir)` — 真字节落地(走通用 blob 通道)。
- `export_dsn` 须从**未布线**板导出(Freerouting 输入);SES 回灌见 `import_ses`。

## 2. 活体验证脚本(全部 RESULT PASS)

| 脚本 | 证明 |
|---|---|
| `build_chain_det.py` | 确定性放件 + 两网无融合最小闭环 |
| `build_cross_det.py` | 连接即命名解跨侧两网(纯 lane 必融) |
| `build_lcsc_det.py` | LCSC 取件 + place_by_lcsc |
| `build_catalog_det.py` | 阳路目录检索层(封装/符号/3D/分类) |
| `build_copper_det.py` | 程序化铜布线 net 长 0→实长 |
| `build_pcbplace_det.py` | 确定性 PCB 铺开 |
| `build_clean_det.py` | 避让布线 DRC 2→0 |
| `build_2layer_det.py` | 2 层过孔布线解共线交叉对 DRC 0 |
| `build_pour_det.py` | GND 覆铜 DRC 3→0、实铜算出 |
| `build_capstone.py` / `build_capstone_full.py` | 端到端 / **全能力大合龙** |

`build_capstone_full.py` 实测:nets [GND,NET_A,NET_B];信号 2 层各长 6000;poured=1;**DRC total=0**;export gerber=8496/bom=6739/pnp=6961 真字节。

## 3. 诚实定界(不夸大、不造假)

- **不靠放宽容差骗过 DRC**。所有 DRC 0 均为真实布通/敷铜所得。
- `lib_Device.searchByProperties` 在本版是**空桩**(恒返回 []),未封装。
- `lib_Cbb.search` API 通,但当前可达库**无 CBB 数据**(返回 [])。
- `lib_Footprint.getRenderImage` 对所试封装返回 **None**,未采用。
- `rebuild_pours` 依赖 GUI Shift+B(extapi 无重建命令)——是当前唯一非 headless 步。
- `dmt_Project.createProject` 曾因我**自己刷页面**致**本实例**卡死(非代码缺陷);新会话冷启动即干净。建工程用 `build_chain_det._scaffold` 路径。

## 4. 仓库 / PR 线路

- 远端:`zhouyoukang1234-spec/Dao-PCB-Design-Agent`。两条并行子系统:`lceda_bridge/`(本文嘉立创深融)与 `kicad_origin/`(KiCad 9 原生 IPC/SWIG 深融,Linux 跑通)——**文件不相交**。
- CI:`.github/workflows/ci.yml` 全仓 py_compile(阻断)。绿灯后 `PUT /pulls/{n}/merge`(merge_method=merge)。base 被改动报错则重试一次。
- 发现固化:`PHASE4_FINDINGS.md`(逆向编年,至第二十四章);`EVOLUTION_NOTES.md`。

## 5. 下一前沿(后续 Agent 可直接接手)

1. **net-class / 差分对** 设计规则(签名已探,未封装)。
2. **3D 预览 / 层叠**(`model3d_search` 已通,可进一步拉装配视图)。
3. **CBB 复用**:接入有数据的库后用 `cbb_search` + `lib_Cbb.openProjectInEditor` 整块复用社区电路。
4. **Freerouting 闭环**:`export_dsn` → 外部布线 → `import_ses` 全自动化跑通密集板。
5. **net 标志/电源符号**:`sch_PrimitiveComponent.createNetFlag` / `setNetFlagComponentUuid_Ground/Power` 做规范电源轨。
6. **KiCad 道**(`kicad_origin/`):继续 IPC API 深融、3D/Gerber/STEP 导出对齐。

> 接手姿势:先 `python build_capstone_full.py` 确认底座活;再挑一条前沿,逆向 → 实现 → `build_*_det.py` 活体验证 → py_compile → 干净 PR → CI 绿 → 合并。一直推进,一直完善。
