"""
LCEDA Bridge — Python 端 HTTP 桥接服务器
================================================
反者道之动 · 道法自然

架构:
    嘉立创EDA Extension (lceda-bridge) ──┐
                                          │ HTTP 长轮询
                                          ▼
                  ┌──────────────────────────────────────┐
                  │  本服务器 :9907                       │
                  │   POST /hello   ← 客户端握手          │
                  │   GET  /poll    ← 客户端拉取命令      │
                  │   POST /result  ← 客户端回传结果      │
                  │   POST /call    ← Python端发起调用    │
                  │   GET  /ping    ← 健康检查            │
                  │   GET  /status  ← 状态                │
                  │   GET  /        ← Web UI              │
                  └──────────────────────────────────────┘

用法:
    # 启动服务器
    python lceda_bridge_server.py

    # 在嘉立创EDA中: 高级 → LCEDA Bridge → 启动桥接

    # Python 端调用:
    from lceda_bridge_server import call
    info = call('dmt_Project.getCurrentProjectInfo')
    print(info)

    # 或CLI:
    python lceda_bridge_server.py call dmt_Project.getCurrentProjectInfo
"""
from __future__ import annotations
import argparse
import json
import os
import queue
import sys
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError

# ──────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────
HOST = '127.0.0.1'
PORT = 9907
POLL_TIMEOUT_S = 25.0       # 长轮询最大等待
CMD_TIMEOUT_S = 30.0        # 命令执行回传超时

# pcb_brain (引擎/对话大脑) 在仓库根的 pcb_brain/ 下
_BRAIN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'pcb_brain')
if os.path.isdir(_BRAIN_DIR) and _BRAIN_DIR not in sys.path:
    sys.path.insert(0, _BRAIN_DIR)


_DIALOG_HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 'L2_extension', 'iframe', 'index.html')


def _read_dialog_html() -> str:
    """读取扩展 iframe 对话框 HTML (主面)。每次读盘, 便于热更新。"""
    with open(_DIALOG_HTML_PATH, 'r', encoding='utf-8') as f:
        return f.read()


def chat_respond(message: str, session: str | None = None,
                 output_dir: str | None = None) -> dict:
    """对话框 → PCB 全流程 → 预测编码裁决, 委托 pcb_copilot.respond。"""
    from pcb_copilot import respond
    return respond(message, session=session, output_dir=output_dir)


def _notify_eda(reply: dict) -> None:
    """深度融合(best-effort): 把裁决以 Toast 注入活动嘉立创EDA。

    无活动客户端 / 无该 API 时静默跳过, 绝不阻塞对话主链路。
    """
    try:
        with STATE.lock:
            if not STATE.sessions:
                return
        delivered = reply.get('delivered')
        fe = reply.get('free_energy')
        name = reply.get('template') or 'PCB'
        if delivered is True:
            text = f'PCB Copilot: 「{name}」已交付 ✓ (自由能=0)'
            level = 0
        elif delivered is False:
            text = f'PCB Copilot: 「{name}」自由能={fe}, {reply.get("next_action") or "尚未闭合"}'
            level = 1
        else:
            text = 'PCB Copilot: ' + (reply.get('reply', '')[:60])
            level = 0
        cmd_id = STATE.queue_cmd(None, 'sys_ToastMessage.showMessage', [text, level])
        # 不强等结果, 给极短超时, 注入失败也不影响对话
        try:
            STATE.wait_result(cmd_id, timeout=3.0)
        except Exception:
            pass
    except Exception as e:
        print(f'[bridge] _notify_eda 跳过: {e}')

