// 本地集成测试: 用 Node 加载真实的 dist/index.js, 注入 mock eda,
// 让它经 WebSocket 连接 Python WS 桥, 模拟嘉立创EDA扩展端。
// 运行: node --experimental-websocket _localtest_mock_eda.js
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const sockets = {};
const storage = {};

global.eda = {
  sys_WebSocket: {
    register(id, uri, onMsg, onConnect) {
      try { if (sockets[id]) sockets[id].close(); } catch (e) {}
      const ws = new WebSocket(uri);
      sockets[id] = ws;
      ws.addEventListener('open', () => { if (onConnect) onConnect(); });
      ws.addEventListener('message', (ev) => {
        const data = typeof ev.data === 'string' ? ev.data : String(ev.data);
        if (onMsg) onMsg({ data });
      });
      ws.addEventListener('error', () => {});
    },
    send(id, data) { const ws = sockets[id]; if (ws && ws.readyState === 1) ws.send(data); },
    close(id) { const ws = sockets[id]; if (ws) { try { ws.close(); } catch (e) {} } delete sockets[id]; },
  },
  sys_Storage: {
    getExtensionUserConfig(k) { return storage[k]; },
    setExtensionUserConfig(k, v) { storage[k] = v; return Promise.resolve(true); },
  },
  sys_ToastMessage: { showMessage(m) { console.log('[toast]', m); } },
  sys_MessageBox: { showInformationMessage(c, t) { console.log('[dialog]', t, c); } },
  sys_IFrame: { openIFrame() { return Promise.resolve(); } },
  // ── mock 业务域 API (用于验证 call 分发) ──
  sys_Environment: {
    getEditorVersion: async () => '2.2.32-mock',
    getLanguage: async () => 'zh-Hans',
  },
  dmt_Project: {
    getCurrentProjectInfo: async () => ({ uuid: 'proj-mock-001', name: '道之测试工程' }),
    getAllProjectsUuid: async () => ['proj-mock-001', 'proj-mock-002'],
    createProject: async (name) => ({ uuid: 'proj-new-xyz', name }),
  },
};

const code = fs.readFileSync(path.join(__dirname, '..', 'L2_extension', 'dist', 'index.js'), 'utf-8');
vm.runInThisContext(code, { filename: 'index.js' });

console.log('[mock-eda] 已加载扩展, 导出:', Object.keys(global.edaEsbuildExportName).join(', '));
global.edaEsbuildExportName.startBridge();

setInterval(() => {}, 1000); // keep alive
