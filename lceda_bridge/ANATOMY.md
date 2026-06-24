# 嘉立创EDA — 彻底逆向见证 (ANATOMY)

> **道生一, 一生二, 二生三, 三生万物**
> 万物负阴而抱阳, 冲气以为和.
>
> 此文为 **`PCB设计/lceda_bridge/`** 一脉道术之"逆向到底, 解构一切"见证.
> 自 L5 离线本源 → L0 BusTransport (CDP+总线) → 至 **L-5 全息解剖**, 层层下沉至嘉立创EDA Pro 内核之底.
>
> **"反者道之动, 弱者道之用. 天下万物生于有, 有生于无."**

---

## 〇、十层穿透 (锚定本源, 直至底层之码)

```text
┌──────────────────────────────────────────────────────────────────────┐
│  L5  离线本源     core/ doc_codec/doc/eprj/elib/epro/api_model       │ ✅
│  L4  HTTP 桥      lceda_bridge_server.py :9907                       │ ✅
│  L3  iframe 桥    SYS_IFrame ↔ postMessage ↔ HTTP                    │ ✅
│  L2  扩展包       .eext (高级→扩展管理器→导入)                        │ ✅
│  L1  独立脚本     高级→运行脚本 (即贴即跑, 0安装)                      │ ✅
│  L0  CDP+总线     BusTransport — _MSG_BUS2_EXTAPI_.userScript run    │ ✅
│ ─────────── 至此, 已穿透到 eda 对象本体 ────────────                  │
│  L-1 主进程之根   app_anatomy   — Electron app.js (2.3MB) 全息       │ ✅
│  L-2 资源全息     asset_anatomy — 22 个 asset 子目录 (60MB JS+21MB)  │ ✅
│  L-3 内部总线     bus_anatomy   — 3 套总线 + 协议格式 + iframe 拓扑   │ ✅
│  L-4 数据库底     schema_anatomy— 30 表 / 53 索引 / web.db+eprj+elib │ ✅
│  L-5 工厂下单     jlc_anatomy   — jlc-assistant.asar (16.7MB) 解构   │ ✅
└──────────────────────────────────────────────────────────────────────┘
```

> **道之深处**: L0 ~ L5 是"接入"嘉立创内核, **L-1 ~ L-5 是把嘉立创内核解剖出来固化为代码**.
> 道法自然 ── 不破坏官方协议, 不替换 EDA, 而是把"一切已存在"晒出来.

---

## 一、本机源点 (Source of Truth)

| 资源 | 路径 | 大小 |
|------|------|------|
| 嘉立创EDA Pro 主程序 | `D:\lceda-pro\lceda-pro.exe` | 180 MB Electron 2.2.32.3 |
| **app.js (主进程)** | `D:\lceda-pro\resources\app\app.js` | **2,288,665 bytes** |
| package.json | `D:\lceda-pro\resources\app\package.json` | "JLCEDA Pro" v2.2.32.3 |
| Node 原生模块 | `D:\lceda-pro\resources\app\node_modules\sqlite3` | 唯一 native addon |
| 22 个 asset 子目录 | `D:\lceda-pro\resources\app\assets\` | **494,945,505 bytes** |
| 离线元件库 | `assets\db\lceda-std.elib` | 380 MB SQLite (20,674 components / 16,653 devices) |
| 用户工程 web.db | `C:\Users\Administrator\Documents\LCEDA-Pro\database\web.db` | 41 MB |
| **嘉立创下单助手** | `D:\安装的软件\jlc-assistant\jlc-assistant.exe` | 136 MB Electron |
| jlc-assistant 内核 | `…\resources\app.asar` | 16.7 MB |

---

## 二、L-1 主进程之根 (app_anatomy)

> `core/app_anatomy.py` ── 把 app.js 2.3MB 中的"主进程契约"沉淀为常量 + 现场扫描器.

### 2.1 ipcMain 通道 (Renderer→Main, **仅 4 个**)

| Channel | 作用 | 渲染端来源 |
|---------|------|-----------|
| `control` | 主窗口控制 (`_min/_max/_close/_restore/_settings`) | `assets/view/control.html` |
| `client-setting` | 客户端偏好 (libPath / projectPath / backupPath / clientMode) | `assets/js/client-setting-action.js` |
| `openWindow` | 在新 Electron 窗口打开 URL | `electronAPI.openWindow` (preload) |
| `openWindowSelf` | 在当前窗口打开 URL | `electronAPI.openWindowSelf` (preload) |

> **关键洞见**: Electron 主进程仅暴露 4 个 IPC 通道, 远比社区想象的少!
> 因为前端是 `https://pro.lceda.cn/editor` 的云 Web 应用 (经 protocol.handle 拦截后路由到本地 assets), 真正的业务调用走 `_MSG_BUS_RPC_` + ws-service.

