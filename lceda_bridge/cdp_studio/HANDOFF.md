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
- `export_gerber/export_bom/export_pick_and_place/export_pdf/export_dsn` 及扩展格式 `export_3d/export_dxf/export_ipc_d356a/export_odb/export_ibom/export_altium/export_test_point/export_netlist` — 真字节落地(走通用 blob 通道)。
- `export_all(out_dir)` 已全谱化(与桌面 `dao_rpc_driver.export_all` 对齐):web 登录态活体实测 **12 格式**真字节 gerber/bom/pnp/pdf/dxf/3d_step/ipc_d356a/odb/ibom(≈5.4MB)/altium/testpoint/netlist,逐格式如实记录 size/err、单格式失败不阻断其余。诚实定界:`getIpc2581CFile`→NO_RESULT、`getAutoRouteJsonFile`→NOT_BLOB(JSON 对象非 File,走 `pcb_import_autoroute_json`)。
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
| `build_export_det.py` | **桌面纯 RPC 全谱导出**:DRC=0 板一次导齐 13 制造/交换格式真字节 |
| `build_web_export_det.py` | **web 在线端全谱导出**:DRC=0 板一次导齐 12 制造/交换格式真字节(与桌面对偶,双通道对齐) |

`build_capstone_full.py` 实测:nets [GND,NET_A,NET_B];信号 2 层各长 6000;poured=1;**DRC total=0**;export gerber=8496/bom=6739/pnp=6961 真字节。

### 桌面纯 RPC 底座 · 制造数据全谱导出(`dao_rpc_driver.DaoRpc`,端口 29230)
`pcb_ManufactureData` 远不止 Gerber/BOM/PnP。桌面离线底座已逐格式**活体实测**产出真
字节,并固化为 `export_all(out_dir)`(`build_board` 可置 `spec["export_all"]=True` 全导)
与 CLI `python dao_rpc_driver.py export <out_dir>`(对当前打开板):
- 实测可达(13):`gerber/bom/pnp/pdf/3d_step(get3DFile step≈1.7MB)/dxf/ipc_d356a/odb(ODB++)/ibom(交互式 HTML≈5.5MB)/altium/testpoint/netlist(.enet)/autoroute_json`。
- 诚实定界(不纳入全谱):`getIpc2581CFile` 无头底座**恒挂起**(疑待 GUI 配置对话框,显式 `fileType='xml'` 仍不返回);`get3DShellFile` 本板型返回 `no file`。

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

## 6. 桌面端纯 RPC 轨 · 本会话新增能力与本源教训

> 桌面端(`bootstrap_desktop.py` → CDP:29230)走 `dao_rpc_driver.py`(类 `DaoRpc`),
> 全链路零 GUI:`place_and_net → apply_constraints → board_outline → autoroute(freerouting) → drc → length_audit → export`。
> 板谱在 `examples/specs.py`(`BOARDS` 字典),`run.py <name|all> --tries N` 跑。

### 已固化原语
- **`auto_fanout(designator, pad_net, ...)`** — 几何驱动**通用扇出**:读目标器件**真实焊盘 (x,y)**(`pad_xy`)→算中心→每脚按 `|dx|`vs`|dy|` 主轴定逃逸边(右/左/上/下)、同侧沿边排序逐颗递增 `depth_step` 错位→串件落「脚垂直对齐线 × 外延深度」。**不对任何封装引脚布局做硬假设**。已在 QFP(四边)/ SOIC(双边)/ BGA(栅格外圈)三类几何验证 DRC=0 通用。谱里器件声明 `auto_fanout={脚:网}` 即接入。
- **`place_and_net(components, chunk=10)`** — 按 `chunk` 件**分批多发 eval**:治大板(如 48 脚 QFP ~120 次绑网)单发破 90s `NO_RESULT`,对任意规模线性可扩。
- **`length_audit(constraints)`** — 布线后以 `pcb_Net.getNetLength` 量实测铜长,报 diff_pair **skew**(`|lP-lN|`)/ equal_length **spread**(`max-min`),据实入 `audit.steps.length_audit`。把「约束兑现度」变成可量测数字。
- **`length_tune(constraints, tol=8, max_passes=6)`** — **布线后原位蛇形调长**,把 freerouting「不调长」的边界转成能力。以组内最长网为基准,给较短网在其**当前最长直段**删原段→同端点画**朝板内的曼哈顿蛇形**(端点不动故电气连续不破)。**闭环迭代**:蛇形几何长 ≠ `getNetLength` 实测增量,故每趟重测按真实 deficit 续补、并自然落到新的最长段(多段分摊),直到 spread≤tol 或无进展。tune 板实证 spread **300→0.0mil、2 趟、DRC=0 CLEAN**。spec 置 `length_tune:True` 即在 build 管线布线后自动调长(改铜后 DRC 重测)。
- **`doc_source(pcb_uuid=None, parse=True, raw=False)`** — **PCB 文档本源序列化读出**:经 `sys_FileManager.getDocumentSource` 取官方序列化(行记录流 `{"type":TAG,"ticket":N,"id":..}||{payload}|`),按 type 结构化解析成 `{counts, records:[{type,ticket,id,payload}]}`。整板一发读出 526 记录/19 型(DOCHEAD/CANVAS/LAYER/LAYER_PHYS/NET/RULE/RULE_SELECTOR/COMPONENT/ATTR/PAD_NET/LINE/VIA/POLY/…),比逐 primitive `.get` 快一个量级。CLI:`python dao_rpc_driver.py docsrc [--records]`。**读写分治**(见下条本源教训)。
- **`drc()` 结构化** — 每违规附 `net`+`pos(x,y)`,返回 `by_net` 把「DRC=N 某型错」变可定位到具体网与坐标的清单(如 mcu 偶发不收敛立现是哪域哪些网未布通)。
- **`_eval(..., retries=2)`** — 对**瞬时** `NO_RESULT`(CDP 偶发空结果)有限重试 + 重连编辑器会话;真错误/超时如实抛,不掩盖。

