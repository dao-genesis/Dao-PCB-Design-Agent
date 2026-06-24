"""ui_director — 道之 UI 导演 (反者道之动 · 真模拟用户操作 · 用户五感可观可感).

═══════════════════════════════════════════════════════════════════════
  核心理念
═══════════════════════════════════════════════════════════════════════

我之前做的 dao_connector + tools_registry 是 **API-level** —
直调 `eda.dmp.placeComponent({...})`, 跳过 UI, 用户看不见.

本模块是 **UI-level** — 真正模拟用户操作:

  1. 鼠标真的发出去 (CDP Input.dispatchMouseEvent — Electron 内核接收)
  2. 键盘真的发出去 (CDP Input.dispatchKeyEvent)
  3. 用户在 EDA 窗口里 **看见** 鼠标光标移动 / 按钮被按下 / 菜单弹开 / 字符出现
  4. 慢动作 (默认 600ms/移动, 50ms/字符), 让用户看清 agent 在做什么
  5. EDA 内注入虚拟光标 div (红色大圆点 + CSS transition), 移动轨迹可见
  6. 操作前高亮目标 DOM (1秒红框), 然后 dispatch 事件

═══════════════════════════════════════════════════════════════════════
  五感映射
═══════════════════════════════════════════════════════════════════════

  视-1: 虚拟光标 (`__dao_cursor__` div, 屏幕上跟随)
  视-2: 目标高亮 (operate 前 outline + 阴影)
  视-3: toast 横幅 ("即将执行: 点击 [打开]")
  视-4: 截屏存档 (~/.lceda_dao/screenshots/)
  听:   winsound.MessageBeep (关键节点)
  触觉(虚): 慢动作时序, 让用户感到节奏

═══════════════════════════════════════════════════════════════════════
  技术要点
═══════════════════════════════════════════════════════════════════════

  * 嘉立创 EDA 是 Electron, 主 page 占满整个窗口, 内含 frames[1..3]
  * CDP Input.dispatchMouseEvent 发到主 page, 浏览器内核会自动 hit-test
    路由到 frame, 与真实鼠标事件无差别
  * 不会移动 OS 真鼠标 (不会干扰用户)
  * 但用户能在 EDA 窗口看见效果: 按钮按下, 菜单弹开, 对话框出现
  * 加上 DOM 虚拟光标层 → 视觉上"鼠标在动"

═══════════════════════════════════════════════════════════════════════
  道之三言
═══════════════════════════════════════════════════════════════════════

  > "上善若水. 水善利万物而不争, 处众人之所恶, 故几于道."
  > UI 导演不替用户决策, 只忠实代行. 所行之事, 用户处处可见.

  > "希言自然. 故飘风不终朝, 骤雨不终日."
  > 慢动作非低效, 是让用户感受得到. 节奏即道.

  > "为学日益, 为道日损. 损之又损, 以至于无为."
  > 此层不堆 API, 只损至 6 个原语: move/click/type/key/drag/wheel.
  > 一切复杂动作皆由此 6 原语合成. 至简, 故无所不为.
"""
from __future__ import annotations

import base64
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .cdp_transport import BusTransport, CdpTransport


