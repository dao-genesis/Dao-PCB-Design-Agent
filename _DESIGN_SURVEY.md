# 全库实践审计 · bind+route 跑遍 16 块板 (KiCad 9.0.9 真 DRC)

> 我(设计者)用自己造的 `netbind`+`route_maze` 把每块占位板往"可制造"推, 用 KiCad
> 自身 DRC 验证, 诚实记录每块板停在哪、为何停。为学日益, 为道日损——下一步该补什么,
> 数据自己会说话。

## 结果 (grid=0.2mm) — 已修性能后, 16 板全部完成, 无超时

> GAP3 性能已先解决: 障碍栅格预栅格化 (owner 表 O(1) 查障) + A* 节点上限 (知止不死等)。
> 三块原 >90s 超时的大板现 23/32/11s 完成。全库一遍 ≈2 分钟。

| 板 | 绑定 | 未绑 | 飞线布通 | err | 未连 | 秒 | 结论 |
|----|-----|-----|---------|-----|-----|----|------|
| ams1117_power            |  9 |  0 |  6/6  | 0 | 0 |  2 | **全净 CLEAN ✓** |
| usb_c_pd_trigger         | 20 | 12 | 13/13 | 0 | 0 |  5 | 已绑部分全布通·0错 |
| w5500_ethernet           | 28 | 22 | 15/15 | 0 | 0 |  4 | 已绑部分全布通·0错 |
| motor_driver_dual        | 24 | 16 |  9/10 | 7 | 1 |  4 | 单层布不完+短路 |
| led_indicator            | 20 |  0 | 11/15 | 1 | 4 |  5 | **全绑定·单层布不完** |
| stm32f103c6_dot_matrix   | 63 |  0 | 13/40 | 46|27 | 11 | **全绑定·单层严重拥塞** |
| lora_sx1276_gateway      | 25 | 12 | 11/15 | 8 | 4 |  8 | 部分未绑+拥塞 |
| rp2040_minimal           | 28 | 29 | 17/19 | 9 | 2 |  8 | 部分未绑+拥塞 |
| stm32g031_minimal        | 36 | 15 | 13/18 | 20| 5 |  9 | 部分未绑+拥塞 |
| nrf52840_ble5            | 34 | 34 |  7/10 | 17| 3 |  6 | 大量命名引脚未绑 |
| esp32_servo_wifi         | 20 | 20 | 12/14 | 25| 2 |  6 | 大量命名引脚未绑 |
| ch32v003_minimal         | 32 | 20 |  9/12 | 17| 3 |  7 | 部分未绑+拥塞 |
| gd32f103_minimal         | 66 |  6 | 15/37 | 27|22 |  6 | 大板·单层严重拥塞 |
| smartwatch_core          | 45 | 57 | 24/30 | 19| 6 | 11 | 命名引脚未绑最多 |
| drone_flight_controller  | 89 |  2 | 44/69 |104|24 | 32 | 大板·单层严重拥塞 |
| drone_aerial_h743        |174 | 41 |45/115 |181|69 | 23 | 大板·单层严重拥塞 |

## 全链路审计 v2 — inline→**spread**→netbind→**route_maze2(双层)**→真 DRC (grid=0.2)

> 补齐三件新工具 (性能/双层/摆放) 后重跑全库。spread 把**所有**板的 courtyard 相叠
> 清零 (drone_aerial 38→0, drone_flight 16→0); 双层布线大幅提升布通率。

