/* ============================================================
 * 嘉立创EDA → Python 桥接 引导脚本 — Layer 1 (轻量版)
 *
 * 此脚本不需要安装扩展, 直接在独立脚本环境内连接到本机 Python 桥服务器.
 * 适合快速测试, 但只能调用部分 API (无 SYS_IFrame).
 *
 * 用法:
 *   1. 终端: python lceda_bridge/lceda_bridge_server.py
 *   2. 嘉立创EDA → 高级 → 运行脚本 → 粘贴本文件 → 运行
 *   3. 终端: 看到 "[bridge] 嘉立创已连接" 即成功
 *   4. Python 端: from lceda_bridge_server import call; call('eda.dmt_Project.getCurrentProjectInfo')
 *
 * 关闭: 重新执行任何独立脚本 (新 eda 对象会替换), 或关闭嘉立创
 * ============================================================ */
(async () => {
    const BRIDGE_URL = 'http://127.0.0.1:9907';
    const log = (...a) => console.log('[嘉立创直连·桥接]', ...a);

    // 通知服务器我们已上线
    let sessionId = null;
    try {
        const r = await fetch(`${BRIDGE_URL}/hello`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                client: 'lceda-pro-standalone',
                ts: Date.now(),
                ua: navigator.userAgent,
            }),
        });
        const j = await r.json();
        sessionId = j.sessionId;
        log(`✅ 已连接 Python 桥, sessionId=${sessionId}`);
    } catch (e) {
        eda.sys_MessageBox?.showInformationMessage?.(
            `无法连接到 ${BRIDGE_URL}\n\n` +
            `请先在终端运行:\n  python lceda_bridge/lceda_bridge_server.py\n\n` +
            `错误: ${e}`,
            '嘉立创直连·桥接失败'
        );
        return;
    }

    // 长轮询循环: Python 推命令 → 此处执行 → 回传结果
    let running = true;
    let cmdCount = 0;

    // 在 window 上保存 stop 句柄
    if (typeof window !== 'undefined') {
        window.__lcedaBridgeStop = () => { running = false; log('停止桥接循环'); };
    }

    eda.sys_ToastMessage?.showMessage?.('已连接 Python 桥, 开始监听命令', 0);
    eda.sys_Log?.add?.('[bridge] 已连接 Python 桥', 0);

    while (running) {
        try {
            const r = await fetch(`${BRIDGE_URL}/poll?sessionId=${sessionId}`, {
                method: 'GET',
                cache: 'no-store',
            });
            if (r.status === 204) continue;  // 无命令, 继续轮询
            const cmd = await r.json();
            cmdCount++;
            log(`[${cmdCount}] 收到命令:`, cmd);

            let result, error;
            try {
                // 执行 eda.<path>(args)
                // 例: { "path": "dmt_Project.getCurrentProjectInfo", "args": [] }
                const fn = cmd.path.split('.').reduce((o, k) => o?.[k], eda);
                if (typeof fn !== 'function') {
                    throw new Error(`eda.${cmd.path} 不是函数`);
                }
                const ctx = cmd.path.split('.').slice(0, -1).reduce((o, k) => o?.[k], eda);
                result = await fn.apply(ctx, cmd.args ?? []);
            } catch (e) {
                error = { message: String(e), stack: e?.stack };
            }

            // 回传
            await fetch(`${BRIDGE_URL}/result`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    sessionId,
                    cmdId: cmd.id,
                    result,
                    error,
                    ts: Date.now(),
                }),
            });
        } catch (e) {
            log('轮询失败, 5秒后重试:', e);
            await new Promise(r => setTimeout(r, 5000));
        }
    }

    log(`桥接循环已停止, 共处理 ${cmdCount} 条命令`);
})();
