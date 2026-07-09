// DAO LCEDA — 嘉立创EDA 归一面板 (VS Code / Devin Desktop 插件)
// 中间面板整块承载嘉立创EDA(经本地 CDP 桥), 左侧工程树, 右/下方道之对话。
// Windows / Linux / Web 版 EDA 一视同仁: 只要有 CDP 目标即可整块路由。
const vscode = require("vscode");
const cp = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");

let serverProc = null;

function cfg() {
  return vscode.workspace.getConfiguration("daoLceda");
}

function findBridgeDir(context) {
  const explicit = cfg().get("bridgePath");
  if (explicit && fs.existsSync(path.join(explicit, "bridge_server.py"))) return explicit;
  for (const f of vscode.workspace.workspaceFolders || []) {
    const cand = path.join(f.uri.fsPath, "lceda_bridge", "vscode_lceda");
    if (fs.existsSync(path.join(cand, "bridge_server.py"))) return cand;
  }
  const bundled = path.join(context.extensionPath, "bridge");
  if (fs.existsSync(path.join(bundled, "bridge_server.py"))) return bundled;
  return null;
}

function health(port) {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port, path: "/api/health", timeout: 2000 },
      (res) => resolve(res.statusCode === 200));
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

function apiJson(port, method, apiPath, body) {
  return new Promise((resolve) => {
    const payload = body ? JSON.stringify(body) : null;
    const req = http.request({
      host: "127.0.0.1", port, path: apiPath, method,
      headers: payload ? { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) } : {},
      timeout: 30000,
    }, (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => {
        try { resolve(JSON.parse(data)); } catch (e) { resolve(null); }
      });
    });
    req.on("error", () => resolve(null));
    req.on("timeout", () => { req.destroy(); resolve(null); });
    if (payload) req.write(payload);
    req.end();
  });
}

async function ensureServer(context) {
  const port = cfg().get("port") || 9940;
  if (await health(port)) return port;
  const dir = findBridgeDir(context);
  if (!dir) {
    vscode.window.showErrorMessage("DAO LCEDA: 找不到 bridge_server.py。请设置 daoLceda.bridgePath。");
    return null;
  }
  const py = cfg().get("python") || "python3";
  serverProc = cp.spawn(py, [path.join(dir, "bridge_server.py")], {
    cwd: dir,
    env: {
      ...process.env,
      LCEDA_BRIDGE_PORT: String(port),
      DAO_CDP_PORTS: cfg().get("cdpPorts") || "9222,29229,29230",
      DAO_PREFER_LOCAL_EDA: cfg().get("preferLocalEda") === false ? "0" : "1",
    },
  });
  serverProc.on("error", (e) =>
    vscode.window.showErrorMessage("DAO LCEDA 桥接启动失败: " + e.message));
  context.subscriptions.push({ dispose: () => serverProc && serverProc.kill() });
  for (let i = 0; i < 24; i++) {
    if (await health(port)) return port;
    await new Promise((r) => setTimeout(r, 500));
  }
  vscode.window.showErrorMessage("DAO LCEDA: 桥接服务未就绪(端口 " + port + ")。请确认嘉立创EDA已带 CDP 启动。");
  return null;
}

// ---------- 中间面板: 整块 EDA ----------
async function runTool(port, tool, args) {
  const r = await apiJson(port, "POST", "/api/agent", { tool, args: args || {} });
  if (!r || !r.ok || !r.job) return null;
  const deadline = Date.now() + 3 * 60 * 1000;
  while (Date.now() < deadline) {
    await new Promise((res) => setTimeout(res, 1200));
    const j = await apiJson(port, "GET", "/api/agent/" + r.job);
    if (j && j.ok && j.job.status !== "running") return j.job;
  }
  return null;
}

async function screenshotPanel(context) {
  const port = await ensureServer(context);
  if (!port) return;
  const job = await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: "嘉立创EDA 画布截图…" },
    () => runTool(port, "canvas.image"));
  const step = job && job.steps && job.steps[0];
  let src = step && step.status === "done" ? step.result : null;
  if (src && src._truncated) src = src._truncated;
  if (typeof src !== "string" || !src.startsWith("data:image")) {
    vscode.window.showErrorMessage("DAO LCEDA: 截图失败(画布未就绪或桥接未响应)");
    return;
  }
  const panel = vscode.window.createWebviewPanel(
    "daoLcedaShot", "EDA 画布截图", vscode.ViewColumn.Active, {});
  panel.webview.html = `<!DOCTYPE html><html><body style="margin:0;background:#1e1e1e">` +
    `<img src="${src}" style="max-width:100%"></body></html>`;
}