| 板 | 绑定/未绑 | courtyard | 飞线 | 过孔 | err | 未连 | 结论 |
|----|---------|-----------|------|-----|-----|-----|------|
| ams1117_power          |  9/0  | 1→0 |  6/6  |  2 | 0 | 0 | **全净 ✓** |
| ch32v003_minimal       | 32/20 | 6→0 | 12/12 |  6 | 0 | 0 | **全净(已绑部分)✓** |
| led_indicator          | 20/0  | 1→0 | 15/15*| 9 | 0 | 0 | **全净 ✓** (grid0.1) |
| lora_sx1276_gateway    | 25/12 | 1→0 | 15/15 | 10 | 0 | 0 | **全净(已绑部分)✓** |
| motor_driver_dual      | 24/16 | 7→0 | 10/10 |  2 | 0 | 0 | **全净(已绑部分)✓** |
| nrf52840_ble5          | 34/34 | 6→0 | 10/10 |  2 | 0 | 0 | **全净(已绑部分)✓** |
| stm32g031_minimal      | 36/15 | 6→0 | 18/18 |  7 | 0 | 0 | **全净(已绑部分)✓** |
| usb_c_pd_trigger       | 20/12 | 0→0 | 13/13 |  4 | 0 | 0 | **全净(已绑部分)✓** |
| w5500_ethernet         | 28/22 | 0→0 | 15/15 |  4 | 0 | 0 | **全净(已绑部分)✓** |
| esp32_servo_wifi       | 20/20 | 6→0 | 14/14 |  7 | 12| 0 | 布线全净; 12 err 全是**封装焊盘钻孔 0.2<板规 0.3**(非布线) |
| rp2040_minimal         | 28/29 | 2→0 | 19/19 |  8 | 4 | 0 | 布通; 4 clearance(grid0.2 偏粗) |
| gd32f103_minimal       | 66/6  | 7→0 | 17/37 |  8 | 0 |20 | 0错但拥塞布不完(双层仍不够) |
| stm32f103c6_dot_matrix | 63/0  | 6→0 | 15/40 |  3 | 0 |25 | 0错但点阵极密·拥塞 |
| smartwatch_core        | 45/57 | 5→0 | 27/30 | 12 | 2 | 3 | 命名引脚未绑最多 |
| drone_flight_controller| 89/2  |16→0 | 47/69 | 16 | 9 |22 | 大板·边缘间距+拥塞 |
| drone_aerial_h743      |174/41 |38→0 | 56/115| 27 | 35|55 | 大板·边缘间距+拥塞 |

**8/16 板做到 0 error / 0 unconnected** (其中 6 块的"已绑部分"全净, 但仍有命名引脚未绑
= 见 GAP1, 严格说尚未"完整设计")。spread 全库 courtyard 清零, 双层把 led 11→15 等拥塞解开。

## 诚实诊断 (按杠杆排序, 为道日损)

**1. 头号瓶颈 — 命名引脚未绑 (netbind GAP). ◐ 已补 pinmap (保守版).**
DNA 网表用逻辑引脚名 (VCC/GND/MOSI/TX+/XTAL1...), 但 inline 出来的封装焊盘是
数字编号 (1..48). 二者无映射 → IC 的引脚全部 unbound。这是几乎每块板 `unbound>0`
的根因 (smartwatch 57, nrf52840 34, rp2040 29...)。
→ 已补: **`pinmap.resolve_named_pins`** —— 据 DNA 元件 value 在 KiCad 符号库认出符号
  (`SymbolIndex.search`), 取 `list_pins` 的 name↔number, 把命名引脚翻成脚号。**保守对齐**:
  只精确 + 高可信归一化匹配 (剥 ~{} 低有效装饰/分隔符/大小写; SCSn↔~{SCS}), 一个电源/地
  逻辑网扇出到符号同名多脚; **对不准的 (VCC↔VDD/AVDD 多电源轨、TX+↔差分名) 不猜, 留空且
  报候选** —— 接错电源即短路, 宁缺毋错。
→ 实测 w5500 (真 DRC): netbind 绑定 **28→43** (+15 脚), 暴露的真飞线 15→30 条 ——
  即原先"看着干净"实因 IC 脚未绑; 绑上后 router 当下布通 19/30 (0 错, 11 未连)。
  这把"假净"变"真活": **下一棒交给 router/拥塞**, 而非自欺。
> 仍是 ◐ 半解: GD32 等符号库无的器件认不出; 多电源轨/差分/XTAL 等名需人工/数据库别名表
> (`extra_aliases`)。本源数据在 KiCad, 已能取; 余下是名实对齐的判断, 留待更准 pinout 源。

**2. 单层拥塞 — 需双层+过孔 (route GAP). ✓ 已补 route_maze2.**
即便全绑定 (led_indicator), 单层 F.Cu 也常布不完 (11/15), 4 条飞线挤不下。
→ 已补: **双层避障布线 `route_maze2`** (A* 状态扩为 (row,col,layer); 顶层受阻则过孔
  下钻 B.Cu 绕行; 焊盘按层设障; 过孔以 via_halo 双层避让)。
→ 实测 led_indicator (grid=0.15): **15/15 飞线全布通、0 unconnected、0 布线错** (10 过孔),
  单层只能 11/15。下一拥塞瓶颈交给第二层化解, 上下相生。