# ──────────────────────────────────────────────────────────
# 全局状态
# ──────────────────────────────────────────────────────────
class BridgeState:
    def __init__(self):
        self.lock = threading.Lock()
        self.sessions: dict[str, dict] = {}    # sessionId → meta
        self.cmd_queues: dict[str, queue.Queue] = {}  # sessionId → Queue[cmd]
        self.results: dict[str, queue.Queue] = {}      # cmdId → Queue[result] (size 1)
        self.history: deque = deque(maxlen=100)        # 命令日志

    def hello(self, meta: dict) -> str:
        sid = uuid.uuid4().hex[:12]
        with self.lock:
            self.sessions[sid] = {**meta, 'sessionId': sid, 'connectedAt': time.time(), 'lastSeen': time.time()}
            self.cmd_queues[sid] = queue.Queue()
        return sid

    def touch(self, sid: str):
        with self.lock:
            if sid in self.sessions:
                self.sessions[sid]['lastSeen'] = time.time()

    def queue_cmd(self, sid: str | None, path: str, args: list[Any] | None = None) -> str:
        cmd_id = uuid.uuid4().hex[:8]
        cmd = {'id': cmd_id, 'path': path, 'args': args or [], 'ts': time.time()}
        with self.lock:
            if sid is None:
                # broadcast 到第一个活跃 session
                if not self.sessions:
                    raise RuntimeError('无活跃 LCEDA 客户端连接')
                sid = next(iter(self.sessions))
            if sid not in self.cmd_queues:
                raise RuntimeError(f'sessionId {sid} 不存在')
            self.cmd_queues[sid].put(cmd)
            self.results[cmd_id] = queue.Queue(maxsize=1)
            self.history.append({'cmd': cmd, 'sessionId': sid, 'queuedAt': time.time()})
        return cmd_id

    def wait_result(self, cmd_id: str, timeout: float = CMD_TIMEOUT_S) -> dict:
        with self.lock:
            q = self.results.get(cmd_id)
            if q is None:
                raise RuntimeError(f'未知 cmdId: {cmd_id}')
        try:
            res = q.get(timeout=timeout)
            return res
        finally:
            with self.lock:
                self.results.pop(cmd_id, None)

    def deliver_result(self, cmd_id: str, payload: dict):
        with self.lock:
            q = self.results.get(cmd_id)
        if q is None:
            print(f'[bridge] ⚠️ 收到孤儿结果 cmdId={cmd_id} (可能已超时清除)')
            return
        try:
            q.put_nowait(payload)
        except queue.Full:
            pass

    def poll_cmd(self, sid: str, timeout: float = POLL_TIMEOUT_S) -> dict | None:
        self.touch(sid)
        with self.lock:
            q = self.cmd_queues.get(sid)
        if q is None:
            return None
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return None

    def status(self) -> dict:
        with self.lock:
            return {
                'pid': os.getpid(),
                'host': HOST, 'port': PORT,
                'sessions': list(self.sessions.values()),
                'pendingCmds': sum(q.qsize() for q in self.cmd_queues.values()),
                'pendingResults': len(self.results),
                'history': list(self.history)[-10:],
            }

STATE = BridgeState()

