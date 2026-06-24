"""state_mirror — eda 全状态镜像 (反者道之动 · 镜).

═══════════════════════════════════════════════════════════════════════
  本然
═══════════════════════════════════════════════════════════════════════

  agent 本可直读 V8 Object Graph. 何须假眼 (screenshot)?

  此模块: 一次调用, 把 EDA 当下一切关键状态序列化为 JSON. 包括:

    env       — version / online / pro / platform
    project   — 当前打开的工程 (uuid, name, path)
    documents — 当前工程内的文档 (类型/uuid/path)
    active    — 当前激活的文档 (type, uuid, name)
    selection — 当前选中的元素 (id list)
    viewport  — 视口 (canvas 中心/缩放, 仅 sch/pcb)
    panels    — 已打开的面板 (DOM aside.layout-panel)
    dom       — 关键 DOM 路径 (toolbar / menu / dialog)
    ts        — Unix 时间戳

  diff(prev, next) — 给 agent 一份 JSON Patch 风格的变更
  watch(callback) — 后台轮询线程, 每次 diff 非空就回调

═══════════════════════════════════════════════════════════════════════
  设计要点 (反者)
═══════════════════════════════════════════════════════════════════════

  * 一次 JS 调用拿全部 (避免多轮 RPC)
  * 失败优雅: 任何子项异常仅置为 null, 不拖垮全图
  * 不缓存, 每次 fresh (反 "看屏后判断" 的颠倒)
  * 序列化策略: 只取 *标识*, 不取大数据 (uuid/name/path 而非完整工程)
  * diff 采用扁平 JSON Patch (path/op/value), 易于 LLM 阅读

═══════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


# ──────────────────────────────────────────────────────────
# 注入到 EDA 沙箱的 JS — 一次调用拿全状态
# ──────────────────────────────────────────────────────────
_SNAPSHOT_JS = r"""
(async function(){
  const safe = async (fn, fallback) => {
    try { return await fn(); } catch (e) { return fallback; }
  };

  // ── env ───────────────────────────────────────────────
  const env = await safe(async () => ({
    editor_version: await eda.sys_Environment.getEditorVersion(),
    online: await eda.sys_Environment.isOnlineMode(),
    pro: await eda.sys_Environment.isProPrivateEdition(),
    web: await eda.sys_Environment.isWeb(),
    offline: await eda.sys_Environment.isOfflineMode(),
  }), null);

  // ── project ───────────────────────────────────────────
  const project = await safe(async () => {
    const info = await eda.dmt_Project.getCurrentProjectInfo();
    if (!info) return null;
    return {
      uuid:  info.uuid || null,
      name:  info.name || null,
      path:  info.localPath || info.path || null,
      title: info.title || null,
    };
  }, null);

  // ── documents (current project's) ─────────────────────
  const documents = await safe(async () => {
    const list = await eda.dmt_Document.getDocumentsInfo();
    if (!Array.isArray(list)) return [];
    return list.map(d => ({
      uuid:    d.uuid || null,
      name:    d.name || null,
      type:    d.type || d.docType || null,
      path:    d.localPath || d.path || null,
    }));
  }, []);

  // ── active doc ────────────────────────────────────────
  const active = await safe(async () => {
    const a = await eda.dmt_Document.getActiveDocumentInfo();
    if (!a) return null;
    return {
      uuid: a.uuid || null,
      name: a.name || null,
      type: a.type || a.docType || null,
    };
  }, null);

  // ── selection (sch/pcb 等) ───────────────────────────
  const selection = await safe(async () => {
    // 试 schematic / pcb 几个候选
    const candidates = [
      'sch_PrimitiveSelection.getSelectedPrimitiveIds',
      'pcb_PrimitiveSelection.getSelectedPrimitiveIds',
      'sch_Selection.getSelectedIds',
      'pcb_Selection.getSelectedIds',
    ];
    for (const path of candidates) {
      try {
        const parts = path.split('.');
        let obj = eda;
        for (const p of parts.slice(0, -1)) obj = obj[p];
        const fn = obj[parts[parts.length - 1]];
        if (typeof fn === 'function') {
          const r = await fn.call(obj);
          if (Array.isArray(r)) return { source: path, ids: r };
        }
      } catch (e) {}
    }
    return { source: null, ids: [] };
  }, { source: null, ids: [] });

  // ── viewport (canvas) ──────────────────────────────────
  const viewport = await safe(async () => {
    // 尝试 sch / pcb canvas 视口
    const candidates = [
      'sch_View.getViewport',
      'pcb_View.getViewport',
      'sch_Canvas.getViewBox',
      'pcb_Canvas.getViewBox',
    ];
    for (const path of candidates) {
      try {
        const parts = path.split('.');
        let obj = eda;
        for (const p of parts.slice(0, -1)) obj = obj[p];
        const fn = obj[parts[parts.length - 1]];
        if (typeof fn === 'function') {
          const r = await fn.call(obj);
          if (r) return { source: path, ...r };
        }
      } catch (e) {}
    }
    // fallback: window 尺寸
    return {
      source: 'window',
      width:  window.innerWidth,
      height: window.innerHeight,
      dpr:    window.devicePixelRatio || 1,
    };
  }, null);

  // ── panels (打开的浮动面板) ────────────────────────────
  const panels = (() => {
    try {
      const nodes = document.querySelectorAll('aside.layout-panel, .lceda-panel, .panel-window');
      return Array.from(nodes).map(n => ({
        title: (n.querySelector('.panel-title, .title, header')?.textContent || '').trim().slice(0, 60),
        cls:   (n.className || '').slice(0, 80),
        visible: n.offsetParent !== null,
      })).filter(p => p.title);
    } catch (e) { return []; }
  })();

  // ── dom 关键节点路径 ───────────────────────────────────
  const dom = (() => {
    try {
      const out = {};
      // 顶部菜单
      const menubar = document.querySelector('.menubar, .top-menu, nav.menu');
      out.menubar_visible = !!(menubar && menubar.offsetParent !== null);
      // 当前激活 dialog
      const dlg = document.querySelector('.modal:not([hidden]), .dialog.active, [role="dialog"]');
      if (dlg) {
        out.dialog = {
          title: (dlg.querySelector('.title, header, h1, h2')?.textContent || '').trim().slice(0, 80),
          visible: dlg.offsetParent !== null,
        };
      } else {
        out.dialog = null;
      }
      // 页面 url + iframe count
      out.url = location.href;
      out.iframes = document.querySelectorAll('iframe').length;
      return out;
    } catch (e) { return {}; }
  })();

  return {
    env, project, documents, active, selection, viewport, panels, dom,
    ts: Date.now() / 1000,
  };
})()
"""


# ──────────────────────────────────────────────────────────
# StateMirror
# ──────────────────────────────────────────────────────────
@dataclass
class MirrorConfig:
    """采集策略 (调和默认)."""
    timeout_seconds: float = 8.0
    cache_ttl_ms: int = 0       # 0 = 不缓存 (每次 fresh, 反"看屏判断")
    poll_interval_ms: int = 1000  # watch() 轮询间隔


class StateMirror:
    """eda 状态镜像 — 一次调用拿全图.

    用法:
        mirror = StateMirror(transport)
        snap = mirror.snapshot()
        time.sleep(2)
        snap2 = mirror.snapshot()
        diff = mirror.diff(snap, snap2)
        # diff = [{op:'replace', path:'/active/uuid', from:..., to:...}, ...]
    """

    def __init__(self, transport, config: Optional[MirrorConfig] = None):
        """
        transport: 必须 BusTransport (有 eval_in_sandbox), CdpTransport 也可
                   (走主 page Runtime.evaluate, 但 eda 不可见)
        """
        self.transport = transport
        self.config = config or MirrorConfig()
        self._cache: Optional[dict] = None
        self._cache_ts = 0.0
        self._watch_thread: Optional[threading.Thread] = None
        self._watch_stop = threading.Event()

    # ── 1. snapshot (核心) ──────────────────────────────
    def snapshot(self, fresh: bool = False) -> dict:
        """采集当下 EDA 状态. 返回结构化 dict.

        fresh=True 强制不走缓存 (默认每次都 fresh, 因 cache_ttl_ms=0).
        """
        # cache 命中
        if not fresh and self.config.cache_ttl_ms > 0:
            age_ms = (time.time() - self._cache_ts) * 1000
            if self._cache is not None and age_ms < self.config.cache_ttl_ms:
                return self._cache

        # 走 BusTransport.eval_in_sandbox 优先
        eval_fn = getattr(self.transport, "eval_in_sandbox", None)
        if not callable(eval_fn):
            # 退而求其次: CDP 主 page eval (eda 仅暴露在 frame 内, 这里能得 dom 但 eda undef)
            return self._snapshot_minimal_dom_only()

        try:
            # eval_in_sandbox 注入并 await Promise
            raw = eval_fn(f"return await ({_SNAPSHOT_JS});")
            if not isinstance(raw, dict):
                raw = {"error": "snapshot_not_dict", "raw": str(raw)[:200]}
        except Exception as e:
            raw = {"error": f"eval_failed: {e}"}

        self._cache = raw
        self._cache_ts = time.time()
        return raw

    # ── 2. minimal fallback (无 sandbox 时) ───────────
    def _snapshot_minimal_dom_only(self) -> dict:
        """退化版: 仅采集 DOM 信息 (不读 eda.*)."""
        try:
            # CdpTransport 一般有 evaluate
            eval_fn = getattr(self.transport, "evaluate", None)
            if not callable(eval_fn):
                return {"error": "no_eval_fn"}
            js = "({url:location.href, title:document.title, ts:Date.now()/1000})"
            r = eval_fn(js)
            return {
                "env": None, "project": None, "documents": [],
                "active": None, "selection": {"source": None, "ids": []},
                "viewport": None, "panels": [], "dom": r if isinstance(r, dict) else {},
                "ts": time.time(),
                "_minimal": True,
            }
        except Exception as e:
            return {"error": f"minimal_eval_failed: {e}", "ts": time.time()}

    # ── 3. diff (JSON Patch 风格) ──────────────────────
    @staticmethod
    def diff(prev: Optional[dict], next_: Optional[dict]) -> list[dict]:
        """两个 snapshot 的 diff. 返回 JSON Patch-like 数组.

        每项: {op: add/remove/replace, path: '/a/b/c', from: ..., to: ...}
        path 用 / 分隔, 数组用 [n] 索引.

        忽略 ts (永远变).
        """
        if prev is None and next_ is None:
            return []
        if prev is None:
            return [{"op": "add", "path": "", "to": next_}]
        if next_ is None:
            return [{"op": "remove", "path": ""}]

        patches: list[dict] = []
        StateMirror._diff_walk("", prev, next_, patches, ignore_keys={"ts"})
        return patches

    @staticmethod
    def _diff_walk(path: str, a: Any, b: Any, out: list[dict],
                   ignore_keys: Optional[set[str]] = None) -> None:
        ignore_keys = ignore_keys or set()
        if a == b:
            return
        if type(a) is not type(b):
            out.append({"op": "replace", "path": path or "/", "from": a, "to": b})
            return
        if isinstance(a, dict):
            keys = set(a.keys()) | set(b.keys())
            for k in sorted(keys):
                if k in ignore_keys:
                    continue
                p = f"{path}/{k}"
                if k not in a:
                    out.append({"op": "add", "path": p, "to": b[k]})
                elif k not in b:
                    out.append({"op": "remove", "path": p, "from": a[k]})
                else:
                    StateMirror._diff_walk(p, a[k], b[k], out, ignore_keys)
            return
        if isinstance(a, list):
            # 长度不同走整体替换 (LLM 易读), 否则按 index diff
            if len(a) != len(b):
                out.append({"op": "replace", "path": path or "/", "from": a, "to": b})
                return
            for i, (x, y) in enumerate(zip(a, b)):
                StateMirror._diff_walk(f"{path}[{i}]", x, y, out, ignore_keys)
            return
        out.append({"op": "replace", "path": path or "/", "from": a, "to": b})

    # ── 4. summary (LLM 友好) ──────────────────────────
    @staticmethod
    def summarize(snap: dict, max_len: int = 600) -> str:
        """把 snapshot 压成 ~600 字符的中文摘要给 LLM 看."""
        if not snap or "error" in snap:
            return f"[mirror error: {snap.get('error', '?') if snap else 'empty'}]"
        env = snap.get("env") or {}
        proj = snap.get("project") or {}
        active = snap.get("active") or {}
        docs = snap.get("documents") or []
        sel = (snap.get("selection") or {}).get("ids", [])
        panels = snap.get("panels") or []
        dom = snap.get("dom") or {}

        bits = []
        if env:
            bits.append(f"env: editor={env.get('editor_version','?')} online={env.get('online','?')} pro={env.get('pro','?')}")
        if proj:
            bits.append(f"project: {proj.get('name', '?')} ({proj.get('uuid', '')[:8]}...)")
        else:
            bits.append("project: <none>")
        bits.append(f"documents: {len(docs)} 个" + (
            f" ({', '.join((d.get('name') or '?')[:18] for d in docs[:5])}...)" if docs else ""
        ))
        if active:
            bits.append(f"active: {active.get('type','?')}#{active.get('name','?')}")
        if sel:
            bits.append(f"selection: {len(sel)} items")
        if panels:
            bits.append(f"panels: {', '.join(p.get('title','?') for p in panels[:5])}")
        if dom.get("dialog"):
            bits.append(f"dialog: {dom['dialog'].get('title','?')}")
        s = "; ".join(bits)
        return s[:max_len] + ("..." if len(s) > max_len else "")

    # ── 5. watch (轮询线程) ────────────────────────────
    def watch(self, callback: Callable[[list[dict], dict], None],
              interval_ms: Optional[int] = None) -> threading.Thread:
        """启后台线程, 每次 diff 非空就 callback(patches, new_snap).

        callback 在 worker 线程执行, 错误不传播.
        多次 watch 共享同一线程 (前一个 stop_watch 后再启).
        """
        if self._watch_thread is not None and self._watch_thread.is_alive():
            self.stop_watch()

        self._watch_stop.clear()
        period = (interval_ms or self.config.poll_interval_ms) / 1000.0

        def loop():
            prev = None
            while not self._watch_stop.is_set():
                try:
                    cur = self.snapshot(fresh=True)
                    if prev is not None:
                        patches = self.diff(prev, cur)
                        if patches:
                            try:
                                callback(patches, cur)
                            except Exception:
                                pass  # callback 错误吞掉
                    prev = cur
                except Exception:
                    pass
                self._watch_stop.wait(period)

        self._watch_thread = threading.Thread(target=loop, daemon=True, name="state_mirror_watch")
        self._watch_thread.start()
        return self._watch_thread

    def stop_watch(self) -> None:
        self._watch_stop.set()
        if self._watch_thread is not None:
            self._watch_thread.join(timeout=2.0)
            self._watch_thread = None

    # ── 6. JSON 输出 ────────────────────────────────────
    def to_json(self, snap: Optional[dict] = None, *, indent: int = 2) -> str:
        snap = snap if snap is not None else self.snapshot()
        return json.dumps(snap, ensure_ascii=False, indent=indent, default=str)


# ──────────────────────────────────────────────────────────
# 便捷
# ──────────────────────────────────────────────────────────
def quick_snapshot(transport) -> dict:
    """一次性: 不持有 mirror 对象, 直接拿."""
    return StateMirror(transport).snapshot()


__all__ = ["StateMirror", "MirrorConfig", "quick_snapshot"]
