"use strict";
/* ============================================================================
 * LCEDA Bridge — L2 扩展入口 (道之直连 · WebSocket 正道)
 * ============================================================================
 * 反者道之动 · 道法自然
 *
 * 为什么是 WebSocket?
 *   嘉立创EDA 专业版渲染端为 HTTPS 上下文, 扩展沙箱内 `fetch('http://127.0.0.1')`
 *   会被 Mixed-Content 策略拦截 (见官方 eext-run-api-gateway 源码)。本机唯一可用
 *   通道是 `eda.sys_WebSocket` —— 故桥接走 WebSocket, 连接到本机 Python WS 桥服务器
 *   (lceda_ws_bridge.py, 端口 9930-9939)。
 *
 * 入口格式:
 *   嘉立创EDA 运行时按 `edaEsbuildExportName.<registerFn>()` 调用导出函数
 *   (与 esbuild `format:iife, globalName:edaEsbuildExportName` 产物一致),
 *   故本文件手写为同构 IIFE, 无需构建链。
 *
 * 协议 (与 lceda_ws_bridge.py 对应):
 *   连接后  server → ext : {type:"handshake", service:"lceda-bridge"}
 *   ext → server         : {type:"register",  windowId}
 *   server → ext         : {type:"call",    id, path, args}
 *                          {type:"execute", id, code}
 *   ext → server         : {type:"result", id, result} | {type:"error", id, error}
 *   心跳                  : ext ping → server pong
 *
 * 权限: 需在扩展管理器中为本扩展勾选「外部交互」, 否则 sys_WebSocket 抛错。
 * ========================================================================== */
