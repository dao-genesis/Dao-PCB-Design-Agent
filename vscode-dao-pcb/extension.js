// DAO PCB — 归一 PCB 工作台 (VS Code / Devin Desktop 插件 · KiCad + 嘉立创EDA 双线合一)
// ─────────────────────────────────────────────────────────────────────────────
// 三合一结构(devin-remote dao-one 同构, PCB 位面):
//   · Devin Desktop 基底 (dao-ai-base): Cascade 三模式面板 + windsurf 垫片;
//   · Proxy Pro 同源模式层 (pcb-mode): native/dao/kicad/lceda 四态提示词隔离/替换;
//   · 归一主页 (media/home.html): 网页套网页, KiCad 工作台与嘉立创EDA 平级标签并列。
// 双桥并行(道并行而不相悖): dao_kicad ide_server(9931) + lceda bridge_server(9940),
// 两路 MCP(dao-kicad + lceda-dao)与官方工具体系并列原生注入。
const vscode = require("vscode");
const cp = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");
const tunnel = require("./tunnel");

let kicadProc = null;
let lcedaProc = null;

function cfg() {
  return vscode.workspace.getConfiguration("daoPcb");
}

// ---------- 发现: KiCad 引擎 / LCEDA 桥 ----------
function findKicadEngine() {
  const explicit = cfg().get("kicadEnginePath");
  if (explicit && fs.existsSync(path.join(explicit, "bridge", "ide_server.py"))) return explicit;
  for (const f of vscode.workspace.workspaceFolders || []) {
    for (const cand of [f.uri.fsPath, path.join(f.uri.fsPath, "dao_kicad")]) {
      if (fs.existsSync(path.join(cand, "bridge", "ide_server.py"))) return cand;
    }
  }
  return null;
}

function findLcedaBridge() {
  const explicit = cfg().get("lcedaBridgePath");
  if (explicit && fs.existsSync(path.join(explicit, "bridge_server.py"))) return explicit;
  for (const f of vscode.workspace.workspaceFolders || []) {
    const cand = path.join(f.uri.fsPath, "lceda_bridge", "vscode_lceda");
    if (fs.existsSync(path.join(cand, "bridge_server.py"))) return cand;
  }
  return null;
}

function findPython() {
  const explicit = cfg().get("python");
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

// ---------- HTTP ----------
function health(port) {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port, path: "/api/health", timeout: 2000 },
      (res) => resolve(res.statusCode === 200));
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

function apiJson(method, port, apiPath, body) {
  return new Promise((resolve) => {
    const data = body ? Buffer.from(JSON.stringify(body)) : null;
    const req = http.request({
      host: "127.0.0.1", port, path: apiPath, method,
      headers: Object.assign({ Authorization: "Bearer " + accessToken() },
        data ? { "Content-Type": "application/json", "Content-Length": data.length } : {}),
      timeout: 30000,
    }, (res) => {
      let buf = "";
      res.on("data", (c) => (buf += c));
      res.on("end", () => { try { resolve(JSON.parse(buf)); } catch (e) { resolve(null); } });
    });
    req.on("error", () => resolve(null));
    req.on("timeout", () => { req.destroy(); resolve(null); });
    if (data) req.write(data);
    req.end();
  });
}

// ---------- MCP: 双路领域工具原生注入(与官方工具体系并列平权) ----------
function registerMcp(py) {
  try {
    const dir = path.join(os.homedir(), ".codeium", "windsurf");
    fs.mkdirSync(dir, { recursive: true });
    const p = path.join(dir, "mcp_config.json");
    let conf = {};
    try { conf = JSON.parse(fs.readFileSync(p, "utf8")); } catch (e) { /* 新建 */ }
    if (!conf.mcpServers || typeof conf.mcpServers !== "object") conf.mcpServers = {};
    let changed = false;
    const kicadEngine = findKicadEngine();
    if (kicadEngine) {
      const entry = {
        command: py,
        args: [path.join(kicadEngine, "bridge", "mcp_server.py")],
        env: { PYTHONPATH: kicadEngine + path.delimiter + path.dirname(kicadEngine) },
      };
      const prev = conf.mcpServers["dao-kicad"];
      if (!prev || JSON.stringify({ command: prev.command, args: prev.args, env: prev.env })
          !== JSON.stringify(entry)) {
        conf.mcpServers["dao-kicad"] = Object.assign({}, prev, entry);
        changed = true;
      }
    }
    const lcedaDir = findLcedaBridge();
    if (lcedaDir) {
      const lcedaRoot = path.dirname(lcedaDir);   // .../lceda_bridge
      const entry = {
        command: py,
        args: ["-m", "core.mcp_server"],
        cwd: lcedaRoot,
      };
      const prev = conf.mcpServers["lceda-dao"];
      if (!prev || JSON.stringify({ command: prev.command, args: prev.args, cwd: prev.cwd })
          !== JSON.stringify(entry)) {
        conf.mcpServers["lceda-dao"] = Object.assign({}, prev, entry);
        changed = true;
      }
    }
    if (changed) fs.writeFileSync(p, JSON.stringify(conf, null, 2));
  } catch (e) { console.error("[dao-pcb] MCP 注册失败: " + e.message); }
}

