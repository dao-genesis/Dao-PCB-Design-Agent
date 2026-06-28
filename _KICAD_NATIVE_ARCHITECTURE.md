# 本源架构 · 深用 KiCAD 一切, 而非从零重造

> 道理 (用户锚定): 像高斯深用 VS Code 底层、Cursor 立于 VS Code 之上, 我们**深用 KiCAD 一切本源**,
> 在其上做 PCB 全流程闭环 —— 而**不从零重造它已有的轮子**。为学者日益, 为道者日损。

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