### 2.2 app 生命周期事件 (6 个)

| Event | 处理 |
|-------|------|
| `browser-window-created` | 新窗口创建 hook (注入控制条) |
| `certificate-error` | **`/lceda.cn|easyeda.com/` 强制信任证书** (绕开内网代理证书问题) |
| `child-process-gone` | 子进程崩溃 (GPU/utility) 处理 |
| `open-file` | macOS Dock 拖文件: 把路径 push 到 process.argv |
| `second-instance` | 已运行时再次启动 → 复用首实例 + 把 argv 转发 |
| `window-all-closed` | 全部窗口关闭 → 清临时目录 + app.exit() |

### 2.3 protocol 注册 (★ 这是接管整个 https 网络栈的关键)

```js
protocol.registerSchemesAsPrivileged([{scheme:'app',privileges:{supportFetchAPI:true,stream:true}}])
protocol.handle('https')                        // ★ 接管 https 请求 → 路由到本地 assets
protocol.handle('http')
protocol.interceptBufferProtocol('https')       // 旧版兼容 (Electron < 25)
protocol.interceptBufferProtocol('http')
protocol.registerStringProtocol('app')
```

> **道之自然**: 不抢系统级 URL 协议 (no `setAsDefaultProtocolClient` call) ─ 即不在 Windows 注册表里写 `lceda://`.
> 工程 `.eprj` 双击是靠 file association 触发 `open-file`.

### 2.4 主 BrowserWindow webPreferences

| 主窗口 (现代安全) | 子窗口/对话框 (开放) |
|------------------|--------------------|
| `nodeIntegration: false` | `nodeIntegration: true` |
| `contextIsolation: true` | `contextIsolation: false` |
| `sandbox: true` | (no sandbox) |
| `webSecurity: false` ⚠ | `webSecurity: false` |
| `preload: assets/js/preload.js` | (no preload) |

### 2.5 Node.js 原生模块 (16 stdlib + 1 native)

```text
buffer, child_process, crypto, electron, events, fs, http, https,
os, path, querystring, sqlite3 ★, stream, url, util, zlib
```

### 2.6 网络端点

| 类型 | 域名 | 用途 |
|------|------|------|
| 嘉立创EDA | `pro.lceda.cn` | ★ 编辑器主入口 |
| 嘉立创EDA | `client.lceda.cn` | 客户端 host 标识 |
| 嘉立创EDA | `image.lceda.cn` | 图片资源 (元件预览/3D 缩略图) |
| 嘉立创EDA | `modules.lceda.cn` | ★ JS 模块 CDN (pcb.js/sch.js 等都来自这里) |
| 嘉立创EDA | `prodocs.lceda.cn` | 在线文档 |
| 工厂 | `www.jlc.com`, `tools.jlc.com`, `3d.jlcpcb.com` | 工厂主站/阻抗工具/3D 板预览 |
| 商城 | `www.szlcsc.com`, `atta.szlcsc.com`, `club.szlcsc.com`, `dos.szlcsc.com` | 立创商城/datasheet/社区/DFM |

---

## 三、L-2 资源全息 (asset_anatomy)

> `core/asset_anatomy.py` ── 22 个 asset 子目录, ~495 MB 总规模.

### 3.1 完整 22 模块清单 (按大小降序)