// ---------- 公网防护令牌 ----------
// 桥经隧道暴露公网时的访问令牌: 首次生成后持久化 ~/.dao-pcb/token,
// 双桥以 DAO_PCB_TOKEN 环境变量启动(除 /api/health 外需 Bearer/?token=)。
function accessToken() {
  const dir = path.join(os.homedir(), ".dao-pcb");
  const f = path.join(dir, "token");
  try {
    const t = fs.readFileSync(f, "utf8").trim();
    if (t) return t;
  } catch (_) {}
  const t = "dao-pcb-" + require("crypto").randomBytes(16).toString("hex");
  try { fs.mkdirSync(dir, { recursive: true }); fs.writeFileSync(f, t); } catch (_) {}
  return t;
}

// ---------- 双桥拉起 ----------
async function ensureKicadServer(context) {
  const port = cfg().get("kicadPort") || 9931;
  if (await health(port)) return port;
  const engine = findKicadEngine();
  if (!engine) {
    vscode.window.showErrorMessage(
      "DAO PCB: 找不到 daokicad 引擎 (bridge/ide_server.py)。请设置 daoPcb.kicadEnginePath。");
    return null;
  }
  const py = findPython();
  registerMcp(py);
  kicadProc = cp.spawn(py, ["-m", "bridge.ide_server", "--port", String(port)], {
    cwd: engine,
    env: { ...process.env, PYTHONPATH: engine + path.delimiter + path.dirname(engine),
           DAO_PCB_TOKEN: accessToken() },
  });
  kicadProc.on("error", (e) =>
    vscode.window.showErrorMessage("DAO PCB: KiCad 桥接启动失败: " + e.message));
  context.subscriptions.push({ dispose: () => kicadProc && kicadProc.kill() });
  for (let i = 0; i < 20; i++) {
    if (await health(port)) return port;
    await new Promise((r) => setTimeout(r, 500));
  }
  vscode.window.showErrorMessage("DAO PCB: KiCad 桥接未在预期时间内就绪 (端口 " + port + ")");
  return null;
}

async function ensureLcedaServer(context) {
  const port = cfg().get("lcedaPort") || 9940;
  if (await health(port)) return port;
  const dir = findLcedaBridge();
  if (!dir) {
    vscode.window.showErrorMessage(
      "DAO PCB: 找不到 lceda bridge_server.py。请设置 daoPcb.lcedaBridgePath。");
    return null;
  }
  const py = findPython();
  registerMcp(py);
  lcedaProc = cp.spawn(py, [path.join(dir, "bridge_server.py")], {
    cwd: dir,
    env: {
      ...process.env,
      LCEDA_BRIDGE_PORT: String(port),
      DAO_CDP_PORTS: cfg().get("cdpPorts") || "9222,29229,29230",
      DAO_PREFER_LOCAL_EDA: cfg().get("preferLocalEda") === false ? "0" : "1",
      DAO_PCB_TOKEN: accessToken(),
    },
  });
  lcedaProc.on("error", (e) =>
    vscode.window.showErrorMessage("DAO PCB: LCEDA 桥接启动失败: " + e.message));
  context.subscriptions.push({ dispose: () => lcedaProc && lcedaProc.kill() });
  for (let i = 0; i < 24; i++) {
    if (await health(port)) return port;
    await new Promise((r) => setTimeout(r, 500));
  }
  vscode.window.showErrorMessage(
    "DAO PCB: LCEDA 桥接未就绪(端口 " + port + ")。请确认嘉立创EDA已带 CDP 启动。");
  return null;
}

