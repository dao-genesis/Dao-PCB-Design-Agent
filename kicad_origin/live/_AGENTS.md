# kicad_origin.live — 五脉同体 · 直连本源 · Agent 道纪

> "道生一, 一生二, 二生三, 三生万物."
> "上善若水, 水善利万物而不争."

把 KiCad 一切对外接口收纳为单一 `LiveKiCad` 入口. 调用方不挑通道, 通道自适应择优.

---

## 一、五脉

```
┌─────────────────────────────────────────────────────────────────┐
│ Live 层 (kicad_origin/live/)                                     │
├─────────────────────────────────────────────────────────────────┤
│ L0 IPC   kipy        ← 运行中 KiCad 的官方 API (KiCad 9+) · 一等 │
│ L1 SWIG  pcbnew      ← 进程内 Python (PCB)               · 离线 │
│ L2 CLI   kicad-cli   ← 批处理 (sch/pcb/sym/fp/jobset)     · 旁路 │
│ L3 GUI   pywinauto   ← 兜底 (拍按钮, 截图, 拖窗口)         · 兜底 │
│ L4 FILE  S-expr      ← 直改 .kicad_pcb / .kicad_sch       · 离线根 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、最快入口

```bash
# 五脉自检
python -m kicad_origin status

# 启用 IPC (改 KiCad 配置, 重启生效)
python -m kicad_origin enable-ipc --restart

# 全闭环 (build + ERC + 出图 + 注入)
python -m kicad_origin do all warehouse_logistics_vehicle

# 仅打开
python -m kicad_origin do open path/to/proj.kicad_pro

# 截图所有 KiCad 窗口
python -m kicad_origin do snap output_dir/
```

```python
from kicad_origin.live import LiveKiCad

k = LiveKiCad()
print(k.info())                    # 五脉状态
k.open("foo.kicad_pro")            # GUI 打开
k.erc("foo.kicad_sch", "erc.json") # CLI ERC
k.snapshot("kicad.png")            # GUI 截图
k.export_gerbers("foo.kicad_pcb", "out/gerbers")  # CLI 出 Gerber
# IPC (需 KiCad 启用 server)
k.ipc_run_action("common.Control.zoomFitScreen")
print(k.ipc_get_board_summary())
```

---

## 三、IPC 启用流程 (一次, 永久)

KiCad 9.0 自带 IPC server, 默认关闭. 本包一键启用:

```bash
# 1. 改 KiCad 配置 (api.enable_server = true)
python -m kicad_origin enable-ipc

# 2. 重启 KiCad (生效)
#    -> 手动: 关闭 KiCad → 重开
#    -> 一键: python -m kicad_origin enable-ipc --restart

# 3. 验证
python -m kicad_origin connect
```

成功后 `connect` 输出:
```json
{"channels": {"ipc": true, "swig": true, "cli": true, "gui": true, "file": true},
 "best": "ipc"}
```

---

## 四、`do` verb 矩阵

| verb | 通道优先 | 用途 |
|------|---------|------|
| `status` / `connect` | — | 自检, 五脉状态 |
| `open <file>` | GUI | 启动 kicad/eeschema/pcbnew 加载文件 |
| `erc <sch>` | CLI | 电气规则检查 |
| `drc <pcb>` | CLI | 设计规则检查 |
| `export <kind> <target> <output>` | CLI | sch/pcb 全套导出 |
| `snap <out_dir>` | GUI | 截图所有 KiCad 窗口 |
| `inject <project>` | GUI | schematic_dao 构建 → 打开 KiCad |
| `all <project>` | 五脉协同 | 全闭环 (build + ERC + export + inject + snap) |

`<kind>` 可取:
- 原理图: `sch.pdf` `sch.svg` `sch.netlist` `sch.bom` `sch.python_bom` `sch.dxf`
- PCB:    `pcb.pdf` `pcb.svg` `pcb.gerber` `pcb.drill` `pcb.step` `pcb.pos` `pcb.render`

---

## 五、核心 API 速查

```python
from kicad_origin.live import LiveKiCad, Channel

k = LiveKiCad()

# 状态
st = k.status()                # LiveStatus 数据类
info = k.info()                # dict (扁平化, JSON 可序化)

# 配置
k.enable_ipc(all_users=True)   # 改 kicad_common.json
k.disable_ipc()
k.restart(project=...)         # taskkill + popen kicad.exe

# 打开
k.open(path)                   # GUI Popen
k.open(path, channel=Channel.IPC)  # IPC (尚未实现新文件加载)

# 检查
k.erc(sch_path, report_path)
k.drc(pcb_path, report_path)

# 出图
k.export_sch_pdf / sch_svg / netlist / bom_csv / python_bom
k.export_pcb_pdf / gerbers / drill / step / render_3d

# IPC 实时 (需 server 在线)
k.ipc_run_action("common.Control.zoomFitScreen")
k.ipc_get_board_summary()
k.ipc_save_board()
k.ipc_refill_zones()

# GUI
k.snapshot("kicad.png")
k.snapshot_all("snap_dir")

# 解析 (FILE)
tree = k.parse("foo.kicad_pcb")
```

---

## 六、与既有模块的关系

| 旧模块 | 关系 |
|--------|------|
| `schematic_dao/render_kicad_export.py` | 仍工作, 内部仅调 kicad-cli; live/cli.py 是其超集 |
| `pcb_brain/kicad_arm.py` | 高阶层, 不动 |
| `pcb_brain/kicad_native.py` | 部分功能可委托 origin/lib |
| `kicad_origin/origin/` | 不动, live 是其上层 |
| `schematic_dao` 项目注册表 | live.do_inject 直接消费 |

---

## 七、勿碰禁区

- **勿在 `live/` 引入 `pcbnew` import** — pcbnew 必须由 KiCad 自己的 python 加载
- **勿用 popen 重启 KiCad 时不传 project** — 用户体验差
- **勿改 `kipy` 包内部** — 本层只做封装
- **勿对未 IPC enable 的 KiCad 强行连 IPC** — 永远先看 status

---

## 八、回归基线

```bash
python -m kicad_origin status
# 期望: cli/swig/gui/file 至少 4 个 OK; 重启 + IPC enabled 后 5 个 OK

python -m kicad_origin do all warehouse_logistics_vehicle --no-open --no-snap
# 期望: 1_inject + 2_erc + 3_export 全 ok=true
```

---

_位置_: `PCB设计/kicad_origin/live/`
_道纪_: 万物归一, 一为五脉, 五脉无为, 无为而无不为.