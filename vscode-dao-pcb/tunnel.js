// DAO PCB · 公网穿透(零账号 · cloudflared 快速隧道)
// ─────────────────────────────────────────────────────────────────────────────
// 与 devin-remote dao-vsix「公网穿透」板块同构的最小实现: 去中心化、零配置、
// 无需任何 Cloudflare 账号 —— 快速隧道(trycloudflare)即开即用; 用户想要固定域名
// 才需要自己的命名隧道(可选, 非前置条件)。
// 把本机 KiCad 桥(9931)/LCEDA 桥(9940)任一端口暴露公网, 公网浏览器直开归一网页。
"use strict";

const cp = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const https = require("https");

const URL_RE = /https:\/\/[a-z0-9-]+\.trycloudflare\.com/;

function findCloudflared() {
  const cands = process.platform === "win32"
    ? ["cloudflared.exe", "cloudflared",
       path.join(process.env.ProgramFiles || "C:\\Program Files", "cloudflared", "cloudflared.exe")]
    : ["cloudflared", "/usr/local/bin/cloudflared", "/usr/bin/cloudflared",
       path.join(os.homedir(), ".local", "bin", "cloudflared")];
  for (const c of cands) {
    try {
      const r = cp.spawnSync(c, ["--version"], { timeout: 5000 });
      if (r.status === 0) return c;
    } catch (e) { /* try next */ }
  }
  return null;
}

// 隧道注册表: port -> { proc, url, startedAt }
const tunnels = new Map();

function status() {
  const out = {};
  for (const [port, t] of tunnels) {
    out[port] = { url: t.url || null, up: !!(t.proc && t.proc.exitCode === null), startedAt: t.startedAt };
  }
  return { bin: !!findCloudflared(), tunnels: out };
}

function start(port, log) {
  return new Promise((resolve) => {
    const existing = tunnels.get(port);
    if (existing && existing.url && existing.proc && existing.proc.exitCode === null) {
      return resolve({ ok: true, url: existing.url, reused: true });
    }
    const bin = findCloudflared();
    if (!bin) {
      return resolve({ ok: false, error: "未找到 cloudflared。安装: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/ (零账号即可用快速隧道)" });
    }
    // --protocol http2: QUIC(udp/7844)受限网络下唯一可达路径, http2 走 443/tcp 恒通。
    const proc = cp.spawn(bin, ["tunnel", "--url", "http://127.0.0.1:" + port, "--no-autoupdate", "--protocol", "http2"],
      { stdio: ["ignore", "pipe", "pipe"] });
    const t = { proc, url: null, startedAt: Date.now() };
    tunnels.set(port, t);
    let buf = "";
    const scan = (d) => {
      buf += d.toString();
      const m = buf.match(URL_RE);
      if (m && !t.url) {
        t.url = m[0];
        if (log) log("tunnel: " + port + " → " + t.url);
        resolve({ ok: true, url: t.url });
      }
    };
    proc.stdout.on("data", scan);
    proc.stderr.on("data", scan);
    proc.on("exit", (code) => {
      if (!t.url) resolve({ ok: false, error: "cloudflared 退出 code=" + code });
      tunnels.delete(port);
      if (log) log("tunnel: " + port + " 已关闭");
    });
    setTimeout(() => {
      if (!t.url) { try { proc.kill(); } catch (e) { /* already dead */ } resolve({ ok: false, error: "快速隧道 30s 内未就绪" }); }
    }, 30000);
  });
}

function stop(port) {
  const t = tunnels.get(port);
  if (t && t.proc) { try { t.proc.kill(); } catch (e) { /* already dead */ } }
  tunnels.delete(port);
  return { ok: true };
}

function stopAll() {
  for (const port of [...tunnels.keys()]) stop(port);
}

// 反向注入: 把公网 URL 写入本地状态文件(~/.dao-pcb/tunnel.json), 供其他进程/Agent 读取。
function persist() {
  try {
    const dir = path.join(os.homedir(), ".dao-pcb");
    fs.mkdirSync(dir, { recursive: true });
    const out = {};
    for (const [port, t] of tunnels) if (t.url) out[port] = { url: t.url, startedAt: t.startedAt };
    fs.writeFileSync(path.join(dir, "tunnel.json"), JSON.stringify(out, null, 2));
  } catch (e) { /* 尽力而为 */ }
}

function probe(url) {
  return new Promise((resolve) => {
    const req = https.get(url + "/api/health", { timeout: 8000 }, (res) => resolve(res.statusCode === 200));
    req.on("error", () => resolve(false));
    req.on("timeout", () => { req.destroy(); resolve(false); });
  });
}

module.exports = { findCloudflared, start, stop, stopAll, status, persist, probe };