// ---------- KiCad 引擎一键挂载 ----------
async function mountEngine(context, silent) {
  const port = await ensureKicadServer(context);
  if (!port) return;
  const st = await apiJson("GET", port, "/api/engine/status");
  const mode = st && st.mode;
  if (mode === "system" || mode === "mounted") {
    if (!silent) vscode.window.showInformationMessage(
      "DAO PCB: KiCad 引擎已就绪 (" + mode + ") — " + (st.version || st.cli));
    return;
  }
  const pick = await vscode.window.showInformationMessage(
    mode === "broken"
      ? "DAO PCB: 检测到 KiCad 引擎已损坏。一键自愈重挂底座?"
      : "DAO PCB: 未发现 KiCad 引擎。一键挂载自带底座 (无需预装 KiCad)?",
    "挂载", "取消");
  if (pick !== "挂载") return;
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification,
      title: "DAO PCB: 正在挂载 KiCad 底座 (首次需下载, 可能较久)…" },
    async () => {
      const start = await apiJson("POST", port, "/api/engine/mount", {});
      if (!start || !start.job) {
        vscode.window.showErrorMessage("DAO PCB: 挂载启动失败");
        return;
      }
      for (;;) {
        await new Promise((r) => setTimeout(r, 3000));
        const j = await apiJson("GET", port, "/api/job?id=" + start.job);
        if (j && j.done) {
          const res = j.result || {};
          if (res.ok) vscode.window.showInformationMessage(
            "DAO PCB: KiCad 引擎挂载完成 — " + (res.version || res.cli));
          else vscode.window.showErrorMessage(
            "DAO PCB: 挂载失败 — " + (res.error || JSON.stringify(res)));
          return;
        }
      }
    });
}

// ---------- 归一主页(网页套网页: KiCad 与 嘉立创EDA 平级标签) ----------
let homePanel = null;

async function openHome(context) {
  const kicadPort = cfg().get("kicadPort") || 9931;
  const lcedaPort = cfg().get("lcedaPort") || 9940;
  ensureKicadServer(context).catch(() => {});
  if (findLcedaBridge()) ensureLcedaServer(context).catch(() => {});
  if (homePanel) { homePanel.reveal(); return; }
  homePanel = vscode.window.createWebviewPanel(
    "daoPcbHome", "DAO PCB 归一工作台", vscode.ViewColumn.One,
    { enableScripts: true, retainContextWhenHidden: true });
  homePanel.onDidDispose(() => { homePanel = null; });
  let html = fs.readFileSync(path.join(context.extensionPath, "media", "home.html"), "utf8");
  const root = (vscode.workspace.workspaceFolders || [])[0];
  const lcedaMode = cfg().get("lcedaPanelMode") || "shell";
  const lcedaPath = lcedaMode === "screencast" ? "/panel"
    : (lcedaMode === "native" ? "/native" : "/shell");
  html = html
    .replace(/__KICAD__/g, "http://127.0.0.1:" + kicadPort + "/?token=" + accessToken())
    .replace(/__LCEDA__/g, "http://127.0.0.1:" + lcedaPort + lcedaPath + "?token=" + accessToken())
    .replace(/__LCEDA_BASE__/g, "http://127.0.0.1:" + lcedaPort)
    .replace(/__ROOT__/g, root ? root.uri.fsPath.replace(/\\/g, "\\\\") : "");
  homePanel.webview.html = html;
  watchHealth(homePanel, kicadPort, lcedaPort);
  wireModeBridge(homePanel);
  wireBoards(homePanel, context);
}

// 宿主侧健康探测: webview 内 fetch http://127.0.0.1 会被混合内容策略拦截,
// 因此由 Node 探测并 postMessage 通知面板显隐 iframe/提示。
function watchHealth(panel, kicadPort, lcedaPort) {
  const last = { kicad: null, lceda: null };
  const timer = setInterval(async () => {
    const [k, l] = await Promise.all([health(kicadPort), health(lcedaPort)]);
    if (k !== last.kicad || l !== last.lceda) {
      panel.webview.postMessage({
        type: "daopcb.health",
        kicad: k, lceda: l,
        reloadKicad: k && last.kicad === false,
        reloadLceda: l && last.lceda === false,
      });
      last.kicad = k;
      last.lceda = l;
    }
  }, 2000);
  panel.onDidDispose(() => clearInterval(timer));
}

