# DAO LCEDA (嘉立创EDA · 归一面板)

把**整个嘉立创EDA**(Web 版 / Windows 桌面版 / Linux 桌面版)整块路由进
VS Code / Devin Desktop —— 用户仍安装嘉立创EDA本体, 但核心操作全部在 IDE 内完成。

## 三面归一

| IDE 面 | 内容 | 通道 |
|---|---|---|
| 左(文件树) | 嘉立创EDA 工程树 | `GET /api/tree` (dmt_Project / dmt_Schematic) |
| 中(主面板) | EDA 完整界面(帧流+全量鼠键) | `GET /api/frame` + `POST /api/input` (CDP screencast) |
| 右/下(对话) | 道之助手(自然语言→官方动词) | `POST /api/chat` → `window._EXTAPI_ROOT_` |

## 原理

本插件不改嘉立创EDA一行代码, 只依赖 Chrome 远程调试(CDP):

```
VS Code webview ⇄ 本地桥 bridge_server.py(:9940) ⇄ CDP ⇄ 嘉立创EDA 本体
                    Page.startScreencast(画面)
                    Input.dispatchMouse/KeyEvent(输入)
                    Runtime.evaluate → _EXTAPI_ROOT_(动词, 94 命名空间/752 方法)
```

Windows/Linux/Web 一视同仁: 只要 EDA 以 `--remote-debugging-port` 启动
(Web 版则用带 CDP 的浏览器打开 pro.lceda.cn/editor), 本插件即可整块接管。

## 使用

1. 启动嘉立创EDA(任一形态):
   - Web: 浏览器(带 `--remote-debugging-port=29229`)打开 https://pro.lceda.cn/editor
   - Linux 桌面: `bash lceda_bridge/desktop/launch_desktop.sh` (CDP :29230)
   - Windows 桌面: `lceda-pro.exe --remote-debugging-port=29230`
2. VS Code 命令面板 → `DAO LCEDA: 打开嘉立创EDA`
3. 中间面板即嘉立创EDA本体; 左侧资源管理器出现「嘉立创EDA 工程」树; 底部面板「道之对话」可下自然语言指令。

配置项: `daoLceda.port`(桥端口, 默认 9940) / `daoLceda.cdpPorts`(默认 `29229,29230`) /
`daoLceda.python`(Windows 设为 `python`) / `daoLceda.bridgePath`。

## 冷启动(全自动)

```bash
# 1. 下载安装桌面版(Linux)
curl -fLo /tmp/lceda.zip https://image.lceda.cn/files/lceda-pro-linux-x64-3.2.149.zip
unzip -q /tmp/lceda.zip -d ~/lceda
# 2. 启动(Xvfb + CDP :29230)
LCEDA_HOME=~/lceda/lceda-pro bash lceda_bridge/desktop/launch_desktop.sh
# 3. 或 Web 版: 登录(密码+滑块全自动) + 会话快照
DAO_CDP_PORT=29229 python3 lceda_bridge/cdp_studio/cold_start.py
# 4. 装插件
cp -r vscode-dao-lceda ~/.vscode/extensions/dao.dao-lceda-0.1.0
```

道法自然 · 无为而无不为