var edaEsbuildExportName = (() => {
	var __defProp = Object.defineProperty;
	var __export = (target, all) => {
		for (var name in all)
			__defProp(target, name, { get: all[name], enumerable: true });
	};
	var index_exports = {};
	__export(index_exports, {
		about: () => about,
		activate: () => activate,
		deactivate: () => deactivate,
		openPanel: () => openPanel,
		ping: () => ping,
		reconnect: () => reconnect,
		startBridge: () => startBridge,
		stopBridge: () => stopBridge,
	});

	// ─── 配置 ───────────────────────────────────────────────────────────
	const WS_ID = "dao-lceda-bridge";
	const PORT_START = 9930;
	const PORT_END = 9939;
	const SERVICE_ID = "lceda-bridge";
	const CONNECT_TIMEOUT_MS = 1200;   // 单端口连接+握手超时
	const RETRY_DELAY_MS = 3000;       // 全端口扫描失败后重试间隔
	const HEARTBEAT_INTERVAL_MS = 15000;
	const HEARTBEAT_TIMEOUT_MS = 5000;
	const STORAGE_AUTOCONNECT = "daoBridgeAutoConnect";

	// ─── 状态 ───────────────────────────────────────────────────────────
	let connected = false;
	let connecting = false;
	let currentPort = null;
	let windowId = null;
	let autoConnect = true;
	let sessionSeq = 0;            // 每次连接流程的代际, 用于取消过期回调
	let heartbeatTimer = null;
	let retryTimer = null;
	let heartbeatPending = false;
	let cmdCount = 0;
	let lastError = "";

	const AsyncFunction = Object.getPrototypeOf(async () => {}).constructor;

	// ─── 工具 ───────────────────────────────────────────────────────────
	function log(...a) {
		try { console.log("[LCEDA-Bridge]", ...a); } catch (e) { /* noop */ }
	}

	function toast(msg) {
		try { eda.sys_ToastMessage.showMessage(String(msg), undefined, 3); }
		catch (e) { log("toast 失败", e); }
	}

	function nextSession() {
		sessionSeq += 1;
		return sessionSeq;
	}

	function isActive(s) {
		return s === sessionSeq;
	}

	function closeWs() {
		try { eda.sys_WebSocket.close(WS_ID); } catch (e) { /* noop */ }
	}

	function clearTimers() {
		if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
		if (retryTimer) { clearTimeout(retryTimer); retryTimer = null; }
		heartbeatPending = false;
	}

	function teardown() {
		nextSession();        // 让所有在途回调失效
		connecting = false;
		connected = false;
		currentPort = null;
		windowId = null;
		clearTimers();
		closeWs();
	}

	function send(obj) {
		try { eda.sys_WebSocket.send(WS_ID, JSON.stringify(obj)); }
		catch (e) { lastError = String(e); log("send 失败", e); }
	}

	function safeResult(v) {
		if (v === undefined) return null;
		try { return JSON.parse(JSON.stringify(v)); }
		catch (e) {
			try { return String(v); } catch (e2) { return null; }
		}
	}

	// ─── 命令处理 ────────────────────────────────────────────────────────
	async function handleMessage(msg) {
		if (!msg || typeof msg !== "object") return;
		switch (msg.type) {
			case "ping":
				send({ type: "pong", id: msg.id, ts: Date.now() });
				return;
			case "pong":
				heartbeatPending = false;
				return;
			case "call":
				await doCall(msg);
				return;
			case "execute":
				await doExecute(msg);
				return;
			default:
				return;
		}
	}

	// 调用 eda.<path>(...args)
	async function doCall(msg) {
		cmdCount += 1;
		try {
			const path = String(msg.path || "");
			if (!path) throw new Error("缺少 path");
			const parts = path.split(".");
			let fn = eda;
			let ctx = null;
			for (const k of parts) {
				ctx = fn;
				fn = (fn == null) ? undefined : fn[k];
			}
			if (typeof fn !== "function") throw new Error("eda." + path + " 不是函数");
			const result = await fn.apply(ctx, Array.isArray(msg.args) ? msg.args : []);
			send({ type: "result", id: msg.id, result: safeResult(result), ts: Date.now() });
		}
		catch (e) {
			lastError = String((e && e.message) || e);
			send({ type: "error", id: msg.id, error: lastError, stack: e && e.stack, ts: Date.now() });
		}
	}

	// 执行任意 JS 代码 (eda 作为参数注入, 可 await, 末尾 return 结果)
	async function doExecute(msg) {
		cmdCount += 1;
		try {
			const code = String(msg.code || "");
			const fn = new AsyncFunction("eda", code);
			const result = await fn(eda);
			send({ type: "result", id: msg.id, result: safeResult(result), ts: Date.now() });
		}
		catch (e) {
			lastError = String((e && e.message) || e);
			send({ type: "error", id: msg.id, error: lastError, stack: e && e.stack, ts: Date.now() });
		}
	}

	// ─── 连接 ───────────────────────────────────────────────────────────
	function tryPort(port, s) {
		return new Promise((resolve) => {
			let settled = false;
			let timer = setTimeout(() => done(false), CONNECT_TIMEOUT_MS);

			function done(ok) {
				if (settled) return;
				settled = true;
				clearTimeout(timer);
				if (!ok && isActive(s)) closeWs();
				resolve(ok);
			}

			if (!isActive(s)) { resolve(false); return; }
			closeWs();  // register 对同 ID 活跃连接不更新参数, 先关旧的

			try {
				eda.sys_WebSocket.register(
					WS_ID,
					"ws://127.0.0.1:" + port + "/eda",
					async (event) => {
						if (!isActive(s)) { done(false); return; }
						let msg;
						try { msg = JSON.parse(event.data); }
						catch (e) { return; }

						if (msg.type === "handshake") {
							if (msg.service === SERVICE_ID) {
								connected = true;
								currentPort = port;
								windowId = (typeof crypto !== "undefined" && crypto.randomUUID)
									? crypto.randomUUID()
									: ("w" + Date.now());
								send({ type: "register", windowId, ts: Date.now() });
								toast("桥接已连接 (端口 " + port + ")");
								log("connected on port", port);
								done(true);
							}
							else {
								done(false);
							}
							return;
						}

						if (!connected) return;
						await handleMessage(msg);
					},
					() => { /* onConnect: 等待服务端握手 */ },
				);
			}
			catch (e) {
				// register 抛错 (通常是未开启外部交互权限)
				lastError = String((e && e.message) || e);
				log("register 抛错", e);
				done(false);
			}
		});
	}

	async function scanAndConnect() {
		if (connecting || connected) return;
		const s = nextSession();
		connecting = true;
		try {
			for (let p = PORT_START; p <= PORT_END; p++) {
				if (!isActive(s)) return;
				const ok = await tryPort(p, s);
				if (!isActive(s)) return;
				if (ok) {
					startHeartbeat(s);
					return;
				}
			}
			// 全端口未发现服务器
			if (autoConnect && isActive(s)) {
				retryTimer = setTimeout(() => {
					if (isActive(s)) { connecting = false; scanAndConnect(); }
				}, RETRY_DELAY_MS);
			}
		}
		finally {
			if (isActive(s) && !retryTimer) connecting = false;
		}
	}

	// ─── 心跳 ───────────────────────────────────────────────────────────
	function startHeartbeat(s) {
		stopHeartbeat();
		connecting = false;
		heartbeatTimer = setInterval(() => {
			if (!isActive(s)) { stopHeartbeat(); return; }
			if (!connected) return;
			heartbeatPending = true;
			send({ type: "ping", id: "hb-" + Date.now(), ts: Date.now() });
			setTimeout(() => {
				if (!isActive(s)) return;
				if (heartbeatPending) {
					log("心跳超时, 重连");
					teardown();
					if (autoConnect) scanAndConnect();
				}
			}, HEARTBEAT_TIMEOUT_MS);
		}, HEARTBEAT_INTERVAL_MS);
	}

	function stopHeartbeat() {
		if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
		heartbeatPending = false;
	}

	// ─── 生命周期 / 菜单导出 ───────────────────────────────────────────
	// eslint-disable-next-line no-unused-vars
	function activate(status, arg) {
		let pref;
		try { pref = eda.sys_Storage.getExtensionUserConfig(STORAGE_AUTOCONNECT); }
		catch (e) { pref = undefined; }
		autoConnect = (pref !== false);
		if (autoConnect) scanAndConnect();
	}

	function deactivate() {
		autoConnect = false;
		teardown();
	}

	function startBridge() {
		autoConnect = true;
		try { eda.sys_Storage.setExtensionUserConfig(STORAGE_AUTOCONNECT, true); } catch (e) { /* noop */ }
		toast("启动桥接, 正在连接...");
		teardown();
		scanAndConnect();
	}

	function stopBridge() {
		autoConnect = false;
		try { eda.sys_Storage.setExtensionUserConfig(STORAGE_AUTOCONNECT, false); } catch (e) { /* noop */ }
		teardown();
		toast("桥接已停止");
	}

	function reconnect() {
		toast("重新连接...");
		teardown();
		autoConnect = true;
		scanAndConnect();
	}

	function ping() {
		if (connected) toast("已连接 (端口 " + currentPort + "), 已处理 " + cmdCount + " 条命令");
		else if (connecting) toast("连接中...");
		else toast("未连接 (请先在本机运行 lceda_ws_bridge.py)");
	}

	function about() {
		const status = connected
			? ("已连接 (端口 " + currentPort + ")")
			: (connecting ? "连接中" : "未连接");
		const body = "LCEDA Bridge (道之直连) v1.1.0\n"
			+ "WebSocket 桥接 — 让 AI 直接驱动嘉立创EDA\n\n"
			+ "状态: " + status + "\n"
			+ "端口扫描: ws://127.0.0.1:" + PORT_START + "-" + PORT_END + "/eda\n"
			+ "已处理命令: " + cmdCount
			+ (lastError ? ("\n最近错误: " + lastError) : "")
			+ "\n\n反者道之动 · 道法自然 · 无为而无不为";
		try { eda.sys_MessageBox.showInformationMessage(body, "关于 LCEDA Bridge"); }
		catch (e) { toast(body); }
	}

	function openPanel() {
		try { eda.sys_IFrame.openIFrame("iframe/index.html", 440, 380); }
		catch (e) { toast("打开面板失败: " + e); }
	}

	return index_exports;
})();
