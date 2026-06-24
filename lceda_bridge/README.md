# 嘉立创EDA 道之直连 (LCEDA Bridge v2.0)

> **锚定本源 · 反者道之动 · 道法自然 · 无为而无不为**
>
> 不重新发明 EDA, 而是逆向连入嘉立创官方扩展API + 直接读写其内部 SQLite/ZIP 文件.
> 五层穿透, 离线本源已开, 由浅入深, 任意一层独立可用.

---

## 〇、本机环境快照 (Source of Truth)

| 资源 | 位置 | 格式 |
|------|------|------|
| **嘉立创EDA Pro 主程序** | `D:\lceda-pro\lceda-pro.exe` | Electron 2.2.32.3 |
| **app.js (主进程)** | `D:\lceda-pro\resources\app\app.js` | 2.3 MB |
| **扩展API SDK** | `D:\lceda-pro\resources\app\assets\pro-api\0.1.79.941a04f4\` | TypeScript .d.ts + .md |
| **API 模型 JSON** | `pro-api\0.1.79\input\eda.extension.api.json` | 2.4 MB TSDoc |
| **PCB 引擎** | `pro-pcb\2.2.32.3.0c4cd1b8\` | WebGL bundle |
| **SCH 引擎** | `pro-sch\2.2.32.3.90a68f64\` | WebGL bundle |
| **OpenCascade 3D** | `assets\occapi\1.2.18\occapi.wasm` | 21 MB WASM |
| **Pangolin 渲染器** | `assets\pangolin\0.2.32\GuiWorker.js` + `index.js` | 2.6 MB each |
| **元件库 (离线)** | `assets\db\lceda-std.elib` | **SQLite 380 MB** |
| **AI Chat 扩展** | `assets\pro-chat\0.1.10\chat.js` | 435 KB |
| **OCR 向导** | `assets\ocr-wizard\0.1.15\` | 纸图扫描转工程 |
| **嘉立创下单助手** | `D:\安装的软件\jlc-assistant\jlc-assistant.exe` | Electron |
| **用户工程根** | `C:\Users\Administrator\Documents\LCEDA-Pro\` | 含 `database\web.db` |
| **离线工程备份** | `D:\电路设计嘉立创\` | `.eprj` 文件 |
| **官方扩展文档** | https://prodocs.lceda.cn/cn/api/ | (在线) |

---

## 一、文件格式本源 (一劳永逸打通)

| 后缀 | 容器 | 内部 | 说明 |
|------|------|------|------|
| `.eprj` | **SQLite 3** | `documents.dataStr` = `base64` + gzip + NDJSON | 工作时项目 (live) |
| `.elib` | **SQLite 3** | `components.dataStr` = 明文 NDJSON | 元件库 (含 FTS 索引) |
| `.epro` | **ZIP** | `SHEET/<uuid>/N.esch`, `PCB/<uuid>.epcb`, `SYMBOL/<uuid>.esym`, `FOOTPRINT/<uuid>.efoo` | 导出包 |
| `.esch` / `.epcb` / `.esym` / `.efoo` | ZIP 内部 | 明文 NDJSON 指令文档 | 单个图档 |
| `.eext` | **ZIP** | 含 `extension.json` + `dist/index.js` 等 | 扩展安装包 |

### NDJSON 指令文档格式

每行一个 JSON 数组, 第一元素是指令类型:

```text
["DOCTYPE","SCH","1.1"]                            ← 文档类型 + 版本
["HEAD",{"originX":0,"originY":0,"maxId":326}]     ← 头信息
["COMPONENT","e1","",0,0,0,0,{},0]                 ← 元件 (id, packageRef, x, y, rot, mirror, props, locked)
["FONTSTYLE","st1",null,...]                       ← 字体样式
["LINESTYLE","st2",null,...]                       ← 线样式
["ATTR","e23","e1","Symbol",null,...]              ← 属性 (attrId, compId, name, value, ...)
["WIRE","e100",[0,0,10,0],"st1"]                   ← 走线
["LAYER",1,"TOP","Top Layer",3,"#FF0000",1,...]    ← (.efoo/.epcb) 层定义
["PAD","e1",1,...]                                  ← (.efoo) 焊盘
["TRACK","e2",1,[...],...]                          ← (.efoo) 走线
```

### 已知 docType 枚举

| 值 | 含义 |
|----|------|
| 1 | 原理图页 (sheet) |
| 2 | SYMBOL |
| 3 | PCB |
| 4 | FOOTPRINT |
| 20 | 模板 (sheet-symbol_a4 等) |

---

## 二、五层穿透架构

```
┌──────────────────────────────────────────────────────────────────┐
│ L5  离线本源    core/ — Python 直接读写 .eprj/.elib/.epro          │ ← 已实施 ✅
│ L4  HTTP桥      lceda_bridge_server.py :9907 长轮询                │ ← 已实施 ✅
│ L3  iframe桥    SYS_IFrame ↔ postMessage ↔ HTTP                  │ ← 已实施 ✅
│ L2  扩展包      .eext (高级→扩展管理器→导入)                       │ ← 已实施 ✅
│ L1  独立脚本    高级→运行脚本 (即贴即跑, 0安装)                     │ ← 已实施 ✅
└──────────────────────────────────────────────────────────────────┘
   ↑ 由浅入深, 任意一层都能独立解决问题
