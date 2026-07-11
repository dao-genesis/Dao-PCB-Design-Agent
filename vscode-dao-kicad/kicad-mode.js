// KiCad 模式 —— Devin Desktop 基底之上的领域提示词隔离/替换层 (Proxy Pro 同源)。
// ─────────────────────────────────────────────────────────────────────────────
// 双态并行(道并行而不相悖):
//   · kicad  模式: 每会话首条消息注入 KiCad 领域系统提示词(引擎状态 + 36 工具目录
//     + PCB 设计工作流), 把整个 AI 基底塑形为专为 KiCad 底层服务的 PCB 设计代理;
//   · native 模式: 字节级直通, 原生 Devin Desktop 编程体验分毫不动。
// 模式持久化在 ~/.dao-kicad/mode.json; 面板 composer 内 ☯ 药丸一键切换。
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");

const STATE_DIR = path.join(os.homedir(), ".dao-kicad");
const STATE_FILE = path.join(STATE_DIR, "mode.json");

// 工具目录兜底(桥接 9931 未起时用): 与 bridge/tools.py 注册表同源的组概览。
const FALLBACK_GROUPS = [
  "engine_status/engine_mount — 引擎状态与一键挂载自带 KiCad 底座",
  "project_tree/project_files/read_artifact — 工程发现与产物读取",
  "render_schematic/render_pcb/render_symbol/render_footprint/list_symbols/list_footprints — KiCad 原生渲染",
  "netlist/build_board/autoroute/drc/erc/fabricate/auto_pipeline/job_status — 设计闭环(网表→建板→布线→DRC→制造)",
  "native_status/native_start/native_open/native_stop — KiCad 软件本体直驱",
  "ipc_status/ipc_board/ipc_run — IPC 底层直连(与 GUI 同一内存文档)",
  "brain_templates/brain_design/brain_guardian/brain_wugan/brain_bom — 电路 DNA 生成",
  "pcm_list/pcm_install/pcm_remove — 扩展内容管理",
  "image_convert — 位图转 KiCad 原生元件",
  "web_search — PCB 领域网络搜索(元器件/datasheet/封装/参考设计)",
];

function loadMode() {
  try { return JSON.parse(fs.readFileSync(STATE_FILE, "utf8")).mode === "native" ? "native" : "kicad"; }
  catch (_) { return "kicad"; }
}

function saveMode(mode) {
  try { fs.mkdirSync(STATE_DIR, { recursive: true }); fs.writeFileSync(STATE_FILE, JSON.stringify({ mode })); }
  catch (_) {}
}

function fetchJson(port, apiPath, timeout) {
  return new Promise((resolve) => {
    const req = http.get({ host: "127.0.0.1", port, path: apiPath, timeout: timeout || 2500 }, (res) => {
      let buf = "";
      res.on("data", (c) => (buf += c));
      res.on("end", () => { try { resolve(JSON.parse(buf)); } catch (_) { resolve(null); } });
    });
    req.on("error", () => resolve(null));
    req.on("timeout", () => { req.destroy(); resolve(null); });
  });
}

function buildSp(catalog, engineStatus) {
  const lines = [];
  lines.push("你现在处于「KiCad 模式」: 你是 DAO KiCad 归一 PCB 设计代理, 全权代替用户驱动 KiCad 全部底层完成电子设计。");
  lines.push("");
  lines.push("## 领域与职责");
  lines.push("- 领域: 电子/PCB 设计 (原理图、网表、布局布线、DRC/ERC、制造文件、元器件与封装库)。");
  lines.push("- 你经 MCP server `dao-kicad` 原生持有全部 KiCad 引擎工具, 一切 KiCad 操作都优先调用这些工具完成, 不要徒手猜测或让用户手动操作 KiCad。");
  lines.push("- 慢操作(挂载/建板/布线/制造/闭环)返回 {job}, 用 job_status 轮询到 done 再继续。");
  if (engineStatus && engineStatus.mode) {
    lines.push("- 当前引擎: mode=" + engineStatus.mode + (engineStatus.version ? " · " + engineStatus.version : "") + " · 桥接 http://127.0.0.1:9931 在线。");
  }
  lines.push("");
  lines.push("## 工具目录 (dao-kicad MCP)");
  if (catalog && Array.isArray(catalog.tools) && catalog.tools.length) {
    for (const t of catalog.tools) {
      const fn = t.function || {};
      lines.push("- " + fn.name + ": " + (fn.description || ""));
    }
  } else {
    for (const g of FALLBACK_GROUPS) lines.push("- " + g);
  }
  lines.push("");
  lines.push("## 工作流约定");
  lines.push("- 设计闭环: netlist → build_board → autoroute → drc → fabricate; 一步到位可用 auto_pipeline。");
  lines.push("- 验证优先: 任何生成/修改后立即 drc/erc, 违例必须修复到 0 才算完成。");
  lines.push("- 器件与资料检索用 web_search (PCB 领域优先级排序), 不要凭记忆编造封装与参数。");
  lines.push("- 用户能看到的一切(原理图/板图)可用 render_* 渲染 SVG 呈现; KiCad 本体 GUI 可用 native_*/ipc_* 直驱。");
  lines.push("- 回答用简体中文, 结论先行; 道法自然, 无为而无不为。");
  return lines.join("\n");
}

// createShaper({ port, log }) → 注册到 dao-ai-base 的 setPromptShaper。
function createShaper(opts) {
  const o = opts || {};
  const port = o.port || 9931;
  const log = o.log || (() => {});
  let mode = loadMode();
  let sp = buildSp(null, null);      // 先用兜底目录, 异步刷成活目录
  let injected = new Set();          // "agent:epoch" → 该会话已注入全量 SP
  let listeners = new Set();

  async function refresh() {
    const [cat, st] = await Promise.all([
      fetchJson(port, "/api/tools/catalog"),
      fetchJson(port, "/api/engine/status"),
    ]);
    if (cat || st) { sp = buildSp(cat, st); log("kicad-mode: SP 刷新 " + sp.length + "字 (工具 " + ((cat && cat.n) || "兜底") + ")"); }
  }
  refresh().catch(() => {});

  return {
    wrap(text, ctx) {
      if (mode !== "kicad") return text;
      const key = ((ctx && ctx.agent) || "?") + ":" + ((ctx && ctx.epoch) || 0);
      if (injected.has(key)) return "[KiCad 模式] " + text;
      injected.add(key);
      return "<dao_kicad_mode>\n" + sp + "\n</dao_kicad_mode>\n\n" + text;
    },
    status() {
      return { mode, label: mode === "kicad" ? "☯ KiCad" : "⌨ 原生",
        hint: mode === "kicad" ? "KiCad 模式: 领域 SP 已就位, 点击切回原生 Devin Desktop"
                               : "原生模式: 提示词字节级直通, 点击切入 KiCad 模式",
        spChars: mode === "kicad" ? sp.length : 0 };
    },
    toggle() {
      mode = mode === "kicad" ? "native" : "kicad";
      saveMode(mode);
      if (mode === "kicad") { injected = new Set(); refresh().catch(() => {}); }
      log("kicad-mode: 切换 → " + mode);
      for (const fn of listeners) { try { fn(mode); } catch (_) {} }
      return mode;
    },
    onChange(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    getMode() { return mode; },
    refresh,
    _sp() { return sp; },
  };
}

module.exports = { createShaper, buildSp, loadMode };
