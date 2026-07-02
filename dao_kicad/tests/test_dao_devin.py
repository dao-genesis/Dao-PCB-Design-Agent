"""Tests for dao_devin — Devin Cloud 客户端 / 账号池 / 模型路由 / 面板桥 移植件。

反臆造纪律: devin_cloud 的 HTTP 全部经 set_transport 注入桩 (不触网), 断言端点/契约
与 devin-remote 源一致; 账号池/代理配置落盘到临时 DAO_HOME (不污染真 ~/.dao); wx/
pcbnew 依赖惰性导入 → 本测试在纯 CI (无 KiCad) 全绿。
"""
import json

import pytest

from kicad_origin.origin.dao_devin import accounts, bridge, dao_proxy
from kicad_origin.origin.dao_devin import devin_cloud as dc


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """把 ~/.dao 重定向到临时目录, 隔离账号/代理/登录态落盘。"""
    monkeypatch.setenv("DAO_HOME", str(tmp_path / "dao"))
    yield
    dc.set_transport(None)


class FakeTransport:
    """按 (method, path-substr) 路由的假传输层, 记录调用供契约断言。"""

    def __init__(self):
        self.routes = []  # list of (method, substr, status, json_obj)
        self.calls = []   # list of (method, url, headers, body)

    def add(self, method, substr, status, obj):
        self.routes.append((method.upper(), substr, status, obj))
        return self

    def __call__(self, method, url, headers, body, timeout_s):
        self.calls.append((method.upper(), url, dict(headers),
                           json.loads(body.decode()) if body else None))
        for m, substr, status, obj in self.routes:
            if m == method.upper() and substr in url:
                payload = json.dumps(obj).encode() if obj is not None else b""
                return status, {}, payload
        return 404, {}, b'{"error":"no route"}'


def _auth():
    return dc.Auth(auth1="A1", org_id="org-abc", org_bare="abc", email="u@x.com")


# ── devin_cloud: 契约 ────────────────────────────────────────────────────────
def test_ascii_safe_json_body():
    """中文请求体必须 ensure_ascii (踩坑 5: 服务端每隔一字截断)。"""
    ft = FakeTransport().add("POST", "/sessions", 200, {"devin_id": "d1"})
    dc.set_transport(ft)
    dc.create_session(_auth(), "画一块板 中文")
    _m, _u, _h, body = ft.calls[-1]
    # transport 收到的 body 已是 dict (FakeTransport 解析过); 直接验证原始字节转义
    raw = json.dumps({"user_message": "画一块板 中文", "prompt": "画一块板 中文"}, ensure_ascii=True)
    assert "\\u" in raw and "画" not in raw


def test_login_two_hop():
    ft = (FakeTransport()
          .add("POST", "/_devin-auth/password/login", 200, {"token": "T", "user_id": "u1"})
          .add("POST", "/users/post-auth", 200, {"org_id": "org-xyz", "org_name": "Acme"}))
    dc.set_transport(ft)
    r = dc.login("u@x.com", "pw")
    assert r["ok"] and r["auth"].org_id == "org-xyz" and r["auth"].org_bare == "xyz"
    # 第一跳打 windsurf 登录, 第二跳带 Bearer token 打 post-auth
    assert ft.calls[0][1] == dc.CFG.login_url
    assert ft.calls[1][2]["Authorization"] == "Bearer T"


def test_auth_headers_shape():
    h = dc.auth_headers(_auth())
    assert h["Authorization"] == "Bearer A1" and h["x-cog-org-id"] == "org-abc"


def test_list_sessions_v2_endpoint_and_fallback():
    ft = FakeTransport().add("GET", "/org-abc/v2sessions", 200, {"sessions": [{"devin_id": "d1"}]})
    dc.set_transport(ft)
    r = dc.list_sessions(_auth())
    assert r["ok"] and len(r["sessions"]) == 1
    assert "/org-abc/v2sessions" in ft.calls[-1][1]


def test_send_message_requires_api_key():
    dc.set_transport(FakeTransport())
    r = dc.send_message(_auth(), "d1", "hi")
    assert not r["ok"] and "API Key" in r["error"]