# ──────────────────────────────────────────────────────────
# 键盘特殊键映射 (CDP key + windowsVirtualKeyCode)
# https://chromedevtools.github.io/devtools-protocol/tot/Input/#method-dispatchKeyEvent
# ──────────────────────────────────────────────────────────
SPECIAL_KEYS: dict[str, dict[str, Any]] = {
    "Enter":      {"key": "Enter",      "code": "Enter",      "windowsVirtualKeyCode": 13,  "text": "\r"},
    "Return":     {"key": "Enter",      "code": "Enter",      "windowsVirtualKeyCode": 13,  "text": "\r"},
    "Escape":     {"key": "Escape",     "code": "Escape",     "windowsVirtualKeyCode": 27},
    "Esc":        {"key": "Escape",     "code": "Escape",     "windowsVirtualKeyCode": 27},
    "Tab":        {"key": "Tab",        "code": "Tab",        "windowsVirtualKeyCode": 9,   "text": "\t"},
    "Backspace":  {"key": "Backspace",  "code": "Backspace",  "windowsVirtualKeyCode": 8},
    "Delete":     {"key": "Delete",     "code": "Delete",     "windowsVirtualKeyCode": 46},
    "Space":      {"key": " ",          "code": "Space",      "windowsVirtualKeyCode": 32,  "text": " "},
    "ArrowUp":    {"key": "ArrowUp",    "code": "ArrowUp",    "windowsVirtualKeyCode": 38},
    "ArrowDown":  {"key": "ArrowDown",  "code": "ArrowDown",  "windowsVirtualKeyCode": 40},
    "ArrowLeft":  {"key": "ArrowLeft",  "code": "ArrowLeft",  "windowsVirtualKeyCode": 37},
    "ArrowRight": {"key": "ArrowRight", "code": "ArrowRight", "windowsVirtualKeyCode": 39},
    "Home":       {"key": "Home",       "code": "Home",       "windowsVirtualKeyCode": 36},
    "End":        {"key": "End",        "code": "End",        "windowsVirtualKeyCode": 35},
    "PageUp":     {"key": "PageUp",     "code": "PageUp",     "windowsVirtualKeyCode": 33},
    "PageDown":   {"key": "PageDown",   "code": "PageDown",   "windowsVirtualKeyCode": 34},
    **{f"F{i}": {"key": f"F{i}", "code": f"F{i}", "windowsVirtualKeyCode": 111 + i} for i in range(1, 13)},
}

MODIFIER_BITS = {"alt": 1, "ctrl": 2, "control": 2, "meta": 4, "cmd": 4, "shift": 8}


def _modifiers_to_int(mods: list[str] | None) -> int:
    if not mods:
        return 0
    return sum(MODIFIER_BITS.get(m.lower(), 0) for m in mods)


# ──────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────
@dataclass
class UIConfig:
    """UI 导演的节奏配置 — 控制可观感."""
    move_duration_ms: int = 600        # 鼠标移动到目标的 CSS 过渡时长
    click_dwell_ms: int = 120          # 按下到松开的停留 (让用户看清按下的瞬间)
    drag_segment_ms: int = 80          # 拖拽中每帧间隔
    drag_segments: int = 6             # 拖拽分多少帧
    type_delay_ms: int = 60            # 每字符键盘事件间隔
    highlight_ms: int = 800            # 高亮 DOM 的持续时长
    cursor_size_px: int = 28           # 虚拟光标大小
    cursor_color: str = "rgba(255,80,80,.75)"
    cursor_glow: str = "0 0 18px 6px rgba(255,80,80,.55)"
    enable_beep: bool = True           # Windows 系统 beep
    enable_cursor: bool = True         # 是否注入虚拟光标
    screenshot_dir: Optional[Path] = None  # 截屏归档目录


