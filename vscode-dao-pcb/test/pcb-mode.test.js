// PCB 四态(提示词隔离/替换层)单测 — 纯 node 可跑: node test/pcb-mode.test.js
const assert = require("assert");
const os = require("os");
const path = require("path");

// 隔离持久化: 测试用独立 HOME, 不污染真实 ~/.dao-pcb/mode.json
process.env.HOME = require("fs").mkdtempSync(path.join(os.tmpdir(), "daopcb-test-"));
os.homedir = () => process.env.HOME;

const { createShaper, buildKicadSp, buildLcedaSp, buildDaoSoul, MODES } = require("../pcb-mode");

let n = 0;
const ok = (name, fn) => { fn(); n++; console.log("✓ " + name); };
const mk = () => createShaper({ kicadPort: 1, lcedaPort: 2, log: () => {} });

ok("默认 kicad 模式, 首条消息注入 道魂+领域 SP", () => {
  const s = mk();
  assert.strictEqual(s.getMode(), "kicad");
  const out = s.wrap("画一块 555 定时器板", { agent: "devin-cloud", epoch: 0 });
  assert.ok(out.startsWith("<dao_kicad_mode>\n"));
  assert.ok(out.includes("KiCad 模式"));
  assert.ok(out.includes("阴符经"));
  assert.ok(out.includes("auto_pipeline"));
  assert.ok(out.endsWith("画一块 555 定时器板"));
});

ok("同会话第二条只带轻量标记, 不重复注入 SP", () => {
  const s = mk();
  s.wrap("首条", { agent: "cascade", epoch: 0 });
  const out2 = s.wrap("跑一下 DRC", { agent: "cascade", epoch: 0 });
  assert.strictEqual(out2, "[KiCad 模式] 跑一下 DRC");
});

ok("新会话代际(epoch)/不同 agent 各自重新注入", () => {
  const s = mk();
  s.wrap("a", { agent: "cascade", epoch: 0 });
  assert.ok(s.wrap("b", { agent: "cascade", epoch: 1 }).startsWith("<dao_kicad_mode>"));
  assert.ok(s.wrap("c", { agent: "devin-local", epoch: 0 }).startsWith("<dao_kicad_mode>"));
});

ok("四态循环: kicad → lceda → native → dao → kicad", () => {
  const s = mk();
  assert.strictEqual(s.getMode(), "kicad");
  assert.strictEqual(s.toggle(), "lceda");
  assert.strictEqual(s.toggle(), "native");
  assert.strictEqual(s.toggle(), "dao");
  assert.strictEqual(s.toggle(), "kicad");
});

ok("lceda 模式注入 道魂+EDA 领域 SP", () => {
  const s = mk();
  s.setMode("lceda");
  const out = s.wrap("复刻一块 STM32 蓝药丸", { agent: "cascade", epoch: 0 });
  assert.ok(out.startsWith("<dao_lceda_mode>\n"));
  assert.ok(out.includes("嘉立创EDA 模式"));
  assert.ok(out.includes("阴符经"));
  assert.ok(out.includes("lib.search"));
  assert.strictEqual(s.wrap("再来", { agent: "cascade", epoch: 0 }), "[嘉立创EDA 模式] 再来");
});

ok("dao 模式注入纯道魂(无领域 SP)", () => {
  const s = mk();
  s.setMode("dao");
  const out = s.wrap("你是谁", { agent: "cascade", epoch: 0 });
  assert.ok(out.startsWith("<dao_mode>\n"));
  assert.ok(out.includes("阴符经"));
  assert.ok(!out.includes("KiCad 模式"));
  assert.ok(!out.includes("嘉立创EDA 模式"));
});

ok("native 模式字节级直通(提示词隔离)", () => {
  const s = mk();
  s.setMode("native");
  assert.strictEqual(s.wrap("原生编程问题", { agent: "cascade", epoch: 0 }), "原生编程问题");
  assert.strictEqual(s.status().spChars, 0);
});

ok("模式持久化: 新实例读到上次模式", () => {
  const s = mk();
  s.setMode("lceda");
  const s2 = mk();
  assert.strictEqual(s2.getMode(), "lceda");
  s2.setMode("kicad");
});

ok("模式切换后同一会话重新注入全量 SP", () => {
  const s = mk();
  s.setMode("kicad");
  s.wrap("a", { agent: "cascade", epoch: 0 });
  s.setMode("lceda");
  assert.ok(s.wrap("b", { agent: "cascade", epoch: 0 }).startsWith("<dao_lceda_mode>"));
});

ok("buildKicadSp 融合活工具目录与引擎状态", () => {
  const sp = buildKicadSp({ tools: [{ function: { name: "drc", description: "设计规则检查" } }], n: 1 },
    { mode: "mounted", version: "10.0.4" }, 9931);
  assert.ok(sp.includes("- drc: 设计规则检查"));
  assert.ok(sp.includes("mode=mounted"));
});

ok("buildLcedaSp 融合活工具目录", () => {
  const sp = buildLcedaSp({ tools: [{ tool: "pcb.route", desc: "PCB 布线" }] }, 9940);
  assert.ok(sp.includes("- pcb.route: PCB 布线"));
  assert.ok(sp.includes("9940"));
});

ok("道魂载入帛书老子与阴符经全文", () => {
  const soul = buildDaoSoul();
  assert.ok(soul.includes("道，可道也"));
  assert.ok(soul.includes("上德不德"));
  assert.ok(soul.includes("觀天之道"));
});

ok("status/MODES 一致性", () => {
  const s = mk();
  assert.deepStrictEqual(s.modes(), MODES);
  for (const m of MODES) {
    s.setMode(m);
    const st = s.status();
    assert.strictEqual(st.mode, m);
    assert.ok(st.label && st.hint !== undefined);
  }
  s.setMode("kicad");
});

console.log("\n" + n + " tests passed · 道法自然");
