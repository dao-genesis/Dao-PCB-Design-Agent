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
    def do_POST(self):
        n = int(self.headers.get('content-length', 0))
        raw = self.rfile.read(n)
        try:
            with open('/tmp/mock_llm_reqs.log', 'a') as f:
                f.write(raw.decode('utf-8', 'replace') + "\n---\n")
        except Exception:
            pass
        body = json.loads(raw or b'{}')
        msgs = body.get('messages', [])
        user_txt = ''.join(str(m.get('content') or '') for m in msgs if m.get('role') == 'user')
        has_tool = any(m.get('role') == 'tool' for m in msgs)
        if has_tool:
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
        resp = {'id': 'mock', 'object': 'chat.completion',
                'choices': [{'index': 0, 'message': msg, 'finish_reason': 'stop'}]}
        b = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    http.server.HTTPServer(('127.0.0.1', PORT), H).serve_forever()
