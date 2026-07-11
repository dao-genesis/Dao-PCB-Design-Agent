// KiCad 模式(提示词隔离/替换层)单测 — 纯 node 可跑: node test/kicad-mode.test.js
const assert = require("assert");
const os = require("os");
const path = require("path");

// 隔离持久化: 测试用独立 HOME, 不污染真实 ~/.dao-kicad/mode.json
process.env.HOME = require("fs").mkdtempSync(path.join(os.tmpdir(), "daokicad-test-"));
const realHomedir = os.homedir;
os.homedir = () => process.env.HOME;

const { createShaper, buildSp } = require("../kicad-mode");

let n = 0;
const ok = (name, fn) => { fn(); n++; console.log("✓ " + name); };

ok("默认 kicad 模式, 首条消息注入全量领域 SP", () => {
  const s = createShaper({ port: 1, log: () => {} });
  assert.strictEqual(s.getMode(), "kicad");
  const out = s.wrap("画一块 555 定时器板", { agent: "devin-cloud", epoch: 0 });
  assert.ok(out.startsWith("<dao_kicad_mode>\n"));
  assert.ok(out.includes("KiCad 模式"));
  assert.ok(out.includes("auto_pipeline"));
  assert.ok(out.includes("web_search"));
  assert.ok(out.endsWith("画一块 555 定时器板"));
});

ok("同会话第二条只带轻量标记, 不重复注入 SP", () => {
  const s = createShaper({ port: 1, log: () => {} });
  s.wrap("首条", { agent: "cascade", epoch: 0 });
  const out2 = s.wrap("跑一下 DRC", { agent: "cascade", epoch: 0 });
  assert.strictEqual(out2, "[KiCad 模式] 跑一下 DRC");
});

ok("新会话代际(epoch)/不同 agent 各自重新注入", () => {
  const s = createShaper({ port: 1, log: () => {} });
  s.wrap("a", { agent: "cascade", epoch: 0 });
  assert.ok(s.wrap("b", { agent: "cascade", epoch: 1 }).startsWith("<dao_kicad_mode>"));
  assert.ok(s.wrap("c", { agent: "devin-local", epoch: 0 }).startsWith("<dao_kicad_mode>"));
});

ok("native 模式字节级直通(提示词隔离)", () => {
  const s = createShaper({ port: 1, log: () => {} });
  assert.strictEqual(s.toggle(), "native");
  assert.strictEqual(s.wrap("原生编程问题", { agent: "cascade", epoch: 0 }), "原生编程问题");
  assert.strictEqual(s.status().spChars, 0);
});

ok("切回 kicad 模式后重新注入, 且模式持久化", () => {
  const s = createShaper({ port: 1, log: () => {} });
  if (s.getMode() === "kicad") s.toggle();      // 归到 native (已持久化)
  const s2 = createShaper({ port: 1, log: () => {} });
  assert.strictEqual(s2.getMode(), "native");   // 新实例读到持久化态
  assert.strictEqual(s2.toggle(), "kicad");
  assert.ok(s2.wrap("x", { agent: "cascade", epoch: 5 }).startsWith("<dao_kicad_mode>"));
});

ok("buildSp 融合活工具目录与引擎状态", () => {
  const sp = buildSp({ tools: [{ function: { name: "drc", description: "设计规则检查" } }], n: 1 },
    { mode: "mounted", version: "10.0.4" });
  assert.ok(sp.includes("- drc: 设计规则检查"));
  assert.ok(sp.includes("mode=mounted"));
  assert.ok(sp.includes("10.0.4"));
});

ok("dao-ai-base 暴露 setPromptShaper(基底融合点)", () => {
  const panelSrc = require("fs").readFileSync(
    path.join(__dirname, "..", "dao-ai-base", "dao-cascade", "panel.js"), "utf8");
  assert.ok(panelSrc.includes("setPromptShaper"));
  assert.ok(panelSrc.includes("_shapeText(msg.text"));
  assert.ok(panelSrc.includes("mode-toggle"));
});

os.homedir = realHomedir;
console.log("ALL " + n + " PASSED");