**2b. 摆放质量 — courtyard 相叠 (placement GAP). ✓ 已补 placement.spread.**
led_indicator 双层布通后仍剩 1 个 `courtyards_overlap` (J1/J2 连接器外廓相叠): 非布线
能解, 是 DNA 把元件摆得 courtyard 物理相叠, 而板上还有大片空地。
→ 已补: **`spread_placement`** —— 读每个元件**真实 F.CrtYd courtyard 几何**(非焊盘外接,
  连接器 courtyard 远大于焊盘), 凡两件外廓相侵, 沿最浅穿插轴互推开各让一半, 迭代至
  互不相侵且不越板框。
→ 实测 led_indicator (grid=0.1, 全链路 inline→**spread**→netbind→route_maze2→真 DRC):
  courtyards_overlap 1→0, **15/15 飞线、0 error、0 unconnected** = 第二块全净可制造板
  (且这块用齐了 spread+双层+性能三件新工具)。

> 注: `courtyard_bbox` 必须取真实 F.CrtYd 图元 (会按 90°/270° 旋转变换), 焊盘外接框会
> 严重低估连接器等元件的占地 (J1 焊盘宽 1.7 但 courtyard 宽 3.54) —— 实践教训, 已修。

**2c. 布通率 — 密板布不完 (route GAP). ☐ 真瓶颈 = 细间距引脚逃逸/扇出 (escape/fanout).**
pinmap 绑上 IC 真引脚后飞线变密 (w5500 15→30), 贪心逐边 A* 布不完
(w5500 19/30, gd32 17/37, dot_matrix 15/40)。**两轮诚实实验把病根钉死**:
- 试 **短边先布** (重排序): 几无改善 (w5500 19→18, gd32 17→16) 且 led 引入 3 clearance → 撤回。
- 试 **撕线重布 rip-up-reroute** (受阻边拆挡路他网线、净增才接受, plan-then-emit 重构):
  w5500/gd32/dot_matrix **0 改善**, drone 仅 +1 边却慢 4× (33s→139s) → 撤回。
- **病根实测确认**: W5500 LQFP-48 **0.5mm 间距**, 焊盘宽 0.3 → 相邻焊盘间隙仅 **0.2mm**,
  而 0.25mm 走线 + 两侧 0.2mm 间距需 **0.65mm** 通道 —— **物理穿不过**。grid 0.1 也无改善
  (几何死墙, 非分辨率)。这不是布线策略问题, 是 **细间距逃逸**: N 个 0.5 间距引脚无法在同层
  以 0.65 间距同时引出, 须**每隔一脚打扇出过孔**下到 B.Cu 分流 (BGA/QFP escape routing)。
→ **第三轮实验 = 正结果**: 既然病灶是"0.65 通道穿不过 0.2 间隙", 那就**收窄走线规则**到
  fab 实可造的 **0.15mm 线 / 0.15mm 间距** (并行节距 0.3 < 0.5 引脚间距, 逃逸得开;
  JLCPCB 标准双层支持到 0.127/0.127)。实测 (真 DRC, grid=0.1):
  **w5500 19/30 → 25/30** (0 错, 未连 11→5), led/ams 仍全净 (无回归)。grid 0.1 无改善 = 几何墙,
  收窄规则才是钥匙 —— 病灶找对, 一击中的。
→ 已把 `--width/--clearance` 接出 design_loop, 设计时按器件间距选 fab 规则 (细间距用 0.15/0.15)。
> 为道日损: 两个负结果把"布不完"从模糊猜测收敛成精确病灶 (逃逸几何), 第三轮据此一击即中。
> 余下 (w5500 仍 5 未连、gd32/dot_matrix 更密) 需真正的 **per-pad 扇出过孔** 进一步分流, 留待专门工具。
> 知止不殆 —— 先得其要, 再图其全。

**3. 性能 — 大板超时 (route GAP). ✓ 已解决.**
`blocked_for` 曾每格扫全部焊盘 = O(格×焊盘); 大板 (drone 43 元件, 1000×900 格) 跑爆。
→ 已补: **障碍栅格预栅格化** (一次性把焊盘光环烧进 `owner` 表, A* 查障 O(1)) +
  **A* 节点上限** (探索超限即知止, 记为未布通而非死等)。
→ 实测: drone_aerial 23s / drone_flight 32s / dot_matrix 11s (原皆 >90s 超时), 全库 16 板 ≈2 分钟跑完。

## 已被证明可用的部分
- `ams1117_power`: 全数字引脚 → 绑定 9/9、布线 6/6、**KiCad DRC 0 错 0 未连** = 真可制造。
- `usb_c_pd_trigger` / `w5500_ethernet`: 已绑定子网 **15/15、13/13 全布通且 0 错** —
  证明布线器本身稳, 瓶颈在绑定 (命名引脚), 不在布线。

