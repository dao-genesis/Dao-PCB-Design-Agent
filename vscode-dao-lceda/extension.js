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
      DAO_CDP_PORTS: cfg().get("cdpPorts") || "29229,29230",
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
async function openPanel(context) {
  const port = await ensureServer(context);
  if (!port) return;
  const base = "http://127.0.0.1:" + port;
  const panel = vscode.window.createWebviewPanel(
    "daoLcedaPanel", "嘉立创EDA (道之面板)", vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true });
  panel.webview.html = `<!DOCTYPE html>
<html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy"
      content="default-src 'none'; frame-src ${base}; style-src 'unsafe-inline';">
<style>html,body{margin:0;padding:0;width:100%;height:100%;overflow:hidden;background:#1e1e1e;}
iframe{border:0;width:100%;height:100vh;}</style></head>
<body><iframe src="${base}/panel" allow="clipboard-read; clipboard-write"></iframe></body></html>`;
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
        const it = new vscode.TreeItem(
          "原理图: " + (s.name || s.uuid || "?"), vscode.TreeItemCollapsibleState.None);
        it.iconPath = new vscode.ThemeIcon("file-code");
        cur.childrenItems.push(it);
      }
      items.push(cur);
    }
    for (const uuid of tree.projectUuids || []) {
      if (tree.current && (uuid === tree.current.uuid)) continue;
      const it = new vscode.TreeItem("工程 " + uuid, vscode.TreeItemCollapsibleState.None);
      it.iconPath = new vscode.ThemeIcon("repo");
      items.push(it);
    }
    if (!items.length) items.push(new vscode.TreeItem("(EDA 内暂无打开的工程)"));
    return items;
  }
}

// ---------- 右/下方: 道之对话 ----------
class ChatViewProvider {
  constructor(context) { this.context = context; }
  resolveWebviewView(view) {
    view.webview.options = { enableScripts: true };
    view.webview.html = `<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
body{font:13px/1.5 var(--vscode-font-family);color:var(--vscode-foreground);margin:0;display:flex;flex-direction:column;height:100vh;}
#log{flex:1;overflow-y:auto;padding:8px;}
.msg{margin:4px 0;padding:6px 8px;border-radius:6px;white-space:pre-wrap;word-break:break-all;}
.user{background:var(--vscode-editor-inactiveSelectionBackground);}
.bot{background:var(--vscode-editorWidget-background);}
#bar{display:flex;padding:6px;gap:6px;border-top:1px solid var(--vscode-panel-border);}
#in{flex:1;background:var(--vscode-input-background);color:var(--vscode-input-foreground);border:1px solid var(--vscode-input-border);padding:4px 6px;}
button{background:var(--vscode-button-background);color:var(--vscode-button-foreground);border:0;padding:4px 10px;cursor:pointer;}
</style></head><body>
<div id="log"><div class="msg bot">道之助手(Copilot 式)已就绪。可说: 建工程 / 检索 STM32F103 / 布局 / 板框 / 自动布线 / 覆铜 / DRC / 出产 / 全链路 / 当前工程信息 / 画布截图。</div></div>
<div id="bar"><input id="in" placeholder="向嘉立创EDA下令…"><button id="send">发</button></div>
<script>
const vscodeApi = acquireVsCodeApi();
const log = document.getElementById('log'); const input = document.getElementById('in');
const jobs = {};
function add(cls, text){ const d=document.createElement('div'); d.className='msg '+cls; d.textContent=text; log.appendChild(d); log.scrollTop=log.scrollHeight; return d; }
function send(){ const t=input.value.trim(); if(!t) return; add('user', t); input.value=''; vscodeApi.postMessage({type:'chat', text:t}); }
document.getElementById('send').onclick = send;
input.addEventListener('keydown', e=>{ if(e.key==='Enter') send(); });
window.addEventListener('message', e=>{
  const m = e.data;
  if (m.type === 'reply') { add('bot', m.text); }
  else if (m.type === 'jobStart') { jobs[m.job] = add('bot', m.text + '\\n⏳ 作业 ' + m.job + ' 执行中…'); }
  else if (m.type === 'jobUpdate') {
    const el = jobs[m.job]; if (!el) return;
    let text = m.text;
    for (const s of m.steps || []) {
      const mark = s.status === 'done' ? '✔' : (s.status === 'failed' ? '✘' : '⏳');
      text += '\\n' + mark + ' ' + s.tool + (s.ms ? ' (' + s.ms + 'ms)' : '');
      if (s.error) text += ' — ' + s.error;
      else if (s.status === 'done' && s.result !== undefined) text += ' → ' + JSON.stringify(s.result).slice(0, 300);
    }
    if (m.status === 'done') text += '\\n✔ 作业完成';
    if (m.status === 'failed') text += '\\n✘ 作业失败';
    el.textContent = text; log.scrollTop = log.scrollHeight;
  }
});
</script></body></html>`;
    view.webview.onDidReceiveMessage(async (m) => {
      if (m.type !== "chat") return;
      const port = cfg().get("port") || 9940;
      const r = await apiJson(port, "POST", "/api/agent", { text: m.text });
      if (!r || !r.ok) {
        view.webview.postMessage({ type: "reply", text: "(桥接未响应)" });
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
    });
  }
}

function activate(context) {
  const treeProvider = new ProjectTreeProvider(context);
  context.subscriptions.push(
    vscode.commands.registerCommand("daoLceda.open", () => openPanel(context)),
    vscode.commands.registerCommand("daoLceda.refreshTree", () => treeProvider.refresh()),
    vscode.commands.registerCommand("daoLceda.restartBridge", async () => {
      if (serverProc) serverProc.kill();
      serverProc = null;
      await ensureServer(context);
      vscode.window.showInformationMessage("DAO LCEDA 桥接已重启");
    }),
    vscode.window.registerTreeDataProvider("daoLcedaProjects", treeProvider),
    vscode.window.registerWebviewViewProvider("daoLcedaChat", new ChatViewProvider(context)),
  );
}

function deactivate() {
  if (serverProc) serverProc.kill();
}

module.exports = { activate, deactivate };
