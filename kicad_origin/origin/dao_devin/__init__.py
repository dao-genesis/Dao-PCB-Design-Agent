"""dao_devin — 把 devin-remote 的 Devin Cloud 本源接入原生移植进 KiCad。

道法自然 · 反者道之动: 上一个会话立起了「进程内活体融合内核」(native_live +
_live_server)——一个活着的 pcbnew 进程握 BOARD 长存, 对外开 HTTP JSON-RPC。本包
把 devin-remote/core/dao-vsix (「把 VS Code 改造成 Devin Desktop 的本源」) 的核心
能力**忠实移植到 Python**, 让 KiCad 本体成为半原生的 Devin Desktop 底座——

  devin_cloud : Devin Cloud 云端客户端 (登录/会话/消息/额度/知识库/剧本/密钥),
                从 core/dao-vsix/rtflow/devin_cloud.js 逐函数移植, 端点/契约一致。
  accounts    : 多账号池 (WAM · 反向注入 · 一键切号) 的最小 Python 实现。
  panel       : KiCad wxPython Action Plugin —— 在 pcbnew 内嵌「Devin 面板」
                (对话窗口/账号管理/会话追踪), 底层经 devin_cloud 起云端会话, 并
                可驱动同进程的活体内核 (_live_server) 直改活板。

反臆造: 端点与请求契约全部照搬 devin-remote 已实测确证者 (见各函数 docstring 的
出处行号), 不臆造新接口。非 ASCII 请求体一律 ensure_ascii (踩坑: 服务端会每隔一字
截断中文), 与 dao-vsix asciiSafeJson 同义。
"""
from __future__ import annotations

__all__ = ["devin_cloud", "accounts", "dao_proxy", "proxy_adapters"]