// 主页「模式」标签 ↔ 宿主 shaper 桥: 面板内可视化查看/切换四态。
function wireModeBridge(panel) {
  const push = () => {
    if (!_shaper) return;
    panel.webview.postMessage({ type: "daopcb.mode", ...(_shaper.status()) });
  };
  panel.webview.onDidReceiveMessage((m) => {
    if (!m || !_shaper) return;
    if (m.type === "daopcb.modeGet") push();
    if (m.type === "daopcb.modeSet") { _shaper.setMode(m.mode); push(); }
  });
  if (_shaper) {
    const off = _shaper.onChange(push);
    panel.onDidDispose(off);
  }
  push();
}

// 穿透/账号板块 ↔ 宿主桥: 公网隧道(零账号 cloudflared 快速隧道)与 Devin 账号自持登录。
function wireBoards(panel, context) {
  const pushTunnel = () => panel.webview.postMessage({ type: "daopcb.tunnel", token: accessToken(), ...tunnel.status() });
  const pushAuth = async () => {
    try {
      const prov = require("./dao-ai-base/dao-cascade/devin-provision");
      const bin = prov.resolveEngine(context.extensionPath,
        context.globalStorageUri && context.globalStorageUri.fsPath);
      const st = await prov.authStatus(bin);
      panel.webview.postMessage({ type: "daopcb.auth", loggedIn: st.loggedIn, name: st.name, bin: !!bin });
    } catch (e) {
      panel.webview.postMessage({ type: "daopcb.auth", loggedIn: false, name: null, error: e.message });
    }
  };
  panel.webview.onDidReceiveMessage(async (m) => {
    if (!m) return;
    if (m.type === "daopcb.tunnelGet") pushTunnel();
    if (m.type === "daopcb.tunnelStart") {
      const r = await tunnel.start(m.port, (s) => console.log("[dao-pcb] " + s));
      tunnel.persist();
      if (!r.ok) vscode.window.showWarningMessage("DAO PCB 穿透: " + r.error);
      pushTunnel();
    }
    if (m.type === "daopcb.tunnelStop") { tunnel.stop(m.port); tunnel.persist(); pushTunnel(); }
    if (m.type === "daopcb.authGet") pushAuth();
    if (m.type === "daopcb.authLogin") vscode.commands.executeCommand("daoPcb.cascade.open");
  });
  pushTunnel();
  pushAuth();
}

// ---------- 道之对话(侧栏) ----------
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
    const port = await ensureKicadServer(this.context);
    view.webview.html = chatHtml(this.context, port || (cfg().get("kicadPort") || 9931));
  }
}

// ---------- 激活 ----------
let _shaper = null;