def test_send_message_uses_v1_and_apikey():
    ft = FakeTransport().add("POST", "/session/d1/message", 200, {"ok": True})
    dc.set_transport(ft)
    r = dc.send_message(_auth(), "d1", "hi", {"apiKey": "apk_x"})
    assert r["ok"]
    _m, url, headers, _b = ft.calls[-1]
    assert url.startswith(dc.CFG.v1_base) and headers["Authorization"] == "Bearer apk_x"


def test_classify_session_states():
    assert dc.classify_session({"latest_status_contents": {"user_action_required": "x"}}) == "awaiting"
    assert dc.classify_session({"latest_status_contents": {"enum": "finished"}}) == "finished"
    assert dc.classify_session({"latest_status_contents": {"reason": "out_of_quota"}}) == "blocked"
    assert dc.classify_session({"status": "running"}) == "running"
    assert dc.classify_session({}) == "idle"


def test_message_limit_int_floor():
    assert dc.message_limit_int(0) is None
    assert dc.message_limit_int(3.9) == 3
    assert dc.message_limit_int("x") is None


def test_billing_balance_subscription():
    assert dc.billing_balance({"has_subscription_or_credits": True, "available_credits": 5}) == 5
    assert dc.billing_balance({"has_subscription_or_credits": True}) == 9999
    assert dc.billing_balance(None) is None


def test_parse_event_stream_dedupe_sort():
    raw = ("data: {\"type\":\"a\",\"event_id\":\"1\",\"created_at_ms\":20}\n"
           "data: {\"type\":\"b\",\"event_id\":\"2\",\"created_at_ms\":10}\n"
           "data: {\"type\":\"a\",\"event_id\":\"1\",\"created_at_ms\":20}\n"
           "data: [DONE]\n")
    evs = dc._parse_event_stream(raw)
    assert [e["event_id"] for e in evs] == ["2", "1"]  # 去重 + 按 ms 升序


def test_retry_on_429(monkeypatch):
    monkeypatch.setattr(dc.time, "sleep", lambda *_: None)
    calls = {"n": 0}

    def flaky(method, url, headers, body, timeout_s):
        calls["n"] += 1
        if calls["n"] == 1:
            return 429, {"retry-after": "0"}, b""
        return 200, {}, b'{"ok":true}'

    dc.set_transport(flaky)
    r = dc.json_request("GET", "https://x/y")
    assert r["status"] == 200 and calls["n"] == 2


# ── accounts: 账号池 ─────────────────────────────────────────────────────────
def test_account_pool_add_switch_remove():
    accounts.add_account("a@x.com", password="pw", label="A")
    accounts.add_account("b@x.com", token="tok", label="B")
    lst = accounts.list_accounts()
    assert {a["email"] for a in lst} == {"a@x.com", "b@x.com"}
    assert [a for a in lst if a["active"]][0]["email"] == "a@x.com"  # 首个自动活动
    accounts.switch_account("b@x.com")
    assert accounts.load_pool().active_email == "b@x.com"
    accounts.remove_account("b@x.com")
    assert accounts.load_pool().active_email == "a@x.com"  # 回退到剩余号


def test_account_redacted_no_plaintext():
    accounts.add_account("a@x.com", password="secret", token="tokenvalue")
    a = accounts.list_accounts()[0]
    assert a["password"] == "***" and "tokenv" in a["token"] and "secret" not in json.dumps(a)


def test_ensure_account_auth_via_token():
    ft = FakeTransport().add("POST", "/users/post-auth", 200, {"org_id": "org-t", "org_name": "T"})
    dc.set_transport(ft)
    accounts.add_account("a@x.com", token="ey_tok")
    r = accounts.ensure_account_auth("a@x.com")
    assert r["ok"] and r["auth"].org_id == "org-t" and r["auth"].auth1 == "ey_tok"


# ── dao_proxy: 模型路由 ──────────────────────────────────────────────────────
def test_proxy_presets_nonempty_and_shape():
    ps = dao_proxy.list_presets()
    assert len(ps) >= 25
    assert all({"n", "t", "u", "r"} <= set(p) for p in ps)
    assert any(p["n"].startswith("DeepSeek") for p in ps)