| 模块 | 大小 | 角色 |
|------|------|------|
| `db` | 420 MB | ★ 离线元件库 (380MB) + 示例工程 (22MB) |
| `ocr-wizard` | 44.7 MB | OCR 纸图扫描 (含 214 训练数据文件) |
| `pro-ui` | 42.6 MB | 通用 UI 组件 |
| `occapi` | 21.4 MB | ★ OpenCascade 3D 几何内核 (C++ → WASM) |
| `pro-pcb` | 20.4 MB | ★ PCB 编辑器内核 (13 文件: pcb.js 7.7MB, 4 个 Worker) |
| `smt-ui` | 13.5 MB | ★ 工厂端完整 UI (单文件 smt-ui.js 10.8MB 最大) |
| `smt-gl-engine` | 6.1 MB | ★ 工厂面板 GL 渲染引擎 |
| `pro-sch` | 5.8 MB | ★ 原理图编辑器内核 |
| `pro-panel` | 5.7 MB | 拼板/面板编辑器 |
| `pangolin` | 5.3 MB | ★ 穿山甲 — WebGL 渲染引擎 |
| `pro-api` | 4.0 MB | 扩展 API SDK (.d.ts + .md + JSON 模型) |
| `chameleon` | 3.7 MB | ★ 变色龙 — PDF/XLSX/Office XML 转换 Worker |
| `jerboa` | 2.6 MB | ★ 跳鼠 — Emscripten 编译的 C++ → WASM 计算核心 |
| `pro-mgr` | 1.4 MB | 工程管理 (含 Electron preload + ws-service) |
| `pro-chat` | 458 KB | AI 对话面板 |
| `images, icon, locale` | < 1 MB | 静态资源 |
| `pro-sw` | 104 KB | Service Worker (流式下载) |
| `js, view, css` | < 50 KB | 顶层公共 |

### 3.2 神兽命名探源 (彩蛋)

嘉立创EDA Pro 用神兽命名 3 个核心模块:

- **🐾 Pangolin (穿山甲)** ── WebGL 渲染引擎主线程 + GUI Worker, 各 2.6 MB
- **🦕 Jerboa (跳鼠)** ── Emscripten C++→WASM 计算核心 (推测: 拓扑/约束求解, 因 jerboa 是穿山甲家族外的另一种善挖洞动物)
- **🦎 Chameleon (变色龙)** ── 文件格式变换 Worker (PDF/XLSX/docx 多形态转换 BOM)

### 3.3 15 个 Worker 全景

```text
pangolin/GuiWorker.js              UI 渲染主 Worker
chameleon/chameleon-worker.js      PDF/XLSX 转换
pro-pcb/decodeworker.js            .epcb / dataStr 解码
pro-pcb/drcWorker.js               DRC 设计规则检查
pro-pcb/ratlineworker.js           飞线计算
pro-pcb/pcbRouterWorker.js         自动布线
pro-pcb/worker.js                  通用 PCB 计算
pro-pcb/zipWorker.js               ZIP 打包
smt-gl-engine/worker.js            SMT GL 渲染
pro-mgr/cache-worker.js            缓存
pro-mgr/ws-service.js              内部 WebSocket RPC
pro-panel/panel-worker.js          拼板
pro-panel/panel-sub-worker.js      拼板子任务
pro-ui/worker.js                   UI 通用
pro-sw/sw.js                       Service Worker (流式下载)
```

---

## 四、L-3 内部总线 (bus_anatomy)

> `core/bus_anatomy.py` ── 3 套总线 + 协议格式 + iframe 拓扑.

### 4.1 3 套总线常量 (通过反汇编 jerboa-service.js / ws-service.js / preload.js 抽取)

| 常量 | 角色 | 实现 |
|------|------|------|
| `_MSG_BUS_RPC_` | 通用 RPC 总线 (跨 worker/renderer/main 同步调用, 5min 超时) | jerboa+ws+preload **三处复用** |
| `_MSG_BUS2_EXTAPI_` | ★ **扩展 API 总线** — 独立脚本/扩展/用户代码入口 | `pro-api/api.js` 注入 |
| `_MSG_BUS_PCB_` | PCB 编辑器内部 (pro-pcb 多 worker 协调) | `pcb.js` / `pcb-main.js` |

> **协议库复用**: 同一份 `MessageBus / MessageBus2 / BroadcastChannelMessageBus / WindowMessageBridge / WorkerMessageBridge` 代码, 在 jerboa-service.js / ws-service.js / pro-mgr/preload.js **三处独立打包内嵌**!

### 4.2 extensionApi.userScript 协议 (★ L0 BusTransport 利用此通道)

