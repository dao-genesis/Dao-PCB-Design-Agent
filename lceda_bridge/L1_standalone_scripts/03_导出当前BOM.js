/* ============================================================
 * 嘉立创EDA 当前PCB → BOM CSV — Layer 1
 * 用法: 切到任一PCB tab → 高级→运行脚本 → 粘贴运行
 * 输出: BOM CSV 自动复制剪贴板, 同时弹窗显示
 * ============================================================ */
(async () => {
    const log = (...a) => console.log('[嘉立创直连·BOM]', ...a);

    const cur = await eda.dmt_SelectControl?.getCurrentDocumentInfo?.();
    log('当前文档:', cur);
    if (!cur) {
        eda.sys_MessageBox?.showInformationMessage?.('请先打开一个 PCB / 原理图', '提示');
        return;
    }

    // 获取 PCB 元件
    let comps = [];
    try {
        // 优先 PCB
        const pcb = await eda.dmt_Pcb?.getCurrentPcbInfo?.();
        if (pcb) {
            comps = await eda.pcb_PrimitiveComponent?.getAllPrimitivesAttributes?.() ?? [];
            log(`PCB 元件: ${comps.length}`);
        } else {
            const sch = await eda.dmt_Schematic?.getCurrentSchematicInfo?.();
            if (sch) {
                comps = await eda.sch_PrimitiveComponent?.getAllPrimitivesAttributes?.() ?? [];
                log(`原理图元件: ${comps.length}`);
            }
        }
    } catch (e) {
        log('获取元件失败:', e);
    }

    // 转 BOM CSV
    const headers = ['Designator', 'Name', 'Footprint', 'Value', 'Manufacturer', 'MfgPartNumber', 'LCSC', 'Quantity'];
    const grouped = {};
    for (const c of comps) {
        const key = `${c?.deviceName ?? c?.name ?? ''}|${c?.footprintName ?? ''}|${c?.value ?? ''}`;
        if (!grouped[key]) {
            grouped[key] = {
                designators: [],
                name: c?.deviceName ?? c?.name ?? '',
                footprint: c?.footprintName ?? '',
                value: c?.value ?? '',
                manufacturer: c?.attributes?.Manufacturer ?? c?.attributes?.['制造商'] ?? '',
                partNumber: c?.attributes?.['Manufacturer Part Number'] ?? c?.attributes?.['制造商型号'] ?? '',
                lcsc: c?.attributes?.['Supplier Part'] ?? c?.attributes?.['LCSC Part'] ?? c?.attributes?.['立创编号'] ?? '',
            };
        }
        grouped[key].designators.push(c?.designator ?? c?.name ?? '?');
    }

    const rows = [headers.join(',')];
    for (const g of Object.values(grouped)) {
        rows.push([
            JSON.stringify(g.designators.join(';')),
            JSON.stringify(g.name),
            JSON.stringify(g.footprint),
            JSON.stringify(g.value),
            JSON.stringify(g.manufacturer),
            JSON.stringify(g.partNumber),
            JSON.stringify(g.lcsc),
            g.designators.length,
        ].join(','));
    }
    const csv = rows.join('\n');
    log('BOM CSV:\n' + csv);

    try { await navigator.clipboard.writeText(csv); } catch {}

    // 同时尝试用 SYS_FileSystem 触发下载
    try {
        const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
        await eda.sys_FileSystem?.saveFile?.(blob, `BOM_${Date.now()}.csv`);
    } catch (e) {
        log('saveFile 失败 (独立脚本可能不支持):', e);
    }

    eda.sys_MessageBox?.showInformationMessage?.(
        `共 ${comps.length} 个元件, ${Object.keys(grouped).length} 种型号\nBOM CSV 已复制剪贴板`,
        '嘉立创直连·BOM导出',
        '了解'
    );
    return { comps, csv };
})();
