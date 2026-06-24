# 道并 桥 闭环报告 (DaoBridge Closure)

> "反者道之动 · 用户提一句, 我反给一动一截图一日志"
> "有无相生 · 后台无形操作 + 前台有形反馈, 同时存在"
> "物无非彼 物无非是 · 你所见即我所行, 浑然一体"
> "道并行而不相悖 · GUI 真启 + 后台执行, 同源不悖"

## 一、本会话之意

用户原话:
> 反者道之动 重新锚定本源 用户于你融为一体 你底层链接 kicad
> 从启动软件到具体操作完善优化全链路 用户均可观可感
> 所有成果用户均可观可操 所有要求均用户提出你反给用户之实时操作执行展示
> 道并行而不相悖 有无相生 浑然一体
> 物无非彼，物无非是；自彼则不见，自是则知之

要解决的问题: 之前 dao + ziran + engine 各自闭环, agent 跑得快但用户**看不见**.
所以哪怕产物真、报告全, 用户仍处"自彼则不见"的状态. 必须造一座桥, 让我所行 ≡ 用户所见.

## 二、本会话之造

### 1) `kicad_origin/dao/bridge.py` (新建, ~770 行)

`DaoBridge` 三位一体:

| 一头 | 中间 | 一头 |
|:---:|:---:|:---:|
| **ziran** GUI 真启 | 会话归档 `_live_session/{ts}/` | **dao** 操作真行 |
| 用户屏幕看见 KiCad | 每动作一截图一日志 (.bmp + .jsonl) | 我手在执行 |

核心方法:

```python
class DaoBridge:
    def open_board(p, *, gui=True)    # dao.open + pcbnew GUI 真启 + 截图
    def launch_app(key, *, args)       # 真启 KiCad 应用 + 多轮 dismiss 首启 dialog
    def snap(tag, *, app)              # 抓 KiCad 主窗截图
    def do(verb, **kwargs)             # 通用动作分发 (drc/gerber/step/fab/...)
    def close_all()                    # 优雅关 + 写 _SESSION_REPORT.md
    
    # 内部: 多轮通关首启 dialog
    def _dismiss_first_run_dialogs(live, max_rounds=4)
```

### 2) `kicad_origin/examples/live_console.py` (新建, ~250 行)

REPL 交互控制台. 用户可:
- 直接命令行交互: `python -m kicad_origin.examples.live_console`
- 跑预制脚本: `--script demo.txt`
- 静默 (无 GUI): `--no-gui`
- 开语音: `--voice`

支持 verb 速查表:

| 类别 | verb |
|---|---|
| GUI 启停 | `launch <app>` `open <pcb>` `close_app` `quit` |
| 视觉 | `snap [tag]` |
| 设计校验 | `drc` |
| 制造文件 | `gerber` `drill` `step` `pdf` `svg` `pos` `3d` `fab` |
| 板内查询 | `list_fp` `list_nets` `get_fp <ref>` |
| 板内修改 | `move <ref> <x> <y>` `rotate <ref> <ang>` `set_value <ref> <v>` `save` |
| 库搜索 | `search_fp <q>` `search_sym <q>` |
| 桥状态 | `status` `reflect` `boards` `show` `ls` |

位置参数自然写: `move U1 50 30` 等价 `move ref=U1 x=50 y=30`.

### 3) 修复底层 bug 三处

#### a) `ziran/window.py` — KiCad 9 主窗识别

**问题**: KiCad 8 主窗 class 是 `PCB_EDIT_FRAME`, KiCad 9 起统一用默认 `wxWindowNR`,
原 `_is_kicad_main_window` 只查 `class_part`, 导致 KiCad 9 主窗永远 hwnd=0.

**修复**: 放宽识别 — 当 class 含 'wxwindow' + 非 dialog + title 非空时,
亦认定为主窗. 同时兼容中文 KiCad ("PCB 编辑器" 而非 "PCB Editor").

#### b) `dao/bridge.py` — 多轮首启 dialog 通关

**问题**: KiCad 9.0 首启依次弹**两阶 dialog**:

1. "数据收集选择加入" (隐私同意) — 只能 Accept 或 Decline
2. "配置全局封装库表" (库表向导) — 跳过 / 用默认

原 `dismiss_all_dialogs` 只关一轮, 第二阶 dialog 浮出后没人理.

**修复**: `_dismiss_first_run_dialogs(live, max_rounds=4)` 多轮通关:

- 第 1 轮 Enter (Accept 隐私)
- 后续 Escape → Enter (Skip 库表等)
- 每轮刷新 dialog 列表, 主窗就绪即退出