```

| 层 | 用途 | 安装代价 | 能力 |
|----|------|---------|------|
| **L5** core/ | 离线读写 + 元件库搜索 + API 模型查询 | 0 (Python stdlib) | **完全离线**, 不需要嘉立创运行 |
| **L4** HTTP桥 | Python ↔ EDA 同步 RPC | Python | 任何 `eda.*` 调用 |
| **L3** iframe | 扩展内置可视化控制台 | 装扩展 | UI + postMessage |
| **L2** 扩展包 | 持久菜单+按钮 | 一次导入 | 完整 API + `SYS_IFrame` |
| **L1** 独立脚本 | 一次性操作 (导出/查询/批改) | 0 | 全部 `eda.*` 除 `SYS_IFrame` |

---

## 三、目录结构

```text
lceda_bridge/
├── README.md                       ← 本文件
├── lceda_cli.py                    ← 统一 CLI 入口 (推荐入口)
├── 一键直连嘉立创.cmd               ← Windows 一键启动
│
├── core/                           ── L5 离线本源 (无需嘉立创运行) ──
│   ├── doc_codec.py                gzip+base64 ↔ NDJSON 编解码
│   ├── doc.py                      NDJSON 文档解析/查询/构建
│   ├── eprj.py                     .eprj SQLite 读写 (项目/文档/BOM)
│   ├── elib.py                     .elib 元件库搜索 (20674 components)
│   ├── epro.py                     .epro ZIP 读写
│   └── api_model.py                TSDoc 模型查询 (91 类 / 770 方法)
│
├── L1_standalone_scripts/          ── L1 即贴即跑 ──
│   ├── 01_环境侦察.js              eda 对象快照 → 剪贴板
│   ├── 02_列出全部工程.js          所有工程 UUID
│   ├── 03_导出当前BOM.js           当前 PCB → BOM CSV
│   ├── 04_注入PFC原理图.js         1500W PFC 23 元件批量占位
│   ├── 05_DRC全检.js               DRC → 错误清单 CSV
│   ├── 06_批量改属性.js            按 designator 模式批改 (DRY_RUN)
│   └── 99_启动桥接.js              连接 Python 桥 (无须扩展)
│
├── L2_extension/                   ── L2 扩展源码 ──
│   ├── extension.json              uuid=c6521a48...
│   ├── dist/index.js               入口 (ES module, 11 KB)
│   ├── iframe/index.html           L3 控制台 UI
│   ├── images/logo.png             扩展图标
│   └── locales/{en,zh-Hans}.json
│
├── tests/
│   └── smoke.py                    核心层烟雾测试 (5 模块全跑)
│
├── dist/
│   └── lceda-bridge.eext           打包产物 (8.2 KB)
│
├── lceda_bridge_server.py          ── L4 HTTP 桥服务器 (:9907) ──
├── build_eext.py                   L2 → .eext 打包工具
├── lceda_db.py                     LCEDA web.db 读取器
├── lceda_project.py                .epro/.eprj 通用解析 (回退)
├── _recon.py / _recon2.py          本源探查脚本
└── _recon_out/                     探查产物 (.gitignore 建议)
```

---

## 四、CLI 统一入口

```bash
python lceda_cli.py status                  # 全栈环境健康检查 ⭐
python lceda_cli.py demo                    # 演示流程
python lceda_cli.py build                   # 打包 L2 → .eext
python lceda_cli.py serve                   # 启动 :9907 桥服务器
python lceda_cli.py call <path> [args]      # 调用 eda.<path>(args)
python lceda_cli.py open-lceda              # 启动嘉立创EDA客户端

