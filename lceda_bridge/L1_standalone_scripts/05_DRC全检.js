/* ============================================================
 * 嘉立创EDA 当前PCB → DRC全规则检查 — Layer 1
 * 用法: 切到 PCB tab → 高级→运行脚本 → 粘贴运行
 * 输出: DRC 错误清单 + 摘要
 * ============================================================ */
(async () => {
    const log = (...a) => console.log('[嘉立创直连·DRC]', ...a);

    const pcb = await eda.dmt_Pcb?.getCurrentPcbInfo?.();
    if (!pcb) {
        eda.sys_MessageBox?.showInformationMessage?.('请先切换到 PCB 标签页', '提示');
        return;
    }

    let errors = [];
    let summary = {};
    try {
        // 优先调用全检 API
        if (typeof eda.pcb_Drc?.runDRCCheck === 'function') {
            errors = await eda.pcb_Drc.runDRCCheck() ?? [];
        } else if (typeof eda.pcb_Drc?.runDrc === 'function') {
            errors = await eda.pcb_Drc.runDrc() ?? [];
        } else if (typeof eda.pcb_Drc?.run === 'function') {
            errors = await eda.pcb_Drc.run() ?? [];
        } else {
            // 列出所有 pcb_Drc 方法
            const methods = Object.getOwnPropertyNames(Object.getPrototypeOf(eda.pcb_Drc ?? {}))
                .filter(n => typeof eda.pcb_Drc[n] === 'function' && !n.startsWith('_'));
            log('可用 DRC 方法:', methods);
            eda.sys_MessageBox?.showInformationMessage?.(
                'DRC 方法名未找到, 请到 F12 控制台查看可用方法:\n' + methods.join('\n'),
                'DRC 探测'
            );
            return { methods };
        }
    } catch (e) {
        log('DRC 调用失败:', e);
        errors = [{ _error: String(e) }];
    }

    // 分类
    for (const err of errors) {
        const k = err?.type ?? err?.errorType ?? err?.category ?? 'unknown';
        summary[k] = (summary[k] ?? 0) + 1;
    }

    log(`DRC 完成: ${errors.length} 条`, summary);

    const csv = ['Index,Type,Description,Layer,X,Y'];
    errors.forEach((e, i) => csv.push(
        [i, e.type ?? '', JSON.stringify(e.description ?? e.message ?? ''), e.layer ?? '', e.x ?? '', e.y ?? ''].join(',')
    ));
    try { await navigator.clipboard.writeText(csv.join('\n')); } catch {}

    eda.sys_MessageBox?.showInformationMessage?.(
        `DRC 共 ${errors.length} 条问题\n` +
        Object.entries(summary).map(([k, v]) => `  ${k}: ${v}`).join('\n') +
        `\n\nCSV 已复制剪贴板`,
        '嘉立创直连·DRC全检',
        '了解'
    );
    return { count: errors.length, summary, errors };
})();