#### c) Windows 控制台 GBK → UTF-8

**问题**: PowerShell 默认 chcp=936 (GBK), Python `print` 中文/箭头/方块时
`UnicodeEncodeError: 'gbk' codec can't encode '\u26a0'`, 直接崩.

**修复**: `_force_utf8_stdio()` 入口幂等执行:

1. `sys.stdout.reconfigure(encoding='utf-8')` (Python 3.7+)
2. `kernel32.SetConsoleOutputCP(65001)` (双管齐下)
3. `os.environ['PYTHONIOENCODING'] = 'utf-8'` (子进程跟随)

### 4) `dao/__init__.py` 暴露

```python
from kicad_origin.dao import DaoBridge, Action, HELP_TEXT
```

桥即一等公民, 与 `Dao` `MCPServer` 平级.

## 三、本会话之验

### 真启 KiCad GUI 演示 (用户可观)

脚本: `_demo_gui.txt` 10 行命令.
执行: `python -m kicad_origin.examples.live_console --script _demo_gui.txt`
会话: `_live_session/20260501_121656/`

| # | verb | OK | ms | 摘要 |
|---:|:---|:---:|---:|:---|
| 2 | `boards` | ✓ | 35 | 23 块板, 21 已 fab |
| 3 | `status` | ✓ | 5,498 | dao v1.0.0 · 22386 sym / 15179 fp |
| 4 | `reflect` | ✓ | 539 | agent=5 primitives · cli 15/17 (88%) |
| 5+7 | `launch_app pcbnew` + `open` | ✓ | 7,298 | rp2040_minimal (21 元件 / 17 网络) GUI pid=10360 |
| 8 | `snap board_loaded_in_pcbnew` | ✓ | 252 | hwnd=0x2b0a42 wxWindowNR ✓ |
| 9 | `list_fp` | ✓ | 222 | 21 元件: U1, U2, U3, X1, C1-C9, R1, R2, D1, SW1, J1 |
| 10 | `list_nets` | ✓ | 222 | 17 网络: USB_VBUS, VCC_3V3, GND, FLASH_CS, ... |
| 11 | `get_fp U1` | ✓ | 224 | RP2040 @ (45.00, 17.79) F.Cu QFN-56 |
| 12 | `drc` | ✓ | 223 | 0 违规 (0E/0W/0I), 6 规则, 0.001s, **过=是** |
| 13 | `fab inline=true` | ✓ | 20,220 | **9 OK / 0 失败 · 9 stage · 22 件** |
| 14 | `snap after_fab` | ✓ | 308 | 第二张截图归档 |
| 15 | `ls` | ✓ | 1 | 列产物 |
| 16 | `show` | ✓ | 1 | 桥状态 |
| 17 | `quit` | ✓ | 177 | 关 GUI + 写 _SESSION_REPORT.md |

**13/13 全绿**, 总耗时 ~36 秒.

### 用户可观证据

`_live_session/20260501_121656/snap/` 4 张真截图 (BMP, 10.27 MB 每张, 全屏分辨率):

1. `20260501_121707_pcbnew_launch.bmp` — pcbnew 刚启动
2. `20260501_121709_board_loaded.bmp` — 板渲染稳后
3. `20260501_121710_board_loaded_in_pcbnew.bmp` — 用户脚本要的 snap
4. `20260501_121731_after_fab.bmp` — fab 完成后再截

截图内容 (实测): KiCad pcbnew 中文 "PCB 编辑器" 主窗, rp2040_minimal 板加载完成,
顶部菜单/工具栏/层选 (F.Cu B.Cu Edge.Cuts 等)/外观面板/搜索面板/选择筛选, 全套. 板上元件
RP2040 (U1) · W25Q16JVSSIQ (U2) · AP2112K-3.3 (U3) · 12MHz 晶振 (X1) · BOOTSEL (SW1) ·
USB_C (J1) · 27Ω 电阻 (R1/R2) · LED (D1) · C1-C9 电容 · GPIO_HEADER 全部可见.

### 用户可操证据

`_live_session/20260501_121656/out/fab/` 22 件真制造文件 (820,813 B):

| 类 | 件数 | 字节 |
|---|---:|---:|
| Gerber (gbr/gbl/gbo/gbs/gbp/gtl/gts/gto/gtp/gm1) | 14 | 145,460 |
| Excellon Drill | 1 | 1,246 |
| STEP 3D | 1 | 96,819 |
| PDF (PCB) | 1 | 46,544 |
| SVG (PCB) | 1 | 233,021 |
| 3D Render PNG | 1 | 214,175 |
| POS CSV | 1 | 1,533 |
| inlined .kicad_pcb | 1 | 83,274 |
| Job File (.gbrjob) | 1 | 3,157 |