async function openPanel(context) {
  const port = await ensureServer(context);
  if (!port) return;
  const base = "http://127.0.0.1:" + port;
  // 归一外壳(本源, 取自 devin-remote dao-vsix「网页套网页」架构):
  // 标签栏平级承载 本地EDA(/native) · 官网网页版(/web) · 配置(/config), 可无限延伸。
  const mode = cfg().get("panelMode") || "shell";
  const framePath = mode === "screencast" ? "/panel"
    : (mode === "native" ? "/native" : "/shell");
  const panel = vscode.window.createWebviewPanel(
    "daoLcedaPanel", "嘉立创EDA (道之面板)", vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true });
  panel.webview.html = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; frame-src ${base}; style-src 'unsafe-inline';">
<style>html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:#1e1e1e;}
iframe{border:0;width:100%;height:100vh;}</style></head>
<body><iframe src="${base}${framePath}" allow="clipboard-read; clipboard-write"></iframe></body></html>`;
}

// ---------- 左侧: 工程树 ----------
class ProjectTreeProvider {
  constructor(context) {
    this.context = context;
    this._emitter = new vscode.EventEmitter();
    this.onDidChangeTreeData = this._emitter.event;
    this.data = null;
  }
  refresh() {
    this.data = null;
    this._emitter.fire();
  }
  getTreeItem(el) { return el; }
  async getChildren(el) {
    if (el) return el.childrenItems || [];
    const port = cfg().get("port") || 9940;
    if (!(await health(port))) {
      return [new vscode.TreeItem("(桥接未就绪 — 先运行 DAO LCEDA: 打开嘉立创EDA)")];
    }
    const tree = await apiJson(port, "GET", "/api/tree");
    if (!tree || !tree.ok) {
      return [new vscode.TreeItem("(未取到工程 — EDA 可能未登录/未打开工程)")];
    }
    const items = [];
    if (tree.current) {
      const cur = new vscode.TreeItem(
        "当前工程: " + (tree.current.friendlyName || tree.current.name || tree.current.uuid || "?"),
        vscode.TreeItemCollapsibleState.Expanded);
      cur.iconPath = new vscode.ThemeIcon("circuit-board");
      cur.childrenItems = [];
      for (const s of tree.schematics || []) {
        const pages = (s.page || []).length ? s.page : [s];
        for (const p of pages) {
          const label = "原理图: " + (s.name || s.uuid || "?") +
            (pages.length > 1 ? " · " + (p.name || p.uuid) : "");
          const it = new vscode.TreeItem(label, vscode.TreeItemCollapsibleState.None);
          it.iconPath = new vscode.ThemeIcon("file-code");
          if (p.uuid) it.command = { command: "daoLceda.openDoc", title: "打开文档", arguments: [p.uuid] };
          cur.childrenItems.push(it);
        }
      }
      items.push(cur);
    }
    for (const uuid of tree.projectUuids || []) {
      if (tree.current && (uuid === tree.current.uuid)) continue;
      const it = new vscode.TreeItem("工程 " + uuid, vscode.TreeItemCollapsibleState.None);
      it.iconPath = new vscode.ThemeIcon("repo");
      it.command = { command: "daoLceda.openProject", title: "切换工程", arguments: [uuid] };
      items.push(it);
    }
    for (const lp of tree.localProjects || []) {
      const it = new vscode.TreeItem(
        (lp.kind === "example-projects" ? "示例: " : "本地: ") + lp.name,
        vscode.TreeItemCollapsibleState.None);
      it.iconPath = new vscode.ThemeIcon("file-directory");
      it.tooltip = lp.path;
      items.push(it);
    }
    if (!items.length) items.push(new vscode.TreeItem("(EDA 内暂无打开的工程)"));
    return items;
  }
}

// ---------- 右/下方: 道之对话 (Copilot/Augment 式) ----------
const HISTORY_KEY = "daoLceda.chatHistory";
const HISTORY_MAX = 200;

class ChatViewProvider {
  constructor(context) {
    this.context = context;
    this.views = new Set();
  }
  loadHistory() { return this.context.globalState.get(HISTORY_KEY) || []; }
  saveHistory(items) {
    this.context.globalState.update(HISTORY_KEY, items.slice(-HISTORY_MAX));
  }
  pushHistory(entry) {
    const items = this.loadHistory();
    items.push(entry);
    this.saveHistory(items);
  }
  clear() {
    this.saveHistory([]);
    for (const v of this.views) v.webview.postMessage({ type: "clear" });
  }
  resolveWebviewView(view) {
    view.webview.options = { enableScripts: true };
    view.webview.html = chatHtml();
    this.views.add(view);
    view.onDidDispose(() => this.views.delete(view));
    view.webview.onDidReceiveMessage(async (m) => {
      const port = cfg().get("port") || 9940;
      if (m.type === "init") {
        view.webview.postMessage({ type: "history", items: this.loadHistory() });
        const tools = await apiJson(port, "GET", "/api/tools");
        if (tools && tools.ok) view.webview.postMessage({ type: "tools", tools: tools.tools });
        this.pushContext(view, port);
        return;
      }
      if (m.type === "context") { this.pushContext(view, port); return; }
      if (m.type === "persist") { this.pushHistory(m.entry); return; }
      if (m.type === "clear") { this.clear(); return; }
      if (m.type !== "chat") return;
      // 斜杠命令: /tool.name {json参数}  → 直调工具; 否则自然语言路由
      let payload = { text: m.text };
      const sm = /^\/([a-z]+\.[a-z]+)\s*(\{.*\})?\s*$/i.exec(m.text || "");
      if (sm) {
        payload = { tool: sm[1] };
        if (sm[2]) { try { payload.args = JSON.parse(sm[2]); } catch (e) { /* 保持无参 */ } }
      }
      const r = await apiJson(port, "POST", "/api/agent", payload);
      if (!r || !r.ok) {
        view.webview.postMessage({ type: "reply", text: "(桥接未响应 — 可运行命令 DAO LCEDA: 重启桥接服务)" });
        return;
      }
      if (!r.job) {
        view.webview.postMessage({ type: "reply", text: r.reply });
        return;
      }
      view.webview.postMessage({ type: "jobStart", job: r.job, text: r.reply });
      const deadline = Date.now() + 15 * 60 * 1000;
      while (Date.now() < deadline) {
        await new Promise((res) => setTimeout(res, 1500));
        const j = await apiJson(port, "GET", "/api/agent/" + r.job);
        if (!j || !j.ok) continue;
        view.webview.postMessage({
          type: "jobUpdate", job: r.job, text: r.reply,
          steps: j.job.steps, status: j.job.status,
        });
        if (j.job.status !== "running") break;
      }
      this.pushContext(view, port);
      vscode.commands.executeCommand("daoLceda.refreshTree");
    });
  }
  async pushContext(view, port) {
    const tree = await apiJson(port, "GET", "/api/tree");
    let label = "未连接";
    if (tree && tree.ok) {
      label = tree.current
        ? (tree.current.friendlyName || tree.current.name || tree.current.uuid)
        : "已连接 · 无打开工程";
    }
    view.webview.postMessage({ type: "contextChip", label });
  }
}

function chatHtml() {
  return `<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{font:13px/1.5 var(--vscode-font-family);color:var(--vscode-foreground);margin:0;display:flex;flex-direction:column;height:100vh;}
