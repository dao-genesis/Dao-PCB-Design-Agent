/* ============================================================
 * 嘉立创EDA 全部工程清单 — Layer 1
 * 输出: 当前工作区/团队下所有工程的 UUID + 元信息 (展开版)
 * ============================================================ */
(async () => {
    const log = (...a) => console.log('[嘉立创直连·工程清单]', ...a);
    const result = { ts: new Date().toISOString(), projects: [] };

    const allUuid = await eda.dmt_Project.getAllProjectsUuid();
    log(`找到 ${allUuid?.length ?? 0} 个工程`);

    for (const uuid of (allUuid ?? [])) {
        try {
            const info = await eda.dmt_Project.getProjectInfo(uuid);
            result.projects.push(info);
        } catch (e) {
            result.projects.push({ uuid, _error: String(e) });
        }
    }

    log('完整列表:', result);

    // 转 CSV
    const headers = ['uuid', 'name', 'friendlyName', 'description', 'createTime', 'modifyTime'];
    const rows = [headers.join(',')];
    for (const p of result.projects) {
        rows.push(headers.map(h => JSON.stringify(p?.[h] ?? '')).join(','));
    }
    const csv = rows.join('\n');

    try {
        await navigator.clipboard.writeText(csv);
        log('✅ CSV 已复制剪贴板');
    } catch {}

    eda.sys_MessageBox?.showInformationMessage?.(
        `共 ${result.projects.length} 个工程\nCSV 已复制到剪贴板`,
        '嘉立创直连·工程清单',
        '了解'
    );
    return result;
})();