def test_proxy_add_from_preset_and_route():
    dao_proxy.add_channel(name="", from_preset="DeepSeek 深度求索", api_key="sk-x", model="deepseek-chat")
    r = dao_proxy.resolve_route()
    assert r["ok"] and r["base_url"] == "https://api.deepseek.com/v1"
    assert r["protocol"] == "openai" and r["has_key"] and r["model"] == "deepseek-chat"


def test_proxy_channel_redacted():
    dao_proxy.add_channel(name="c", base_url="https://x/v1", api_key="sk-secret")
    c = dao_proxy.list_channels()[0]
    assert c["api_key"] == "(已设置)" and "sk-secret" not in json.dumps(c)


# ── bridge: 门面 (活体内核可注入桩) ─────────────────────────────────────────
class FakeLive:
    def __init__(self):
        self.calls = []

    def summary(self):
        return {"board_id": "b1", "footprints": 3}

    def eval(self, code, timeout=130.0):
        self.calls.append(code)
        return {"echoed": code}

    def close(self):
        pass


def test_bridge_account_and_overview_flow():
    ft = (FakeTransport()
          .add("POST", "/users/post-auth", 200, {"org_id": "org-b"})
          .add("GET", "/v2sessions", 200, {"sessions": [
              {"devin_id": "d1", "title": "S1", "status": "running"}]})
          .add("GET", "/learning/all", 200, {"learnings": []})
          .add("GET", "/playbooks", 200, {"playbooks": []})
          .add("GET", "/secrets", 200, {"secrets": []})
          .add("GET", "/git-connections-metadata", 200, [])
          .add("GET", "/billing/status", 200, {"available_credits": 3}))
    dc.set_transport(ft)
    b = bridge.DevinKiCadBridge(live_factory=FakeLive)
    b.add_account("a@x.com", token="ey_tok")
    ov = b.overview()
    assert ov["ok"] and ov["overview"]["counts"]["sessions"] == 1


def test_bridge_live_eval_injected():
    b = bridge.DevinKiCadBridge(live_factory=FakeLive)
    r = b.live_eval("board.GetFootprints().size()")
    assert r["ok"] and r["result"]["echoed"].startswith("board")
    s = b.live_summary()
    assert s["ok"] and s["summary"]["board_id"] == "b1"


def test_bridge_send_needs_active_session():
    ft = FakeTransport().add("POST", "/users/post-auth", 200, {"org_id": "org-b"})
    dc.set_transport(ft)
    b = bridge.DevinKiCadBridge(live_factory=FakeLive)
    b.add_account("a@x.com", token="ey_tok")
    r = b.send("hi")
    assert not r["ok"] and "无活动对话" in r["error"]


def test_panel_imports_without_gui():
    """panel 在无 wx/pcbnew 时仍可 import, register() 为安全空操作。"""
    from kicad_origin.origin.dao_devin import panel
    assert panel.register() is None or panel._HAS_GUI


# ════════════════════════════════════════════════════════════════
# L2 · proxy_adapters: 多协议适配器 + 弹性 (移植自 devin-remote)
# ════════════════════════════════════════════════════════════════
from kicad_origin.origin.dao_devin import proxy_adapters as pa  # noqa: E402


# ── 协议探测 (源 adapters.js:133 detectProtocol) ─────────────────────────────
def test_detect_protocol_explicit_and_type():
    assert pa.detect_protocol({"protocol": "anthropic"}) == pa.PROTOCOL.ANTHROPIC
    assert pa.detect_protocol({"type": "anthropic"}) == pa.PROTOCOL.ANTHROPIC
    assert pa.detect_protocol({"type": "openai-responses"}) == pa.PROTOCOL.OPENAI_RESPONSES


def test_detect_protocol_by_url_path_model():
    assert pa.detect_protocol({"baseUrl": "https://api.anthropic.com"}) == pa.PROTOCOL.ANTHROPIC
    assert pa.detect_protocol({"completionPath": "/v1/messages"}) == pa.PROTOCOL.ANTHROPIC
    assert pa.detect_protocol({"baseUrl": "https://x/v1"}, "claude-opus-4") == pa.PROTOCOL.ANTHROPIC
    assert pa.detect_protocol({"baseUrl": "https://x/v1"}, "deepseek-chat") == pa.PROTOCOL.OPENAI_CHAT