# ──────────────────────────────────────────────────────────
# HTTP Handler
# ──────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 静默默认日志
        pass

    def _send_json(self, code: int, payload: Any):
        body = json.dumps(payload, ensure_ascii=False, default=str).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, code: int, text: str, content_type='text/plain'):
        body = text.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', f'{content_type}; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        n = int(self.headers.get('Content-Length', '0'))
        if not n:
            return {}
        raw = self.rfile.read(n)
        return json.loads(raw.decode('utf-8'))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/ping':
            return self._send_json(200, {'ok': True, 'pid': os.getpid(), 'ts': time.time()})

        if u.path == '/status':
            return self._send_json(200, STATE.status())

        if u.path == '/poll':
            qs = parse_qs(u.query)
            sid = qs.get('sessionId', [''])[0]
            if not sid:
                return self._send_json(400, {'error': '缺少 sessionId'})
            cmd = STATE.poll_cmd(sid)
            if cmd is None:
                self.send_response(204)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                return
            return self._send_json(200, cmd)

        if u.path == '/' or u.path == '/index.html' or u.path == '/ui' or u.path == '/dialog':
            # 主面: PCB Copilot 对话框 (复用扩展 iframe, 即"对用户只增加一个对话框")。
            try:
                return self._send_text(200, _read_dialog_html(), 'text/html')
            except Exception as e:
                return self._send_text(500, f'对话框加载失败: {e}')

        if u.path == '/console':
            return self._send_text(200, _UI_HTML, 'text/html')

        return self._send_json(404, {'error': '未知路径', 'path': u.path})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            data = self._read_json()
        except Exception as e:
            return self._send_json(400, {'error': f'JSON 解析失败: {e}'})

        if u.path == '/hello':
            sid = STATE.hello(data)
            print(f'[bridge] 🟢 LCEDA 已连接 sessionId={sid} client={data.get("client")}')
            return self._send_json(200, {'sessionId': sid, 'serverTs': time.time()})

        if u.path == '/result':
            cmd_id = data.get('cmdId')
            sid = data.get('sessionId')
            if sid: STATE.touch(sid)
            STATE.deliver_result(cmd_id, data)
            return self._send_json(200, {'ok': True})

        if u.path == '/call':
            # Python 端调用入口 (curl/requests)
            try:
                path = data.get('path')
                args = data.get('args', [])
                timeout = float(data.get('timeout', CMD_TIMEOUT_S))
                cmd_id = STATE.queue_cmd(data.get('sessionId'), path, args)
                res = STATE.wait_result(cmd_id, timeout)
                return self._send_json(200, res)
            except Exception as e:
                return self._send_json(500, {'error': str(e)})

        if u.path == '/chat':
            # 对话框入口: 一句话 → PCB 全流程 → 预测编码裁决 → 人话回复。
            # 这是"对用户只增加一个对话框、AI 与 PCB 软件深度融合"的语言中枢。
            try:
                reply = chat_respond(
                    data.get('message', ''),
                    session=data.get('session'),
                    output_dir=data.get('output_dir') or None,
                )
            except Exception as e:
                import traceback
                traceback.print_exc()
                return self._send_json(500, {
                    'reply': f'大脑处理时出错: {e}',
                    'intent': 'error', 'error': str(e),
                })
            # 深度融合: 若有活动 EDA 客户端, 把裁决以 Toast 注入活动嘉立创EDA。
            _notify_eda(reply)
            return self._send_json(200, reply)

        return self._send_json(404, {'error': '未知路径', 'path': u.path})

# ──────────────────────────────────────────────────────────
# Web UI
# ──────────────────────────────────────────────────────────
_UI_HTML = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><title>LCEDA Bridge 服务器</title>
<style>
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #0a0a0a; color: #e0e0e0;
       margin: 0; padding: 20px; }