# ── 离线本源 (L5, 无需启动嘉立创/无需联网) ──
python lceda_cli.py search ESP32            # 元件库搜索 (20K+ 离线)
python lceda_cli.py by-lcsc C82899          # LCSC 编号反查
python lceda_cli.py inspect <eprj|epro>     # 工程结构概览
python lceda_cli.py decode <eprj>           # 列出工程内全部文档
python lceda_cli.py decode <eprj> <uuid>    # 解码某文档为明文 NDJSON
python lceda_cli.py encode <text>           # 明文 → dataStr (gzip+base64)
python lceda_cli.py bom <eprj>              # 工程 → BOM
python lceda_cli.py bom <eprj> --format csv -o bom.csv
python lceda_cli.py api SYS_Environment     # 看类方法签名
python lceda_cli.py api-classes             # 列全部 91 个类
python lceda_cli.py api-search project      # 按关键字搜方法

# ── 测试 ──
python lceda_cli.py smoke                   # 核心层烟雾测试
```

---

## 五、最快上手 (60秒)

### 路径 A: 立即用一次, 不动嘉立创 (Layer 5 — 离线本源)

```bash
# 在工程已经存在 .eprj 的情况下, 完全离线分析:
python lceda_cli.py inspect "D:\电路设计嘉立创\xxx.eprj"
python lceda_cli.py search "10K 0603"
python lceda_cli.py by-lcsc C82899
```

### 路径 B: 在嘉立创内跑一次脚本 (Layer 1)

```text
1. 嘉立创EDA → 任意工程
2. 高级 → 运行脚本 (V3) 或 设置→扩展→独立脚本 (V2)
3. 复制 L1_standalone_scripts/01_环境侦察.js 全文 → 粘贴 → 运行
4. F12 三次 → 控制台看输出 (并自动复制 JSON 到剪贴板)
```

### 路径 C: 持久化 + Python 实时驱动 (Layer 2 + 3 + 4)

```text
1. python lceda_cli.py build                       # 生成 dist/lceda-bridge.eext
2. 嘉立创EDA → 高级 → 扩展管理器 → 导入 → 选 .eext   # 一次
3. 启用扩展 + 勾选 "外部交互" 权限                   # 一次
4. python lceda_cli.py serve                       # 终端1
5. 嘉立创EDA → 顶部菜单 LCEDA Bridge → 启动桥接
6. python lceda_cli.py call sys_Environment.getEditorVersion   # 终端2 — 测试
```

### 路径 D: 一键 (Windows)

```text
双击  一键直连嘉立创.cmd
   → 自动 status + build + 启动 EDA + 启动桥服务器
```

---

## 六、调试模式 (官方支持)

```javascript
// 嘉立创客户端 → F12 三次 → 控制台 → 输入:
window.location.href = 'https://client/editor?cll=debug';
// 然后再 F12 三次, 在控制台中:
console.log(eda);                               // 看完整 API
console.log(Object.keys(eda).sort());           // 看顶层对象
```

---

## 七、关键 API 速查 (eda.* 对象, 共 91 类 / 770 方法)

| 类前缀 | 数量 | 用途 |
|-------|------|------|
| `DMT_*` | 10 | Document/Model Tree (Project/Board/Pcb/Schematic/Workspace/Team/Folder/Panel/EditorControl/SelectControl) |
| `SYS_*` | ~10 | 系统 (Environment/I18n/Log/MessageBox/IFrame/ToastMessage/FileSystem/...) |
| `PCB_*` / `IPCB_*` | ~25 | PCB 图元 (Arc/Component/Pad/Via/Track/Polygon/...) + DRC/制造数据 |
| `SCH_*` / `ISCH_*` | ~25 | 原理图图元 (Arc/Bus/Circle/Component/Pin/Polygon/Rectangle/Text/Wire/...) |

**最常用**:

```javascript
eda.sys_Environment.getEditorVersion()
eda.dmt_Project.getCurrentProjectInfo()
eda.dmt_Project.getAllProjectsUuid()
eda.dmt_Pcb.getCurrentPcbInfo()
eda.dmt_Schematic.getCurrentSchematicInfo()
eda.pcb_PrimitiveComponent.getAllPrimitivesAttributes()
eda.sch_PrimitiveComponent.getAllPrimitivesAttributes()
eda.pcb_Drc.runDRCCheck()
eda.sys_MessageBox.showInformationMessage(msg, title, btn)
eda.sys_ToastMessage.showMessage(msg, type)
eda.sys_IFrame.openIFrame(html, w, h, id, props)   // 仅扩展内
eda.sys_FileSystem.saveFile(blob, name)
```

完整索引:

```bash
python lceda_cli.py api-classes              # 列全部
python lceda_cli.py api SYS_Environment      # 看某类
python lceda_cli.py api-search project       # 搜方法名
```

完整文档:
- `D:\lceda-pro\resources\app\assets\pro-api\0.1.79.941a04f4\eda.extension.api.md` (125 KB)
- 在线: https://prodocs.lceda.cn/cn/api/reference/

---

## 八、Python API (示例)

### 8.1 离线分析 (L5 — 无需嘉立创运行)

```python
import sys
sys.path.insert(0, r'e:\道\道生一\一生二\PCB设计\lceda_bridge')

