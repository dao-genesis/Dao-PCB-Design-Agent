"""test_project_state — 项目全貌感知 + 反向接入 HTTP API 纯测 (无 pcbnew/wx)。"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from kicad_origin.origin.dao_devin import access_api, agent_loop, project_state, tools

_BOARD_TEXT = """(kicad_pcb (version 20240108)
  (net 0 "")
  (net 1 "GND")
  (net 2 "+5V")
  (footprint "R_0603" (at 10 10))
  (footprint "C_0603" (at 20 10))
  (segment (start 1 1) (end 2 2) (net 1))
  (segment (start 2 2) (end 3 3) (net 1))
  (via (at 5 5) (net 1))
  (zone (net 1) (layer "F.Cu"))
)
"""


def _make_project(tmp_path):
    pd = tmp_path / "proj"
    out = pd / "out"
    out.mkdir(parents=True)
    (out / "board.kicad_pcb").write_text(_BOARD_TEXT, "utf-8")
    (out / "report.json").write_text(json.dumps(
        {"project": "T", "components": 2, "nets": 2, "copper_layers": 2,
         "route": {"ok": True, "unrouted_after": 0}}), "utf-8")
    (out / "board_drc.json").write_text(json.dumps(
        {"violations": [{"severity": "error"}, {"severity": "warning"}],
         "unconnected_items": []}), "utf-8")
    return pd


# ── 板况纯文本解析 ────────────────────────────────────────────────────────
def test_parse_board_text_counts(tmp_path):
    pd = _make_project(tmp_path)
    b = project_state.parse_board_text(pd / "out" / "board.kicad_pcb")
    assert b["footprints"] == 2
    assert b["segments"] == 2 and b["vias"] == 1 and b["tracks"] == 3
    assert b["zones"] == 1 and b["nets"] == 3
    assert b["source"] == "file"


def test_detect_project_dir():
    p = project_state.detect_project_dir("/a/b/proj/out/board.kicad_pcb")
    assert str(p).endswith("proj")


# ── journal ──────────────────────────────────────────────────────────────
def test_journal_append_and_tail(tmp_path):
    pd = _make_project(tmp_path)
    for i in range(5):
        project_state.journal(pd, {"actor": "agent", "action": f"a{i}"})
    tail = project_state.journal_tail(pd, 3)
    assert [e["action"] for e in tail] == ["a2", "a3", "a4"]
    assert all("ts" in e for e in tail)


# ── snapshot / markdown / 落盘 ───────────────────────────────────────────
def test_snapshot_full_picture(tmp_path):
    pd = _make_project(tmp_path)
    project_state.journal(pd, {"actor": "agent", "action": "kicad_eval",
                               "detail": "move C11"})
    snap = project_state.snapshot(pd)
    assert snap["ok"] is True
    assert snap["board"]["footprints"] == 2
    assert snap["drc"]["errors"] == 1 and snap["drc"]["warnings"] == 1
    assert snap["flow"]["route"]["ok"] is True
    assert snap["artifacts"]["boards"] == ["board.kicad_pcb"]
    assert snap["journal"][-1]["action"] == "kicad_eval"


def test_snapshot_prefers_live_board(tmp_path):
    pd = _make_project(tmp_path)

    class FakeLive:
        def summary(self):
            return {"ok": True, "board": {"file": str(pd / "out" / "board.kicad_pcb"),
                                          "footprints": 28, "tracks": 43,
                                          "nets": 36, "zones": 2}}

    snap = project_state.snapshot(pd, live=FakeLive())
    assert snap["board"]["source"] == "live"
    assert snap["board"]["footprints"] == 28


def test_render_markdown_and_write_state(tmp_path):
    pd = _make_project(tmp_path)
    md = project_state.render_markdown(project_state.snapshot(pd))
    assert "PROJECT_STATE" in md and "板况" in md and "DRC" in md
    out = project_state.write_state(pd)
    assert (pd / "PROJECT_STATE.md").exists()
    state = json.loads((pd / "out" / "dao_state" / "state.json").read_text("utf-8"))
    assert state["board"]["footprints"] == 2
    assert out["markdown"].endswith("PROJECT_STATE.md")


# ── kicad_project_state 工具注册 ─────────────────────────────────────────
def test_project_state_tool_registered(tmp_path):
    pd = _make_project(tmp_path)

    class FakeBridge:
        def project_state(self, project_dir=None):
            return project_state.snapshot(project_dir or pd)

        def live_summary(self):
            return {"ok": True}

        def live_eval(self, code):
            return {"ok": True, "result": None}

        def new_session(self, prompt):
            return {"ok": True}

    reg = tools.default_registry(FakeBridge())
    assert "kicad_project_state" in reg.names()
    r = reg.dispatch("kicad_project_state", {})
    assert r["ok"] is True and r["board"]["footprints"] == 2
    # 别名可达
    assert tools.normalize_name("project_state") == "kicad_project_state"


# ── agent_loop 停止 / 流式回调 ───────────────────────────────────────────
def test_run_turn_should_stop_and_on_step():
    reg = tools.ToolRegistry()
    reg.register("kicad_board_summary", lambda: {"ok": True, "result": {"n": 1}})
    calls = {"n": 0}

    def chat(messages, **kw):
        calls["n"] += 1
        return {"ok": True, "content": "", "tool_calls": [
            {"id": "1", "function": {"name": "kicad_board_summary",
                                     "arguments": "{}"}}]}

    seen = []
    r = agent_loop.run_turn([{"role": "user", "content": "x"}], reg,
                            chat_fn=chat, max_steps=5,
                            should_stop=lambda: calls["n"] >= 2,
                            on_step=seen.append)
    assert r["stopped"] is True and calls["n"] == 2
    assert len(seen) == 2 and seen[0]["tool"] == "kicad_board_summary"


# ── 反向接入 HTTP API ────────────────────────────────────────────────────
class _StubBridge:
    def __init__(self, pd):
        self.pd = pd
        self._reg = tools.ToolRegistry()
        self._reg.register("kicad_board_summary",
                           lambda: {"ok": True, "result": {"layers": 4}})

    def project_state(self, project_dir=None):
        return project_state.snapshot(self.pd)

    def project_state_markdown(self, project_dir=None):
        return project_state.render_markdown(self.project_state())

    def registry(self):
        return self._reg

    def ai_tools(self):
        return self._reg.schemas()

    def ai_conversations(self):
        return []

    def ai_new_conversation(self, **kw):
        return {"ok": True, "conversation": {"id": "conv-test"}}

    def ai_send(self, cid, text, **kw):
        return {"ok": True, "content": "回声: " + text, "steps": []}

    def live_eval(self, code):
        return {"ok": True, "result": "evald:" + code}

    def journal(self, *a, **kw):
        pass


def _req(method, url, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_access_server_endpoints(tmp_path):
    pd = _make_project(tmp_path)
    srv = access_api.AccessServer(_StubBridge(pd), port=0, token="t-secret")
    info = srv.start()
    url = info["url"]
    try:
        # health 免鉴权
        code, raw = _req("GET", url + "/api/health")
        assert code == 200 and json.loads(raw)["ok"] is True
        # 无 token → 401
        code, raw = _req("GET", url + "/api/state")
        assert code == 401
        # state 带鉴权
        code, raw = _req("GET", url + "/api/state", token="t-secret")
        assert code == 200 and json.loads(raw)["board"]["footprints"] == 2
        # state.md
        code, raw = _req("GET", url + "/api/state.md", token="t-secret")
        assert code == 200 and b"PROJECT_STATE" in raw
        # tools / tool
        code, raw = _req("GET", url + "/api/tools", token="t-secret")
        assert code == 200
        code, raw = _req("POST", url + "/api/tool", token="t-secret",
                         body={"name": "kicad_board_summary", "args": {}})
        assert code == 200 and json.loads(raw)["result"]["layers"] == 4
        # eval
        code, raw = _req("POST", url + "/api/eval", token="t-secret",
                         body={"code": "1+1"})
        assert code == 200 and json.loads(raw)["result"] == "evald:1+1"
        # chat (自动开会话)
        code, raw = _req("POST", url + "/api/chat", token="t-secret",
                         body={"text": "你好"})
        r = json.loads(raw)
        assert code == 200 and r["content"] == "回声: 你好"
        assert r["conversation_id"] == "conv-test"
        # doc
        code, raw = _req("GET", url + "/api/doc", token="t-secret")
        assert code == 200 and "反向接入".encode() in raw
        # 404
        code, raw = _req("GET", url + "/api/nope", token="t-secret")
        assert code == 404
    finally:
        srv.stop()


def test_access_doc_and_token(tmp_path):
    tok = access_api.load_or_create_token(tmp_path / "tok")
    assert tok.startswith("dao-kicad-")
    assert access_api.load_or_create_token(tmp_path / "tok") == tok  # 幂等
    doc = access_api.render_access_doc("http://127.0.0.1:8323", tok)
    for must in ("/api/state", "/api/eval", "/api/chat", "Bearer", "cloudflared"):
        assert must in doc
    srv = access_api.AccessServer(_StubBridge(tmp_path), port=0, token=tok)
    p = srv.write_doc(tmp_path / "AGENT_ACCESS.md")
    assert p.exists() and tok in p.read_text("utf-8")
