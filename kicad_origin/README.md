# kicad_origin — KiCad 本源逆向 · 一劳永逸

> "道生一, 一生二, 二生三, 三生万物."  
> "天下万物生于有, 有生于无."

本包是 KiCad 工程数据**纯 Python 本源逆向**: 不依赖 KiCad 安装, 不依赖 pcbnew SWIG, 不依赖第三方包, 即可读写 / 镜像 / 索引 / 出图全部 KiCad 资源.

---

## 一、为何而生

| 痛点 | 解 |
|------|---|
| `pcb_brain/kicad_native.py` 991 行混合纯 Python + 子进程桥, 难独立 | 抽出纯 Python 部分到 `origin/` |
| `schematic_dao/_kicad_lib.py` 强依赖 `D:\KICAD\share\kicad\symbols\` 路径 | 镜像至本工作区, 路径自由 |
| 三处重复 KiCad 路径探测 (bootstrap / kicad_native / _kicad_lib) | 统一至 `origin/env.py` |
| 工作区无 KiCad 副本, 笔记本/CI 流水线断 | `python -m kicad_origin mirror sync` 一劳永逸 |
| 不同 KiCad 版本格式微差异 (v6/v7/v8/v9) | `origin/version.py` 自动适配 |

---

## 二、立即上手

### 安装 (零依赖, 直接 import)
```python
import sys
sys.path.insert(0, r"e:\道\道生一\一生二\PCB设计")
import kicad_origin
print(kicad_origin.__version__)
```

### 拉镜像 (首次, ~5 分钟)
```bash
python -m kicad_origin mirror sync           # symbols + footprints (~250MB)
python -m kicad_origin mirror sync --full    # +3D models (~2GB)
```

### 解析 .kicad_pcb (无 KiCad 也行)
```python
from kicad_origin import parse_file, find_all

tree = parse_file("PCB设计/pcb_brain/output/esp32_servo_wifi/esp32_servo_wifi.kicad_pcb")
print(f"{len(find_all(tree, 'footprint'))} 封装")
print(f"{len(find_all(tree, 'net'))} 网络")
```

### 索引查询
```python
from kicad_origin.lib import SymbolIndex, FootprintIndex

# 模糊搜 STM32F103
for r in SymbolIndex.search("STM32F103", limit=5):
    print(f"{r['lib']}:{r['name']}")

# 精准/模糊匹配封装
fp = FootprintIndex.smart_match("Package_QFP", "LQFP-48_7x7mm_P0.5mm")
```

---

## 三、架构 · 五层

```
┌─────────────────────────────────────────────────────────────────┐
│ Layer 4  万物·app/      CLI · MCP · pcbnew_compat               │
├─────────────────────────────────────────────────────────────────┤
│ Layer 3  三·engine/     DRC · Gerber · Excellon · Specctra · ODB │
├─────────────────────────────────────────────────────────────────┤
│ Layer 2  二·pcb/        Board · Footprint · Track · Geometry    │
├─────────────────────────────────────────────────────────────────┤
│ Layer 1  一·lib/        Mirror Sync · Symbol/Footprint Index    │
├─────────────────────────────────────────────────────────────────┤
│ Layer 0  道·origin/     SExpr · Unit · Version · Env            │
└─────────────────────────────────────────────────────────────────┘
       依赖只能向下, 不可平级或跨层向上.
```

详见 [`_AGENTS.md`](./_AGENTS.md) 与 [`KICAD_REVERSE_BIBLE.md`](./KICAD_REVERSE_BIBLE.md).

---

## 四、CLI 速查

```bash
python -m kicad_origin                    # 默认 = status
python -m kicad_origin status             # 本源状态自检
python -m kicad_origin mirror sync        # 拉镜像 (sym+fp)
python -m kicad_origin mirror sync --full # 拉全部 (sym+fp+3D+templates)
python -m kicad_origin mirror status      # 镜像状态
python -m kicad_origin index build        # 重建索引
python -m kicad_origin parse <file>       # 解析 KiCad 文件
python -m kicad_origin search sym <q>     # 搜符号
python -m kicad_origin search fp <q>      # 搜封装
python -m kicad_origin env                # KiCad 安装探测
```

---

## 五、与现存系统的关系

| 旧模块 | 关系 | 行为 |
|--------|------|------|
| `pcb_brain/kicad_native.py` | shim → origin | 老 API 不变, 内部委托 |
| `schematic_dao/_kicad_lib.py` | shim → lib.symbol_reader | 老 API 不变, 内部委托 |
| `pcb_brain/kicad_arm.py` | 高阶层, 不动 | 内部可改用 origin |
| `pcb_brain/_pcb_bootstrap.py` | 不动 | env 探测仍归此 |

**渐进迁移**, 不一刀切.

---

## 六、本源的本源 (元说明)

代码量上限: **5,000 行** (含注释).  
依赖项数: **0** (仅 Python 标准库).  
覆盖文件类型: `.kicad_pcb` `.kicad_sch` `.kicad_sym` `.kicad_mod` `.kicad_pro` `.kicad_wks` `.kicad_dru` `.gbr` `.drl` `.xnc` `.dsn` `.ses` `.ipc` `.ipc356` `.odb`.  
KiCad 版本: 6/7/8/9 全兼容.  
平台: Windows / Linux / macOS.  

> "为学日益, 为道日损. 损之又损, 以至于无为. 无为而无不为."

---

_位置_: `PCB设计/kicad_origin/`  
_道纪_: [`_AGENTS.md`](./_AGENTS.md)  
_逆向手册_: [`KICAD_REVERSE_BIBLE.md`](./KICAD_REVERSE_BIBLE.md)