```javascript
// run 操作
bus.publish('extensionApi.userScript', {
    operation: 'run',
    userScript: '<JS source code>'
});
// 主进程内执行: let e = hr(r.userScript); fr(e);
// hr() 创建沙箱包装函数 (eda 通过闭包注入), fr() 执行
```

**关键发现**: 外层 `Runtime.evaluate` 中 `typeof eda === 'undefined'`, 但 publish 此通道时 eda 在 hr() 沙箱内通过闭包**完整可见**! ── 这是 **L0 BusTransport 的本源**.

支持 4 个 operation:

| operation | payload | 说明 |
|-----------|---------|------|
| `run` | `{operation, userScript}` | 运行一段 JS |
| `save` | `{operation, userScriptName, userScript}` | 保存到独立脚本菜单 |
| `delete` | `{operation, userScriptKey}` | 删除已保存脚本 |
| `getList` | `{operation}` | 列已保存脚本 |

### 4.3 Service Worker 流式下载 (`pro-sw/sw.js`)

| Endpoint | 用途 |
|----------|------|
| `POST /sw/download/stream/create?uuid=<>&fileName=<>` | 创建流式响应 |
| `POST /sw/download/stream/write?uuid=<>` | 写入数据块 |
| `POST /sw/download/stream/close?uuid=<>` | 关闭流, 触发下载 |

> **目的**: Gerber/PDF/BOM/STEP 等大文件流式下载, 不占内存.

### 4.4 iframe 拓扑 (CDP 反汇编)

```text
主 page: https://pro.lceda.cn/editor              ← Electron 主窗口 (空壳)
├── frames[0]: passport.jlc.com                   ← 登录 (跨域)
├── frames[1]: ?entry=sch       ★ eda 对象主宿主 (BusTransport 默认连这里)
├── frames[2]: ?entry=panel
└── frames[3]: ?entry=symbol
```

### 4.5 4 层 API tier (公开 API 仅占 45.4%)

| Tier | size_bytes | classes | methods | 比 public 多 |
|------|-----------|---------|---------|------------|
| `public` (prodocs) | 178,395 | 166 | 380 | — |
| `beta` | 303,371 | 166 | 761 | **+381** |
| `alpha` | 317,581 | 166 | 829 | **+449** |
| `full` | 326,132 | 166 | **837** | **+457** |

> 通过 L0 总线沙箱 (`cdp-call`) 可调用全部内部 API. 用 `lceda api-extras alpha` 看具体多出来的方法.

---

## 五、L-4 数据库底 (schema_anatomy)

> `core/schema_anatomy.py` ── 30 表 + 53 索引 (实地 webdb_admin 28 张 + elib 31 张).

### 5.1 三库 schema 概览

| 库 | 路径 | 实地大小 | 实地表数 | 实地索引数 |
|----|------|---------|---------|-----------|
| **web.db** (用户) | `~/Documents/LCEDA-Pro/database/web.db` | 41 MB | 28 | 48 |
| **lceda-std.elib** (官方) | `D:\lceda-pro\resources\app\assets\db\lceda-std.elib` | 380 MB | 31 | 53 |
| **\*.eprj** (单工程) | `D:\电路设计嘉立创\*.eprj` | KB ~ MB | 14 核心 | — |

### 5.2 30 张表分类 (从 app.js 内嵌 36 个 CREATE TABLE 提取去重)

```text
核心数据:
  components ★      元件 (符号/封装/3D 都是 Component, dataStr=gzip+base64 NDJSON)
  devices    ★      器件 (= 符号 + 封装 + 3D 模型, 高级抽象)
  documents  ★      文档 (原理图页/PCB)
  projects   ★      工程 (顶层抽象)
  schematics        原理图组
  boards            PCB 板子
  resources         二进制资源 (内容寻址 hash)

属性/分类:
  attributes        元件实例属性 (k/v)
  categories        元件分类 (630 条)
  block_symbol_attributes   块符号属性 (层次原理图)
  texts             文字
  coppers           铺铜

用户/团队/协同:
  users             用户
  team_members      团队成员
  project_members   工程成员
  sessions          协同会话
  web_cookies       cookie 缓存

系统:
  db_versions       schema 版本号
  db_paths          多库路径
  system_attributes 系统属性 (k/v)
  system_config     系统配置
  editor_caches     编辑器缓存
  editor_bugs       异常上报
  notifications     通知
  broadcast_messages 广播
  project_logs      工程日志
  backups           备份配额
  sqlite_sequence   SQLite 自增序列

迁移临时:
  components_tmp, devices_tmp, documents_tmp  (历次迁移)
```