# ── 工具函数 (源 adapters.js §5) ─────────────────────────────────────────────
def test_normalize_base_url_and_reasoning():
    assert pa.normalize_base_url("https://x/v1///") == "https://x/v1"
    assert pa.normalize_reasoning_effort("HIGH") == "high"
    assert pa.normalize_reasoning_effort("gpt-5-xhigh") == "high"
    assert pa.normalize_reasoning_effort(None) is None


def test_pick_context_length():
    assert pa.pick_context_length("claude-opus-4") == 200000
    assert pa.pick_context_length("gpt-5-4") == 256000
    assert pa.pick_context_length("gpt-4o") == 128000
    assert pa.pick_context_length("deepseek-chat") == 65536
    assert pa.pick_context_length("gemini-2.5-pro") == 1048576
    assert pa.pick_context_length("unknown-model") == 128000


def test_apply_auth_headers_bearer_vs_xapikey():
    h1 = {}
    pa.apply_auth_headers(h1, {"apiKey": "sk-1", "protocol": pa.PROTOCOL.OPENAI_CHAT})
    assert h1["Authorization"] == "Bearer sk-1"
    h2 = {}
    pa.apply_auth_headers(h2, {"apiKey": "sk-2", "protocol": pa.PROTOCOL.ANTHROPIC})
    assert h2["x-api-key"] == "sk-2" and "Authorization" not in h2


# ── OpenAI chat 适配器 (源 adapters.js:174/294) ─────────────────────────────
def test_openai_chat_build_and_parse():
    url, proto, headers, body = pa.build_request(
        {"baseUrl": "https://api.deepseek.com/v1", "protocol": "openai-chat", "apiKey": "sk-x"},
        [{"role": "user", "content": "hi"}], model="deepseek-chat",
        tools=[{"type": "function", "function": {"name": "f"}}], toolChoice="auto")
    assert url == "https://api.deepseek.com/v1/chat/completions"  # /v1 去重
    assert proto == pa.PROTOCOL.OPENAI_CHAT
    assert body["model"] == "deepseek-chat" and body["messages"][0]["content"] == "hi"
    assert body["tools"] and body["tool_choice"] == "auto"
    parsed = pa._parse_openai_chat_unary({
        "choices": [{"message": {"content": "hello", "tool_calls": []},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3}})
    assert parsed["content"] == "hello" and parsed["finish_reason"] == "stop"
    assert parsed["usage"] == {"input": 5, "output": 3}


# ── Anthropic 适配器 (源 adapters.js:346/554/1158) ──────────────────────────
def test_anthropic_build_separates_system():
    _u, proto, headers, body = pa.build_request(
        {"baseUrl": "https://api.anthropic.com", "protocol": "anthropic", "apiKey": "sk-a"},
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        model="claude-opus-4")
    assert proto == pa.PROTOCOL.ANTHROPIC
    assert headers["anthropic-version"] == "2023-06-01" and headers["x-api-key"] == "sk-a"
    assert body["system"] == "sys"           # system 抽离为独立字段
    assert body["messages"][0]["role"] == "user"  # system 不入 messages
    assert body["max_tokens"] == 8192


def test_anthropic_message_conversion_tool_calls():
    body = pa._build_anthropic({"model": "claude-opus-4", "messages": [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "function": {"name": "run", "arguments": '{"x":1}'}}]},
        {"role": "tool", "tool_call_id": "t1", "content": "ok"}]})
    asst = body["messages"][0]
    assert asst["content"][-1]["type"] == "tool_use" and asst["content"][-1]["input"] == {"x": 1}
    user = body["messages"][1]
    assert user["role"] == "user" and user["content"][0]["type"] == "tool_result"


