# kicad_origin — Agent 道纪

> **一句话**: 任何 PCB Agent 在任何机器上, 不依赖 KiCad 安装, 即可读写 / 镜像 / 索引 / 出图 KiCad 全部资源.
>
> **入口**: `from kicad_origin import SExpr, mirror_sync` 或 `python -m kicad_origin`
>
> **本源**: `kicad_origin/origin/` — 无中生有, S-expr 语义之根.

---

## 一、何时用本包

| 情景 | 用 kicad_origin | 不用 |
|------|----------------|------|
| 本机无 KiCad, 仍要读写 .kicad_pcb | ✅ 唯一选择 | — |
| 镜像 KiCad 官方库到工作区 | ✅ `mirror sync` | — |
| 在 pcb_brain 流水线中需要纯 Python 解析 | ✅ 性能/无依赖 | — |
| 已有 D:\KICAD, 仅做索引查询 | ✅ 仍可工作 | 也可走 pcbnew |
| 需要 pcbnew 1211 API (DRC/Gerber 等) | ⚠️ 部分实现 | 走 `kicad_native.py` 子进程桥 |

**简言**: 任何"不需要运行 KiCad 主程序"的 PCB 工作, 优先 kicad_origin.

---

## 二、五层架构 (与《道德经》对应)

```
┌──────────────────────────────────────────────────────────────────────┐
│  live/            五脉   Layer 5   IPC / SWIG / CLI / GUI / FILE      │
│                                    LiveKiCad 直连本源 · 无为而无不为   │
├──────────────────────────────────────────────────────────────────────┤
│  万物·app/        Layer 4   CLI / MCP / pcbnew_compat                │
│                             "三生万物"                                │
├──────────────────────────────────────────────────────────────────────┤
│  三·engine/       Layer 3   DRC / Gerber / Excellon / Specctra      │
│                             "二生三"                                  │
├──────────────────────────────────────────────────────────────────────┤
│  二·pcb/          Layer 2   Board / Footprint / Track / Geometry    │
│                             "一生二"                                  │
├──────────────────────────────────────────────────────────────────────┤
│  一·lib/          Layer 1   Mirror Sync + Symbol/Footprint Index    │
│                             "道生一"                                  │
├──────────────────────────────────────────────────────────────────────┤
│  道·origin/       Layer 0   SExpr / Unit / Version / Env            │
│                             "天下万物生于有, 有生于无"                  │
└──────────────────────────────────────────────────────────────────────┘
```

> **Layer 5 (live/)** 是 KiCad 一切对外接口的统一门面.
> 详见 [`live/_AGENTS.md`](./live/_AGENTS.md).
> 一句话: `python -m kicad_origin do all <project>` 即一键全境贯通.

**每层依赖只能向下**, 不可平级或跨层向上.

---

## 三、Agent 任务速查

### 任务 A: 解析任意 KiCad 文件 (本机无 KiCad 也能用)
```python
from kicad_origin import parse_file, find_all, find_first

tree = parse_file("project.kicad_pcb")
fps = find_all(tree, "footprint")     # 全部封装
nets = find_all(tree, "net")          # 全部网络
print(f"{len(fps)} 封装, {len(nets)} 网络")
```

### 任务 B: 镜像 KiCad 官方库到工作区
```bash
# 默认 symbols + footprints (~250 MB, ~5 分钟, 一劳永逸)
python -m kicad_origin mirror sync

# 含 3D 模型 (~2 GB, ~30 分钟, 完全自洽)
python -m kicad_origin mirror sync --scope=full

# 仅 symbols (轻量, ~50 MB)
python -m kicad_origin mirror sync --scope=symbols
```

### 任务 C: 全量索引并搜索 (无需 KiCad 安装)
```python
from kicad_origin.lib import SymbolIndex, FootprintIndex

SymbolIndex.build()             # 自动用镜像副本, 没有则尝试 D:\KICAD
matches = SymbolIndex.search("STM32F103")      # 模糊搜
print(matches[:5])

FootprintIndex.build()
fp_path = FootprintIndex.smart_match("Package_QFP", "LQFP-48_7x7mm_P0.5mm")
```