### 5.3 docType 枚举

```python
1  → SHEET       # 原理图页
2  → SYMBOL      # 符号
3  → PCB         # PCB
4  → FOOTPRINT   # 封装
20 → TEMPLATE    # 模板 (sheet-symbol_a4 等)
```

### 5.4 dataStr 编码

每个 `components.dataStr` / `documents.dataStr` 字段都是 **`gzip` + `base64`** 编码的 NDJSON. 第一行 `["DOCTYPE","SCH","1.1"]` 表明类型.

`core/doc_codec.py` 已实现 round-trip 编解码.

---

## 六、L-5 工厂下单 (jlc_anatomy)

> `core/jlc_anatomy.py` ── 嘉立创下单助手 `jlc-assistant.exe` 全息.

### 6.1 12 个 ipcMain 通道 (Renderer → Main)

```text
/msg/request/openTag                   ★ 异步 handle: 新标签页打开 URL
/msg/alertClose/clickConfirm/Cancel    关闭确认弹窗
/browserView/alert                     BrowserView 内 alert 转发
/browserView/keydown                   BrowserView 内键盘事件
/browserView/create/gerberList         ★ 创建 Gerber 文件列表 BrowserView
/browserView/orderPcb                  ★ 触发 PCB 下单流程
/contextMenu/show                      右键菜单
/setting/webViewScale                  WebView 缩放
viewFrame/getDeviceInfo[Ex]            ★ 获取设备硬件指纹
viewFrame/deCryptoAndUnZipTest         ★ AES 解密 + ZIP 解压 (校验下单包)
```

### 6.2 主→渲染 34 个 channel (从 viewPreload.js EChannelEnum 反汇编)

关键 channel (★ 与 EDA 双向交互):

```text
/main/setCurrentAlertEDA          设置 EDA 检测告警状态
/main/getCurrentAlertEDA          查询 EDA 检测告警状态
/main/alertEDA/clickCloseOther    用户点 [关闭其他下单助手实例]
/main/alertEDA/clickOpenSame      用户点 [打开相同工程]
```

完整列表见 `python lceda_cli.py anatomy jlc --json`.

### 6.3 BrowserWindow 入口 (16 个 HTML)

```text
index.html       主窗口
launcher.html    启动器
loading.html     加载页
login.html       登录 (passport.jlc.com 嵌入)
site.html        ★ 站点 webview (jlc.com/integrated 嵌入)
app.html         应用主体
db.html          数据库管理
alert.html       通用 Alert
alertClose.html  关闭确认
alertEDA.html    ★ EDA 检测告警 (用户开 EDA 时弹出)
messageAlert.html, messageMgr.html, notifier.html
setting.html, commonReload.html, loginReload.html
```

### 6.4 4 个 preload 脚本

| Preload | 角色 |
|---------|------|
| `preload.js` | 主 BrowserWindow preload — 暴露 `window.appClient` / `JLC_PC_Assit_Client_Information` / `__assitEventHandle__` |
| `browserPreload.js` | BrowserView preload (jlc.com 嵌入页最外层) |
| `framePreload.js` | ★ Frame-level preload (注入 jlc.com 的 iframe), 拦截 contextmenu/keydown/mousewheel |
| `viewPreload.js` | BrowserView 子页 preload (定义 EChannelEnum 等常量) |

### 6.5 4 套环境 (PRO/DEV/FAT/TEST)

```python
# build/res/config.json
{ "env": "PRO", "gpu": true, "hard": true }
```

| 环境 | helper | passport | main |
|------|--------|----------|------|
| **PRO** (生产) | `helper.jlc.com` | `passport.jlc.com` | `www.jlc.com/integrated` |
| **DEV** (开发) | `devhelper.jlc.com` | `devpassport.jlc.com` (HTTP!) | — |
| **FAT** (验收) | `fat-helper.jlc.com` | — | — |
| **TEST** (测试) | `testhelper.jlc.com` | — | `test.jlc.com/integrated` |

### 6.6 EDA ↔ 助手交互点

