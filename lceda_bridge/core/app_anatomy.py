"""app_anatomy — 嘉立创EDA Electron 主进程解剖.

锚定本源, 把 D:\\lceda-pro\\resources\\app\\app.js (2.3 MB 打包后代码) 中的:
  · ipcMain channels   (主进程暴露的 IPC 通道)
  · app.on 事件        (生命周期 hook)
  · protocol 注册      (https/http/app:// 接管)
  · BrowserWindow 主窗口 webPreferences
  · Node.js 原生模块导入清单
  · 网络端点 (lceda/jlc/szlcsc/jlcpcb 等域名)

这些静态事实, 沉淀为可查的 Python 数据 + 现场 grep 验证器.

用法:
    from core import app_anatomy as a
    a.summary()                       # 全部静态事实
    a.scan_app_js(a.LCEDA_APP_JS)     # 现场再 grep 验证 (返回完整 dict)
    a.find_pattern(r'foo')            # 临场探查任意正则
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

LCEDA_APP_JS = Path(r"D:\lceda-pro\resources\app\app.js")


# ────────────────────────────────────────────────────────────────────
# 1. ipcMain channels (Renderer → Main 主进程暴露的全部 4 个通道)
# ────────────────────────────────────────────────────────────────────
# Electron 主进程仅注册了 4 个对外通道, 远比社区预期的"几十个"少 —
# 因为前端是 https://pro.lceda.cn/editor 的云端 Web 应用 (经 protocol.handle
# 拦截后路由到本地 assets), 真正的业务调用走 _MSG_BUS_RPC_ + ws-service,
# Electron 主进程仅承担 ① 窗口控制 ② 偏好设置 ③ 新窗口打开 三件事.
IPC_MAIN_CHANNELS: dict[str, dict[str, str]] = {
    "control": {
        "method": "on",
        "purpose": "主窗口控制 — _min/_max/_close/_restore/_settings",
        "renderer": "assets/view/control.html",
    },
    "client-setting": {
        "method": "on",
        "purpose": "客户端偏好设置 — libPath / projectPath / backupPath / clientMode",
        "renderer": "assets/js/client-setting-action.js",
        "cmds": ", ".join([
            "_settings", "Confirm", "Cancel", "cancel", "close",
            "libAddOne", "libDelOne", "libDot",
            "projectPathAddOne", "projectPathDelOne",
            "projectPathMoveUp", "projectPathMoveDown",
            "projectPathDot", "changeLibPath", "changeProjectPath",
            "changeLaunchType", "backupPath",
        ]),
    },
    "openWindow": {
        "method": "on",
        "purpose": "在新窗口中打开 URL",
        "renderer": "assets/js/preload.js (electronAPI.openWindow)",
    },
    "openWindowSelf": {
        "method": "on",
        "purpose": "在当前窗口中打开 URL",
        "renderer": "assets/js/preload.js (electronAPI.openWindowSelf)",
    },
}


# ────────────────────────────────────────────────────────────────────
# 2. app 生命周期事件
# ────────────────────────────────────────────────────────────────────
APP_EVENTS: dict[str, str] = {
    "browser-window-created": "新窗口创建 hook (注入控制条)",
    "certificate-error": "lceda.cn|easyeda.com 域名强制信任证书 (绕开内网代理证书问题)",
    "child-process-gone": "子进程崩溃 (GPU/utility) 处理",
    "open-file": "macOS Dock 拖文件: 把路径 push 到 process.argv",
    "second-instance": "已运行时再次启动 → 复用首实例 + 把 argv 转发",
    "window-all-closed": "全部窗口关闭 → 清临时目录 + app.exit()",
}


# ────────────────────────────────────────────────────────────────────
# 3. 自定义 protocol (Electron 接管整个 https 网络栈是关键!)
# ────────────────────────────────────────────────────────────────────
PROTOCOL_REGISTRATIONS: dict[str, str] = {
    "registerSchemesAsPrivileged([{scheme:'app',privileges:{supportFetchAPI:true,stream:true}}])":
        "声明 app:// 为特权 scheme (允许 fetch/stream)",
    "protocol.handle('https')":
        "★ 接管全部 https 请求 — 把 https://pro.lceda.cn/* 路由到本地 assets",
    "protocol.handle('http')":
        "接管 http (兼容)",
    "protocol.interceptBufferProtocol('https')":
        "旧版兼容 (Electron < 25)",
    "protocol.interceptBufferProtocol('http')":
        "旧版兼容",
    "protocol.registerStringProtocol('app')":
        "app:// 字符串协议处理",
}

# 不抢系统级 URL 协议 (no setAsDefaultProtocolClient call) ─ 即不在 Windows
# 注册表里写 lceda://. 工程 .eprj 是双击 → file association 触发 open-file.


# ────────────────────────────────────────────────────────────────────
# 4. 主 BrowserWindow webPreferences (现代 Electron 安全配置)
# ────────────────────────────────────────────────────────────────────
MAIN_WINDOW_WEB_PREFERENCES: dict[str, Any] = {
    "nodeIntegration": False,           # 不在 renderer 里直接暴露 require()
    "contextIsolation": True,           # contextBridge 隔离
    "nodeIntegrationInWorker": False,
    "nodeIntegrationInSubFrames": False,
    "sandbox": True,                    # 沙箱
    "webSecurity": False,               # ⚠ 关了同源策略 (允许跨域)
    "enableWebSQL": False,
    "spellcheck": False,
    "preload": "assets/js/preload.js",  # contextBridge 暴露 electronAPI
}

# 子窗口/对话框 (control.html, client-setting.html 等) 用更宽配置:
DIALOG_WINDOW_WEB_PREFERENCES: dict[str, Any] = {
    "nodeIntegration": True,            # ⚠ 子窗口直接 require('electron')
    "contextIsolation": False,
    "webSecurity": False,
}


# ────────────────────────────────────────────────────────────────────
# 5. Node.js 原生模块导入 (16 个 stdlib + 1 个 native sqlite3)
# ────────────────────────────────────────────────────────────────────
NODE_REQUIRES = [
    "buffer", "child_process", "crypto", "electron", "events",
    "fs", "http", "https", "os", "path", "querystring",
    "sqlite3",      # ★ node_modules/sqlite3/ — 唯一的 native addon
    "stream", "url", "util", "zlib",
]


# ────────────────────────────────────────────────────────────────────
# 6. 网络端点
# ────────────────────────────────────────────────────────────────────
# 嘉立创 EDA 子域:
LCEDA_DOMAINS = {
    "pro.lceda.cn":      "★ 编辑器主入口 (Electron 加载的 URL)",
    "client.lceda.cn":   "客户端 host 标识",
    "image.lceda.cn":    "图片资源 (元件预览/3D 模型缩略图)",
    "modules.lceda.cn":  "★ JS 模块 CDN (pcb.js/sch.js 等都来自这里)",
    "prodocs.lceda.cn":  "在线文档 (扩展 API 参考)",
}

# 工厂端 (jlc.com 系):
JLC_DOMAINS = {
    "www.jlc.com":          "嘉立创工厂主站",
    "tools.jlc.com":        "工具集 (阻抗计算等)",
    "3d.jlcpcb.com":        "3D 板预览",
    # jlc-assistant 内还有: helper.jlc.com (CAS 登录), passport.jlc.com (账号)
}

# LCSC 商城 (szlcsc.com 系):
LCSC_DOMAINS = {
    "www.szlcsc.com":       "立创商城",
    "atta.szlcsc.com":      "datasheet PDF / 附件",
    "club.szlcsc.com":      "立创社区",
    "dos.szlcsc.com":       "DFM 在线服务 (面板拼版)",
}


# ────────────────────────────────────────────────────────────────────
# 7. SQLite schema 规模 (从 app.js 内嵌的迁移脚本统计)
# ────────────────────────────────────────────────────────────────────
SQLITE_SCHEMA_STATS = {
    "create_table_total": 36,    # 含历次迁移的 _tmp 表
    "create_table_unique": 30,   # 终态独立表名
    "create_index": 25,
    "create_unique_index": 19,
    "create_view": 0,
    "create_trigger": 0,
}


# ────────────────────────────────────────────────────────────────────
# 8. 现场扫描 (fresh re-scan, 用于 app.js 升级后验证)
# ────────────────────────────────────────────────────────────────────
def scan_app_js(path: str | Path = LCEDA_APP_JS) -> dict[str, Any]:
    """读 app.js, 实时再 grep 全部已知模式, 与静态 const 对照."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8", errors="ignore")
    return {
        "path": str(p),
        "size_bytes": p.stat().st_size,
        "ipc_main_channels": _grep_unique(text, r'ipcMain\.(?:handle|on|once)\("([^"]+)"'),
        "app_events": _grep_unique(text, r'app\.on\("([^"]+)"'),
        "protocol_calls": _grep_unique(text, r'protocol\.(\w+)'),
        "node_requires": sorted(set(re.findall(
            r'require\("([a-z][a-z0-9_/-]+)"\)', text))),
        "sqlite_create": {
            "create_table": len(re.findall(r"CREATE TABLE", text)),
            "create_index": len(re.findall(r"CREATE INDEX", text)),
            "create_unique_index": len(re.findall(r"CREATE UNIQUE", text)),
            "create_view": len(re.findall(r"CREATE VIEW", text)),
            "create_trigger": len(re.findall(r"CREATE TRIGGER", text)),
        },
        "lceda_urls": _grep_unique(text, r'(https?://[a-zA-Z0-9.\-]+\.lceda\.cn[^"\'\s]*)'),
        "jlc_urls":   _grep_unique(text, r'(https?://[a-zA-Z0-9.\-]+\.jlc\.com[^"\'\s]*)'),
        "lcsc_urls":  _grep_unique(text, r'(https?://[a-zA-Z0-9.\-]+\.szlcsc\.com[^"\'\s]*)'),
    }