# ──────────────────────────────────────────────────────────
# DOM 注入: 虚拟光标 + toast + 高亮
# ──────────────────────────────────────────────────────────
_INSTALL_OVERLAY_JS = r"""
(() => {
  if (window.__DAO_OVERLAY_INSTALLED__) return 'already';
  const cfg = __CFG__;
  // ── 虚拟光标 ─────────────────────────────────────
  const cur = document.createElement('div');
  cur.id = '__dao_cursor__';
  cur.style.cssText = `
    position: fixed; left: -100px; top: -100px;
    width: ${cfg.size}px; height: ${cfg.size}px;
    margin-left: -${cfg.size/2}px; margin-top: -${cfg.size/2}px;
    border-radius: 50%; background: ${cfg.color};
    box-shadow: ${cfg.glow}; pointer-events: none;
    z-index: 2147483646; opacity: 0;
    transition: left ${cfg.move_ms}ms cubic-bezier(.4,.0,.2,1),
                top ${cfg.move_ms}ms cubic-bezier(.4,.0,.2,1),
                opacity 200ms ease, transform 100ms ease;
  `;
  document.body.appendChild(cur);

  // ── toast 横幅 (顶部居中) ───────────────────────
  const toast = document.createElement('div');
  toast.id = '__dao_toast__';
  toast.style.cssText = `
    position: fixed; top: 18px; left: 50%; transform: translateX(-50%);
    min-width: 320px; max-width: 80vw; padding: 12px 22px;
    background: linear-gradient(135deg,#1f2937,#111827);
    color:#f0f9ff; font:600 14px/1.5 -apple-system,BlinkMacSystemFont,'Microsoft YaHei',sans-serif;
    border-radius: 10px; box-shadow: 0 8px 32px rgba(0,0,0,.45);
    border: 1px solid rgba(96,165,250,.4);
    z-index: 2147483647; opacity: 0;
    transition: opacity .25s ease, transform .25s ease;
    pointer-events: none;
  `;
  toast.innerHTML = '<span style="margin-right:8px">🤖</span><span id="__dao_toast_text__"></span>';
  document.body.appendChild(toast);

  // ── 高亮框 ──────────────────────────────────────
  const hl = document.createElement('div');
  hl.id = '__dao_highlight__';
  hl.style.cssText = `
    position: fixed; pointer-events: none; z-index: 2147483645;
    border: 3px solid #ef4444; background: rgba(239,68,68,.12);
    box-shadow: 0 0 0 6px rgba(239,68,68,.25), inset 0 0 16px rgba(239,68,68,.3);
    border-radius: 4px; opacity: 0;
    transition: all .25s cubic-bezier(.4,.0,.2,1);
  `;
  document.body.appendChild(hl);

  // ── API 函数 ────────────────────────────────────
  window.__DAO_OVERLAY__ = {
    moveCursor(x, y) {
      cur.style.opacity = '1';
      cur.style.left = x + 'px';
      cur.style.top = y + 'px';
    },
    pulseCursor() {
      cur.style.transform = 'scale(.6)';
      setTimeout(() => { cur.style.transform = 'scale(1)'; }, 100);
    },
    hideCursor() { cur.style.opacity = '0'; },
    toast(text, ms) {
      document.getElementById('__dao_toast_text__').textContent = text;
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(-50%) translateY(0)';
      clearTimeout(window.__dao_toast_t);
      window.__dao_toast_t = setTimeout(() => {
        toast.style.opacity = '0';
      }, ms || 1800);
    },
    highlightRect(x, y, w, h, ms) {
      hl.style.left = x + 'px';
      hl.style.top = y + 'px';
      hl.style.width = w + 'px';
      hl.style.height = h + 'px';
      hl.style.opacity = '1';
      clearTimeout(window.__dao_hl_t);
      window.__dao_hl_t = setTimeout(() => { hl.style.opacity = '0'; }, ms || 800);
    },
    highlightSelector(sel, ms) {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      this.highlightRect(r.left, r.top, r.width, r.height, ms);
      return { x: r.left + r.width/2, y: r.top + r.height/2,
               w: r.width, h: r.height, text: (el.innerText||'').slice(0,80) };
    }
  };
  window.__DAO_OVERLAY_INSTALLED__ = true;
  return 'installed';
})()
"""


