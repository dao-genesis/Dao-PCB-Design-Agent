"""asset_anatomy — 嘉立创EDA assets/ 资源全息表.

D:\\lceda-pro\\resources\\app\\assets\\ 下 22 个子目录, 共 ~60MB JS + 21MB WASM,
是嘉立创EDA 的全部内核. 本模块对每个 asset 给出:
  · 角色 (内核/渲染/工厂端/UI/i18n/...)
  · 哈希指纹版本号 (chameleon/2.1.35.04530fc3)
  · 主要文件大小
  · 加载位置 (主进程/Worker/Service Worker/iframe)
  · 同名 JS bundle 在 modules.lceda.cn 的 CDN URL

用法:
    from core import asset_anatomy as aa
    aa.list_assets()                     # 全部资源 + 大小
    aa.scan_assets(aa.ASSETS_ROOT)       # 现场扫描真实文件 (返回 dict)
    aa.role_of("chameleon")              # 查询某 asset 的角色
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ASSETS_ROOT = Path(r"D:\lceda-pro\resources\app\assets")


# ────────────────────────────────────────────────────────────────────
# 22 个 asset 子目录 — 全部静态事实
# ────────────────────────────────────────────────────────────────────
# 字段:
#   role        中文角色描述
#   layer       前端层级 (main / renderer / worker / sw / iframe / native)
#   key_files   主要文件 (相对 asset 子目录)
#   approx_size 总大小 (字节)
#   cdn_base    modules.lceda.cn 上的 CDN 路径 (在 app.js 中已观测到)
ASSETS: dict[str, dict[str, Any]] = {
    # ── 0 系统级公共 (无版本号) ──
    "view": {
        "role": "Electron 主窗口加载的 HTML 入口",
        "layer": "main-renderer",
        "key_files": ["index.html", "control.html", "dialog.html", "netError.html"],
        "approx_size": 10_100,
        "cdn_base": None,
    },
    "js": {
        "role": "顶层公共 JS (preload + 通用对话框)",
        "layer": "main-renderer",
        "key_files": ["preload.js (electronAPI)", "action.js", "client-setting-action.js",
                      "dialog.template.js", "translate.js", "Drag.js"],
        "approx_size": 36_300,
        "cdn_base": None,
    },
    "css": {
        "role": "全局样式",
        "layer": "main-renderer",
        "key_files": ["style.css"],
        "approx_size": None,
        "cdn_base": None,
    },
    "images": {"role": "全局图片素材", "layer": "main-renderer",
               "key_files": ["eda-loading-gif.gif"], "approx_size": None, "cdn_base": None},
    "icon": {"role": "图标资源", "layer": "main-renderer",
             "key_files": [], "approx_size": None, "cdn_base": None},
    "locale": {"role": "i18n 语言包 (zh-Hans/en)", "layer": "main-renderer",
               "key_files": [], "approx_size": None, "cdn_base": None},

    "db": {
        "role": "★ 离线元件库 + 示例工程",
        "layer": "native",
        "key_files": [
            "lceda-std.elib  (380MB SQLite, 20K components, 16K devices)",
            "example-projects.zip  (22MB)",
        ],
        "approx_size": 420_768_409,
        "cdn_base": None,
    },

    # ── 1 渲染引擎 (PCB/SCH 共用内核) ──
    "pangolin": {
        "role": "★ 穿山甲 — WebGL 渲染引擎主线程 + GUI Worker (基于 dat.GUI/Three.js 衍生)",
        "version": "0.2.32.9e6b87fb",
        "layer": "renderer + worker",
        "key_files": ["index.js (2.6MB)", "GuiWorker.js (2.6MB)", "index.html",
                      "images/"],
        "approx_size": 5_262_604,
        "cdn_base": "modules.lceda.cn/pangolin/0.2.32.9e6b87fb/",
    },

    "occapi": {
        "role": "★ OpenCascade 3D 几何内核 (C++ → WASM, ISO 标准 BREP)",
        "version": "1.2.18.56bae065",
        "layer": "native (WASM)",
        "key_files": ["occapi.wasm (21MB)", "occapi_ex.js (loader)"],
        "approx_size": 21_429_805,
        "cdn_base": "modules.lceda.cn/occapi/1.2.18.56bae065/",
    },

    "jerboa": {
        "role": "★ 跳鼠 — Emscripten 编译的 C++ 计算核心 (推测: 拓扑/约束求解)",
        "version": "0.1.3.098894ce",
        "layer": "renderer (Module ready Promise)",
        "key_files": ["jerboa.js (2.6MB Emscripten 模板 + 嵌入 WASM 二进制 base64)"],
        "approx_size": 2_575_229,
        "cdn_base": "modules.lceda.cn/jerboa/0.1.3.098894ce/",
    },

    "chameleon": {
        "role": "★ 变色龙 — 文件格式变换 Worker (PDF / XLSX / Office XML / docx 转换 BOM)",
        "version": "2.1.35.04530fc3",
        "layer": "worker",
        "key_files": ["chameleon-worker.js (3.7MB, 含 SheetJS XLSX + pdf.js + 大量 mime)"],
        "approx_size": 3_652_185,
        "cdn_base": "modules.lceda.cn/chameleon/2.1.35.04530fc3/js/",
    },

    # ── 2 PCB 引擎 (13 个 JS, 总 ~17MB) ──
    "pro-pcb": {
        "role": "★ PCB 编辑器内核 (引擎 + 4 个 Worker + 3 个查看器)",
        "version": "2.2.32.3.0c4cd1b8",
        "layer": "renderer + worker",
        "key_files": [
            "pcb.js (7.7MB, ★ 主引擎)",
            "pcb-main.js (1.9MB, 主线程协调)",
            "decodeworker.js (2.2MB, .epcb 解码 Worker)",
            "drcWorker.js (1.8MB, DRC 检查 Worker)",
            "ratlineworker.js (1.6MB, 飞线计算 Worker)",
            "pcbRouterWorker.js (0.7MB, 自动布线 Worker)",
            "worker.js (1.7MB, 通用 Worker)",
            "pcb3d.js (0.3MB, 3D 视图)",
            "silkViewer.js (1.4MB, 丝印查看器)",
            "debug.js (1.1MB, 调试器)",
            "jerboa-service.js (16KB, jerboa C++ 内核 + _MSG_BUS_RPC_ 协议库)",
            "zipWorker.js (99KB)",
            "cncViewerPage.js (1KB)",
        ],
        "approx_size": 17_192_592,
        "cdn_base": "modules.lceda.cn/pro-pcb/2.2.32.3.0c4cd1b8/js/",
    },

    "pro-sch": {
        "role": "★ 原理图编辑器内核",
        "version": "2.2.32.3.90a68f64",
        "layer": "renderer + worker",
        "key_files": [
            "sch.js (3.0MB, ★ 主引擎)",
            "sch-main.js (2.9MB, 主线程协调)",
            "worker.js (2KB, 占位)",
        ],
        "approx_size": 5_822_613,
        "cdn_base": "modules.lceda.cn/pro-sch/2.2.32.3.90a68f64/js/",
    },

    # ── 3 工厂端 (SMT 下单) ──
    "smt-gl-engine": {
        "role": "★ 工厂面板 GL 渲染引擎 (PCB 拼板预览)",
        "version": "0.10.274.07368e76",  # 含 0.10.103 旧版回退
        "layer": "renderer + worker",
        "key_files": [
            "smt-gl-engine.js (1.9MB)",
            "worker.js (1.2MB)",
        ],
        "approx_size": 3_108_967,
        "cdn_base": "modules.lceda.cn/smt-gl-engine/0.10.274.07368e76/",
    },

    "smt-ui": {
        "role": "★ 工厂端完整 UI (单文件最大 — 嘉立创下单流程的全部前端)",
        "version": "1.0.12.2f0646a5",
        "layer": "renderer (iframe)",
        "key_files": [
            "smt-ui.js (10.8MB, ★ EDA 内最大单 JS)",
            "eda-welding-tools.js (2.1MB, EDA 内嵌焊接工具)",
            "smt-welding-tools.js (0.6MB, SMT 焊接工具)",
            "jlc-panelize-tool.js (拼板工具)",
            "assets/ (素材)",
        ],
        "approx_size": 13_533_570,
        "cdn_base": "modules.lceda.cn/smt-ui/1.0.12.2f0646a5/",
    },

    # ── 4 工程管理 (Electron preload + ws + cache) ──
    "pro-mgr": {
        "role": "★ 工程管理 (Electron preload, WebSocket, cache worker)",
        "version": "2.2.32.1.a44b17bd",
        "layer": "main-renderer + sw + worker",
        "key_files": [
            "preload.js (30KB, ★ 真正的 Electron preload — 暴露 DOCTYPE/MODULE/Logger/pinSort)",
            "pro-mgr.js (702KB, 工程管理主逻辑)",
            "ws-service.js (33KB, 内部 WebSocket — 含 _MSG_BUS_RPC_ 协议库)",
            "cache-worker.js (684KB, 缓存 Worker)",
        ],
        "approx_size": 1_449_414,
        "cdn_base": "modules.lceda.cn/pro-mgr/2.2.32.1.a44b17bd/js/",
    },

    "pro-sw": {
        "role": "★ Service Worker — 流式下载文件 (Gerber/PDF/BOM)",
        "version": "0.1.4.5d832218",
        "layer": "service-worker",
        "key_files": [
            "sw.js (4.7KB, ★ /sw/download/stream/{create,write,close} 三个 endpoint)",
            "loader.js (99KB, SW 注册器)",
        ],
        "approx_size": 103_717,
        "cdn_base": "modules.lceda.cn/pro-sw/0.1.4.5d832218/js/",
    },

    "pro-ui": {
        "role": "通用 UI 组件 (底栏/3D 查看器/登录注册/CNC 预览)",
        "version": "2.2.32.3.ed5b0549",
        "layer": "renderer",
        "key_files": [
            "ui.js", "bottom.js", "regist.js", "logout.js",
            "pcb3dview.js", "cnc-previewer.js", "cnc-test-page-index.js", "worker.js",
        ],
        "approx_size": None,
        "cdn_base": "modules.lceda.cn/pro-ui/2.2.32.3.ed5b0549/js/",
    },

    "pro-panel": {
        "role": "拼板/面板编辑器",
        "version": "2.2.32.1.0cb05813",
        "layer": "renderer + worker",
        "key_files": ["panel-main.js", "panel.js", "panel-worker.js",
                      "panel-sub-worker.js", "panel3d.js"],
        "approx_size": None,
        "cdn_base": "modules.lceda.cn/pro-panel/2.2.32.1.0cb05813/js/",
    },

    # ── 5 扩展 / AI / OCR ──
    "pro-api": {
        "role": "★ 扩展 API SDK — TS .d.ts + Markdown 文档 + JSON 模型",
        "version": "0.1.79.941a04f4",
        "layer": "documentation",
        "key_files": [
            "api.js (扩展 API 注入)",
            "input/eda.extension.api.json (2.4MB TSDoc 模型, 91 类 / 837 方法)",
            "eda.extension.api.md (125KB)",
        ],
        "approx_size": None,
        "cdn_base": "modules.lceda.cn/pro-api/0.1.79.941a04f4/",
    },

    "pro-chat": {
        "role": "AI 助手对话面板",
        "version": "0.1.10.e0161b48",
        "layer": "renderer (iframe)",
        "key_files": ["chat.js (435KB)"],
        "approx_size": None,
        "cdn_base": "modules.lceda.cn/pro-chat/0.1.10.e0161b48/",
    },

    "ocr-wizard": {
        "role": "OCR 纸图扫描 → 工程 (符号识别 + 模型训练 + PDF 查看)",
        "version": "0.1.15.c5462977",
        "layer": "renderer + worker",
        "key_files": ["ocrSymbol.js", "ocrTraining.js", "pdfViewer.js"],
        "approx_size": None,
        "cdn_base": "modules.lceda.cn/ocr-wizard/0.1.15.c5462977/js/",
    },
}


# ────────────────────────────────────────────────────────────────────
# Workers / Service Worker 总览
# ────────────────────────────────────────────────────────────────────
WORKERS_INVENTORY = {
    "GuiWorker": "pangolin/GuiWorker.js — UI 渲染主 Worker",
    "decodeworker": "pro-pcb/decodeworker.js — .epcb / dataStr 解码",
    "drcWorker": "pro-pcb/drcWorker.js — DRC 设计规则检查",
    "ratlineworker": "pro-pcb/ratlineworker.js — 飞线计算",
    "pcbRouterWorker": "pro-pcb/pcbRouterWorker.js — 自动布线",
    "pcb-worker": "pro-pcb/worker.js — 通用 PCB 计算",
    "zipWorker": "pro-pcb/zipWorker.js — ZIP 打包",
    "smt-gl-worker": "smt-gl-engine/worker.js",
    "chameleon-worker": "chameleon/chameleon-worker.js — PDF/XLSX 转换",
    "cache-worker": "pro-mgr/cache-worker.js — 缓存",
    "ws-service": "pro-mgr/ws-service.js — 内部 WebSocket RPC",
    "panel-worker": "pro-panel/panel-worker.js + panel-sub-worker.js",
    "ui-worker": "pro-ui/worker.js",
    "sch-worker": "pro-sch/worker.js (占位)",
    "service-worker": "pro-sw/sw.js — /sw/download/stream/* 流式下载",
}


# ────────────────────────────────────────────────────────────────────
# 现场扫描 — 真实 file size + version (assets 升级时再读)
# ────────────────────────────────────────────────────────────────────
def scan_assets(root: str | Path = ASSETS_ROOT) -> dict[str, Any]:
    """实地扫描 assets/, 返回每个子目录的真实大小+文件数+第一层子项."""
    p = Path(root)
    if not p.exists():
        raise FileNotFoundError(p)
    out: dict[str, Any] = {"root": str(p), "subdirs": {}}
    for child in sorted(p.iterdir()):
        if not child.is_dir():
            continue
        # 探子版本目录 (xxx.hash 形式)
        versions = [c for c in child.iterdir() if c.is_dir()]
        info = {
            "path": str(child),
            "is_versioned": bool(versions and any("." in v.name for v in versions)),
            "versions": [v.name for v in sorted(versions, key=lambda x: x.name)],
            "files_top": [f.name for f in sorted(child.iterdir())
                          if f.is_file()][:8],
            "total_size": _dir_size(child),
            "file_count": _dir_filecount(child),
        }
        # 注入静态 role
        if child.name in ASSETS:
            info["role"] = ASSETS[child.name]["role"]
            info["layer"] = ASSETS[child.name].get("layer")
        out["subdirs"][child.name] = info
    return out


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def _dir_filecount(p: Path) -> int:
    return sum(1 for f in p.rglob("*") if f.is_file())


def list_assets() -> list[dict[str, Any]]:
    """所有静态登记的 asset, 按 size 降序."""
    out = []
    for name, info in ASSETS.items():
        out.append({
            "name": name,
            "role": info["role"],
            "layer": info.get("layer"),
            "version": info.get("version"),
            "approx_size": info.get("approx_size"),
            "cdn_base": info.get("cdn_base"),
        })
    out.sort(key=lambda r: r.get("approx_size") or 0, reverse=True)
    return out


def role_of(asset_name: str) -> str | None:
    info = ASSETS.get(asset_name)
    return info["role"] if info else None


def summary() -> dict[str, Any]:
    return {
        "root": str(ASSETS_ROOT),
        "asset_count": len(ASSETS),
        "total_approx_bytes": sum(
            (info.get("approx_size") or 0) for info in ASSETS.values()
        ),
        "by_size_desc": list_assets(),
        "workers_inventory": WORKERS_INVENTORY,
    }


__all__ = [
    "ASSETS_ROOT", "ASSETS", "WORKERS_INVENTORY",
    "scan_assets", "list_assets", "role_of", "summary",
]


if __name__ == "__main__":
    print(json.dumps(summary(), ensure_ascii=False, indent=2, default=str))
