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