def find_pattern(pattern: str, path: str | Path = LCEDA_APP_JS,
                 limit: int = 50) -> list[str]:
    """临场任意正则探查 app.js."""
    p = Path(path)
    text = p.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(pattern, text)
    out: list[str] = []
    seen: set[str] = set()
    for m in matches:
        s = m if isinstance(m, str) else " | ".join(m)
        if s not in seen:
            seen.add(s)
            out.append(s)
            if len(out) >= limit:
                break
    return out


def _grep_unique(text: str, pattern: str) -> list[str]:
    return sorted(set(re.findall(pattern, text)))


# ────────────────────────────────────────────────────────────────────
# 9. 概览
# ────────────────────────────────────────────────────────────────────
def summary() -> dict[str, Any]:
    return {
        "source": str(LCEDA_APP_JS),
        "ipc_main_channels": IPC_MAIN_CHANNELS,
        "app_events": APP_EVENTS,
        "protocol_registrations": PROTOCOL_REGISTRATIONS,
        "main_window_web_prefs": MAIN_WINDOW_WEB_PREFERENCES,
        "dialog_window_web_prefs": DIALOG_WINDOW_WEB_PREFERENCES,
        "node_requires": NODE_REQUIRES,
        "lceda_domains": LCEDA_DOMAINS,
        "jlc_domains": JLC_DOMAINS,
        "lcsc_domains": LCSC_DOMAINS,
        "sqlite_schema_stats": SQLITE_SCHEMA_STATS,
    }


__all__ = [
    "LCEDA_APP_JS",
    "IPC_MAIN_CHANNELS", "APP_EVENTS", "PROTOCOL_REGISTRATIONS",
    "MAIN_WINDOW_WEB_PREFERENCES", "DIALOG_WINDOW_WEB_PREFERENCES",
    "NODE_REQUIRES", "LCEDA_DOMAINS", "JLC_DOMAINS", "LCSC_DOMAINS",
    "SQLITE_SCHEMA_STATS",
    "scan_app_js", "find_pattern", "summary",
]


if __name__ == "__main__":
    print(json.dumps(summary(), ensure_ascii=False, indent=2, default=str))
