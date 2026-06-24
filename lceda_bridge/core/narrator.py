"""narrator — 五感反馈合一 (用户可观可感).

═══════════════════════════════════════════════════════════════════════
  道之第六感: 让用户感受到 agent 的每一步
═══════════════════════════════════════════════════════════════════════

> "音声相和, 前后相随."
> agent 一动, 用户三处皆见: 视(toast/光标/高亮) + 听(beep) + 档(截屏).

本模块是 observer 之上的"播报员":

  on_pre  →  toast: "🤖 即将执行 <action>"  +  beep(info)  +  截屏(可选)
  on_post →  toast: "✓ done in 234ms"      +  beep(ok)
  on_err  →  toast: "✗ <error>"             +  beep(error)  +  截屏存档

这套与 events.jsonl 并行 — 文件给历史, narrator 给现场.

═══════════════════════════════════════════════════════════════════════
  不喧宾, 不夺主
═══════════════════════════════════════════════════════════════════════

> "希言自然." — 老子
> narrator 默认精简: toast 1.8s 自动消失, beep 仅在重要节点.
> 详细事件流仍在 events.jsonl, 不污染 EDA 视野.

═══════════════════════════════════════════════════════════════════════
  解耦设计
═══════════════════════════════════════════════════════════════════════

  Narrator(ui_director, level='normal')
    ├─ before_action(tool_name, summary)
    ├─ after_action(tool_name, ok, duration_ms, summary?)
    ├─ error(tool_name, error_msg)
    ├─ banner(text, ms?)              # 大横幅, 启动/重大事件
    └─ snapshot(tag?)                 # 强制截屏存档

  Narrator 持有 UIDirector 引用. UIDirector 不可用时退化为纯 print.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .ui_director import UIDirector


# 不同 side_effect 用不同的视觉标记
SIDE_EFFECT_ICON = {
    "read":         "🔍",
    "write":        "✏️ ",
    "interactive":  "👆",
    "destructive":  "💥",
}

# 工具名 → 简短中文摘要 (没找到就用名)
TOOL_SUMMARY = {
    "eda.environment.info":     "查看 EDA 环境",
    "eda.project.current":      "读取当前工程",
    "eda.project.list":         "列出全部工程",
    "eda.project.open":         "打开工程",
    "eda.document.list":        "列出文档",
    "eda.document.active":      "读取激活文档",
    "eda.component.search":     "搜索元件",
    "eda.pcb.drc":              "运行 DRC",
    "eda.pcb.export_gerber":    "导出 Gerber",
    "eda.sch.netlist":          "导出网表",
    "eda.bom.export":           "导出 BOM",
    "eda.system.notify":        "EDA 内通知",
    "eda.system.console_log":   "EDA 内日志",
    "eda.system.call":          "调 eda.* API",
    "eda.system.eval":          "沙箱执行 JS",
    "eda.system.introspect":    "EDA 自省",
    "eda.dao.diagnose":         "道直连器诊断",
    "eda.ui.click_text":        "点 UI 文字",
    "eda.ui.click_at":          "点屏幕坐标",
    "eda.ui.type":              "键盘输入",
    "eda.ui.hotkey":            "按快捷键",
    "eda.ui.drag":              "鼠标拖拽",
    "eda.ui.scroll":            "滚轮滚动",
    "eda.ui.screenshot":        "截屏",
    "eda.ui.narrate":           "屏上播报",
    "eda.ui.find":              "扫视屏上可点元素",
}


@dataclass
class NarratorConfig:
    """播报员的节奏 — 默认精简, 可加详细."""
    enable_pre_toast: bool = True       # 操作前弹 toast
    enable_post_toast: bool = True      # 操作后弹简短确认
    enable_error_toast: bool = True
    enable_beep: bool = True
    snapshot_on_pre: bool = False       # 默认不每次截屏 (太多)
    snapshot_on_error: bool = True      # 出错时强制截屏
    snapshot_on_destructive: bool = True  # destructive 工具必截
    pre_toast_ms: int = 1500
    post_toast_ms: int = 1000
    error_toast_ms: int = 4000
    banner_ms: int = 3500


class Narrator:
    """五感播报员. 由 dao_connector 创建, observer 调用."""

    def __init__(
        self,
        ui: Optional["UIDirector"] = None,
        config: Optional[NarratorConfig] = None,
    ):
        self.ui = ui
        self.config = config or NarratorConfig()
        self._action_start: dict[str, float] = {}

    # ── 渠道 ─────────────────────────────────────
    def _toast(self, text: str, ms: int) -> None:
        if self.ui is not None:
            try:
                self.ui.narrate(text, duration_ms=ms)
                return
            except Exception:
                pass
        # 退化: 纯 print
        print(f"[narrator] {text}", flush=True)

    def _beep(self, kind: str) -> None:
        if not self.config.enable_beep or self.ui is None:
            return
        try:
            self.ui.beep(kind)
        except Exception:
            pass

    def _snapshot(self, tag: str) -> None:
        if self.ui is None:
            return
        try:
            ts = time.strftime("%Y%m%d_%H%M%S")
            self.ui.screenshot(save_as=f"{ts}_{tag}.png")
        except Exception:
            pass

    # ── 公共 API ─────────────────────────────────
    def banner(self, text: str, ms: Optional[int] = None) -> None:
        """大横幅 — 启动 / 重大事件."""
        self._toast(text, ms or self.config.banner_ms)
        self._beep("info")

    def before_action(self, tool_name: str, *, side_effect: str = "read",
                       summary: Optional[str] = None) -> None:
        """工具调用前的 toast + beep."""
        self._action_start[tool_name] = time.time()
        if not self.config.enable_pre_toast:
            return
        icon = SIDE_EFFECT_ICON.get(side_effect, "🤖")
        sm = summary or TOOL_SUMMARY.get(tool_name, tool_name)
        self._toast(f"{icon} 即将: {sm}", self.config.pre_toast_ms)
        # 重要操作 beep
        if side_effect in ("write", "interactive", "destructive"):
            self._beep("info" if side_effect != "destructive" else "warn")
        # destructive 操作前强制截屏 (留证据)
        if (self.config.snapshot_on_destructive and side_effect == "destructive") \
                or self.config.snapshot_on_pre:
            self._snapshot(f"pre_{tool_name.replace('.', '_')}")

    def after_action(self, tool_name: str, *, ok: bool, duration_ms: float,
                      side_effect: str = "read", summary: Optional[str] = None) -> None:
        """工具调用后."""
        if ok and not self.config.enable_post_toast:
            return
        if not ok:
            return  # 错误走 error()
        sm = summary or TOOL_SUMMARY.get(tool_name, tool_name)
        d = int(duration_ms)
        self._toast(f"✓ {sm} · {d}ms", self.config.post_toast_ms)
        # destructive 完成后也 beep
        if side_effect == "destructive":
            self._beep("ok")

    def error(self, tool_name: str, error_msg: str, *, summary: Optional[str] = None) -> None:
        """报错."""
        if not self.config.enable_error_toast:
            return
        sm = summary or TOOL_SUMMARY.get(tool_name, tool_name)
        msg = error_msg if len(error_msg) <= 80 else error_msg[:77] + "..."
        self._toast(f"✗ {sm} 失败: {msg}", self.config.error_toast_ms)
        self._beep("error")
        if self.config.snapshot_on_error:
            self._snapshot(f"err_{tool_name.replace('.', '_')}")

    # ── 直接快照 ─────────────────────────────────
    def snapshot(self, tag: str = "manual") -> None:
        self._snapshot(tag)


# ──────────────────────────────────────────────────────────
# 工厂 + 自描述
# ──────────────────────────────────────────────────────────
def attach_to_observer(narrator: Narrator, observer) -> None:
    """把 narrator 装到 observer 上 — observer.hooks.publish 调 narrator.

    observer 会在 on_pre/on_post 时 publish('tool.pre', data), 我们这里
    把 publish 转成 narrator.before_action / after_action.
    """
    orig_publish = observer.hooks.publish

    def relay(event_type: str, data: dict) -> None:
        try:
            tool_name = data.get("tool", "")
            if event_type == "tool.pre":
                narrator.before_action(
                    tool_name,
                    side_effect=data.get("side_effect", "read"),
                )
            elif event_type == "tool.post":
                if data.get("ok"):
                    narrator.after_action(
                        tool_name,
                        ok=True,
                        duration_ms=data.get("duration_ms", 0),
                        side_effect=data.get("side_effect", "read"),
                    )
                else:
                    narrator.error(tool_name, data.get("error") or "(无详情)")
        except Exception:
            pass
        # 链式: 不阻原 publish
        if orig_publish:
            try:
                orig_publish(event_type, data)
            except Exception:
                pass

    observer.hooks.publish = relay


__all__ = ["Narrator", "NarratorConfig", "attach_to_observer",
           "TOOL_SUMMARY", "SIDE_EFFECT_ICON"]


if __name__ == "__main__":
    print("narrator — 五感反馈合一")
    print()
    print("功能:")
    print("  banner(text)        — 大横幅 (启动/重大)")
    print("  before_action(...)  — 操作前 toast+beep+(截屏)")
    print("  after_action(...)   — 操作后简短确认")
    print("  error(...)          — 错误 + 强制截屏")
    print()
    print(f"内置工具摘要: {len(TOOL_SUMMARY)} 条")