#chip{padding:4px 8px;font-size:11px;opacity:.85;border-bottom:1px solid var(--vscode-panel-border);display:flex;justify-content:space-between;align-items:center;}
#chip .ctx{background:var(--vscode-badge-background);color:var(--vscode-badge-foreground);border-radius:8px;padding:1px 8px;}
#chip a{cursor:pointer;text-decoration:underline;}
#quick{padding:3px 8px;border-bottom:1px solid var(--vscode-panel-border);display:flex;gap:6px;}
#quick a{cursor:pointer;font-size:11px;background:var(--vscode-button-secondaryBackground);color:var(--vscode-button-secondaryForeground);border-radius:8px;padding:1px 8px;}
#log{flex:1;overflow-y:auto;padding:8px;}
.msg{margin:4px 0;padding:6px 8px;border-radius:6px;white-space:pre-wrap;word-break:break-all;}
.user{background:var(--vscode-editor-inactiveSelectionBackground);}
.bot{background:var(--vscode-editorWidget-background);}
.msg img{max-width:100%;display:block;margin-top:6px;border:1px solid var(--vscode-panel-border);}
#menu{display:none;position:absolute;bottom:44px;left:6px;right:6px;max-height:180px;overflow-y:auto;background:var(--vscode-editorWidget-background);border:1px solid var(--vscode-panel-border);z-index:9;}
#menu div{padding:4px 8px;cursor:pointer;}
#menu div.sel,#menu div:hover{background:var(--vscode-list-activeSelectionBackground);color:var(--vscode-list-activeSelectionForeground);}
#bar{display:flex;padding:6px;gap:6px;border-top:1px solid var(--vscode-panel-border);position:relative;}
#in{flex:1;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border);padding:4px 6px;}
button{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:0;padding:4px 10px;cursor:pointer;}
</style></head><body>
<div id="chip"><span>当前工程: <span class="ctx" id="ctx">…</span></span><a id="clear">清空会话</a></div>
<div id="quick"><a data-t="当前工程信息">工程信息</a><a data-t="画布截图">画布截图</a><a data-t="DRC">DRC</a><a data-t="全链路">全链路</a></div>
<div id="log"><div class="msg bot">道之助手(Copilot 式)已就绪。输入 / 可选工具; 或说: 建工程 / 检索 STM32F103 / 布局 / 板框 / 自动布线 / 覆铜 / DRC / 出产 / 全链路 / 当前工程信息 / 画布截图。</div></div>
<div id="bar"><div id="menu"></div><input id="in" placeholder="向嘉立创EDA下令… (/工具名 直调)"><button id="send">发</button></div>
<script>
const vscodeApi = acquireVsCodeApi();
const log = document.getElementById('log'); const input = document.getElementById('in');
const menu = document.getElementById('menu');
const jobs = {}; let toolList = []; let menuSel = 0;
const IMG_RE = /^(data:image\\/[a-z+]+;base64,|iVBORw0KGgo|\\/9j\\/)/;
function asImgSrc(v){
  if (typeof v !== 'string' || v.length < 200 || !IMG_RE.test(v)) return null;
  if (v.startsWith('data:image')) return v;
  return 'data:image/' + (v.startsWith('iVBOR') ? 'png' : 'jpeg') + ';base64,' + v;
}
function add(cls, text, img, persist){
  const d=document.createElement('div'); d.className='msg '+cls; d.textContent=text;
  if (img){ const i=document.createElement('img'); i.src=img; d.appendChild(i); }
  log.appendChild(d); log.scrollTop=log.scrollHeight;
  if (persist !== false) vscodeApi.postMessage({type:'persist', entry:{cls, text, img: img||null}});
  return d;
}
function send(){ const t=input.value.trim(); if(!t) return; hideMenu(); add('user', t); input.value=''; vscodeApi.postMessage({type:'chat', text:t}); }
document.getElementById('send').onclick = send;
document.getElementById('clear').onclick = ()=> vscodeApi.postMessage({type:'clear'});
[].forEach.call(document.querySelectorAll('#quick a'), a=>{
  a.onclick = ()=>{ input.value = a.dataset.t; send(); };
});
function showMenu(prefix){
  const q = prefix.slice(1).toLowerCase();
  const hits = toolList.filter(t=> t.tool.includes(q) || (t.desc||'').toLowerCase().includes(q));
  if (!hits.length){ hideMenu(); return; }
  menu.innerHTML=''; menuSel=0;
  hits.forEach((t,i)=>{ const d=document.createElement('div'); if(i===0)d.className='sel';
    d.textContent='/'+t.tool+' — '+t.desc; d.onclick=()=>{ input.value='/'+t.tool+' '; hideMenu(); input.focus(); };
    menu.appendChild(d); });
  menu.style.display='block';
}
function hideMenu(){ menu.style.display='none'; }
input.addEventListener('input', ()=>{ const v=input.value; (v.startsWith('/') && !v.includes(' ')) ? showMenu(v) : hideMenu(); });
input.addEventListener('keydown', e=>{
  if (menu.style.display==='block'){
    const items=[].slice.call(menu.children);
    if (e.key==='ArrowDown'||e.key==='ArrowUp'){ e.preventDefault();
      items[menuSel]&&(items[menuSel].className='');
      menuSel=(menuSel+(e.key==='ArrowDown'?1:items.length-1))%items.length;
      items[menuSel].className='sel'; items[menuSel].scrollIntoView({block:'nearest'}); return; }
    if (e.key==='Tab'||e.key==='Enter'){ e.preventDefault(); items[menuSel]&&items[menuSel].onclick(); return; }
    if (e.key==='Escape'){ hideMenu(); return; }
  }
  if(e.key==='Enter') send();
});
function renderSteps(el, m){
  let text = m.text; let img=null;
  for (const s of m.steps || []) {
    const mark = s.status === 'done' ? '✔' : (s.status === 'failed' ? '✘' : '⏳');
    text += '\\n' + mark + ' ' + s.tool + (s.ms ? ' (' + s.ms + 'ms)' : '');
    if (s.error) text += ' — ' + s.error;
    else if (s.status === 'done' && s.result !== undefined) {
      const src = asImgSrc(s.result) || asImgSrc(s.result && s.result._truncated);
      if (src) { img = src; text += ' → [图像]'; }
      else text += ' → ' + JSON.stringify(s.result).slice(0, 300);
    }
  }
  if (m.status === 'done') text += '\\n✔ 作业完成';
  if (m.status === 'failed') text += '\\n✘ 作业失败';
  el.textContent = text;
  if (img){ const i=document.createElement('img'); i.src=img; el.appendChild(i); }
  log.scrollTop = log.scrollHeight;
  if (m.status && m.status !== 'running')
    vscodeApi.postMessage({type:'persist', entry:{cls:'bot', text, img: img||null}});
}
window.addEventListener('message', e=>{
  const m = e.data;
  if (m.type === 'history') { for (const h of m.items || []) add(h.cls, h.text, h.img, false); }
  else if (m.type === 'tools') { toolList = m.tools || []; }
  else if (m.type === 'contextChip') { document.getElementById('ctx').textContent = m.label; }
  else if (m.type === 'clear') { log.innerHTML=''; add('bot','(会话已清空)', null, false); }
  else if (m.type === 'reply') { add('bot', m.text); }
  else if (m.type === 'jobStart') { jobs[m.job] = add('bot', m.text + '\\n⏳ 作业 ' + m.job + ' 执行中…', null, false); }
  else if (m.type === 'jobUpdate') { const el = jobs[m.job]; if (el) renderSteps(el, m); }
});
vscodeApi.postMessage({type:'init'});
</script></body></html>`;
}

function activate(context) {
  // AI 交互基底(dao-ai-base · Devin Desktop 同源): Cascade 三模式面板, 命名空间 daoLceda.cascade*。
  try {
    const daoAiBase = require("./dao-ai-base");
    daoAiBase.activateDaoAiBase(context, { ns: "daoLceda", log: (m) => console.log("[dao-ai-base] " + m) });
  } catch (e) { console.error("[dao-ai-base] 基底激活失败: " + (e && e.stack ? e.stack : e)); }
  const treeProvider = new ProjectTreeProvider(context);
  const chatProvider = new ChatViewProvider(context);
  // 右下角状态栏按钮: 一键弹出 EDA 面板。
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, -1000);
  status.text = "$(circuit-board) 嘉立创EDA";
  status.tooltip = "一键弹出嘉立创EDA 道之面板";
  status.command = "daoLceda.open";
  status.show();
  const pollHealth = async () => {
    const ok = await health(cfg().get("port") || 9940);
    status.text = ok ? "$(circuit-board) 嘉立创EDA" : "$(debug-disconnect) 嘉立创EDA(桥断)";
    status.tooltip = ok ? "桥接在线 · 打开道之面板" : "桥接未就绪 · 点击启动";
  };
  pollHealth();
  const healthTimer = setInterval(pollHealth, 15000);
  context.subscriptions.push({ dispose: () => clearInterval(healthTimer) });
  const treeOp = async (tool, args, label) => {
    const port = await ensureServer(context);
    if (!port) return;
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: label },
      () => runTool(port, tool, args));
    treeProvider.refresh();
  };
  context.subscriptions.push(
    status,
    vscode.commands.registerCommand("daoLceda.open", () => openPanel(context)),
    vscode.commands.registerCommand("daoLceda.refreshTree", () => treeProvider.refresh()),
    vscode.commands.registerCommand("daoLceda.clearChat", () => chatProvider.clear()),
    vscode.commands.registerCommand("daoLceda.screenshot", () => screenshotPanel(context)),
    vscode.commands.registerCommand("daoLceda.openDoc",
      (uuid) => treeOp("doc.open", { uuid }, "打开文档…")),
    vscode.commands.registerCommand("daoLceda.openProject",
      (uuid) => treeOp("project.open", { uuid }, "切换工程…")),
    vscode.commands.registerCommand("daoLceda.restartBridge", async () => {
      if (serverProc) serverProc.kill();
      serverProc = null;
      await ensureServer(context);
      vscode.window.showInformationMessage("DAO LCEDA 桥接已重启");
    }),
    vscode.window.registerTreeDataProvider("daoLcedaProjects", treeProvider),
    vscode.window.registerWebviewViewProvider("daoLcedaChat", chatProvider),
    vscode.window.registerWebviewViewProvider("daoLcedaChatSide", chatProvider),
  );
}

function deactivate() {
  if (serverProc) serverProc.kill();
}

module.exports = { activate, deactivate };