---

## 本源纠偏 · 自动布线改用 KiCAD 原生 DSN/SES 桥 + 生态布线器 Freerouting (✓ 决定性)

> 用户再锚定本源:「充分利用 kiCAD 一切资源, 而非从零开始；像深用 VS Code 底层一样深用 KiCAD」。
> 此前我那套 route_maze/route_maze2 (从零造 A*) 正是「从零开始」之误。**为道日损, 弃之。**

**摸清本源 (VM 实测 KiCAD 9.0.9 原生面):**
- `pcbnew` Python 模块 = KiCAD 真引擎: `ExportSpecctraDSN` / `ImportSpecctraSES` (与生态布线器对接的**本来通道**)、
  `GetConnectivity()` (真 ratsnest)、`GetAllNetClasses()` / `GetDesignSettings()` (真设计规则)、`PCB_TRACK`/`PCB_VIA`。
- `kicad-cli pcb`: drc / export(Gerber·钻孔·贴片) / render —— 制造产出本源齐全。
- 生态自动布线器 **Freerouting v2.2.4** (需 JRE25): 经 pcbnew 原生 DSN/SES 往返即可无头驱动。

**本源布线链路** (取代自研 A*): `bound .kicad_pcb` ──pcbnew ExportSpecctraDSN──▶ `.dsn`
──Freerouting(无头, `-Djava.awt.headless=true`)──▶ `.ses` ──pcbnew ImportSpecctraSES──▶ 真走线落板 ──kicad-cli 真 DRC。

**自研 A* vs 本源 Freerouting (同板, KiCad 真 DRC 为准):**
| 板 | 自研 A* | 本源 Freerouting |
|----|--------|------------------|
| w5500_ethernet (30 网) | 25/30 (5 未连) | **0 未连, 129 轨, 0 错** |
| gd32f103_minimal (37 网) | 17/37 | **0 未连, 243 轨, 0 错** |
| stm32f103c6_dot_matrix | 布不完 | **0 未连, 248 轨, 0 错** |
本源即在, 何须重造 —— 成熟布线器的 rip-up/shove 几秒解决了我两轮实验都啃不动的密板。

**全库 16 板审计 (spread + pinmap + 本源 freerouting, 逐板真 DRC):**
- **9/16 板 0 错且全导通** (ams/ch32v003/gd32/led/lora/nrf52840/dot_matrix/usb_c_pd/w5500)。
- 余下诚实归因 (**非布线器问题**): ① 命名引脚未绑 (pinmap GAP1: nrf52840 37 脚全未绑、smartwatch 55 未绑);
  ② 大板 courtyards_overlap (placement, drone 系列); ③ copper_edge_clearance (FR 未读板框 keepout, 需在 DSN 设边距规则);
  ④ esp32 drill_out_of_range 12 处 = 封装自带 0.2mm 钻孔 < 板规 (预存数据问题)。

**一个真 bug 已解 (诚实记录):** Freerouting 贴 DRC 间距边界走线, 因 ~1.8µm 几何取整被判 1 处 clearance 违例。
修法: 导出 DSN 前把网类间距临时加 **0.005mm** 余量 (仅够覆盖取整)。注意余量过大 (试过 0.05) 会挤垮密板布通率
(w5500 120→41 轨), 故取小余量 —— 扫描 0.003/0.005/0.01 均使 ams+w5500 双双 0 错全通。

**摆放板缘留白 bug 已修 (✓ +1 净板):** spread_placement 的 `clamp` 原只在"两件相叠"分支里调用,
故孤立越界/贴板缘却不与谁相叠的元件永不被拉回 → copper_edge_clearance。修法: 迭代前先对**所有**元件
无条件夹回板框内 (含 board_margin 留白)。smartwatch_core: 2 处 copper_edge_clearance → **0 错 0 未连** (全净)。
全库本源审计 **9→10/16 板 0 错且全导通**。(drone_aerial 174 元件挤在过小板框, 夹回后更拥挤 = 板尺寸问题, 另议。)

---

## 本源迭代 A→B→C→D (闭环实践, 全程 KiCAD 真 DRC 为准)

亲手把工具补到链路上, 再跑遍全库量化净益。基线 10/16 → **现 12/16 板 0 错且全导通**,
余 4 板皆诚实定性 (非本轮 A/B/C/D 所能解, 各有本源根因)。

