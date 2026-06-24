"""
kicad_origin.live — 五脉同体 · 直连本源

"道生一, 一生二, 二生三, 三生万物."

把 KiCad 的全部对外接口收纳为单一 `LiveKiCad` 入口:

    L0 IPC   kipy        ← 运行中 KiCad 的官方 API (KiCad 9+)  · 一等公民
    L1 SWIG  pcbnew      ← 进程内 Python (PCB)                  · 离线
    L2 CLI   kicad-cli   ← 批处理 (sch/pcb/sym/fp/jobset)        · 旁路
    L3 GUI   pywinauto   ← 兜底 (拍按钮, 截图, 拖窗口)            · 兜底
    L4 FILE  S-expr      ← 直改 .kicad_pcb / .kicad_sch         · 离线根

调用方只需:
    from kicad_origin.live import LiveKiCad
    k = LiveKiCad()
    k.open(r"path/to/project.kicad_pro")
    k.erc(r"...kicad_sch", "out.json")
    info = k.info()
    k.snapshot("kicad_main_window.png")

或一键:
    from kicad_origin.live import do_all
    do_all("warehouse_logistics_vehicle")

哲学:
    "无为而无不为" — 调用者不挑通道, LiveKiCad 自适应择优.
    "上善若水, 水善利万物而不争" — 五通道并存, 无优劣, 各善其所.
"""

from __future__ import annotations

from kicad_origin.live.connector import (
    LiveKiCad,
    Channel,
    LiveStatus,
    NotConnected,
)
from kicad_origin.live.config import (
    KiCadConfig,
    enable_ipc_server,
    is_ipc_server_enabled,
    detect_running_kicad,
)
from kicad_origin.live.do import (
    do_status,
    do_connect,
    do_enable_ipc,
    do_open,
    do_erc,
    do_drc,
    do_export,
    do_snap,
    do_inject,
    do_all,
)

__all__ = [
    # facade
    "LiveKiCad", "Channel", "LiveStatus", "NotConnected",
    # config
    "KiCadConfig", "enable_ipc_server", "is_ipc_server_enabled", "detect_running_kicad",
    # one-shot actions
    "do_status", "do_connect", "do_enable_ipc",
    "do_open", "do_erc", "do_drc", "do_export", "do_snap",
    "do_inject", "do_all",
]
