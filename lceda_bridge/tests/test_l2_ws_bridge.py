"""L2 WebSocket 桥 端到端集成测试 (无需活 EDA)。

把真实的 L2_extension/dist/index.js 加载进 Node (mock_eda.js, 注入 mock `eda`),
让其经 WebSocket 连接 Python WS 桥 (lceda_ws_bridge), 再从 Python 端经
WsTransport 驱动 eda.*, 验证 整条 L2 链路 (握手/注册/call/execute/错误传播)。

运行:
    python tests/test_l2_ws_bridge.py
前置: 安装 Node (>=20, 自动加 --experimental-websocket 提供 WebSocket)。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from core.sdk import EDA
from core.ws_transport import WsTransport


def _start_mock() -> subprocess.Popen:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("未找到 node, 跳过 (本测试需要 Node >=20)")
    return subprocess.Popen(
        [node, "--experimental-websocket", os.path.join(HERE, "mock_eda.js")],
        cwd=HERE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def main() -> int:
    proc = _start_mock()
    failures: list[str] = []
    try:
        t = WsTransport(wait_connect_s=30.0, timeout=15.0)
        if not t.connected:
            print("[test] ❌ 30s 内 mock 扩展未连接")
            return 1
        eda = EDA(t)

        def check(label: str, got: object, want: object) -> None:
            mark = "✅" if got == want else "❌"
            if got != want:
                failures.append(label)
            print(f"  {mark} {label}: {got!r}")

        check("getEditorVersion", eda.sys_Environment.getEditorVersion(), "2.2.32-mock")
        check("getCurrentProjectInfo.name",
              eda.dmt_Project.getCurrentProjectInfo().get("name"), "道之测试工程")
        check("getAllProjectsUuid",
              eda.dmt_Project.getAllProjectsUuid(), ["proj-mock-001", "proj-mock-002"])
        check("createProject(arg).name",
              eda.dmt_Project.createProject("新工程A").get("name"), "新工程A")
        check("run_code",
              t.run_code("return (await eda.sys_Environment.getLanguage()) + '!';"), "zh-Hans!")

        try:
            eda.dmt_Project.noSuchMethod()
            failures.append("error-propagation")
            print("  ❌ error-propagation: 期望抛错但未抛")
        except RuntimeError as e:
            print(f"  ✅ error-propagation: {e}")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    if failures:
        print(f"[test] ⚠️ 失败: {failures}")
        return 2
    print("[test] 全部通过 🎉")
    return 0


if __name__ == "__main__":
    sys.exit(main())
