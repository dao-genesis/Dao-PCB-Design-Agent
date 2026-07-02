"use strict";
/* ============================================================================
 * DAO AI IDE — 扩展宿主入口 (道之枢机)
 * ============================================================================
 * 锚定本源:嘉立创EDA 本体即 AI IDE。本扩展以官方扩展体系原生集成:
 *   · 顶部菜单 DAO AI → 打开 AI IDE → eda.sys_IFrame 打开面板(ide/index.html)
 *   · 面板为同源(https://client)iframe,可直达 window.top._EXTAPI_ROOT_:
 *       - LLM 外呼: sys_ClientUrl.request —— 客户端特权网络通道,免 CORS/Mixed-Content
 *       - 引擎直驱: 全部 94 命名空间 / 749 方法(放器件/布线/DRC/导出…)
 *   故面板自身即完整 AI IDE(对话/会话/模型/提示词/工具),宿主只负责开窗与生命周期。
 *
 * 入口格式: 嘉立创EDA 运行时按 `edaEsbuildExportName.<registerFn>()` 调用导出函数。
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
		openIDE: () => openIDE,
	});

	var IFRAME_ID = "dao-ai-ide-panel";

	function toast(msg) {
		try { eda.sys_Message.showToastMessage(String(msg)); }
		catch (e) { try { eda.sys_ToastMessage.showMessage(String(msg)); } catch (e2) { /* noop */ } }
	}

	function activate() { /* 按需开窗,启动时静默 */ }
	function deactivate() {
		try { eda.sys_IFrame.closeIFrame(IFRAME_ID); } catch (e) { /* noop */ }
	}

	async function openIDE() {
		try {
			if (await eda.sys_IFrame.isIFrameAlreadyExist(IFRAME_ID)) {
				await eda.sys_IFrame.showIFrame(IFRAME_ID);
				return;
			}
		} catch (e) { /* 继续尝试打开 */ }
		try {
			await eda.sys_IFrame.openIFrame("ide/index.html", 980, 640, IFRAME_ID, {
				title: "DAO AI IDE",
				maximizeButton: true,
				minimizeButton: true,
				minimizeStyle: "collapsed",
				grayscaleMask: false,
			});
		} catch (e) {
			toast("打开 AI IDE 失败: " + (e && e.message || e));
		}
	}

	function about() {
		var body = "DAO AI IDE (道之枢机) v1.0.0\n"
			+ "嘉立创EDA 本体即 AI IDE:\n"
			+ "· 原生对话面板 + 会话管理\n"
			+ "· 外接 API 多模型管理(OpenAI 兼容 / Proxy Pro 式)\n"
			+ "· 提示词库\n"
			+ "· 工具调用直驱 EDA 引擎(94 命名空间 / 749 方法)\n\n"
			+ "道法自然 · 无为而无不为";
		try { eda.sys_Dialog.showInformationMessage(body, "关于 DAO AI IDE"); }
		catch (e) { toast(body); }
	}

	return index_exports;
})();