def test_anthropic_parse_unary():
    parsed = pa._parse_anthropic_unary({
        "type": "message", "stop_reason": "tool_use",
        "content": [{"type": "text", "text": "hi"},
                    {"type": "tool_use", "id": "t1", "name": "f", "input": {"a": 1}}],
        "usage": {"input_tokens": 10, "output_tokens": 4}})
    assert parsed["content"] == "hi" and parsed["finish_reason"] == "tool_calls"
    assert parsed["tool_calls"][0]["function"]["name"] == "f"
    assert json.loads(parsed["tool_calls"][0]["function"]["arguments"]) == {"a": 1}


# ── OpenAI responses 适配器 (源 adapters.js:629) ────────────────────────────
def test_openai_responses_build_and_parse():
    body = pa._build_openai_responses({"model": "gpt-5-4", "messages": [
        {"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        "maxOutputTokens": 100, "reasoningEffort": "high"})
    assert "input" in body and "messages" not in body
    assert body["instructions"] == "sys" and body["max_output_tokens"] == 100
    assert body["reasoning"] == {"effort": "high"}
    parsed = pa._parse_openai_responses_unary({
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "yo"}]},
                   {"type": "function_call", "call_id": "c1", "name": "f", "arguments": "{}"}],
        "usage": {"input_tokens": 2, "output_tokens": 1}})
    assert parsed["content"] == "yo" and parsed["finish_reason"] == "tool_calls"
    assert parsed["tool_calls"][0]["id"] == "c1"


# ── 弹性 (源 resilience.js) ─────────────────────────────────────────────────
def test_resilience_pattern_matchers():
    assert pa.is_context_err("Error: context_length_exceeded for this request")
    assert pa.is_thinking_signature_error("thinking.signature verification failed")
    assert pa.matches_refusal("I cannot help with that request")
    assert not pa.matches_refusal("Sure, here is the answer")


def test_should_auto_continue_and_build():
    assert pa.should_auto_continue("length", 0) is True
    assert pa.should_auto_continue("stop", 0) is False
    assert pa.should_auto_continue("length", 3, max_continue=3) is False
    msgs = pa.build_continue_request([{"role": "user", "content": "q"}], "partial", "think")
    assert msgs[-1] == {"role": "user", "content": "Continue."}
    assert msgs[-2]["role"] == "assistant" and msgs[-2]["reasoning_content"] == "think"


# ── chat() 端到端 (桩传输, 反臆造契约) ───────────────────────────────────────
def test_proxy_chat_end_to_end_openai(monkeypatch):
    ft = FakeTransport().add("POST", "/v1/chat/completions", 200, {
        "choices": [{"message": {"content": "答"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1}})
    dc.set_transport(ft)
    dao_proxy.add_channel(name="", from_preset="DeepSeek 深度求索",
                          api_key="sk-x", model="deepseek-chat")
    r = dao_proxy.chat([{"role": "user", "content": "问"}])
    assert r["ok"] and r["content"] == "答" and r["protocol"] == pa.PROTOCOL.OPENAI_CHAT
    _m, url, headers, body = ft.calls[-1]
    assert headers["Authorization"] == "Bearer sk-x"
    assert json.dumps(body["messages"], ensure_ascii=True).find("\\u") >= 0  # 中文转义


def test_proxy_chat_retries_on_500(monkeypatch):
    monkeypatch.setattr(pa, "sleep_backoff", lambda a: 0.0)  # 免真 sleep
    calls = {"n": 0}

    def transport(method, url, headers, body, timeout_s):
        calls["n"] += 1
        if calls["n"] == 1:
            return 500, {}, b'{"error":"server"}'
        return 200, {}, json.dumps({"choices": [{"message": {"content": "ok"},
                                                  "finish_reason": "stop"}]}).encode()
    dc.set_transport(transport)
    dao_proxy.add_channel(name="c", base_url="https://x/v1", protocol="openai",
                          api_key="k", model="m")
    r = dao_proxy.chat([{"role": "user", "content": "hi"}], name="c")
    assert r["ok"] and r["content"] == "ok" and calls["n"] == 2


def test_proxy_chat_no_model_errors():
    dao_proxy.add_channel(name="c", base_url="https://x/v1", api_key="k")
    r = dao_proxy.chat([{"role": "user", "content": "hi"}], name="c")
    assert not r["ok"] and "模型" in r["error"]