### A. GND 地平面覆铜 + 过孔缝合 (`copper_pour.py` / `_pour_helper.py`)
本源: pcbnew 原生 ZONE/ZONE_FILLER 双层铺 GND + 间距校验过孔缝合 (SOLID 连接, 非
THERMAL, 免 starved_thermal)。**stm32g031: 0错/1未连 → 0/0 (✓ 全净)**。诚实发现:
rp2040/motor 余 1–2 个 GND 焊盘是细间距 QFN 引脚, 与相邻信号脚间隙≈0 (实测 -0.037mm),
0.3mm 过孔几何上进不去 —— 摆放/封装约束, 非工具缺陷 (via-in-pad 微孔违 0.3mm 最小钻规, 不强改)。

### B. 命名引脚保守别名 (`pinmap.py`: MPN_SYMBOL_ALIASES / PIN_NAME_ALIASES)
本源: 料号→KiCAD 符号别名 + 引脚名同义归一, **仅收逐个核对无误者, 错则宁缺** (接错即短路)。
摸到更深根因: DNA 用厂商料号 (E73-2G4M08S1C / QMI8658C / MAX30102EFD+T), 且其中心芯片
**KiCAD 根本无对应符号** (E73 模块只有 nRF52832 的 M04S 变体, 脚位不同不可挪用); 另有数颗
(TP4056/MAX30102/QMI8658) 在板上**未被 inline (0 焊盘)** = 另一条 inline 覆盖缺口。
故安全可绑面很小 (PCF8563 料号别名 + VDD↔VCC/地同义)。已验证 nrf52840/smartwatch **无回归**。
诚实结论: 绑更多中心芯片需用户提供 pinout 或反推符号, 不猜接电源。

### C. 板框自适应放大 + 圆形外廓解析修正 (`placement.py`: fit_placement / autosize_board)
本源: 自适应 —— 先 spread, 仍挤则等比放大 Edge.Cuts 板框再 spread, 直到无叠或知止;
本就宽裕的板**不动分毫** (无为)。**并揪出一个 courtyard 解析真 bug**: 元件圆形外廓
(`fp_circle`) 旧解析只取 center/end 两点 → 退化成零高度线框 → spread 永不分离它, 而
KiCAD 真 DRC 按真圆判叠。修法: fp_circle 按 圆心±半径 取真 bbox。
**drone_flight: 1错(courtyard) → 0错; drone_aerial: 24错 → 4错 (courtyard 全消)**。
余 drone_aerial 4 clearance = J2 USB-C 连接器 A/B 行镜像焊盘未绑而重叠 (binding 缺口, 同 B);
drone_flight 余 1 未连 = freerouting 把 U5.VCC_3V3 落到离焊盘 0.99mm 处 (布线器末段缺口)。

### D. 可投产设计规则 + 外露地焊盘全绑 (`design_rules.py` / netbind 修正)
两处本源修正合力解 esp32:
1. **netbind 同号焊盘全绑** (`footprint.pads_by_number`): ESP32 外露地焊盘 EP (号 "39") 带
   12 个散热过孔皆同号, 旧 `pad_by_number` 只绑首个 → 余 11 个空网被 GND 走线短路 (5 shorting)。
   改为同号全绑 → 短路全消。
2. **最小钻规对齐** (`set_fab_rules`): KiCAD 默认最小通孔钻 0.3mm, 但 ESP32-WROOM 模块封装
   自带 0.2mm 散热过孔 (主流厂支持)。与其篡改 KiCAD 自带封装真实数据, 不如把板级规则对齐到
   器件与产线真实能力 → 12 个 drill_out_of_range 全消。**esp32: 17错 → 0错/0未连 (✓ 全净)**。

### 余 4 板诚实定性 (本轮范围外, 各有本源根因)
| 板 | 状态 | 根因 (诚实) |
|----|------|------|
| drone_flight | 0错/1未连 | freerouting 末段把 VCC_3V3 落到离焊盘 0.99mm (布线器缺口) |
| drone_aerial | 4错/1未连 | J2 USB-C 镜像焊盘未绑而重叠 (连接器 binding 缺口) |
| motor | 0错/1未连 | 细间距 QFN GND 焊盘几何受困 (-0.037mm, 过孔进不去) |
| rp2040 | 0错/2未连 | 同上, 细间距 QFN GND 几何受困 |

> 为道日损: 把"看似布线/摆放问题"逐一证伪、收敛到真实根因 (连接器/中心芯片符号缺失、
> 封装 inline 覆盖、细间距几何墙)。这些非 A/B/C/D 所能强解, 强解即背道 —— 知止不殆。
