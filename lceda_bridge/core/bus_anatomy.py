"""bus_anatomy — 嘉立创EDA 内部消息总线协议解构.

嘉立创 EDA 内部用 3 套消息总线达成 main↔renderer↔worker↔extension 通信.
本模块基于对 jerboa-service.js / ws-service.js / pro-mgr/preload.js 的
反汇编, 沉淀完整的总线拓扑 + 通道清单 + RPC 协议格式.

3 套总线:
  _MSG_BUS_RPC_       通用 RPC (jerboa+ws+preload 三处复用同一份协议库)
  _MSG_BUS2_EXTAPI_   扩展 API 沙箱 (用户脚本/扩展运行的入口)
  _MSG_BUS_PCB_       PCB 编辑器内部 (pro-pcb 内 worker↔main 通信)

关键: BusTransport (core/cdp_transport.BusTransport) 利用的就是
_MSG_BUS2_EXTAPI_ 上的 'extensionApi.userScript' 通道, 在 hr() 沙箱里
拿到 eda 闭包对象 — 这是 L0 直连的本源.
"""
from __future__ import annotations

from typing import Any


# ────────────────────────────────────────────────────────────────────
# 1. 总线常量 (从 jerboa-service.js / ws-service.js 抽取的字符串常量)
# ────────────────────────────────────────────────────────────────────
BUS_CONSTANTS = {
    "_MSG_BUS_RPC_": {
        "role": "通用 RPC 总线 — 跨 worker/renderer/main 同步调用",
        "default_timeout_ms": 5 * 60 * 1000,   # 5 分钟
        "implementation": "jerboa-service.js / ws-service.js / preload.js (复用)",
        "primitives": ["MessageBus", "MessageBus2", "BroadcastChannelMessageBus",
                       "WindowMessageBridge", "WorkerMessageBridge"],
    },
    "_MSG_BUS2_EXTAPI_": {
        "role": "★ 扩展 API 总线 — 独立脚本/扩展/用户代码的执行入口",
        "implementation": "pro-api/api.js (注入 webContents)",
        "channels": [
            "extensionApi.userScript",                  # ★ 运行/保存/删除独立脚本
            "extensionApi.callFunctionInExtension",     # 在已装扩展中调函数
            "extensionApi.SCH_Event.mouseEvent",        # 原理图鼠标事件
            "extensionApi.PCB_Event.mouseEvent",        # PCB 鼠标事件
        ],
        "rpc_format": "{ operation, ticket, data }",
    },
    "_MSG_BUS_PCB_": {
        "role": "PCB 编辑器内部总线 (pro-pcb 多 worker 协调)",
        "implementation": "pcb.js / pcb-main.js + 6 个 worker",
    },
}


# ────────────────────────────────────────────────────────────────────
# 2. extensionApi.userScript 协议 (★ L0 直连利用此通道)
# ────────────────────────────────────────────────────────────────────
USER_SCRIPT_PROTOCOL = {
    "channel": "extensionApi.userScript",
    "operations": {
        "run": {
            "payload": {"operation": "run", "userScript": "<JS source code>"},
            "exec": "let e = hr(r.userScript); fr(e);",
            "note": "hr() 创建沙箱包装函数 (eda 通过闭包注入), fr() 执行",
        },
        "save": {
            "payload": {"operation": "save",
                        "userScriptName": "<显示名>",
                        "userScript": "<JS source code>"},
            "note": "保存到嘉立创独立脚本菜单",
        },
        "delete": {
            "payload": {"operation": "delete",
                        "userScriptKey": "<由 save 返回的 key>"},
        },
        "getList": {
            "payload": {"operation": "getList"},
            "returns": "已保存脚本数组",
        },
    },
    "key_finding": (
        "外层 Runtime.evaluate 中 typeof eda === 'undefined', "
        "但 bus.publish('extensionApi.userScript', {operation:'run', ...}) "
        "时, eda 在 hr() 沙箱内通过闭包完整可见. 这就是 L0 BusTransport 的本源."
    ),
}


# ────────────────────────────────────────────────────────────────────
# 3. ipcMain 通道 (Electron IPC, 已在 app_anatomy 详细; 此处对照)
# ────────────────────────────────────────────────────────────────────
ELECTRON_IPC_MAIN = ["control", "client-setting", "openWindow", "openWindowSelf"]


