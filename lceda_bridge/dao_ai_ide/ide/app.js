/* ============================================================================
 * DAO AI IDE — 面板逻辑 (道之枢机)
 * ----------------------------------------------------------------------------
 * 本文件运行于 sys_IFrame 打开的同源(https://client) iframe 内。经 window.top
 * 直达 _EXTAPI_ROOT_:
 *   · LLM 外呼 → ROOT.sys_ClientUrl.request(url, 'POST', body, {headers})
 *   · 引擎直驱 → ROOT[namespace][method](...args)   (94 命名空间 / 749 方法)
 * 会话/模型/提示词均持久化于 localStorage(同源 https://client,重启不丢)。
 * ========================================================================== */
(function () {
  "use strict";

  // ─── EDA 引擎句柄(顶帧特权根) ──────────────────────────────────────────
  function getRoot() {
    var cands = [];
    try { cands.push(window.top._EXTAPI_ROOT_); } catch (e) {}
    try { cands.push(window.parent._EXTAPI_ROOT_); } catch (e) {}
    try { cands.push(window._EXTAPI_ROOT_); } catch (e) {}
    for (var i = 0; i < cands.length; i++) if (cands[i]) return cands[i];
    return null;
  }
  var ROOT = getRoot();

  // 经客户端特权通道发起外部 HTTP(免 CORS / Mixed-Content)
  async function clientRequest(url, method, bodyStr, headers) {
    if (!ROOT || !ROOT.sys_ClientUrl) throw new Error("_EXTAPI_ROOT_.sys_ClientUrl 不可用");
    var resp = await ROOT.sys_ClientUrl.request(url, method || "GET", bodyStr, { headers: headers || {} });
    var text = "";
    try { text = await resp.text(); } catch (e) { text = ""; }
    return { status: resp.status, text: text };
  }

  // 调 eda.<ns>.<method>(...args),结果安全序列化
  async function edaCall(ns, method, args) {
    if (!ROOT) throw new Error("_EXTAPI_ROOT_ 不可用(引擎未就绪)");
    var mod = ROOT[ns];
    if (!mod) throw new Error("命名空间不存在: " + ns);
    var fn = mod[method];
    if (typeof fn !== "function") throw new Error(ns + "." + method + " 不是函数");
    var r = await fn.apply(mod, dematerialize(Array.isArray(args) ? args : []));
    return safe(await materialize(r));
  }
  // 反向: 参数里的 {__file__,name,type,text|base64} 还原为真 File (与后端同契约)
  function dematerialize(v) {
    if (v == null) return v;
    if (Array.isArray(v)) return v.map(dematerialize);
    if (typeof v === "object") {
      if (v.__file__ === true && (typeof v.text === "string" || typeof v.base64 === "string")) {
        var bits;
        if (typeof v.text === "string") bits = [v.text];
        else { var s = atob(v.base64), u = new Uint8Array(s.length);
               for (var i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); bits = [u]; }
        return new File(bits, v.name || "file", { type: v.type || "application/octet-stream" });
      }
      var o = {};
      Object.keys(v).forEach(function (k) { o[k] = dematerialize(v[k]); });
      return o;
    }
    return v;
  }
  function safe(v) {
    if (v === undefined) return null;
    try { return JSON.parse(JSON.stringify(v)); }
    catch (e) { try { return String(v); } catch (e2) { return null; } }
  }
  // File/Blob 等宿主对象 JSON 化即空壳; 物化为 {__file__,name,size,text|base64}
  async function materialize(v) {
    if (v == null) return v;
    if ((typeof File !== "undefined" && v instanceof File) ||
        (typeof Blob !== "undefined" && v instanceof Blob)) {
      var name = v.name || null, size = v.size, type = v.type || "";
      var textLike = /^(text\/|application\/(json|xml|x-ndjson))/.test(type) ||
                     /\.(net|json|txt|csv|xml|rep|log|bom)$/i.test(name || "");
      if (textLike || size <= 4 * 1024 * 1024) {
        try {
          if (textLike) return { __file__: true, name: name, size: size, type: type, text: await v.text() };
          var buf = await v.arrayBuffer(); var b = new Uint8Array(buf), s = "";
          for (var i = 0; i < b.length; i++) s += String.fromCharCode(b[i]);
          return { __file__: true, name: name, size: size, type: type, base64: btoa(s) };
        } catch (e) {}
      }
      return { __file__: true, name: name, size: size, type: type, unread: true };
    }
    if (Array.isArray(v)) {
      for (var j = 0; j < v.length; j++) v[j] = await materialize(v[j]);
      return v;
    }
    return v;
  }

  // ─── 存储 ──────────────────────────────────────────────────────────────
  var K = { models: "dao.ai.ide.models", activeModel: "dao.ai.ide.activeModel",
            prompts: "dao.ai.ide.prompts", activePrompt: "dao.ai.ide.activePrompt",
            sessions: "dao.ai.ide.sessions", activeSession: "dao.ai.ide.activeSession" };
  function load(k, d) { try { var v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } }
  function save(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} }
  function uid() { return "x" + Date.now().toString(36) + Math.random().toString(36).slice(2, 6); }

  var state = {
    models: load(K.models, []),
    activeModel: load(K.activeModel, null),
    prompts: load(K.prompts, []),
    activePrompt: load(K.activePrompt, null),
    sessions: load(K.sessions, []),
    activeSession: load(K.activeSession, null),
    busy: false,
    abort: false,
  };

  // 首次:内置一条通用提示词
  if (!state.prompts.length) {
    var pid = uid();
    state.prompts = [{ id: pid, name: "PCB 设计助手(默认)", body:
      "你是嵌入在嘉立创EDA专业版中的资深 PCB/原理图设计 AI 助手。你能通过工具直接驱动 EDA 引擎:\n"
      + "- 用 eda_call(namespace, method, args) 调用官方 EXTAPI(94 命名空间/749 方法)。\n"
      + "- 常用: dmt_Project.getCurrentProjectInfo、dmt_Pcb.getCurrentPcbInfo、dmt_Board.getAllBoardsInfo、"
      + "sys_Environment.getEditorCurrentVersion、sys_Message.showToastMessage(msg)、pcb_* 图元/网络/DRC/制造、sch_* 原理图。\n"
      + "- 修改类操作前先用 get_context 了解当前工程/板;不确定方法名时先小步试探并读回结果。\n"
      + "回答用中文,简洁务实。需要执行操作时直接调用工具,不要只描述。" }];
    state.activePrompt = pid;
    save(K.prompts, state.prompts); save(K.activePrompt, state.activePrompt);
  }

  // ─── DOM ────────────────────────────────────────────────────────────────
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var el = {
    sessList: $("#sessList"), msgs: $("#msgs"), input: $("#input"), send: $("#send"),
    chatTitle: $("#chatTitle"), modelSel: $("#modelSel"), modelList: $("#modelList"),
    promptList: $("#promptList"), edaDot: $("#edaDot"), edaTxt: $("#edaTxt"),
    ctxTxt: $("#ctxTxt"), modelTxt: $("#modelTxt"), hint: $("#hint"),
  };

  // ─── 视图切换 ─────────────────────────────────────────────────────────
  $$(".nav button").forEach(function (b) {
    b.addEventListener("click", function () {
      $$(".nav button").forEach(function (x) { x.classList.remove("active"); });
      b.classList.add("active");
      $$(".view").forEach(function (v) { v.classList.remove("active"); });
      $("#view-" + b.dataset.view).classList.add("active");
      if (b.dataset.view === "models") renderModels();
      if (b.dataset.view === "prompts") renderPrompts();
    });
  });

  // ─── 会话 ────────────────────────────────────────────────────────────────
  function curSession() {
    return state.sessions.find(function (s) { return s.id === state.activeSession; }) || null;
  }
  function newSession() {
    var s = { id: uid(), name: "新会话", createdAt: Date.now(), messages: [] };
    state.sessions.unshift(s);
    state.activeSession = s.id;
    persistSessions(); renderSessions(); renderChat();
    el.input.focus();
  }
  function persistSessions() { save(K.sessions, state.sessions); save(K.activeSession, state.activeSession); }
  function renderSessions() {
    el.sessList.innerHTML = "";
    if (!state.sessions.length) { el.sessList.innerHTML = '<div class="empty">暂无会话，点 + 新建</div>'; return; }
    state.sessions.forEach(function (s) {
      var d = document.createElement("div");
      d.className = "sess" + (s.id === state.activeSession ? " active" : "");
      var n = s.messages.filter(function (m) { return m.role === "user" || m.role === "assistant"; }).length;
      d.innerHTML = '<div class="name"></div><div class="meta">' + n + ' 条 · ' +
        new Date(s.createdAt).toLocaleDateString() + '</div><span class="del">✕</span>';
      d.querySelector(".name").textContent = s.name;
      d.addEventListener("click", function (e) {
        if (e.target.classList.contains("del")) { delSession(s.id); return; }
        state.activeSession = s.id; persistSessions(); renderSessions(); renderChat();
      });
      el.sessList.appendChild(d);
    });
  }
  function delSession(id) {
    state.sessions = state.sessions.filter(function (s) { return s.id !== id; });
    if (state.activeSession === id) state.activeSession = state.sessions.length ? state.sessions[0].id : null;
    persistSessions(); renderSessions(); renderChat();
  }
  $("#newSess").addEventListener("click", newSession);

  // ─── 渲染对话 ─────────────────────────────────────────────────────────
  function renderChat() {
    var s = curSession();
    el.chatTitle.textContent = s ? s.name : "无会话";
    el.msgs.innerHTML = "";
    if (!s) { el.msgs.innerHTML = '<div class="empty">新建或选择一个会话开始</div>'; return; }
    if (!s.messages.length) { el.msgs.innerHTML = '<div class="empty">开始对话吧。AI 可直接操作嘉立创EDA。</div>'; return; }
    s.messages.forEach(function (m) { if (m.role !== "system") appendMsgDom(m); });
    el.msgs.scrollTop = el.msgs.scrollHeight;
  }
  function appendMsgDom(m) {
    var wrap = document.createElement("div");
    wrap.className = "msg " + m.role;
    var avTxt = m.role === "user" ? "我" : m.role === "assistant" ? "AI" : m.role === "tool" ? "⚙" : "S";
    var who = m.role === "user" ? "我" : m.role === "assistant" ? "AI 助手" : m.role === "tool" ? "工具结果" : "系统";
    var html = '<div class="av">' + avTxt + '</div><div class="body"><div class="who">' + who + '</div>';
    if (m.content) html += '<div class="content"></div>';
    if (m.tool_calls && m.tool_calls.length) {
      m.tool_calls.forEach(function (tc) {
        html += '<div class="toolcall"><div class="h">⚙ ' + esc(tc.function.name) +
          (tc._running ? ' <span class="run">运行中…</span>' : '') + '</div><pre>' +
          esc(tc.function.arguments || "") + '</pre>' +
          (tc._result !== undefined ? '<pre class="res' + (tc._error ? ' err' : '') + '">' + esc(tc._result) + '</pre>' : '') +
          '</div>';
      });
    }
    html += "</div>";
    wrap.innerHTML = html;
    if (m.content) {
      var c = wrap.querySelector(".content");
      if (m.role === "assistant") c.innerHTML = md(m.content); else c.textContent = m.content;
    }
    el.msgs.appendChild(wrap);
    return wrap;
  }

  // 流式过程中的活节点: 思考态 → 逐 token 更新
  function appendStreamingDom() {
    var wrap = document.createElement("div");
    wrap.className = "msg assistant streaming";
    wrap.innerHTML = '<div class="av">AI</div><div class="body"><div class="who">AI 助手</div>' +
      '<div class="content"><span class="thinking"><i></i><i></i><i></i></span></div></div>';
    el.msgs.appendChild(wrap);
    el.msgs.scrollTop = el.msgs.scrollHeight;
    return wrap;
  }
  function updateStreamingDom(wrap, text) {
    var c = wrap.querySelector(".content");
    c.innerHTML = md(text) + '<span class="caret"></span>';
    el.msgs.scrollTop = el.msgs.scrollHeight;
  }
  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

  // 极简 Markdown 渲染(先转义后编译, 无外依赖): 代码块/行内码/粗斜体/标题/列表/链接
  function md(text) {
    var src = String(text == null ? "" : text);
    var blocks = [];
    src = src.replace(/```(\w*)\n?([\s\S]*?)```/g, function (_, lang, code) {
      blocks.push('<pre class="code">' + esc(code.replace(/\n$/, "")) + "</pre>");
      return "\u0000B" + (blocks.length - 1) + "\u0000";
    });
    var h = esc(src);
    h = h.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    h = h.replace(/\*\*([^*\n]+)\*\*/g, "<b>$1</b>");
    h = h.replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<i>$2</i>");
    h = h.replace(/\[([^\]\n]+)\]\((https?:[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    var lines = h.split("\n"), out = [], inUl = false, inOl = false;
    function closeLists() { if (inUl) { out.push("</ul>"); inUl = false; } if (inOl) { out.push("</ol>"); inOl = false; } }
    for (var i = 0; i < lines.length; i++) {
      var ln = lines[i], m;
      if ((m = ln.match(/^(#{1,4})\s+(.*)$/))) { closeLists(); out.push("<h" + (m[1].length + 2) + ">" + m[2] + "</h" + (m[1].length + 2) + ">"); continue; }
      if ((m = ln.match(/^\s*[-*・]\s+(.*)$/))) { if (!inUl) { closeLists(); out.push("<ul>"); inUl = true; } out.push("<li>" + m[1] + "</li>"); continue; }
      if ((m = ln.match(/^\s*\d+[.、]\s+(.*)$/))) { if (!inOl) { closeLists(); out.push("<ol>"); inOl = true; } out.push("<li>" + m[1] + "</li>"); continue; }
      closeLists();
      out.push(ln.length ? ln + "<br>" : "");
    }
    closeLists();
    var html = out.join("\n").replace(/(<br>\n?)+$/, "");
    return html.replace(/\u0000B(\d+)\u0000/g, function (_, n) { return blocks[+n]; });
  }

  // ─── 模型管理 ─────────────────────────────────────────────────────────
  function renderModelSelect() {
    el.modelSel.innerHTML = "";
    if (!state.models.length) {
      var o = document.createElement("option"); o.textContent = "未配置模型"; o.value = ""; el.modelSel.appendChild(o);
      el.modelTxt.textContent = "模型: 未配置"; return;
    }
    state.models.forEach(function (m) {
      var o = document.createElement("option"); o.value = m.id; o.textContent = m.name + " · " + m.model;
      if (m.id === state.activeModel) o.selected = true; el.modelSel.appendChild(o);
    });
    if (!state.activeModel || !state.models.find(function (m) { return m.id === state.activeModel; }))
      state.activeModel = state.models[0].id;
    var am = state.models.find(function (m) { return m.id === state.activeModel; });
    el.modelTxt.textContent = "模型: " + (am ? am.name + " · " + am.model : "—");
  }
  el.modelSel.addEventListener("change", function () {
    state.activeModel = el.modelSel.value; save(K.activeModel, state.activeModel); renderModelSelect();
  });
  function renderModels() {
    el.modelList.innerHTML = "";
    if (!state.models.length) { el.modelList.innerHTML = '<div class="empty">尚无供应商，填写上方表单保存</div>'; return; }
    state.models.forEach(function (m) {
      var d = document.createElement("div");
      d.className = "list-item" + (m.id === state.activeModel ? " active" : "");
      d.innerHTML = '<div class="info"><div class="n"></div><div class="d"></div></div>' +
        '<span class="pill' + (m.id === state.activeModel ? ' on' : '') + '">' + (m.id === state.activeModel ? '使用中' : '启用') + '</span>' +
        '<button class="btn sm">编辑</button><button class="btn sm danger">删除</button>';
      d.querySelector(".n").textContent = m.name + "  (" + m.model + ")";
      d.querySelector(".d").textContent = m.base;
      var btns = d.querySelectorAll("button");
      d.querySelector(".pill").addEventListener("click", function () { state.activeModel = m.id; save(K.activeModel, m.id); renderModels(); renderModelSelect(); });
      btns[0].addEventListener("click", function () { editModel(m); });
      btns[1].addEventListener("click", function () {
        state.models = state.models.filter(function (x) { return x.id !== m.id; });
        save(K.models, state.models); renderModels(); renderModelSelect();
      });
      el.modelList.appendChild(d);
    });
  }
  function editModel(m) {
    $("#m_name").value = m.name; $("#m_base").value = m.base; $("#m_key").value = m.key;
    $("#m_model").value = m.model; $("#m_temp").value = m.temp; $("#m_save").dataset.edit = m.id;
  }
  function clearModelForm() {
    ["m_name", "m_base", "m_key", "m_model"].forEach(function (i) { $("#" + i).value = ""; });
    $("#m_temp").value = "0.3"; delete $("#m_save").dataset.edit;
  }
  $("#m_clear").addEventListener("click", clearModelForm);
  $("#m_save").addEventListener("click", function () {
    var name = $("#m_name").value.trim(), base = $("#m_base").value.trim().replace(/\/+$/, "");
    var key = $("#m_key").value.trim(), model = $("#m_model").value.trim(), temp = parseFloat($("#m_temp").value) || 0.3;
    if (!name || !base || !model) { toast("名称 / Base URL / 模型 ID 必填"); return; }
    var editId = $("#m_save").dataset.edit;
    if (editId) {
      var m = state.models.find(function (x) { return x.id === editId; });
      if (m) { m.name = name; m.base = base; m.key = key; m.model = model; m.temp = temp; }
    } else {
      var nm = { id: uid(), name: name, base: base, key: key, model: model, temp: temp };
      state.models.push(nm); if (!state.activeModel) state.activeModel = nm.id;
    }
    save(K.models, state.models); save(K.activeModel, state.activeModel);
    clearModelForm(); renderModels(); renderModelSelect(); toast("已保存供应商");
  });
  $("#m_test").addEventListener("click", async function () {
    var base = $("#m_base").value.trim().replace(/\/+$/, ""), key = $("#m_key").value.trim(), model = $("#m_model").value.trim();
    if (!base || !model) { toast("填写 Base URL 与模型 ID 再测试"); return; }
    $("#m_test").textContent = "测试中…"; $("#m_test").disabled = true;
    try {
      var body = JSON.stringify({ model: model, messages: [{ role: "user", content: "ping" }], max_tokens: 5 });
      var r = await clientRequest(base + "/chat/completions", "POST", body,
        { "Content-Type": "application/json", "Authorization": "Bearer " + key });
      if (r.status >= 200 && r.status < 300) toast("连接成功 (HTTP " + r.status + ")");
      else toast("响应 HTTP " + r.status + ": " + r.text.slice(0, 120));
    } catch (e) { toast("测试失败: " + (e && e.message || e)); }
    $("#m_test").textContent = "测试连接"; $("#m_test").disabled = false;
  });

  // ─── 提示词管理 ───────────────────────────────────────────────────────
  function renderPrompts() {
    el.promptList.innerHTML = "";
    if (!state.prompts.length) { el.promptList.innerHTML = '<div class="empty">尚无提示词</div>'; return; }
    state.prompts.forEach(function (p) {
      var d = document.createElement("div");
      d.className = "list-item" + (p.id === state.activePrompt ? " active" : "");
      d.innerHTML = '<div class="info"><div class="n"></div><div class="d"></div></div>' +
        '<span class="pill' + (p.id === state.activePrompt ? ' on' : '') + '">' + (p.id === state.activePrompt ? '使用中' : '启用') + '</span>' +
        '<button class="btn sm">编辑</button><button class="btn sm danger">删除</button>';
      d.querySelector(".n").textContent = p.name;
      d.querySelector(".d").textContent = p.body.slice(0, 100);
      d.querySelector(".pill").addEventListener("click", function () { state.activePrompt = p.id; save(K.activePrompt, p.id); renderPrompts(); });
      var btns = d.querySelectorAll("button");
      btns[0].addEventListener("click", function () { $("#p_name").value = p.name; $("#p_body").value = p.body; $("#p_save").dataset.edit = p.id; });
      btns[1].addEventListener("click", function () {
        state.prompts = state.prompts.filter(function (x) { return x.id !== p.id; });
        if (state.activePrompt === p.id) state.activePrompt = state.prompts.length ? state.prompts[0].id : null;
        save(K.prompts, state.prompts); save(K.activePrompt, state.activePrompt); renderPrompts();
      });
      el.promptList.appendChild(d);
    });
  }
  $("#p_clear").addEventListener("click", function () { $("#p_name").value = ""; $("#p_body").value = ""; delete $("#p_save").dataset.edit; });
  $("#p_save").addEventListener("click", function () {
    var name = $("#p_name").value.trim(), body = $("#p_body").value.trim();
    if (!name || !body) { toast("名称与内容必填"); return; }
    var editId = $("#p_save").dataset.edit;
    if (editId) { var p = state.prompts.find(function (x) { return x.id === editId; }); if (p) { p.name = name; p.body = body; } }
    else { var np = { id: uid(), name: name, body: body }; state.prompts.push(np); if (!state.activePrompt) state.activePrompt = np.id; }
    save(K.prompts, state.prompts); save(K.activePrompt, state.activePrompt);
    $("#p_name").value = ""; $("#p_body").value = ""; delete $("#p_save").dataset.edit; renderPrompts(); toast("已保存提示词");
  });

  // ─── 工具定义(供 LLM function calling) ────────────────────────────────
  // 统一动词层: 与后端 MCP/CLI/SDK 共用同一份 verbs.manifest (core/verbs.py 生成),
  // 同一套动词、同一执行语义. 面板本地便捷工具 (eda_call/get_context/toast) 保留为逃生口.
  var VERB_TOOLS = (window.DaoVerbs && window.DaoVerbs.buildTools()) || [];
  var TOOLS = VERB_TOOLS.concat([
    { type: "function", function: {
      name: "eda_call",
      description: "调用嘉立创EDA官方 EXTAPI 的任意方法直接驱动引擎。namespace 如 dmt_Project/dmt_Pcb/pcb_PrimitiveVia/pcb_Drc/sch_Netlist/sys_Message 等;method 为该命名空间下方法名;args 为参数数组。返回该方法结果。",
      parameters: { type: "object", properties: {
        namespace: { type: "string", description: "命名空间, 如 dmt_Pcb" },
        method: { type: "string", description: "方法名, 如 getCurrentPcbInfo" },
        args: { type: "array", description: "参数数组, 无参传 []", items: {} }
      }, required: ["namespace", "method"] } } },
    { type: "function", function: {
      name: "get_context",
      description: "获取当前 EDA 上下文:编辑器版本、当前工程、当前板、所有板信息。用于开始操作前的态势感知。",
      parameters: { type: "object", properties: {} } } },
    { type: "function", function: {
      name: "toast",
      description: "在嘉立创EDA界面弹出一条提示消息给用户。",
      parameters: { type: "object", properties: { message: { type: "string" } }, required: ["message"] } } },
  ]);

  async function runTool(name, argStr) {
    var args = {};
    try { args = argStr ? JSON.parse(argStr) : {}; } catch (e) { return { error: true, out: "参数解析失败: " + e.message }; }
    try {
      // 统一动词 (eda.* / eda_*): 走与后端一致的 recipe 执行器
      var verb = window.DaoVerbs && window.DaoVerbs.verbByToolName(name);
      if (verb && !verb.backend_only) {
        var vr = await window.DaoVerbs.execVerb(edaCall, verb, args);
        return { error: false, out: JSON.stringify(vr) };
      }
      if (name === "eda_call") {
        var r = await edaCall(args.namespace, args.method, args.args || []);
        return { error: false, out: JSON.stringify(r) };
      }
      if (name === "get_context") {
        var ctx = {};
        ctx.version = await edaCall("sys_Environment", "getEditorCurrentVersion", []).catch(function (e) { return String(e); });
        ctx.project = await edaCall("dmt_Project", "getCurrentProjectInfo", []).catch(function (e) { return null; });
        ctx.pcb = await edaCall("dmt_Pcb", "getCurrentPcbInfo", []).catch(function (e) { return null; });
        ctx.boards = await edaCall("dmt_Board", "getAllBoardsInfo", []).catch(function (e) { return null; });
        updateContextBar(ctx);
        return { error: false, out: JSON.stringify(ctx) };
      }
      if (name === "toast") {
        await edaCall("sys_Message", "showToastMessage", [String(args.message || "")]).catch(function () {
          return edaCall("sys_ToastMessage", "showMessage", [String(args.message || "")]);
        });
        return { error: false, out: "已弹出提示" };
      }
      return { error: true, out: "未知工具: " + name };
    } catch (e) { return { error: true, out: String(e && e.message || e) }; }
  }

  // ─── 对话主回路(含工具调用循环) ──────────────────────────────────────
  async function sendMessage() {
    if (state.busy) { state.abort = true; return; }
    var text = el.input.value.trim();
    if (!text) return;
    var s = curSession();
    if (!s) { newSession(); s = curSession(); }
    var model = state.models.find(function (m) { return m.id === state.activeModel; });
    if (!model) { toast("请先在「模型」页配置外接 API"); return; }

    s.messages.push({ role: "user", content: text });
    if (s.messages.filter(function (m) { return m.role === "user"; }).length === 1) {
      s.name = text.slice(0, 24); el.chatTitle.textContent = s.name;
    }
    el.input.value = ""; autosize();
    persistSessions(); renderSessions(); renderChat();
    setBusy(true);

    try {
      var maxIters = 8;
      for (var iter = 0; iter < maxIters; iter++) {
        if (state.abort) break;
        // 流式: 先挂思考态活节点, 逐 token 更新, 结束后固化进会话
        var live = appendStreamingDom();
        var reply;
        try {
          reply = await callLLM(model, s, function (partial) { updateStreamingDom(live, partial); });
        } finally { live.remove(); }
        if (!reply) break;
        var asMsg = { role: "assistant", content: reply.content || "", tool_calls: reply.tool_calls || null };
        s.messages.push(asMsg);
        persistSessions(); renderChat();
        if (!reply.tool_calls || !reply.tool_calls.length) break;
        // 执行工具并实时回显(运行态 → 结果)
        for (var i = 0; i < reply.tool_calls.length; i++) {
          var tc = asMsg.tool_calls[i];
          tc._running = true; renderChat();
          var res = await runTool(tc.function.name, tc.function.arguments);
          tc._running = false; tc._result = res.out; tc._error = res.error;
          s.messages.push({ role: "tool", tool_call_id: tc.id, name: tc.function.name, content: res.out });
          persistSessions(); renderChat();
        }
      }
    } catch (e) {
      s.messages.push({ role: "assistant", content: "⚠ 出错: " + (e && e.message || e) });
      persistSessions(); renderChat();
    }
    setBusy(false);
  }

  // 构造 OpenAI 兼容 messages 并请求 — 首选 SSE 流式(真机验证 sys_ClientUrl 返回
  // 真 fetch Response, body 可增量读); 服务不支持流式时自动回退整包 JSON.
  async function callLLM(model, s, onDelta) {
    var msgs = [];
    var prompt = state.prompts.find(function (p) { return p.id === state.activePrompt; });
    if (prompt) msgs.push({ role: "system", content: prompt.body });
    s.messages.forEach(function (m) {
      if (m.role === "user") msgs.push({ role: "user", content: m.content });
      else if (m.role === "assistant") {
        var a = { role: "assistant", content: m.content || "" };
        if (m.tool_calls) a.tool_calls = m.tool_calls.map(function (t) { return { id: t.id, type: "function", function: { name: t.function.name, arguments: t.function.arguments } }; });
        msgs.push(a);
      } else if (m.role === "tool") msgs.push({ role: "tool", tool_call_id: m.tool_call_id, content: m.content });
    });
    var body = { model: model.model, messages: msgs, temperature: model.temp, tools: TOOLS, tool_choice: "auto", stream: true };
    if (!ROOT || !ROOT.sys_ClientUrl) throw new Error("_EXTAPI_ROOT_.sys_ClientUrl 不可用");
    var resp = await ROOT.sys_ClientUrl.request(model.base + "/chat/completions", "POST", JSON.stringify(body),
      { headers: { "Content-Type": "application/json", "Authorization": "Bearer " + model.key } });
    if (resp.status < 200 || resp.status >= 300) {
      var errTxt = ""; try { errTxt = await resp.text(); } catch (e) {}
      throw new Error("LLM HTTP " + resp.status + ": " + errTxt.slice(0, 200));
    }
    var full = "";
    var acc = { content: "", tool_calls: [] };
    var sawSSE = false;
    if (resp.body && typeof resp.body.getReader === "function") {
      var reader = resp.body.getReader();
      var dec = new TextDecoder("utf-8");
      var buf = "";
      while (true) {
        var chunk = await reader.read();
        if (chunk.done) break;
        var piece = dec.decode(chunk.value, { stream: true });
        full += piece; buf += piece;
        var nl;
        while ((nl = buf.indexOf("\n")) >= 0) {
          var line = buf.slice(0, nl).replace(/\r$/, ""); buf = buf.slice(nl + 1);
          if (line.indexOf("data:") !== 0) continue;
          var payload = line.slice(5).trim();
          if (!payload || payload === "[DONE]") { sawSSE = sawSSE || payload === "[DONE]"; continue; }
          var evt; try { evt = JSON.parse(payload); } catch (e) { continue; }
          sawSSE = true;
          var delta = evt.choices && evt.choices[0] && evt.choices[0].delta;
          if (!delta) continue;
          if (delta.content) { acc.content += delta.content; if (onDelta) onDelta(acc.content); }
          if (delta.tool_calls) {
            delta.tool_calls.forEach(function (d) {
              var i = d.index || 0;
              var t = acc.tool_calls[i] || (acc.tool_calls[i] = { id: "", type: "function", function: { name: "", arguments: "" } });
              if (d.id) t.id = d.id;
              if (d.function && d.function.name) t.function.name += d.function.name;
              if (d.function && d.function.arguments) t.function.arguments += d.function.arguments;
            });
          }
        }
      }
    } else {
      try { full = await resp.text(); } catch (e) { full = ""; }
    }
    if (sawSSE) return { content: acc.content || null, tool_calls: acc.tool_calls.length ? acc.tool_calls : null };
    // 回退: 服务忽略 stream, 返回了整包 chat.completion JSON
    var data = JSON.parse(full);
    var m = data.choices && data.choices[0] && data.choices[0].message;
    if (!m) throw new Error("响应无 choices: " + full.slice(0, 200));
    if (m.content && onDelta) onDelta(m.content);
    return { content: m.content, tool_calls: m.tool_calls };
  }

  function setBusy(b) {
    state.busy = b; state.abort = false;
    el.send.textContent = b ? "停止" : "发送";
    el.send.classList.toggle("stop", b);
    el.input.disabled = false;
  }

  // ─── 状态栏 ──────────────────────────────────────────────────────────
  function updateContextBar(ctx) {
    try {
      var p = ctx && ctx.project, pcb = ctx && ctx.pcb;
      var t = "工程: " + (p && (p.name || p.projectName) || "—");
      if (pcb && (pcb.name || pcb.pcbName)) t += " · 板: " + (pcb.name || pcb.pcbName);
      el.ctxTxt.textContent = t;
    } catch (e) {}
  }
  async function detectEda() {
    ROOT = getRoot();
    if (ROOT) {
      el.edaDot.className = "dot on";
      try {
        var v = await edaCall("sys_Environment", "getEditorCurrentVersion", []);
        el.edaTxt.textContent = "EDA 引擎: 已连 v" + (v || "?");
      } catch (e) { el.edaTxt.textContent = "EDA 引擎: 已连(命名空间就绪)"; }
      try {
        var proj = await edaCall("dmt_Project", "getCurrentProjectInfo", []).catch(function () { return null; });
        var pcb = await edaCall("dmt_Pcb", "getCurrentPcbInfo", []).catch(function () { return null; });
        updateContextBar({ project: proj, pcb: pcb });
      } catch (e) {}
    } else {
      el.edaDot.className = "dot off";
      el.edaTxt.textContent = "EDA 引擎: 未就绪(需在编辑器内打开)";
    }
  }

  function toast(msg) {
    if (ROOT) { edaCall("sys_Message", "showToastMessage", [String(msg)]).catch(function () {
      edaCall("sys_ToastMessage", "showMessage", [String(msg)]).catch(function () {}); }); }
    // 也在 hint 区回显
    el.hint.textContent = msg; setTimeout(function () {
      el.hint.textContent = "AI 可调用工具直接驱动嘉立创EDA引擎(放置/布线/DRC/导出)。先在「模型」页配置外接 API。";
    }, 4000);
  }

  // ─── 输入交互 ─────────────────────────────────────────────────────────
  function autosize() { el.input.style.height = "auto"; el.input.style.height = Math.min(el.input.scrollHeight, 160) + "px"; }
  el.input.addEventListener("input", autosize);
  el.input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });
  el.send.addEventListener("click", sendMessage);

  // ─── 启动 ────────────────────────────────────────────────────────────
  renderModelSelect(); renderSessions();
  if (!state.sessions.length) newSession(); else renderChat();
  detectEda();
  setInterval(detectEda, 8000);
})();
