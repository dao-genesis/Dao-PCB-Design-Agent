# cdp_studio — 嘉立创EDA Pro Web 冷启动 + CDP 直驱底座

> 道法自然 · 无为而无不为 —— 全新 VM 跑一条命令，即落到"已登录、`_EXTAPI_ROOT_`
> 可直驱"的编辑器状态，后续 Agent 像 Cursor 写代码一样直接操作 EDA 全模块。

## 这是什么

嘉立创EDA专业版 **Web 编辑器**(`https://pro.lceda.cn/editor`，V3)把整套**官方扩展 API**
挂在主页面全局 `window._EXTAPI_ROOT_` 上。于是无需安装/激活扩展、无需扩展沙箱自建
WebSocket，只要经 Chrome 远程调试(CDP)在**主页面上下文** `Runtime.evaluate` 调用
`_EXTAPI_ROOT_.<命名空间>.<方法>(...)`，即可用 EDA 自己的机制完成新建工程/原理图、放件、
移动、并用 `dmt_EditorControl.getCurrentRenderedAreaImage()` 取画布实时图回传。

执行面(Agent 下指令) → EDA 真实变化 → 反馈/呈现面(截图/状态回传)，三面归一。

## 文件

| 文件 | 作用 |
|---|---|
| `dao_eda_cdp_driver.py` | 极简 CDP 客户端(无第三方依赖) + `_EXTAPI_ROOT_` 调用封装(`call_eda`/`probe`/`capture_canvas`) |
| `cdp_nav.py` | 导航/截图/查 target 的小工具 |
| `jlc_login.py` | 经 CDP 驱动 `passport.jlc.com` 登录(手机号短信 / 账号密码) |
| `jlc_session.py` | 登录态(cookies + 鉴权 localStorage)的**快照/恢复**——冷启动免登录核心 |
| `cold_start.py` | **一键冷启动编排**:开编辑器→已登录?→注入登录态→账号密码登录→校验→**heal SW** |
| `eda_api_catalog.py` / `eda_api_catalog.json` | 全量**测绘** `_EXTAPI_ROOT_`(94 命名空间 / 701 方法)→ 机器可读目录 |
| `eda_api.py` | **编辑器层**高层绑定:`eda.dmt_Project.xxx()` 直调、字符串寻址、`.map()` 多并发、自动重连、对照目录告警 |
| `eda_rest.py` | **账号层**高层绑定:工程/团队/用户/文件夹的 REST CRUD(cookie 直连,绕过浏览器 SW) |
| `eda_flow.py` | **全流程编排**:建工程→打开→放件→原理图转 PCB(自动确认)→DRC→导出 Gerber/BOM/贴片坐标 |
| `PHASE4_FINDINGS.md` | Phase 4 本体测绘与实战发现录(两层架构 / SW 坑 / 全流程已通 / 已验证端点) |

## 两层架构(道并行而不相悖)

嘉立创EDA Pro Web 本源是**两层**,职责互补、不可混淆:

- **账号层** = REST `pro.lceda.cn/api/*`(带登录 cookie):工程/文件夹/团队/用户的生命周期 CRUD。用 `eda_rest.py`。
- **编辑器层** = `window._EXTAPI_ROOT_`(经 CDP):**已打开**工程/文档内的原理图、PCB、图元、渲染。用 `eda_api.py`。

> 注:`_EXTAPI_ROOT_.dmt_Project.createProject` 在编辑器页是空操作、`getAllProjectsUuid`(无参)只反映当前已打开工程;账号级工程 CRUD **必须走 REST 层**。详见 `PHASE4_FINDINGS.md`。
>
> **桌面离线版(免账号登录)**:工程创建由本地 `fetch("/api/client/createProject")`(Electron 主进程)接管,且**新建后需先以工程目录调一次 `getAllProjectsUuid("<projects_dir>")` 扫描注册**,`openProject` 才能加载板。详见 `DESKTOP_OFFLINE_FINDINGS.md`。

### Service Worker 健康化(关键坑)

本 VM 上编辑器页的 Service Worker 会拦截并挂起所有运行时 fetch(`/api/*` 永不返回,GUI 新建工程报 `Network Error!`),而 shell/Python 直连 API 正常。冷启动登录后会自动 `heal_service_workers`(注销 SW + 重载)恢复;也可手动:

```bash
python dao_eda_cdp_driver.py heal
```

### 两层调用示例

```python
from eda_rest import EdaRest          # 账号层
r = EdaRest()
r.list_projects(); r.create_project("我的工程")

import eda_api                         # 编辑器层
eda = eda_api.EDA()
eda.dmt_Project.getCurrentProjectInfo()
eda.map(["sys_Environment.getEditorCurrentVersion", "dmt_Project.getAllProjectsUuid"])  # 多并发
```

## 冷启动:全新 VM 一条命令

```bash
python lceda_bridge/cdp_studio/cold_start.py
```

逐级回退,直到"已登录"为止:

1. 复用 **Devin 托管的 Chrome CDP**(默认 `:29229`,随会话常驻,无需自起)。
2. 打开/切到 `pro.lceda.cn/editor`;已登录则直接完成。
3. 用 `JLC_SESSION_B64`(或本地 `~/.dao/jlc_session.json`)**注入登录态** → 多数情况下零登录直接进。
4. 仍未登录且有 `JLC_PHONE` + `JLC_PASSWORD` → **账号密码自动登录**。
5. 登录成功后自动刷新本地会话快照,便于下次零登录。

> 若嘉立创对新设备触发**滑块/短信风控**,第 4 步会返回 `NEED_SMS` 提示,此时需**一次**
> 人工短信验证(见下"手工登录")。验证后 `jlc_session.py save` 固化,后续又回到零登录。

### 所需 secret(用户级,已随会话注入为环境变量)

| 环境变量 | 含义 |
|---|---|
| `JLC_PHONE` | 登录手机号 |
| `JLC_PASSWORD` | 登录密码(满足嘉立创策略:6-12 位含数字+大小写字母) |
| `JLC_SESSION_B64` | 已登录态快照(base64),注入即免登录 |

> 仓库内**不存任何明文凭据/cookie**;一切走加密 secret 注入。本地快照落在
> `~/.dao/jlc_session.json`(在仓库之外,不入库)。

## 手工登录(仅当风控需要一次人工时)

```bash
python jlc_login.py open                 # 在编辑器点 Login 打开登录页
python jlc_login.py tab 手机号            # 切到手机号登录
python jlc_login.py phone <手机号>        # 填手机号
python jlc_login.py sendcode             # 获取验证码(用户收短信)
python jlc_login.py code <6位验证码>      # 填验证码并提交
python jlc_session.py save               # 固化登录态(下次零登录)
```

## 直驱 EDA(登录后)

```bash
python dao_eda_cdp_driver.py probe                               # 探测 _EXTAPI_ROOT_ 与命名空间
python dao_eda_cdp_driver.py call "dmt_Project.getAllProjectsUuid" '[]'
python dao_eda_cdp_driver.py call "dmt_Project.getCurrentProjectInfo" '[]'
python dao_eda_cdp_driver.py shot canvas.png                     # 取当前画布渲染图
```

## 环境变量

- `DAO_CDP_PORT` Chrome 远程调试端口(默认 `29229`)
- `JLC_SESSION_FILE` 本地会话快照路径(默认 `~/.dao/jlc_session.json`)
- `JLC_LS_CAP` 快照里单个 localStorage 值的最大字节(默认 20000,丢弃 UI 大缓存)