# ──────────────────────────────────────────────────────────
# UIDirector
# ──────────────────────────────────────────────────────────
class UIDirector:
    """UI 导演 — 用户在 EDA 窗口可见的代行者.

    底层走 BusTransport.cdp (CdpTransport) 的 _send_cmd / evaluate.

    用法:
        from core.ui_director import UIDirector
        ui = UIDirector(bus)
        ui.install_overlay()
        ui.narrate("打开元件搜索面板")
        ui.click(800, 24)              # 工具栏
        ui.type("电阻")
        ui.press("Enter")
    """

    def __init__(self, bus: "BusTransport", config: Optional[UIConfig] = None):
        self.bus = bus
        self.cdp: "CdpTransport" = bus.cdp
        self.config = config or UIConfig()
        self._overlay_installed = False
        if self.config.screenshot_dir is None:
            self.config.screenshot_dir = Path.home() / ".lceda_dao" / "screenshots"
        self.config.screenshot_dir.mkdir(parents=True, exist_ok=True)

    # ── 底层 CDP send 简便 ─────────────────────────
    def _cdp(self, method: str, params: dict | None = None) -> Any:
        resp = self.cdp._send_cmd(method, params or {})
        if "error" in resp:
            raise RuntimeError(f"CDP {method} failed: {resp['error']}")
        return resp.get("result")

    # ── overlay 注入 ────────────────────────────────
    def install_overlay(self) -> None:
        """注入 DOM overlay (虚拟光标 + toast + 高亮框). 幂等."""
        if self._overlay_installed:
            return
        cfg = {
            "size": self.config.cursor_size_px,
            "color": self.config.cursor_color,
            "glow": self.config.cursor_glow,
            "move_ms": self.config.move_duration_ms,
        }
        js = _INSTALL_OVERLAY_JS.replace("__CFG__", json.dumps(cfg))
        try:
            r = self.cdp.evaluate(js)
            self._overlay_installed = True
        except Exception as e:
            # overlay 不是关键路径, 失败也不影响真鼠标键盘
            print(f"[ui_director] overlay 注入失败 (非关键): {e}", file=sys.stderr)

    def _safe_evaluate(self, js: str) -> Any:
        """走主 page 的 Runtime.evaluate, 异常吞掉 (overlay 操作不重要)."""
        try:
            return self.cdp.evaluate(js)
        except Exception:
            return None

    # ──────────────────────────────────────────────
    # 五感反馈
    # ──────────────────────────────────────────────
    def narrate(self, text: str, duration_ms: Optional[int] = None) -> None:
        """在 EDA 顶部弹一条 toast (用户能看见)."""
        self.install_overlay()
        ms = duration_ms or 1800
        js = f"window.__DAO_OVERLAY__ && window.__DAO_OVERLAY__.toast({json.dumps(text)}, {ms})"
        self._safe_evaluate(js)

    def beep(self, kind: str = "info") -> None:
        """系统提示音 (Windows). info/warn/error/ok."""
        if not self.config.enable_beep:
            return
        try:
            import winsound  # type: ignore
            mapping = {
                "info": winsound.MB_ICONASTERISK,
                "warn": winsound.MB_ICONEXCLAMATION,
                "error": winsound.MB_ICONHAND,
                "ok": winsound.MB_OK,
            }
            winsound.MessageBeep(mapping.get(kind, winsound.MB_OK))
        except Exception:
            pass

    def screenshot(self, save_as: Optional[str] = None) -> bytes:
        """截 EDA 当前画面 (Page.captureScreenshot CDP). 返 PNG bytes; 同时存档."""
        r = self._cdp("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        b64 = r.get("data") if r else None
        if not b64:
            raise RuntimeError("截屏失败 (no data)")
        data = base64.b64decode(b64)
        # 存档
        ts = time.strftime("%Y%m%d_%H%M%S")
        name = save_as or f"shot_{ts}_{int(time.time()*1000)%1000:03d}.png"
        path = self.config.screenshot_dir / name
        path.write_bytes(data)
        return data

    def highlight(self, selector: str, duration_ms: Optional[int] = None) -> Optional[dict]:
        """在 EDA 中高亮某 DOM 元素 (CSS selector). 返中心坐标."""
        self.install_overlay()
        ms = duration_ms or self.config.highlight_ms
        js = (
            f"window.__DAO_OVERLAY__ && "
            f"window.__DAO_OVERLAY__.highlightSelector({json.dumps(selector)}, {ms})"
        )
        return self._safe_evaluate(js)

    def highlight_rect(self, x: float, y: float, w: float = 24, h: float = 24, duration_ms: Optional[int] = None) -> None:
        """在屏幕坐标画红框 (用于点击前提示)."""
        self.install_overlay()
        ms = duration_ms or self.config.highlight_ms
        # 框居中于 (x,y), 边长至少 28
        bw = max(w, 28); bh = max(h, 28)
        bx = x - bw/2; by = y - bh/2
        js = (
            f"window.__DAO_OVERLAY__ && "
            f"window.__DAO_OVERLAY__.highlightRect({bx},{by},{bw},{bh},{ms})"
        )
        self._safe_evaluate(js)

    # ──────────────────────────────────────────────
    # 鼠标 (走 CDP Input.dispatchMouseEvent)
    # ──────────────────────────────────────────────
    def move_to(self, x: int, y: int, duration_ms: Optional[int] = None, *, settle_ms: int = 50) -> None:
        """鼠标移到 (x,y). 虚拟光标走 CSS transition (用户可见), 真事件直接到位."""
        self.install_overlay()
        dur = duration_ms if duration_ms is not None else self.config.move_duration_ms
        # 1. DOM 虚拟光标走 transition
        if self.config.enable_cursor:
            self._safe_evaluate(
                f"window.__DAO_OVERLAY__ && window.__DAO_OVERLAY__.moveCursor({x},{y})"
            )
        # 2. 等动画走完
        if dur > 0:
            time.sleep(dur / 1000)
        # 3. 发真鼠标 mouseMoved 事件 (告诉 EDA 内核鼠标在 x,y, 触发 hover 等)
        self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y, "button": "none",
        })
        if settle_ms:
            time.sleep(settle_ms / 1000)

    def click(self, x: int, y: int, *, button: str = "left", clicks: int = 1,
              modifiers: list[str] | None = None, highlight: bool = True) -> None:
        """点 (x,y). 含: 虚拟光标移动 → 高亮 → 按下 → dwell → 松开."""
        self.move_to(x, y)
        if highlight:
            self.highlight_rect(x, y, 36, 36, duration_ms=self.config.click_dwell_ms + 200)
            time.sleep(0.15)  # 让用户看清高亮
        mods = _modifiers_to_int(modifiers)
        # mousePressed
        self._cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": button, "buttons": 1 if button == "left" else (2 if button == "right" else 4),
            "clickCount": clicks, "modifiers": mods,
        })
        # 按下脉冲
        if self.config.enable_cursor:
            self._safe_evaluate("window.__DAO_OVERLAY__ && window.__DAO_OVERLAY__.pulseCursor()")
        time.sleep(self.config.click_dwell_ms / 1000)
        # mouseReleased
        self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": button, "buttons": 0,
            "clickCount": clicks, "modifiers": mods,
        })

    def double_click(self, x: int, y: int, **kw) -> None:
        self.click(x, y, clicks=2, **kw)

    def right_click(self, x: int, y: int, **kw) -> None:
        kw.pop("button", None)
        self.click(x, y, button="right", **kw)

    def drag(self, x1: int, y1: int, x2: int, y2: int, *, button: str = "left",
             segments: Optional[int] = None, segment_ms: Optional[int] = None) -> None:
        """从 (x1,y1) 拖到 (x2,y2). 多帧 mouseMoved 让用户看见移动."""
        seg = segments or self.config.drag_segments
        sms = segment_ms or self.config.drag_segment_ms
        self.move_to(x1, y1)
        # 按下
        self._cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x1, "y": y1,
            "button": button, "buttons": 1, "clickCount": 1,
        })
        # 中间帧
        for i in range(1, seg + 1):
            t = i / seg
            xi = int(x1 + (x2 - x1) * t)
            yi = int(y1 + (y2 - y1) * t)
            if self.config.enable_cursor:
                self._safe_evaluate(
                    f"window.__DAO_OVERLAY__ && window.__DAO_OVERLAY__.moveCursor({xi},{yi})"
                )
            self._cdp("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": xi, "y": yi,
                "button": button, "buttons": 1,
            })
            time.sleep(sms / 1000)
        # 松开
        self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x2, "y": y2,
            "button": button, "buttons": 0, "clickCount": 1,
        })

    def scroll(self, x: int, y: int, delta_y: int, delta_x: int = 0) -> None:
        """在 (x,y) 滚轮. delta_y 正向为下滚 (内容上移)."""
        self.move_to(x, y, duration_ms=200)
        self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": x, "y": y,
            "deltaX": delta_x, "deltaY": delta_y,
            "button": "none",
        })

    # ──────────────────────────────────────────────
    # 键盘 (走 CDP Input.dispatchKeyEvent)
    # ──────────────────────────────────────────────
    def type_text(self, text: str, *, delay_ms: Optional[int] = None) -> None:
        """逐字符敲键盘. 用 type='char' (合 IME 友好)."""
        d = delay_ms if delay_ms is not None else self.config.type_delay_ms
        for ch in text:
            self._cdp("Input.dispatchKeyEvent", {
                "type": "char", "text": ch,
            })
            if d > 0:
                time.sleep(d / 1000)

    def press(self, key: str, modifiers: list[str] | None = None) -> None:
        """按一下功能键. 例: press('Enter') / press('s', ['ctrl']) / press('F2')."""
        mods = _modifiers_to_int(modifiers)
        spec = SPECIAL_KEYS.get(key)
        if spec is None:
            # 普通字母/数字
            ch = key
            spec = {"key": ch, "code": f"Key{ch.upper()}" if ch.isalpha() else ch,
                    "text": ch, "windowsVirtualKeyCode": ord(ch.upper()) if ch.isalnum() else 0}
        # keyDown
        params_down = {"type": "keyDown", "modifiers": mods, **spec}
        # 带修饰符时 char 不发 text (避免 ctrl+s 输出 's')
        if mods:
            params_down.pop("text", None)
        self._cdp("Input.dispatchKeyEvent", params_down)
        time.sleep(self.config.click_dwell_ms / 2 / 1000)
        # keyUp
        params_up = {"type": "keyUp", "modifiers": mods, **spec}
        params_up.pop("text", None)
        self._cdp("Input.dispatchKeyEvent", params_up)

    def hotkey(self, *keys: str) -> None:
        """组合键. 例: hotkey('ctrl','s') / hotkey('ctrl','shift','z').
        最后一个是主键, 其余是修饰符."""
        if not keys:
            return
        mods = list(keys[:-1])
        main = keys[-1]
        self.press(main, modifiers=mods)

    # ──────────────────────────────────────────────
    # 高层语义 (基于 6 原语合成)
    # ──────────────────────────────────────────────
    def click_text(self, text: str, *, exact: bool = False, nth: int = 0,
                   tag_filter: Optional[str] = None) -> dict:
        """在 EDA DOM 里找带某文字的可点击元素并点它.
        返回点击位置信息. 找不到抛 RuntimeError."""
        self.install_overlay()
        # 用 JS 在 EDA 内自找
        find_js = f"""
        (() => {{
          const txt = {json.dumps(text)};
          const exact = {str(exact).lower()};
          const nth = {nth};
          const tags = {json.dumps(tag_filter.split(',') if tag_filter else ['button','a','div','span','li','td'])};
          const all = [];
          for (const tag of tags) {{
            for (const el of document.getElementsByTagName(tag)) {{
              const t = (el.innerText || el.textContent || '').trim();
              if (!t) continue;
              if (exact ? t === txt : t.includes(txt)) {{
                const r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                all.push({{
                  tag, text: t.slice(0,80),
                  x: r.left + r.width/2, y: r.top + r.height/2,
                  w: r.width, h: r.height,
                }});
              }}
            }}
          }}
          // 去重 (相同坐标)
          const seen = new Set();
          const uniq = all.filter(e => {{
            const k = `${{Math.round(e.x)}},${{Math.round(e.y)}}`;
            if (seen.has(k)) return false; seen.add(k); return true;
          }});
          return {{ total: uniq.length, picked: uniq[nth] || null }};
        }})()
        """
        out = self._safe_evaluate(find_js) or {}
        picked = out.get("picked")
        if not picked:
            raise RuntimeError(
                f"未找到含文字 {text!r} 的可点击元素 "
                f"(共找到 {out.get('total', 0)} 个候选)"
            )
        # 高亮 + 点击
        x = int(picked["x"]); y = int(picked["y"])
        self.highlight_rect(picked["x"] - picked["w"]/2, picked["y"] - picked["h"]/2,
                            picked["w"], picked["h"])
        time.sleep(0.25)
        self.click(x, y, highlight=False)
        return picked

    def find_clickables(self, *, contains: Optional[str] = None, limit: int = 50) -> list[dict]:
        """列出 EDA 当前可见的可点击元素 (按钮/链接/列表项). 给 agent 看视觉地图."""
        self.install_overlay()
        sub = json.dumps(contains or "")
        js = f"""
        (() => {{
          const sub = {sub};
          const tags = ['button','a','li[role="menuitem"]','[role="button"]','[onclick]'];
          const out = [];
          for (const sel of tags) {{
            for (const el of document.querySelectorAll(sel)) {{
              const t = (el.innerText || el.textContent || '').trim();
              if (!t) continue;
              if (sub && !t.includes(sub)) continue;
              const r = el.getBoundingClientRect();
              if (r.width <= 0 || r.height <= 0) continue;
              if (r.bottom < 0 || r.top > innerHeight) continue;
              out.push({{
                text: t.slice(0,60), tag: el.tagName.toLowerCase(),
                x: Math.round(r.left + r.width/2),
                y: Math.round(r.top + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height),
              }});
              if (out.length >= {limit}) return out;
            }}
          }}
          return out;
        }})()
        """
        return self._safe_evaluate(js) or []

    def viewport(self) -> dict:
        """返回 EDA 视口尺寸 (用于坐标计算)."""
        return self._safe_evaluate(
            "({ width: innerWidth, height: innerHeight, "
            "  dpr: devicePixelRatio, url: location.href })"
        ) or {}

    def close(self) -> None:
        """退场 — 隐藏虚拟光标, 不强卸 (其他 dao 仍可能在跑)."""
        self._safe_evaluate("window.__DAO_OVERLAY__ && window.__DAO_OVERLAY__.hideCursor()")


# ──────────────────────────────────────────────────────────
# 道之自言
# ──────────────────────────────────────────────────────────
__all__ = ["UIDirector", "UIConfig", "SPECIAL_KEYS"]


if __name__ == "__main__":
    # 自描述: import 即可见职责
    print("ui_director — 道之 UI 导演 (反者道之动)")
    print()
    print("六原语 (损之又损, 至于无为):")
    print("  move_to / click / drag / scroll / type_text / press")
    print()
    print("五感:")
    print("  视: 虚拟光标 + 目标高亮 + toast 横幅 + 截屏")
    print("  听: winsound.MessageBeep")
    print("  触: 慢动作时序 (move 600ms, type 60ms/字)")
    print()
    print("用法:")
    print("  from core.cdp_transport import BusTransport")
    print("  from core.ui_director  import UIDirector")
    print("  bus = BusTransport.connect()")
    print("  ui  = UIDirector(bus)")
    print("  ui.install_overlay()")
    print("  ui.narrate('打开元件搜索')")
    print("  ui.click_text('打开')        # 在 EDA UI 里找 [打开] 按钮并点它")
    print("  ui.type_text('电阻')         # 用户看见字符在搜索框出现")
    print("  ui.press('Enter')")
