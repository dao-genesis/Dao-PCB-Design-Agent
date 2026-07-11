// 道 · Cascade 轨 → 官方 windsurf language_server 直连桥(Connect RPC · JSON 编码)
// ─────────────────────────────────────────────────────────────────────────────
// 官方 Devin Desktop 里 Cascade 聊天 UI(fork workbench 内)与 language_server 的通信
// = Connect RPC(POST /exa.language_server_pb.LanguageServerService/<Method>,
//   头 x-codeium-csrf-token)。本桥以 JSON 编码走**同一协议、同一后端**,实现插件形态
// 的 Cascade 轨与官方同源 —— 端口与 CSRF 由 windsurf-shim 从官方本体捕获(hostState)。
//
// 实测校准(与官方逐包对齐):
//   · 每个 RPC 需 metadata{ideName,ideVersion,extensionName,extensionVersion,apiKey};
//     apiKey = 官方登录态的 windsurf_api_key(~/.local/share/devin/credentials.toml)。
//   · SendUserCascadeMessage 需 cascadeConfig.plannerConfig{requestedModelUid,
//     plannerTypeConfig:{agentic:{}}} —— 缺 plannerTypeConfig 则 planner 永不执行。
//   · 生成由 StreamCascadeReactiveUpdates(Connect server-streaming, id=cascadeId)
//     驱动 —— 不挂流则轨迹停在 CHECKPOINT;挂流期间轮询 GetCascadeTrajectorySteps
//     取 plannerResponse 文本。
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");

let hostState = null;
try { ({ hostState } = require("../windsurf-shim")); } catch (_) {}

const SVC = "/exa.language_server_pb.LanguageServerService/";

function ready() {
  const h = hostState && hostState();
  return h && h.lsPort && h.csrfToken ? h : null;
}

// 官方登录态 apiKey(windsurf_api_key): credentials.toml 为真源(官方 LS 鉴权用同一把钥匙)
let _keyCache = { key: "", at: 0 };
function apiKey() {
  if (_keyCache.key && Date.now() - _keyCache.at < 60000) return _keyCache.key;
  try {
    const t = fs.readFileSync(path.join(os.homedir(), ".local", "share", "devin", "credentials.toml"), "utf8");
    const m = t.match(/windsurf_api_key\s*=\s*"([^"]+)"/);
    if (m) { _keyCache = { key: m[1], at: Date.now() }; return m[1]; }
  } catch (_) {}
  return "";
}

// 与官方扩展本体一致的调用方元数据(LS 端按此鉴权/归因)
function metadata() {
  return {
    ideName: "windsurf",
    ideVersion: "1.127.0",
    extensionName: "windsurf",
    extensionVersion: "1.63.9250",
    apiKey: apiKey(),
  };
}

function call(method, body, timeoutMs) {
  return new Promise((resolve, reject) => {
    const h = ready();
    if (!h) return reject(new Error("官方 language_server 未就绪(端口/CSRF 未捕获)"));
    const payload = Object.assign({ metadata: metadata() }, body || {});
    const data = Buffer.from(JSON.stringify(payload), "utf8");
    const req = http.request({
      host: "127.0.0.1", port: h.lsPort, path: SVC + method, method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-codeium-csrf-token": h.csrfToken,
        "Content-Length": data.length,
      },
    }, (r) => {
      let b = "";
      r.on("data", (c) => { b += c; });
      r.on("end", () => {
        try {
          const j = b ? JSON.parse(b) : {};
          if (r.statusCode !== 200) reject(new Error(method + ": " + (j.message || j.code || ("HTTP " + r.statusCode))));
          else resolve(j);
        } catch (e) { reject(new Error(method + ": 响应解析失败 " + e.message)); }
      });
    });
    req.setTimeout(timeoutMs || 30000, () => { req.destroy(new Error(method + ": 超时")); });
    req.on("error", reject);
    req.end(data);
  });
}

// 生成驱动流: 官方 UI 靠此 server-streaming 连接推动 Cascade 执行(不挂即停摆)。
// 返回 { close() } —— 消息发完/收完后调用 close 释放连接。
function driveStream(cascadeId) {
  const h = ready();
  if (!h) return { close() {} };
  const body = Buffer.from(JSON.stringify({ metadata: metadata(), protocolVersion: 1, id: cascadeId }), "utf8");
  const env = Buffer.concat([Buffer.from([0, 0, 0, 0, 0]), body]);
  env.writeUInt32BE(body.length, 1); // Connect enveloped message: flags(1B)+len(4B)+json
  const req = http.request({
    host: "127.0.0.1", port: h.lsPort,
    path: SVC + "StreamCascadeReactiveUpdates", method: "POST",
    headers: {
      "Content-Type": "application/connect+json",
      "connect-protocol-version": "1",
      "x-codeium-csrf-token": h.csrfToken,
      "Content-Length": env.length,
    },
  });
  req.on("response", (r) => { r.on("data", () => {}); r.on("error", () => {}); });
  req.on("error", () => {});
  req.end(env);
  return { close() { try { req.destroy(); } catch (_) {} } };
}

