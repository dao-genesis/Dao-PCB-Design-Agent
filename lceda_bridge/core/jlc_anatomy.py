"""jlc_anatomy — 嘉立创下单助手 (jlc-assistant) 解剖.

D:\\安装的软件\\jlc-assistant\\jlc-assistant.exe (136MB Electron + app.asar 16.7MB).
本模块对其内核做了静态逆向, 沉淀:
  · ipcMain channels    (Renderer → Main 12 个)
  · 主进程→渲染 channel  (EChannelEnum 反汇编, 30+ 个)
  · BrowserWindow/View 入口 (18 个 HTML)
  · 4 个 preload 脚本角色
  · URL endpoints 4 套环境 (PRO/DEV/FAT/TEST)
  · 与嘉立创 EDA 的双向交互点 (alertEDA/orderPcb)

注: 完整 .asar 已解到 lceda_bridge/_recon_jlc/build/. 用 npx @electron/asar
extract 可重现.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

JLC_ASSISTANT_EXE = Path(r"D:\安装的软件\jlc-assistant\jlc-assistant.exe")
JLC_ASSISTANT_ASAR = Path(r"D:\安装的软件\jlc-assistant\resources\app.asar")
ASAR_RECON_ROOT = Path(__file__).resolve().parents[1] / "_recon_jlc"


# ────────────────────────────────────────────────────────────────────
# 1. ipcMain channels (Renderer → Main, 12 个)
# ────────────────────────────────────────────────────────────────────
IPC_MAIN_CHANNELS: dict[str, str] = {
    # /msg/* 系列 — 业务消息
    "/msg/request/openTag":           "★ ipcMain.handle — 在新标签页打开 URL (异步返回结果)",
    "/msg/alertClose/clickConfirm":   "关闭确认弹窗的 Confirm",
    "/msg/alertClose/clickCancel":    "关闭确认弹窗的 Cancel",

    # /browserView/* — 嵌入 jlc.com 的 BrowserView 控制
    "/browserView/alert":             "BrowserView 内 alert 转发",
    "/browserView/keydown":           "BrowserView 内键盘事件 (Ctrl+S 等)",
    "/browserView/create/gerberList": "★ 创建 Gerber 文件列表 BrowserView",
    "/browserView/orderPcb":          "★ 触发 PCB 下单流程",

    # /contextMenu — 右键菜单
    "/contextMenu/show":              "弹出右键菜单",

    # /setting — 设置
    "/setting/webViewScale":          "WebView 缩放比例",

    # viewFrame/* — frame preload 注入的桥
    "viewFrame/getDeviceInfo":        "★ 获取设备硬件信息 (CPU/内存/显卡/网卡)",
    "viewFrame/getDeviceInfoEx":      "扩展设备信息 (含磁盘/操作系统)",
    "viewFrame/deCryptoAndUnZipTest": "★ 解密+解压测试 (用 crypto-js)",
}


# ────────────────────────────────────────────────────────────────────
# 2. 主进程 → 渲染 channel (从 viewPreload.js EChannelEnum 反汇编)
# ────────────────────────────────────────────────────────────────────
MAIN_TO_RENDERER_CHANNELS: dict[str, str] = {
    # 窗口控制
    "/main/window/minimize":     "最小化",
    "/main/window/maximize":     "最大化",
    "/main/window/close":        "关闭",
    "/main/window/open":         "打开",
    "/msg/request/isMaximized":  "查询最大化状态",

    # Alert (一般信息)
    "/main/alert/ok":            "Alert OK",
    "/main/alert/cancel":        "Alert Cancel",
    "/main/alert/info":          "Alert info",

    # Alert (关闭确认)
    "/main/setCurrentHideTask":  "设置隐藏到后台",
    "/main/getCurrentHideTask":  "查询隐藏到后台",
    "/main/setCurrentAlertClose":"设置关闭弹窗状态",
    "/main/getCurrentAlertClose":"查询关闭弹窗状态",
    "/main/setCloseOther":       "设置 关闭其他",
    "/main/getCloseOther":       "查询 关闭其他",

    # 自启动
    "/main/getAutoStart":        "查询自启动",
    "/main/setAutoStart":        "设置自启动",

    # ★ Alert EDA — 与嘉立创 EDA 的双向交互 ★
    "/main/setCurrentAlertEDA":  "★ 设置 EDA 检测告警状态",
    "/main/getCurrentAlertEDA":  "★ 查询 EDA 检测告警状态",
    "/main/alertEDA/clickCloseOther": "★ 点击 [关闭其他] (关闭其他下单助手实例)",
    "/main/alertEDA/clickOpenSame":   "★ 点击 [打开相同] (打开 EDA 内同款工程)",

    # 系统/配置
    "/main/customerInfo":        "客户信息",
    "/main/config":              "主进程配置",
    "/main/performance":         "性能指标",
    "/main/getWin10":            "Windows 10 检测",
    "/main/getProxy":            "系统代理",
    "/main/reset":               "重置整个 assistant",

    # BrowserView 控制
    "/main/browser/setTop":      "BrowserView 置顶",
    "/main/browser/close":       "关闭 BrowserView",
    "/main/resetBound":          "重置 BrowserView 边界",

    # 标签/设置
    "/main/switchTab":           "切换标签页",
    "/main/setting/reset":       "重置设置",
    "/msg/request/getCurrentWebViewScale": "查询当前 WebView 缩放",

    # 登录
    "/login/success":            "登录成功",

    # 搜索 (主菜单搜索框)
    "/main/search/start":        "开始搜索",
}


# ────────────────────────────────────────────────────────────────────
# 3. BrowserWindow / BrowserView 入口 (18 个 HTML)
# ────────────────────────────────────────────────────────────────────
BROWSER_WINDOWS: dict[str, str] = {
    "index.html":         "主窗口入口",
    "launcher.html":      "启动器",
    "loading.html":       "加载页",
    "login.html":         "登录页 (passport.jlc.com 嵌入)",
    "loginReload.html":   "登录重载",
    "site.html":          "★ 站点 webview (jlc.com/integrated 嵌入)",
    "app.html":           "应用主体",
    "db.html":            "数据库管理",
    "alert.html":         "通用 Alert 弹窗",
    "alertClose.html":    "关闭确认弹窗",
    "alertEDA.html":      "★ EDA 检测告警 (用户开 EDA 时弹出)",
    "messageAlert.html":  "消息 Alert",
    "messageMgr.html":    "消息管理器",
    "notifier.html":      "通知器",
    "setting.html":       "设置面板",
    "commonReload.html":  "通用重载",
}


# ────────────────────────────────────────────────────────────────────
# 4. 4 个 preload 脚本角色
# ────────────────────────────────────────────────────────────────────
PRELOAD_SCRIPTS: dict[str, dict[str, str]] = {
    "preload.js": {
        "role": "主 BrowserWindow preload (主窗口 + 设置/弹窗)",
        "exposes": "appClient / JLC_PC_Assit_Client_Information / __assitEventHandle__",
    },
    "browserPreload.js": {
        "role": "BrowserView preload (jlc.com 嵌入页的最外层 frame)",
    },
    "framePreload.js": {
        "role": "★ Frame-level preload (注入到 jlc.com 的 iframe 内)",
        "intercepts": "contextmenu / keydown (Ctrl+S, Ctrl+滚轮) / mousewheel",
        "globals": "window.appClient, window.parent.__assitEventHandle__",
    },
    "viewPreload.js": {
        "role": "BrowserView 子页 preload (定义 EChannelEnum 等常量)",
        "definitions": "EChannelEnum (30+ 个 /main/* channel)",
    },
}


# ────────────────────────────────────────────────────────────────────
# 5. URL endpoints (4 套环境 + 跨服务集成)
# ────────────────────────────────────────────────────────────────────
URL_ENVIRONMENTS = {
    "PRO": {
        "config": "build/res/config.json — { env: 'PRO', gpu: true, hard: true }",
        "lceda_editor": "https://pro.lceda.cn/editor",
        "lceda_trace":  "https://pro.lceda.cn/editor?cll=trace",
        "jlc_login":    "https://passport.jlc.com/login",
        "jlc_helper_login": "https://helper.jlc.com/cas/login.html?f=jlc_helper&ui=pchelper",
        "jlc_main":     "https://www.jlc.com/integrated",
        "lcsc_pay":     "https://pay.szlcsc.com/cashier/pay",
        "jlc_3dcart":   "https://3dcart.jlc.com/fa",
    },
    "DEV": {
        "lceda_editor": "https://devpro.lceda.cn/editor",
        "passport":     "http://devpassport.jlc.com/login (HTTP! 仅开发环境)",
    },
    "FAT": {
        "helper":       "https://fat-helper.jlc.com/cas/login.html?f=jlc_helper&ui=pchelper",
    },
    "TEST": {
        "main":         "https://test.jlc.com/",
        "integrated":   "https://test.jlc.com/integrated",
        "helper":       "https://testhelper.jlc.com/cas/login.html?f=jlc_helper&ui=pchelper",
    },
    "wechat_login": "https://passport.jlc.com/wechat?service=...",
}


# ────────────────────────────────────────────────────────────────────
# 6. EDA ↔ 助手 双向交互点
# ────────────────────────────────────────────────────────────────────
EDA_INTEROP_POINTS = {
    "alertEDA_window": {
        "html": "alertEDA.html",
        "role": "用户从 EDA 内点 [立即下单] 时, 检测到 jlc-assistant 已运行, 弹出此窗口",
        "buttons": [
            "/main/alertEDA/clickCloseOther — 关闭其他下单助手实例",
            "/main/alertEDA/clickOpenSame   — 打开相同 (复用现有助手)",
        ],
    },
    "orderPcb_flow": {
        "channel": "/browserView/orderPcb",
        "role": "★ 触发 PCB 下单流程 (Gerber 上传 → www.jlc.com/integrated)",
    },
    "gerberList": {
        "channel": "/browserView/create/gerberList",
        "role": "创建 Gerber 文件列表 BrowserView (用户对照下单清单)",
    },
    "deCryptoAndUnZipTest": {
        "channel": "viewFrame/deCryptoAndUnZipTest",
        "role": "用 crypto-js (AES?) 解密 + zip 解压, 推测用于校验下单包完整性",
        "uses": "crypto-js@4.x (build/node_modules/crypto-js)",
    },
}


# ────────────────────────────────────────────────────────────────────
# 7. 第三方依赖 (从 build/node_modules 看)
# ────────────────────────────────────────────────────────────────────
DEPENDENCIES_NOTABLE = {
    "react / react-dom": "UI 框架",
    "rxjs": "响应式流 (用于 channel 解耦)",
    "crypto-js": "加密/解密 (orderPcb 包校验)",
}


def has_recon() -> bool:
    """返回是否已 npx asar extract 解到 _recon_jlc/."""
    return (ASAR_RECON_ROOT / "build" / "main.js").exists()


def summary() -> dict[str, Any]:
    return {
        "exe": str(JLC_ASSISTANT_EXE),
        "exe_exists": JLC_ASSISTANT_EXE.exists(),
        "asar": str(JLC_ASSISTANT_ASAR),
        "asar_exists": JLC_ASSISTANT_ASAR.exists(),
        "recon_root": str(ASAR_RECON_ROOT),
        "has_recon": has_recon(),
        "ipc_main_channels": IPC_MAIN_CHANNELS,
        "main_to_renderer_channels": MAIN_TO_RENDERER_CHANNELS,
        "browser_windows": BROWSER_WINDOWS,
        "preload_scripts": PRELOAD_SCRIPTS,
        "url_environments": URL_ENVIRONMENTS,
        "eda_interop_points": EDA_INTEROP_POINTS,
        "dependencies_notable": DEPENDENCIES_NOTABLE,
    }


__all__ = [
    "JLC_ASSISTANT_EXE", "JLC_ASSISTANT_ASAR", "ASAR_RECON_ROOT",
    "IPC_MAIN_CHANNELS", "MAIN_TO_RENDERER_CHANNELS",
    "BROWSER_WINDOWS", "PRELOAD_SCRIPTS", "URL_ENVIRONMENTS",
    "EDA_INTEROP_POINTS", "DEPENDENCIES_NOTABLE",
    "has_recon", "summary",
]


if __name__ == "__main__":
    print(json.dumps(summary(), ensure_ascii=False, indent=2, default=str))