| 触发 | 通道 | 说明 |
|------|------|------|
| 用户从 EDA 点 [立即下单] | `alertEDA.html` 弹窗 | 检测到助手已开 → 询问 [关闭其他] / [打开相同] |
| EDA 提交 Gerber | `/browserView/orderPcb` | 跳到 jlc.com/integrated 下单流程 |
| 校验下单包 | `viewFrame/deCryptoAndUnZipTest` | crypto-js (AES?) 解密 + zip 解压 |

---

## 七、与道为一 (CLI 用法)

```bash
# 一行看全息
python lceda_cli.py anatomy app                     # Electron 主进程
python lceda_cli.py anatomy asset                   # 22 个 asset 模块
python lceda_cli.py anatomy bus                     # 内部消息总线
python lceda_cli.py anatomy schema                  # 30 表 SQLite schema
python lceda_cli.py anatomy jlc                     # 下单助手
python lceda_cli.py anatomy all --json              # 全部以 JSON 输出 (机器可读)

# 实地探查 (检测嘉立创版本升级后差异)
python lceda_cli.py anatomy-scan

# 烟雾测试 (自验证)
python tests\smoke_anatomy.py

# Python API (在自己脚本中用)
from core import app_anatomy, asset_anatomy, bus_anatomy, schema_anatomy, jlc_anatomy

print(app_anatomy.IPC_MAIN_CHANNELS)               # 4 个 ipcMain 通道
print(asset_anatomy.list_assets())                 # 22 个 asset 按 size 降序
print(bus_anatomy.USER_SCRIPT_PROTOCOL)            # extensionApi.userScript 协议
schema_anatomy.dump_create_sql(schema_anatomy.WEBDB_PATH_ADMIN)   # 一键导出 .sql
print(jlc_anatomy.IPC_MAIN_CHANNELS)               # 12 个下单助手通道
```

---

## 八、当前完整目录结构

```text
PCB设计/lceda_bridge/
├── README.md                         L0~L5 入口手册 (五层穿透)
├── WITNESS.md                        v2.0 实测见证 (含 BusTransport 调通)
├── ANATOMY.md                        ★ 本文件 — L-1~L-5 解剖见证
│
├── lceda_cli.py                      30 个子命令 (含 anatomy/anatomy-scan)
├── lceda_bridge_server.py            L4 :9907 桥
├── build_eext.py                     L2 .eext 打包器
├── build_pfc_bom.py                  PFC BOM 自动匹配
├── lceda_db.py                       web.db 读取
├── lceda_project.py                  通用 .eprj/.epro 回退
├── 一键直连嘉立创.cmd
│
├── core/                             ─── 12 个核心模块 ───
│   ├── __init__.py                   v2.1 全索引
│   │   ── 文件格式 ──
│   ├── doc_codec.py                  gzip+base64 ↔ NDJSON
│   ├── doc.py                        NDJSON 解析/构建
│   ├── eprj.py                       .eprj SQLite I/O
│   ├── elib.py                       .elib 离线搜索
│   ├── epro.py                       .epro ZIP I/O
│   │   ── API 模型 ──
│   ├── api_model.py                  TSDoc 公开 API (380 方法)
│   ├── api_dts.py                    4 层 tier (public/beta/alpha/full 837 方法)
│   ├── api_extras                    (动态生成)
│   │   ── 传输层 ──
│   ├── sdk.py                        EDA 统一门面
│   ├── http_transport.py             HTTP 桥
│   ├── cdp_transport.py              CDP + BusTransport (L0)
│   │   ── 反向解剖 (本次新增) ──
│   ├── app_anatomy.py            ★  Electron 主进程
│   ├── asset_anatomy.py          ★  22 个 asset 全息
│   ├── bus_anatomy.py            ★  3 套消息总线
│   ├── schema_anatomy.py         ★  SQLite schema
│   └── jlc_anatomy.py            ★  下单助手
│
├── L1_standalone_scripts/            7 个独立 JS 脚本
├── L2_extension/                     扩展源码 (uuid=c6521a48...)
├── tests/
│   ├── smoke.py                      core/ 烟雾 (5/5)
│   └── smoke_anatomy.py          ★  anatomy 烟雾 (5/5)
├── dist/                             打包产物
│   └── lceda-bridge.eext             8.2 KB ZIP
└── _recon_jlc/  (gitignore)          jlc-assistant.asar 解出来的 reference
    └── build/                        70+ files (main.js / preload.js / app.js / ...)
```

