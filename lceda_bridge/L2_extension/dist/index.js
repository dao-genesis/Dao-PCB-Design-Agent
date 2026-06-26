/* ============================================================
 * LCEDA Bridge — 扩展入口 (L2 entry)  ·  反者道之动
 *
 * 这是嘉立创EDA专业版扩展的主代码 (extension.json 的 "entry": "./dist/index").
 * headerMenus 里每个 menuItem 的 registerFn 对应此模块导出的同名函数,
 * 用户点击菜单项时由 EDA 调用。
 *
 * 三件事:
 *   1. openPanel  — 打开对话框 iframe (Cursor 式侧边对话, 深度融合)
 *   2. startBridge/stopBridge — 连接本机 Python 桥 :9907 长轮询,
 *      让 Python(AI 大脑) 能反向驱动 eda.*  (把成果注入到 EDA)
 *   3. ping/about — 自检 / 关于
 *
 * 对话本身: iframe 直接 fetch 桥 :9907/chat (CORS 已放行),
 * 一句话 → 桥调用 design_spec/pipeline_spec/reconcile 三元组 → 回裁决。
 * 启动桥接的长轮询是另一条正交通道, 供 AI 把板子/提示注入活动 EDA。
 * ============================================================ */

const BRIDGE_URL = 'http://127.0.0.1:9907';
const PANEL_HTML = 'iframe/index.html';

// 桥接长轮询的运行态 (供 AI 反向驱动 eda.*)
const _bridge = {
  running: false,
  sessionId: null,
  cmdCount: 0,
  lastError: null,
};

function _toast(msg, type = 0) {
  try { eda.sys_ToastMessage && eda.sys_ToastMessage.showMessage(msg, type); } catch (e) { /* noop */ }
}

function _log(...a) {
  try { console.log('[LCEDA Bridge]', ...a); } catch (e) { /* noop */ }
}

/* ── 打开对话框面板 ───────────────────────────────────────── */
export function openPanel() {
  try {
    // 宽 ~ 侧栏, 高 ~ 大半屏; 第一参数为相对扩展根目录的 HTML 路径
    eda.sys_IFrame.openIFrame(PANEL_HTML, 460, 680);
  } catch (e) {
    _log('openPanel 失败:', e);
    try {
      eda.sys_MessageBox &&
        eda.sys_MessageBox.showInformationMessage(
          '无法打开对话框: ' + e, 'LCEDA Bridge');
    } catch (_) { /* noop */ }
  }
}

/* ── 启动桥接长轮询 (AI 反向驱动 eda.*) ───────────────────── */
export async function startBridge() {
  if (_bridge.running) {
    _toast('桥接已在运行', 0);
    return;
  }
  // 握手
  try {
    const r = await fetch(BRIDGE_URL + '/hello', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        client: 'lceda-pro-extension',
        ts: Date.now(),
        ua: (typeof navigator !== 'undefined' && navigator.userAgent) || 'lceda-pro',
      }),
    });
    const j = await r.json();
    _bridge.sessionId = j.sessionId;
    _bridge.running = true;
    _bridge.lastError = null;
    _toast('已连接 Python 桥, 开始监听 (sessionId=' + j.sessionId + ')', 0);
    _log('已连接桥, sessionId=', j.sessionId);
  } catch (e) {
    _bridge.lastError = String(e);
    try {
      eda.sys_MessageBox &&
        eda.sys_MessageBox.showInformationMessage(
          '无法连接到 ' + BRIDGE_URL + '\n\n请先在终端运行:\n  python lceda_bridge/lceda_bridge_server.py\n\n错误: ' + e,
          'LCEDA Bridge · 连接失败');
    } catch (_) { /* noop */ }
    return;
  }

  // 长轮询循环: Python 推命令 → 此处执行 eda.<path>(args) → 回传
  (async () => {
    while (_bridge.running) {
      try {
        const r = await fetch(
          BRIDGE_URL + '/poll?sessionId=' + encodeURIComponent(_bridge.sessionId),
          { method: 'GET', cache: 'no-store' });
        if (r.status === 204) continue; // 无命令
        const cmd = await r.json();
        _bridge.cmdCount++;

        let result, error;
        try {
          const fn = cmd.path.split('.').reduce((o, k) => (o == null ? o : o[k]), eda);
          if (typeof fn !== 'function') {
            throw new Error('eda.' + cmd.path + ' 不是函数');
          }
          const ctx = cmd.path.split('.').slice(0, -1)
            .reduce((o, k) => (o == null ? o : o[k]), eda);
          result = await fn.apply(ctx, cmd.args || []);
        } catch (e) {
          error = { message: String(e), stack: e && e.stack };
        }

        await fetch(BRIDGE_URL + '/result', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            sessionId: _bridge.sessionId,
            cmdId: cmd.id,
            result,
            error,
            ts: Date.now(),
          }),
        });
      } catch (e) {
        _bridge.lastError = String(e);
        _log('轮询失败, 5秒后重试:', e);
        await new Promise((res) => setTimeout(res, 5000));
      }
    }
    _log('桥接循环已停止, 共处理', _bridge.cmdCount, '条命令');
  })();
}

/* ── 停止桥接 ─────────────────────────────────────────────── */
export function stopBridge() {
  _bridge.running = false;
  _bridge.sessionId = null;
  _toast('桥接已停止', 0);
  _log('桥接已停止');
}

/* ── 测试连接 ─────────────────────────────────────────────── */
export async function ping() {
  try {
    const r = await fetch(BRIDGE_URL + '/ping', { cache: 'no-store' });
    const j = await r.json();
    _toast('桥在线 ✅ pid=' + j.pid, 0);
  } catch (e) {
    _toast('桥不可达 ❌ ' + e, 2);
  }
}

/* ── 关于 ─────────────────────────────────────────────────── */
export function about() {
  const msg =
    'LCEDA Bridge (道之直连)\n' +
    '反者道之动 · 道法自然 · 无为而无不为\n\n' +
    '在嘉立创EDA内用一句话驱动 PCB 全流程:\n' +
    '  规格 → DNA → 布局布线 → DRC/Gerber/BOM/CPL → 预测编码裁决\n\n' +
    '用法: 点击「打开控制台」打开对话框, 直接说出你想做的板子。\n' +
    'Python 桥: ' + BRIDGE_URL;
  try {
    eda.sys_MessageBox &&
      eda.sys_MessageBox.showInformationMessage(msg, '关于 LCEDA Bridge');
  } catch (e) {
    _toast('LCEDA Bridge · 道之直连', 0);
  }
}

/* ── 生命周期 (启用扩展时调用) ────────────────────────────── */
export function activate() {
  _log('扩展已激活');
}

export function deactivate() {
  stopBridge();
}
