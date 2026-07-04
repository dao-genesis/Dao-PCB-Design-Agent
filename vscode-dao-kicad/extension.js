// DAO KiCad — 归一 PCB 工作台 (VS Code / Devin Desktop 插件)
// Spawns the daokicad bridge server and hosts the single-page home webview.
const vscode = require("vscode");
const cp = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");

let serverProc = null;

function findEngine() {
  const cfg = vscode.workspace.getConfiguration("daoKicad");
  const explicit = cfg.get("enginePath");
  if (explicit && fs.existsSync(path.join(explicit, "bridge", "ide_server.py"))) {
    return explicit;
  }
  for (const f of vscode.workspace.workspaceFolders || []) {
    for (const cand of [f.uri.fsPath, path.join(f.uri.fsPath, "dao_kicad")]) {
      if (fs.existsSync(path.join(cand, "bridge", "ide_server.py"))) return cand;
    }
  }
  return null;
}

function findPython() {
  const cfg = vscode.workspace.getConfiguration("daoKicad");
  const explicit = cfg.get("python");
  const candidates = explicit && explicit !== "python3"
    ? [explicit]
    : process.platform === "win32"
      ? ["python", "py", "python3"]
      : ["python3", "python"];
  for (const c of candidates) {
    try {
      const r = cp.spawnSync(c, ["--version"], { timeout: 5000 });
      if (r.status === 0) return c;
    } catch (e) { /* try next */ }
  }
  return candidates[0];
}

function health(port) {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port, path: "/api/health", timeout: 2000 },
      (res) => resolve(res.statusCode === 200));
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

async function ensureServer(context) {
  const cfg = vscode.workspace.getConfiguration("daoKicad");
  const port = cfg.get("port") || 9931;
  if (await health(port)) return port;
  const engine = findEngine();
  if (!engine) {
    vscode.window.showErrorMessage(
      "DAO KiCad: 找不到 daokicad 引擎 (bridge/ide_server.py)。请设置 daoKicad.enginePath。");
    return null;
  }
  const py = findPython();
  serverProc = cp.spawn(py, ["-m", "bridge.ide_server", "--port", String(port)], {
    cwd: engine,
    env: { ...process.env, PYTHONPATH: engine + path.delimiter + path.dirname(engine) },
  });
  serverProc.on("error", (e) =>
    vscode.window.showErrorMessage("DAO KiCad 桥接启动失败: " + e.message));
  context.subscriptions.push({ dispose: () => serverProc && serverProc.kill() });
  for (let i = 0; i < 20; i++) {
    if (await health(port)) return port;
    await new Promise((r) => setTimeout(r, 500));
  }
  vscode.window.showErrorMessage("DAO KiCad: 桥接服务未在预期时间内就绪 (端口 " + port + ")");
  return null;
}

async function openHome(context) {
  const port = await ensureServer(context);
  if (!port) return;
  const panel = vscode.window.createWebviewPanel(
    "daoKicadHome", "DAO KiCad 归一主页", vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true });
  let html = fs.readFileSync(path.join(context.extensionPath, "media", "home.html"), "utf8");
  const root = (vscode.workspace.workspaceFolders || [])[0];
  html = html
    .replace(/__SERVER__/g, "http://127.0.0.1:" + port)
    .replace(/__ROOT__/g, root ? root.uri.fsPath.replace(/\\/g, "\\\\") : "");
  panel.webview.html = html;
}

function chatHtml(context, port) {
  let html = fs.readFileSync(path.join(context.extensionPath, "media", "chat.html"), "utf8");
  const root = (vscode.workspace.workspaceFolders || [])[0];
  return html
    .replace(/__SERVER__/g, "http://127.0.0.1:" + port)
    .replace(/__ROOT__/g, root ? root.uri.fsPath.replace(/\\/g, "\\\\") : "");
}

class ChatViewProvider {
  constructor(context) { this.context = context; }
  async resolveWebviewView(view) {
    view.webview.options = { enableScripts: true };
    const port = await ensureServer(this.context);
    view.webview.html = chatHtml(this.context, port || 9931);
  }
}

async function openChat(context) {
  const port = await ensureServer(context);
  if (!port) return;
  const panel = vscode.window.createWebviewPanel(
    "daoKicadChat", "DAO KiCad Copilot", vscode.ViewColumn.Beside,
    { enableScripts: true, retainContextWhenHidden: true });
  panel.webview.html = chatHtml(context, port);
}

function activate(context) {
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("daoKicad.chatView",
      new ChatViewProvider(context), { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.commands.registerCommand("daoKicad.openChat", () => openChat(context)),
    vscode.commands.registerCommand("daoKicad.openHome", () => openHome(context)),
    vscode.commands.registerCommand("daoKicad.restartBridge", async () => {
      if (serverProc) serverProc.kill();
      serverProc = null;
      await ensureServer(context);
      vscode.window.showInformationMessage("DAO KiCad 桥接已重启");
    }));
}

function deactivate() {
  if (serverProc) serverProc.kill();
}

module.exports = { activate, deactivate };