### 本源教训(实证)
- **几何优先**:高脚数器件能否一次布通,命门在**放置质量**而非布线器。qfp 实证——detached 栅格放 32 扇出残留 8 Connection Error;改「就近同侧逃逸」即一次过 DRC=0。`auto_fanout` 把这套手调几何**自动化**。
- **几何优先**有方向性,不是「永远紧簇」**(本会话反例)**:mcu(双层无平面、16 LED 密集阴极汇流)把扇出链**竖列紧簇**反令 DRC 由 ~4 暴增到 0/37/51。**就近紧簇利于高脚数逃逸,却害双层密集汇流**——后者紧簇令 GND 汇流与限流支路两层互锁拥塞,**均匀铺开(_grid)反更优**。故 mcu 保留 _grid;实验证伪即纳之(反者道之动)。
- **差分对约束需可并走的真实跨段**(cap vs qdiff 实证):`auto_fanout` 的「焊盘→1 串阻」退化短桩上声明 `diff_pairs` 触发 Differential Pair Error(cap 实测 DRC=1);给配对两网真实并走跨段(qdiff:源相邻两脚→远端竖向紧邻 sink),freerouting 差分布线即收敛 DRC=0、skew≈2.7mil。
- **边界→能力(length_tune·本会话)**:freerouting **不做长度调谐**曾据实存档为边界;今以**布线后原位蛇形**跨过它——删一段直走线、同端点重画更长的朝板内梳状折线,端点不动故连通不破。关键两堑:① 盲目**交替两侧**会把铜推出板框/贴焊盘(净距违规)→ 改**单侧朝板内 bbox 心 + 两端 inset**;② 蛇形**几何长 ≠ getNetLength 实测增量**(单发开环欠补)→ 改**闭环迭代**重测续补。tune 板 spread 300→0.0mil DRC=0。诚实留界:**短网/密板无处可蛇**(skewlen:NA 仅 ~220mil 欠 1380mil,物理补不满,留大 residual 据实记,不强补)。
- **文件本源·读写分治(doc_source·本会话逆向)**:`.eprj2` **实为 SQLite**(`SQLite format 3`),但 PCB 几何**不**以扁平 blob 存——`documents/coppers/texts.dataStr` 常空,真实状态由 `branches/history_data/project_history_*` 的**操作日志(op-log)重建**(CRDT 式)。直接逆 op-log **脆弱且随版本漂移**,非本源正道。转锚**官方序列化层**:`sys_FileManager.getDocumentSource(uuid)` 一发取全文(行记录 `{"type":TAG,"ticket":N,"id":..}||{payload}|`),稳定可解析(`doc_source` 原语)。**吃一堑**:对偶的 `setDocumentSource(uuid,src)` **整文回写不生效**(实测恒返 `False`;改 LINE.width 读回不变,仅 DOCHEAD.client 重序列化)——故**读经序列化、写经 typed primitive(`.modify/.create/.delete`)/ 布线经 `importAutoRouteSesFile`**,各得其所,不强行整文写(知止不殆)。`pcb_Document.importChanges(arg)`(argc=1)经探:喂行记录串/对象数组/`{modify:[...]}` 三形**皆返 `true` 却均不生效**(改 LINE.width 读回不变)——其私有 changeset schema 非平凡,**不盲猜硬凑**(返 true 仅证其对未识别输入宽容,非已应用)。结论锚定:**typed primitive 即官方写信道**(此为 live 会话内的写;**离线文件级直写**见下条已被实证打通,二者并存)。
- **op-log 加密已破 + headless 直写 PCB 文件·字节级实证(`eprj2_codec`·本会话,一波三折的真结论)**:把上条「op-log 不盲逆」从论断升级为**可读可写的实证原语**。①**破密(READ)**:`history_data.dataStr` = `base64(AES-128-GCM(gzip_l1(源记录流)))`;key=该分支 `project_history_<branch>.key`、iv=该行 `uuid` 的 hex 前缀(`-N` 后缀截断故同文档各段共 IV)、tag=末 16B;**加解密 round-trip 无损**。`eprj2_codec.py` 可零 GUI 直读任意 `.eprj2` 全量 live 源记录流(明文与 `getDocumentSource` 同构)。②**曾误判→修正**:先前改 `.eprj2` 重开**不显现**,一度误判「`.eprj2` 非权威」。**真因**是 **Service Worker CacheStorage** 里的**明文** `localSave`/`project` 热缓存(`https://client/localSave/<id>?key=..`→`{DOCHEAD..PCB..}`):编辑器 open **优先喂该缓存**,旧值掩盖了磁盘改动。③**决性突破(WRITE)**:`getCurrentProjectInfo` 确认打开的就是被改文件、`web.db`/IndexedDB/recovery/`snapshot` 实测**均空**、`pkill` 清内存、**再清 SW CacheStorage 强制 cache-miss**后——改 `"Top Layer"→"DAOTOPXX"` 写回 `.eprj2`,重开 `getDocumentSource` **出 DAOTOPXX**、且 **DRC=0 CLEAN**;经 `edit_docs()` 原语反向还原亦 DRC=0。**进一步**:改**真实几何**——某 `LINE`(net DP_P)`width:10→14`,重开如实读回 14、DRC=0(再还原 10),证明可程控改电气/几何记录,非仅改 cosmetic 串。∴ **cache-miss 时 `.eprj2` history_data(加密 op-log)即权威面,headless 直写 PCB 文件可行**。写路径 = `edit_docs(改 op-log)` → `invalidate_doc_cache(清 SW 缓存)` → 重开(**全新工程无缓存,首开即读,无须清**)。**两条写信道并存**:文件级直写(`eprj2_codec`,关编辑器、离线)/ 会话级 typed RPC primitive(live,已建全 14 板 DRC=0)。
- **诚实定界**:① headless 无实铜覆铜(`rebuildCopperRegion` 恒 undefined,见 FINDINGS);② freerouting **仅通孔**——故 BGA **内圈球** escape 是当前布线级前沿(等长/差分长度匹配已由 `length_tune` 在布线后补上,见上条);③ length_audit 的 skew/spread 取决于放置对称性,如实记录(hs 对称放置恰好 skew=0,skewlen 不对称放置 spread=1380mil 验证审计量真);④ mcu 偶发不收敛(~1/8)是 **2 层无平面**的真实边界,据实存档,不以更差紧簇粉饰。

### 板谱(14,VM 活体 DRC=0 CLEAN;mcu 见上注 ~1/8 偶发不收敛)
`simple/medium/complex/mcu`(几何全链)· `hs`(约束级:网类+差分对+等长组+类线宽注入 DSN)· `via6`(6 层+自定义过孔+盲埋孔层对)· `qfp`(LQFP48 四边手调扇出)· `autofan`(同 QFP 但 auto_fanout 零手填坐标)· `soicfan`(SOIC16 双边 auto_fanout)· `bga`(BGA64 0.65mm 外圈通孔逃逸)· `skewlen`(不对称等长组反验 length_audit 报非零 spread)· `tune`(现实等长场景:适度 skew+可比长+留余量,布线后 `length_tune` 把 spread 收到 0)· `cap`(合龙:几何扇出+网类+等长+4 层+审计可组合)· `qdiff`(高脚数 QFP 真差分对 DRC=0)。

> 接手姿势:先 `python build_capstone_full.py` 确认底座活;再挑一条前沿,逆向 → 实现 → `build_*_det.py` 活体验证 → py_compile → 干净 PR → CI 绿 → 合并。一直推进,一直完善。
