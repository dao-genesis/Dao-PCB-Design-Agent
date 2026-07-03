#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mock_llm — 本机 OpenAI 兼容 mock 服务(工具调用回路验证用)。

首轮返回 get_context 工具调用;见到 tool 结果后返回最终中文答复。
用于在无真实 API Key 的环境里活体验证「对话→工具→引擎→答复」全链路。
"""
import http.server
import json

PORT = 9944


class H(http.server.BaseHTTPRequestHandler):
    def _read_body(self):
        """兼容 Content-Length 与 Transfer-Encoding: chunked (sys_ClientUrl 大包即 chunked)."""
        te = (self.headers.get('transfer-encoding') or '').lower()
        if 'chunked' in te:
            out = b''
            while True:
                line = self.rfile.readline().strip()
                try:
                    size = int(line.split(b';')[0], 16)
                except ValueError:
                    break
                if size == 0:
                    self.rfile.readline()
                    break
                out += self.rfile.read(size)
                self.rfile.readline()
            return out
        n = int(self.headers.get('content-length', 0))
        return self.rfile.read(n)

    def do_POST(self):
        raw = self._read_body()
        try:
            with open('/tmp/mock_llm_reqs.log', 'a') as f:
                f.write(raw.decode('utf-8', 'replace') + "\n---\n")
        except Exception:
            pass
        body = json.loads(raw or b'{}')
        msgs = body.get('messages', [])
        stream = bool(body.get('stream'))
        user_txt = ''.join(str(m.get('content') or '') for m in msgs if m.get('role') == 'user')
        n_tool = sum(1 for m in msgs if m.get('role') == 'tool')
        if '多步' in user_txt:
            # 多步工具流: get_context → toast → 最终 Markdown 流式答复
            if n_tool == 0:
                msg = {'role': 'assistant', 'content': None, 'tool_calls': [
                    {'id': 'call_1', 'type': 'function',
                     'function': {'name': 'get_context', 'arguments': '{}'}}]}
            elif n_tool == 1:
                msg = {'role': 'assistant', 'content': None, 'tool_calls': [
                    {'id': 'call_2', 'type': 'function',
                     'function': {'name': 'toast',
                                  'arguments': json.dumps({'message': '☸ 多步工具流验证中'}, ensure_ascii=False)}}]}
            else:
                msg = {'role': 'assistant', 'content':
                       '## 多步验证完成\n\n- **上下文**已读取\n- 引擎`toast`已弹出\n\n一切就绪。'}
        elif n_tool:
            msg = {'role': 'assistant', 'content': '已完成工具执行,引擎在线,一切就绪。'}
        elif '提示' in user_txt:
            msg = {'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': 'call_t', 'type': 'function',
                 'function': {'name': 'toast',
                              'arguments': json.dumps({'message': '☸ DAO AI IDE 直驱引擎 · 道法自然'}, ensure_ascii=False)}}]}
        elif '版本' in user_txt:
            msg = {'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': 'call_v', 'type': 'function',
                 'function': {'name': 'eda_call',
                              'arguments': json.dumps({'namespace': 'sys_Environment', 'method': 'getEditorCurrentVersion', 'args': []})}}]}
        else:
            msg = {'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': 'call_1', 'type': 'function',
                 'function': {'name': 'get_context', 'arguments': '{}'}}]}
        if stream:
            self._send_stream(msg)
        else:
            resp = {'id': 'mock', 'object': 'chat.completion',
                    'choices': [{'index': 0, 'message': msg, 'finish_reason': 'stop'}]}
            b = json.dumps(resp).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(b)))
            self.end_headers()
            self.wfile.write(b)

    def _send_stream(self, msg):
        """按 OpenAI SSE 协议分片发送: content 逐字, tool_calls 按 delta."""
        import time
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        def emit(delta, finish=None):
            evt = {'id': 'mock', 'object': 'chat.completion.chunk',
                   'choices': [{'index': 0, 'delta': delta, 'finish_reason': finish}]}
            self.wfile.write(('data: ' + json.dumps(evt, ensure_ascii=False) + '\n\n').encode())
            self.wfile.flush()

        emit({'role': 'assistant'})
        if msg.get('tool_calls'):
            for i, tc in enumerate(msg['tool_calls']):
                emit({'tool_calls': [{'index': i, 'id': tc['id'], 'type': 'function',
                                      'function': {'name': tc['function']['name'], 'arguments': ''}}]})
                args = tc['function']['arguments']
                for j in range(0, len(args), 8):
                    emit({'tool_calls': [{'index': i, 'function': {'arguments': args[j:j + 8]}}]})
            emit({}, 'tool_calls')
        else:
            content = msg.get('content') or ''
            for j in range(0, len(content), 4):
                emit({'content': content[j:j + 4]})
                time.sleep(0.02)
            emit({}, 'stop')
        self.wfile.write(b'data: [DONE]\n\n')
        self.wfile.flush()

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    http.server.HTTPServer(('127.0.0.1', PORT), H).serve_forever()