### 任务 D: 替代 schematic_dao/_kicad_lib.py 的功能 (无 KiCad 也工作)
```python
from kicad_origin.lib import extract_symbol_block, get_pin_positions

# 原 schematic_dao._kicad_lib 等价 API, 但优先读镜像副本
block = extract_symbol_block("Device:R")
pins = get_pin_positions("MCU_ST_STM32F1:STM32F103C8Tx")
```

### 任务 E: 在脚本里检测有无 KiCad
```python
from kicad_origin import has_kicad_install, detect_kicad

if has_kicad_install():
    info = detect_kicad()       # {root, bin, version, python, ...}
    print(f"KiCad {info['version']} @ {info['root']}")
else:
    print("使用纯 Python 回退路径 (mirror + origin)")
```

### 任务 F: 直连运行中的 KiCad (Layer 5 live)
```python
from kicad_origin.live import LiveKiCad

k = LiveKiCad()
print(k.info())                      # {channels: {ipc, swig, cli, gui, file}, ...}
k.open("path/to/proj.kicad_pro")     # GUI 打开
k.erc(sch_path, "erc.json")          # CLI ERC
k.export_gerbers(pcb_path, "gerbers/")
k.snapshot("kicad.png")              # GUI 截图

# IPC 实时操作 (需 enable-ipc + 重启)
k.enable_ipc()
# ... 重启 KiCad ...
k.ipc_run_action("common.Control.zoomFitScreen")
print(k.ipc_get_board_summary())     # {footprints, nets, name}
```

CLI:
```bash
python -m kicad_origin status                          # 五脉状态
python -m kicad_origin enable-ipc --restart            # 启用 IPC + 重启
python -m kicad_origin do all warehouse_logistics_vehicle  # 全闭环
```

---

## 四、与现有模块的关系

| 旧模块 | 新位置 | 行动 |
|--------|--------|------|
| `pcb_brain/kicad_native.py` 中 SExprParser | `kicad_origin/origin/sexpr.py` | 老模块 import shim, API 不变 |
| `pcb_brain/kicad_native.py` 中 FootprintIndex/SymbolIndex | `kicad_origin/lib/index.py` | 同上 |
| `pcb_brain/kicad_native.py` 中 _find_kicad_root | `kicad_origin/origin/env.py` | 同上 |
| `schematic_dao/_kicad_lib.py` | `kicad_origin/lib/symbol_reader.py` (TODO) | shim 委托 |
| `schematic_dao/render_kicad.py` | 不变 (上层应用) | — |
| `pcb_brain/kicad_arm.py` 四重协议 | 不变 (高阶编排层) | 内部可调用 origin |

**原则**: 新本源是**底层**, 旧代码继续工作, 仅 import 路径透明改写.

---

## 五、镜像策略 (一劳永逸)

镜像位置: `kicad_origin/lib/_mirror/`
```
_mirror/
  ├── symbols/        ~50 MB    140 lib × .kicad_sym         必拉
  ├── footprints/     ~200 MB   150 lib × .pretty/*.kicad_mod  必拉
  ├── 3dmodels/       ~2 GB     .step + .wrl                 可选
  ├── templates/      ~5 MB     工程模板                       附带
  └── _meta.json                同步时间, 版本, 校验
```

**镜像源**: GitLab https://gitlab.com/kicad/libraries/
- kicad-symbols
- kicad-footprints
- kicad-packages3D
- kicad-templates

**增量同步**: 默认 `git fetch --depth=1`, 仅取最新, 不带 history.

---

## 六、勿碰禁区

- **勿改 `origin/sexpr.py` 的 `Symbol` / `parse` API** — 全包之根
- **勿在 `origin/` 引入任何第三方包依赖** — 道之纯性
- **勿删 `lib/_mirror/` 已下载副本** — 浪费用户带宽
- **勿在 `app/pcbnew_compat.py` 里写 hack** — 兼容层只做形似神似

---

## 七、回归基线

```bash
python -m kicad_origin status        # 本源状态自检
python -m kicad_origin parse e:/道/道生一/一生二/PCB设计/pcb_brain/output/<某模板>/<某>.kicad_pcb
```

**目标**: status 报告 origin 4/4 ✅, lib 2/2 ✅ (镜像未拉时为 ⚠️), 解析 0 错误.

---

_位置_: `PCB设计/kicad_origin/`
_最后更新_: 2026-04-21
_道纪_: 万物作焉而不辞, 生而不有, 为而不恃, 功成而弗居.