h1 { color: #4fc3f7; }
.card { background: #1a1a2e; border-radius: 8px; padding: 16px; margin: 12px 0;
        border-left: 3px solid #4fc3f7; }
.label { color: #999; }
.val { color: #81c784; font-family: 'Cascadia Code', monospace; }
button { background: transparent; border: 1px solid #4fc3f7; color: #4fc3f7;
         padding: 8px 16px; border-radius: 4px; cursor: pointer; }
button:hover { background: #4fc3f7; color: #0a0a0a; }
input, textarea { background: #0a0a18; border: 1px solid #333; color: #e0e0e0;
                  padding: 6px; border-radius: 4px; font-family: monospace; }
pre { background: #000; padding: 12px; border-radius: 4px; overflow: auto; max-height: 300px; }
</style></head>
<body>
<h1>🌉 LCEDA Bridge — 服务器控制台</h1>
<div class="card">
  <span class="label">状态:</span> <span id="status" class="val">加载中...</span>
  <button onclick="refresh()" style="float:right">🔄 刷新</button>
</div>
<div class="card">
  <h3>测试 eda.* 调用</h3>
  <input id="path" placeholder="dmt_Project.getCurrentProjectInfo" style="width: 60%">
  <input id="args" placeholder="JSON 参数数组, 如 []" style="width: 30%" value="[]">
  <button onclick="callApi()">调用</button>
  <pre id="result">(无)</pre>
</div>
<script>
async function refresh() {
  const r = await fetch('/status'); const j = await r.json();
  document.getElementById('status').textContent = JSON.stringify(j, null, 2);
}
async function callApi() {
  const path = document.getElementById('path').value;
  const args = JSON.parse(document.getElementById('args').value || '[]');
  document.getElementById('result').textContent = '调用中...';
  try {
    const r = await fetch('/call', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ path, args, timeout: 30 })
    });
    const j = await r.json();
    document.getElementById('result').textContent = JSON.stringify(j, null, 2);
  } catch (e) {
    document.getElementById('result').textContent = String(e);
  }
}
refresh(); setInterval(refresh, 5000);
</script>
</body></html>
"""

# ──────────────────────────────────────────────────────────
# Python 客户端 API
# ──────────────────────────────────────────────────────────
def call(path: str, *args, server: str = f'http://{HOST}:{PORT}', timeout: float = CMD_TIMEOUT_S, session_id: str | None = None) -> Any:
    """从 Python 端调用 eda.<path>(args), 通过 HTTP 同步获得结果

    例:
        info = call('dmt_Project.getCurrentProjectInfo')
        ver  = call('sys_Environment.getEditorVersion')
    """
    body = json.dumps({'path': path, 'args': list(args), 'timeout': timeout, 'sessionId': session_id}).encode('utf-8')
    req = Request(f'{server}/call', data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(req, timeout=timeout + 5) as resp:
        payload = json.loads(resp.read().decode('utf-8'))
    if payload.get('error'):
        raise RuntimeError(f"嘉立创端报错: {payload['error']}")
    return payload.get('result')

def ping(server: str = f'http://{HOST}:{PORT}') -> bool:
    try:
        with urlopen(f'{server}/ping', timeout=2) as resp:
            return resp.status == 200
    except URLError:
        return False

# ──────────────────────────────────────────────────────────
# 服务器启动
# ──────────────────────────────────────────────────────────
class ThreadedHTTPServer(HTTPServer):
    """多线程版本, 支持长轮询并发"""
    daemon_threads = True

    def process_request(self, request, client_address):
        thread = threading.Thread(target=self._process_request_thread, args=(request, client_address), daemon=True)
        thread.start()

    def _process_request_thread(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)


def serve():
    httpd = ThreadedHTTPServer((HOST, PORT), Handler)
    print(f'[bridge] 🌉 LCEDA Bridge 服务器已启动')
    print(f'[bridge]   监听: http://{HOST}:{PORT}')
    print(f'[bridge]   Web UI: http://{HOST}:{PORT}/')
    print(f'[bridge]   API: POST /call  GET /poll  POST /hello  POST /result  GET /ping  GET /status')
    print(f'[bridge] 等待嘉立创EDA连接... (顶部菜单 LCEDA Bridge → 启动桥接)')
    print(f'[bridge] Ctrl+C 退出')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n[bridge] 已停止')


def main():
    ap = argparse.ArgumentParser(description='LCEDA Bridge 服务器')
    sub = ap.add_subparsers(dest='cmd')

    sub.add_parser('serve', help='启动服务器 (默认)')

    p_call = sub.add_parser('call', help='向已连接的嘉立创发起调用')
    p_call.add_argument('path', help='eda.* 路径, 如 dmt_Project.getCurrentProjectInfo')
    p_call.add_argument('args', nargs='*', help='JSON 参数')

    p_status = sub.add_parser('status', help='查看服务器状态')

    args = ap.parse_args()
    cmd = args.cmd or 'serve'

    if cmd == 'serve':
        serve()
    elif cmd == 'call':
        if not ping():
            print(f'❌ 服务器未运行, 请先 python {sys.argv[0]} serve', file=sys.stderr)
            sys.exit(1)
        try:
            parsed_args = [json.loads(a) for a in args.args]
        except Exception:
            parsed_args = args.args
        try:
            result = call(args.path, *parsed_args)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        except Exception as e:
            print(f'❌ {e}', file=sys.stderr)
            sys.exit(2)
    elif cmd == 'status':
        if not ping():
            print(f'❌ 服务器未运行')
            sys.exit(1)
        with urlopen(f'http://{HOST}:{PORT}/status') as r:
            print(json.dumps(json.loads(r.read()), ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