# ────────────────────────────────────────────────────────────────────
# 4. Service Worker /sw/download/stream/ 协议
# ────────────────────────────────────────────────────────────────────
SW_DOWNLOAD_STREAM = {
    "register_url": "/sw/download/stream/create",
    "endpoints": {
        "POST /sw/download/stream/create?uuid=<>&fileName=<>":
            "创建流式响应 (返回 ReadableStream, content-type=octet-stream)",
        "POST /sw/download/stream/write?uuid=<>":
            "写入数据块 (body=arrayBuffer)",
        "POST /sw/download/stream/close?uuid=<>":
            "关闭流, 触发浏览器下载",
    },
    "purpose": "Gerber/PDF/BOM/STEP 等大文件流式下载, 不占内存",
}


# ────────────────────────────────────────────────────────────────────
# 5. iframe 框架结构 (CDP 反汇编得到)
# ────────────────────────────────────────────────────────────────────
IFRAME_TOPOLOGY = {
    "main_page": {
        "url": "https://pro.lceda.cn/editor",
        "role": "Electron 主窗口 (空壳, 仅做 iframe host)",
    },
    "frames": [
        {"idx": 0, "url": "passport.jlc.com", "role": "登录 (跨域)"},
        {"idx": 1, "url": "?entry=sch", "role": "★ 原理图编辑器内核 — eda 对象的主宿主"},
        {"idx": 2, "url": "?entry=panel", "role": "拼板/面板编辑器内核"},
        {"idx": 3, "url": "?entry=symbol", "role": "符号编辑器内核"},
    ],
    "note": (
        "eda 对象在 frames[1] (sch entry) 内最完整. BusTransport 默认连 frame_idx=1, "
        "可通过 --frame 切换到 panel(2) / symbol(3)."
    ),
}


# ────────────────────────────────────────────────────────────────────
# 6. extensionApi 4 层 API tier (public/beta/alpha/full)
# ────────────────────────────────────────────────────────────────────
API_TIER_STATS = {
    "public": {"size_bytes": 178_395, "classes": 166, "methods": 380},
    "beta":   {"size_bytes": 303_371, "classes": 166, "methods": 761,
               "extra_vs_public": 381},
    "alpha":  {"size_bytes": 317_581, "classes": 166, "methods": 829,
               "extra_vs_public": 449},
    "full":   {"size_bytes": 326_132, "classes": 166, "methods": 837,
               "extra_vs_public": 457},
}
# 公开 API 仅占内部全部 API 的 45.4% — 通过 L0 总线沙箱可调用全部内部 API.


# ────────────────────────────────────────────────────────────────────
# 7. 主进程 → 渲染进程的 webContents.send() 通道 (从 control.html 反推)
# ────────────────────────────────────────────────────────────────────
MAIN_TO_RENDERER = {
    "loadingMessage": "启动加载进度 — message=逗号分隔阶段名",
    "control": "窗口最大化/最小化状态切换 + fail (控制条加载失败) — 子值 _max/_restore/fail",
    "client-setting": "弹窗回调 — libAddOne/projectPathAddOne/changeLibPath/changeProjectPath/libDot/projectPathDot/backupPath",
}


# ────────────────────────────────────────────────────────────────────
# 8. contextBridge 暴露的 window 全局
# ────────────────────────────────────────────────────────────────────
CONTEXT_BRIDGE_GLOBALS = {
    "window.electronAPI": {
        "openWindow(url)": "在新 Electron 窗口里打开 URL",
        "openWindowSelf(url)": "在当前窗口里打开 URL",
        "source": "assets/js/preload.js (主窗口, sandbox=true)",
    },
}
# 注: 主窗口是 sandbox=true + contextIsolation=true, 所以 webContents 内
# typeof require === 'undefined'. 但子窗口 (control.html, client-setting.html)
# nodeIntegration=true + contextIsolation=false, 直接 require('electron') 可用.


def summary() -> dict[str, Any]:
    return {
        "bus_constants": BUS_CONSTANTS,
        "user_script_protocol": USER_SCRIPT_PROTOCOL,
        "electron_ipc_main": ELECTRON_IPC_MAIN,
        "sw_download_stream": SW_DOWNLOAD_STREAM,
        "iframe_topology": IFRAME_TOPOLOGY,
        "api_tier_stats": API_TIER_STATS,
        "main_to_renderer": MAIN_TO_RENDERER,
        "context_bridge_globals": CONTEXT_BRIDGE_GLOBALS,
    }


__all__ = [
    "BUS_CONSTANTS", "USER_SCRIPT_PROTOCOL", "ELECTRON_IPC_MAIN",
    "SW_DOWNLOAD_STREAM", "IFRAME_TOPOLOGY", "API_TIER_STATS",
    "MAIN_TO_RENDERER", "CONTEXT_BRIDGE_GLOBALS",
    "summary",
]


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), ensure_ascii=False, indent=2, default=str))