function activate(context) {
  // AI 交互基底(dao-ai-base · Devin Desktop 同源): Cascade 三模式面板, 命名空间 daoPcb.cascade*。
  // 深度融合: 基底上注册 PCB 四态塑形器(Proxy Pro 同源提示词隔离/替换) ——
  // dao/kicad/lceda 态把三模式整体塑形为对应位面的设计代理, native 态字节级直通。
  try {
    const daoAiBase = require("./dao-ai-base");
    daoAiBase.activateDaoAiBase(context, { ns: "daoPcb", log: (m) => console.log("[dao-ai-base] " + m) });
    const pcbMode = require("./pcb-mode");
    _shaper = pcbMode.createShaper({
      kicadPort: cfg().get("kicadPort") || 9931,
      lcedaPort: cfg().get("lcedaPort") || 9940,
      log: (m) => console.log("[pcb-mode] " + m),
    });
    daoAiBase.setPromptShaper(_shaper);
    // ACP 原生并列层: 领域 MCP 经 session/new 直接下发进三模式会话,
    // 与官方工具同层原生 function-calling; 按当前模态取相应位面(道/原生态不带领域工具)。
    if (typeof daoAiBase.setDomainMcpServers === "function") {
      daoAiBase.setDomainMcpServers(() => {
        const mode = _shaper ? _shaper.getMode() : "native";
        const py = findPython();
        const out = [];
        const kicadEngine = findKicadEngine();
        if ((mode === "kicad") && kicadEngine) {
          out.push({
            name: "dao-kicad",
            command: py,
            args: [path.join(kicadEngine, "bridge", "mcp_server.py")],
            env: { PYTHONPATH: kicadEngine + path.delimiter + path.dirname(kicadEngine) },
          });
        }
        const lcedaDir = findLcedaBridge();
        if ((mode === "lceda") && lcedaDir) {
          out.push({
            name: "lceda-dao",
            command: py,
            args: ["-m", "core.mcp_server"],
            env: { PYTHONPATH: path.dirname(lcedaDir) },
          });
        }
        return out;
      });
    }
  } catch (e) { console.error("[dao-ai-base] 基底激活失败: " + (e && e.stack ? e.stack : e)); }

  // 状态栏四态药丸: 一键循环 原生 → 道 → KiCad → 嘉立创EDA。
  const modeSb = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 10001);
  const renderModeSb = () => {
    const st = _shaper ? _shaper.status() : { label: "—", hint: "" };
    modeSb.text = st.label;
    modeSb.tooltip = st.hint;
  };
  modeSb.command = "daoPcb.modeToggle";
  renderModeSb(); modeSb.show();
  context.subscriptions.push(modeSb,
    vscode.commands.registerCommand("daoPcb.modeToggle", () => {
      if (!_shaper) return;
      const m = _shaper.toggle();
      renderModeSb();
      const msg = { native: "⌨ 已切回原生模式", dao: "☯ 已切入 道 模式",
        kicad: "☯ 已切入 KiCad 模式", lceda: "☯ 已切入 嘉立创EDA 模式" }[m];
      vscode.window.setStatusBarMessage(msg, 3000);
    }),
    vscode.commands.registerCommand("daoPcb.modePick", async () => {
      if (!_shaper) return;
      const items = [
        { label: "⌨ 原生", description: "提示词字节级直通", mode: "native" },
        { label: "☯ 道", description: "帛书老子+阴符经道魂隔离/替换", mode: "dao" },
        { label: "☯ KiCad", description: "道魂 + KiCad 领域 SP + 36 工具", mode: "kicad" },
        { label: "☯ 嘉立创EDA", description: "道魂 + EDA 领域 SP + CDP 桥工具", mode: "lceda" },
      ];
      const pick = await vscode.window.showQuickPick(items, { placeHolder: "选择 PCB 模式" });
      if (pick) { _shaper.setMode(pick.mode); renderModeSb(); }
    }));
  if (_shaper) _shaper.onChange(renderModeSb);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("daoPcb.chatView",
      new ChatViewProvider(context), { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.commands.registerCommand("daoPcb.openHome", () => openHome(context)),
    vscode.commands.registerCommand("daoPcb.mountEngine", () => mountEngine(context, false)),
    vscode.commands.registerCommand("daoPcb.restartBridges", async () => {
      if (kicadProc) kicadProc.kill();
      if (lcedaProc) lcedaProc.kill();
      kicadProc = null;
      lcedaProc = null;
      await ensureKicadServer(context);
      if (findLcedaBridge()) await ensureLcedaServer(context);
      vscode.window.showInformationMessage("DAO PCB 双桥已重启");
    }));

  // 右下角状态栏 ☯ 按钮: 一键打开归一工作台
  const sb = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 10000);
  sb.text = "☯ DAO PCB";
  sb.tooltip = "打开 DAO PCB 归一工作台 (KiCad + 嘉立创EDA)";
  sb.command = "daoPcb.openHome";
  sb.show();
  context.subscriptions.push(sb);

  // 启动即拉起双桥并打开归一工作台 (仅当工作区内有引擎时);
  // 若机器上没有 KiCad, 自动提示一键挂载自带底座。
  if (findKicadEngine() || findLcedaBridge()) {
    openHome(context);
    if (findKicadEngine()) {
      ensureKicadServer(context).then(async (port) => {
        if (!port) return;
        const st = await apiJson("GET", port, "/api/engine/status");
        if (st && (st.mode === "absent" || st.mode === "broken"))
          mountEngine(context, true);
      });
    }
  }
}

function deactivate() {
  if (kicadProc) kicadProc.kill();
  if (lcedaProc) lcedaProc.kill();
  tunnel.stopAll();
}

module.exports = { activate, deactivate };