# 离线读 .eprj
from core import eprj
with eprj.EprjReader(r"D:\电路设计嘉立创\xxx.eprj") as e:
    print(e.summary())                        # 工程概览
    print(e.bom())                            # BOM
    for d in e.documents():
        print(d.uuid, d.kind, d.display_title)
        text = d.decode()                     # 明文 NDJSON
        doc = d.to_doc()                      # 结构化对象
        for c in doc.components():
            print(c['ref'], c['value'], c['lcsc'])

# 离线元件库搜索
from core import elib
with elib.ELibrary() as lib:
    for d in lib.search("ESP32", limit=10):
        print(d.display_title, d.lcsc, d.mfr_part)
    info = lib.by_lcsc("C82899")[0]
    print(info.manufacturer, info.attrs)

# API 模型查询
from core import api_model
m = api_model.ApiModel()
cls = m.class_by_name("DMT_Project")
for me in cls.methods():
    print(me.name, me.signature())

# dataStr 编解码
from core import doc_codec
plain = doc_codec.decode(open("xxx.eprj.fragment", "rb").read())
encoded = doc_codec.encode(plain)
```

### 8.2 实时驱动 (L4 — 需嘉立创 + 扩展运行)

```python
from lceda_bridge_server import call

# 同步调用任何 eda.* 方法
ver = call("sys_Environment.getEditorVersion")
proj = call("dmt_Project.getCurrentProjectInfo")
pcb = call("dmt_Pcb.getCurrentPcbInfo")
comps = call("pcb_PrimitiveComponent.getAllPrimitivesAttributes")
errs = call("pcb_Drc.runDRCCheck")

# 弹窗
call("sys_MessageBox.showInformationMessage", "Hello from Python!", "Title", "OK")
```

---

## 九、安全 / 风险提示

| 风险 | 说明 | 缓解 |
|------|------|------|
| `.eprj` 写操作 | 直接 SQLite 修改可能损坏工程 | `EprjReader` 默认只读 (`?mode=ro`); `EprjWriter` 仅当用户明确开启 |
| 扩展权限 | "外部交互" 允许扩展访问任意 HTTP | 桥服务器仅监听 `127.0.0.1`, 不开放外网 |
| 命令注入 | `eda.<path>` 通过点号路径调用 | 服务器执行前只解析 path, 不 eval 代码 |
| 备份建议 | 改任何 `.eprj` 前先复制 | `cp xxx.eprj xxx.eprj.bak` |

---

## 十、设计哲学

```
我无为   ── 不替换 EDA, 不破坏数据, 不脱离官方扩展协议
你无不为 ── 通过官方 API + iframe + postMessage + 直连 SQLite, 万法可达
反者道之动 ── 不正面爬, 反向走官方扩展通道 + 反向解码 dataStr
道法自然 ── 依官方 docType / NDJSON / SQLite, 而非自创格式
```

```
不出户, 知天下;
不窥牖, 见天道.
       ── 道德经 第四十七章

(离线本源 core/ 模块即此意 — 不联网, 不启动嘉立创, 已洞悉全部工程结构)
```

---

## 版本历史

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v1.0 | 2026-04-28 | 初版架构 (L1/L2/L3/L4), 探明文件格式 |
| **v2.0** | **2026-04-28** | **新增 L5 离线本源 (`core/` 6 模块), CLI 全打通, smoke 测试通过, README 重写** |

*文档版本: v2.0 | 2026-04-28 | 道之直连 · 一劳永逸*