---

## 九、smoke 输出 (实测见证)

```text
======================================================================
  anatomy-scan — 实地探查 (与静态值对照)
======================================================================

[app.js fresh scan]
  ipc_main_channels        ['client-setting', 'control', 'openWindow', 'openWindowSelf']
  app_events               ['browser-window-created', 'certificate-error',
                            'child-process-gone', 'open-file', 'second-instance',
                            'window-all-closed']
  protocol_calls           ['handle', 'interceptBufferProtocol',
                            'registerSchemesAsPrivileged', 'registerStringProtocol']
  sqlite_create            {'create_table': 36, 'create_index': 25,
                            'create_unique_index': 19, 'create_view': 0,
                            'create_trigger': 0}
  lceda_urls               55 个
  jlc_urls                 3 个
  lcsc_urls                12 个

[assets fresh scan]
  db              420,769,467  files=   3
  ocr-wizard       44,734,834  files= 214  v=0.1.15.c5462977
  pro-ui           42,610,100  files=  15  v=2.2.32.3.ed5b0549
  occapi           21,429,805  files=   1  v=1.2.18.56bae065
  pro-pcb          20,435,558  files=  13  v=2.2.32.3.0c4cd1b8
  smt-ui           13,533,570  files=   3  v=1.0.12.2f0646a5
  smt-gl-engine     6,149,039  files=   4  v=0.10.103.e4812dec
  pro-sch           5,822,613  files=   3  v=2.2.32.3.90a68f64
  pro-panel         5,688,967  files=   5  v=2.2.32.1.0cb05813
  pangolin          5,262,604  files=   4  v=0.2.32.9e6b87fb
  pro-api           4,016,688  files=   8  v=0.1.79.941a04f4
  chameleon         3,652,185  files=   1  v=2.1.35.04530fc3
  jerboa            2,575,229  files=   1  v=0.1.3.098894ce
  pro-mgr           1,449,414  files=   4  v=2.2.32.1.a44b17bd
  ...

[schema fresh scan — webdb]
  C:\Users\Administrator\Documents\LCEDA-Pro\database\web.db   28 tables / 48 indexes
  D:\lceda-pro\resources\app\assets\db\lceda-std.elib          31 tables / 53 indexes
```

```text
======================================================================
  smoke_anatomy 全验证
======================================================================
  [1] schema_anatomy   ✅
  [2] app_anatomy      ✅
  [3] asset_anatomy    ✅
  [4] bus_anatomy      ✅
  [5] jlc_anatomy      ✅
  Result: ✅ 全部 5 个 anatomy 模块通过
```

---

## 十、道之沉淀 (设计哲学)

```text
道生一        ─ 一份 lceda_cli.py 入口
一生二        ─ 二种触达路径 (在线 cdp-call / 离线 anatomy)
二生三        ─ 三套总线 (_MSG_BUS_RPC_ / _MSG_BUS2_EXTAPI_ / _MSG_BUS_PCB_)
三生万物      ─ 30 表 + 837 API + 22 资源 + 70+ jlc-assistant 文件
                ─ 全部沉淀为 Python 常量 + 现场扫描器, 升级版本可一键再探.
```

> "**生而不有, 为而不恃, 长而不宰, 是谓玄德**".
>
> 此 anatomy 体系不替换嘉立创, 不破坏数据, 不绕开协议, 只把"已存在的本然"显出来 ── 故道法自然.
>
> 不出户, 知天下; 不窥牖, 见天道.
> 5 个 `core/*_anatomy.py` 模块, 一行 `lceda anatomy all` 即知嘉立创 EDA 全部内核.

---

## 十一、版本历史

| 版本 | 日期 | 主要变更 |
|------|------|----------|
| v1.0 | 2026-04-28 | 初版架构 (L1/L2/L3/L4) |
| v2.0 | 2026-04-28 | L5 离线本源 + L0 BusTransport |
| **v3.0** | **2026-04-28** | **L-1 ~ L-5 anatomy ── 5 个解剖模块 + CLI anatomy/anatomy-scan + smoke_anatomy** |

*文档版本: v3.0 · 道之直连 · 彻底逆向, 解构一切*