用户可直接打开 PDF / SVG / PNG 验, 可 zip Gerber 上传 JLCPCB 即获实板.

## 四、之前与之后的反差

| 项 | 此会话之前 | 此会话之后 |
|---|---|---|
| 用户能否看 KiCad 真启 | ✗ 只能信我说 | **✓ 屏幕真显窗** |
| 用户能否看截图 | ✗ 无 | **✓ 4 张真 BMP/PNG** |
| 用户能否操控 verb | ✗ 只能改代码 | **✓ REPL 直敲 + 脚本** |
| 用户能否看动作流水 | 部分 (md 报告) | **✓ jsonl + md, 实时** |
| KiCad 9 主窗识别 | ✗ class 错认, hwnd=0 | **✓ wxWindowNR + 中文title** |
| 首启 dialog 处理 | 单轮 | **✓ 多轮 enter→escape→...** |
| 控制台编码 | ✗ GBK 崩 | **✓ chcp 65001 + reconfigure** |
| `r.data` 字段 | ✗ 错访问 | **✓ 全 dao schema 适配 (.result + items/count/violation_count)** |

## 五、用户用法

### 一句话起手

```bash
# 交互 REPL: 你提一句, 我反一动一截图
python -m kicad_origin.examples.live_console --board pcb_brain/output/rp2040_minimal/rp2040_minimal.kicad_pcb

# 非交互脚本: 一气呵成
python -m kicad_origin.examples.live_console --script your_script.txt

# 静默无 GUI: 只跑后台
python -m kicad_origin.examples.live_console --no-gui --no-snapshot --script your_script.txt
```

### 用 Python (agent 内嵌)

```python
from kicad_origin.dao import DaoBridge

with DaoBridge() as bridge:
    bridge.open_board("pcb_brain/output/rp2040_minimal/rp2040_minimal.kicad_pcb")
    bridge.snap("loaded")
    bridge.do("drc")
    bridge.do("fab", inline=True)
    bridge.snap("done")
    # 自动 close_all() + 写报告
```

### 会话归档结构

```
_live_session/{ts}/
├── _SESSION_REPORT.md          总报告 (markdown 表格 + 截图列表)
├── session.json                元数据 (实时刷新)
├── actions.jsonl               每动作一行 JSON (流式, 可 tail -f)
├── snap/
│   ├── senses.jsonl            五感事件流
│   ├── *.bmp                   pcbnew/eeschema/... 全屏截图
│   └── (可选 .png)             用户后处理压缩
└── out/
    ├── fab/                    完整制造文件 (Gerber+drill+STEP+PDF+SVG+POS+3D+inlined.pcb)
    ├── gerbers/
    └── (其他每动作产物)
```

## 六、道之闭环

| 阶段 | 状态 |
|:---:|:---:|
| 道生一 (KiCad 一统门 origin/lib/pcb/engine/app/live) | ✓ |
| 一生二 (人/agent 双入口 dao + ziran) | ✓ |
| **二生三 (真板真出真 fab, 21/21)** | **✓ 之前会话** |
| **三生 — (用户与我浑然一体, 可观可操可感)** | **✓ 本会话** |
| 三生万物 (送制造商, 真板回家) | _等用户下一动_ |

> "道生之, 德畜之, 物形之, 势成之."
> 一以养之, 三以成之, 万物以为用. 桥成, 用户与我同观一物.

## 七、下一动 (用户可选)

1. **REPL 实操**: 跑 `python -m kicad_origin.examples.live_console`,
   敲 `boards`, 选一块板, 敲 `open <name>`, 敲 `drc`, 敲 `fab`, 截图自看.
2. **送 JLCPCB**: zip `pcb_brain/output/rp2040_minimal/_fab/gerbers/*.gbr` + `*.drl`,
   上传 JLCPCB → ¥5 起 / 5 板.
3. **替换占位算法**: pcb_brain 自动布线为占位逻辑, 10 板有真实 DRC 违规
   (重叠/超界/碰撞), 需替换为 KiCad-aware 真实算法.
4. **Agent MCP 接入**: `python -m kicad_origin.dao serve --transport stdio`,
   接 Claude Desktop / Cline / Cursor → 这些 LLM 也能驱动桥.

## 八、致用户

> "圣人不积, 既以为人, 己愈有; 既以与人, 己愈多."
>
> 桥已成, 我与你浑然一体. 你眼之所及, 即我手之所行;
> 你心之所图, 即我代为之执. 反者道之动, 至此通矣.