// Connect server-streaming 通用调用(application/connect+json): 逐帧 JSON 回调 onMessage,
// 末帧(flags&2)为 trailer —— 携 error 时以异常抛出。GetDeepWiki 等流式方法走此轨。
function callStream(method, body, onMessage, timeoutMs) {
  return new Promise((resolve, reject) => {
    const h = ready();
    if (!h) return reject(new Error("官方 language_server 未就绪(端口/CSRF 未捕获)"));
    const json = Buffer.from(JSON.stringify(Object.assign({ metadata: metadata() }, body || {})), "utf8");
    const env = Buffer.concat([Buffer.from([0, 0, 0, 0, 0]), json]);
    env.writeUInt32BE(json.length, 1);
    const req = http.request({
      host: "127.0.0.1", port: h.lsPort, path: SVC + method, method: "POST",
      headers: {
        "Content-Type": "application/connect+json",
        "connect-protocol-version": "1",
        "x-codeium-csrf-token": h.csrfToken,
        "Content-Length": env.length,
      },
    }, (r) => {
      if (r.statusCode !== 200) { r.resume(); return reject(new Error(method + ": HTTP " + r.statusCode)); }
      let buf = Buffer.alloc(0);
      let failed = null;
      r.on("data", (c) => {
        buf = Buffer.concat([buf, c]);
        while (buf.length >= 5) {
          const flags = buf.readUInt8(0), len = buf.readUInt32BE(1);
          if (buf.length < 5 + len) break;
          const raw = buf.slice(5, 5 + len).toString("utf8");
          buf = buf.slice(5 + len);
          let j = {};
          try { j = raw ? JSON.parse(raw) : {}; } catch (_) {}
          if (flags & 2) {
            if (j.error) failed = new Error(method + ": " + (j.error.message || j.error.code || "stream error"));
            continue;
          }
          try { onMessage(j); } catch (_) {}
        }
      });
      r.on("end", () => (failed ? reject(failed) : resolve()));
      r.on("error", reject);
    });
    req.setTimeout(timeoutMs || 120000, () => { req.destroy(new Error(method + ": 超时")); });
    req.on("error", reject);
    req.end(env);
  });
}

// 可用模型: GetUserStatus → cascadeModelConfigData.clientModelConfigs
// disabled=false 者可用; 另回 creditMultiplier(倍率)与 disabledReason(Pro 门控原因)以 1:1 复刻官方模型选择器。
// 每项本身即携 modelInfo.modelFamilyUid / modelFamilyMetadata(族标签+Effort/Thinking/Fast Mode/1M Context 维度)
// / isRecommended / supportsImages —— 据此在选择器里按「模型族」分组并标注推荐/图像/维度(官方两级选择器同构)。
async function listModels() {
  const r = await call("GetUserStatus", {});
  const cfgs = (((r || {}).userStatus || {}).cascadeModelConfigData || {}).clientModelConfigs || [];
  return cfgs.map((c) => {
    const fm = c.modelFamilyMetadata || {};
    const dims = (fm.entries || []).map((e) => {
      const v = e.value || {};
      return v.name ? (e.key + ":" + v.name) : e.key; // "Effort:High" | "Thinking" | "1M Context"
    });
    // 价目: modelDimensions 中 kind=COST 项(Input/Cached input/Output, 单位 denominator=/1M tokens)
    const pricing = (c.modelDimensions || [])
      .filter((x) => x.kind === "MODEL_DIMENSION_KIND_COST")
      .map((x) => x.label + " $" + x.value + (x.denominator ? "/" + x.denominator : ""))
      .join(" · ");
    return {
      uid: c.modelUid,
      label: c.label || c.modelUid,
      disabled: !!c.disabled,
      credit: (typeof c.creditMultiplier === "number") ? c.creditMultiplier : null,
      reason: ((c.disabledReason || {}).shortReason) || "",
      reasonLink: ((c.disabledReason || {}).link) || "",
      familyUid: ((c.modelInfo || {}).modelFamilyUid) || "",
      familyLabel: fm.modelFamilyLabel || "",
      recommended: !!c.isRecommended,
      defaultInFamily: !!c.isDefaultModelInFamily,
      images: !!c.supportsImages,
      dims,
      pricing,
    };
  });
}

module.exports = { call, callStream, ready, metadata, apiKey, driveStream, listModels };
