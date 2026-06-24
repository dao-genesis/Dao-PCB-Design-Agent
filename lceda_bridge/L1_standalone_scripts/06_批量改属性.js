/* ============================================================
 * 嘉立创EDA 批量改属性 — Layer 1
 *
 * 用法:
 *   1. 打开一个原理图或PCB tab
 *   2. 编辑下方 RULES 配置 (按需改)
 *   3. 高级 → 运行脚本 → 粘贴运行
 *
 * 能力:
 *   - 按 designator 前缀 (如 'R*', 'C*') 批量改属性
 *   - 按当前值替换 (例: Value='10K' → '10k')
 *   - 自动写日志, 干跑模式 (DRY_RUN=true 不实改)
 * ============================================================ */
(async () => {
    const log = (...a) => console.log('[嘉立创直连·改属性]', ...a);

    // ── 配置 ──
    const DRY_RUN = true;  // ← 改 false 才实改
    const RULES = [
        // {designator: 'R*', set: { Value: '10k' }, where: { Value: '10K' }},
        // {designator: 'C*', set: { Manufacturer: 'Murata' }},
    ];
    if (RULES.length === 0) {
        eda.sys_MessageBox?.showInformationMessage?.(
            '请先在脚本顶部编辑 RULES 数组, 加入要改的规则.\n\n' +
            '示例:\n' +
            "  {designator: 'R*', set: {Value: '10k'}, where: {Value: '10K'}}\n",
            '提示·未配置规则'
        );
        return;
    }

    // ── 取元件 ──
    let comps = [];
    try {
        if (await eda.dmt_Pcb?.getCurrentPcbInfo?.()) {
            comps = await eda.pcb_PrimitiveComponent?.getAllPrimitivesAttributes?.() ?? [];
        } else if (await eda.dmt_Schematic?.getCurrentSchematicInfo?.()) {
            comps = await eda.sch_PrimitiveComponent?.getAllPrimitivesAttributes?.() ?? [];
        }
    } catch (e) {
        log('获取元件失败:', e);
        return;
    }
    log(`共 ${comps.length} 个元件`);

    // ── 模式匹配 ──
    const matchDes = (des, pat) => {
        if (!pat || pat === '*') return true;
        if (pat.endsWith('*')) return des?.startsWith(pat.slice(0, -1));
        return des === pat;
    };
    const matchWhere = (c, where) => {
        if (!where) return true;
        return Object.entries(where).every(([k, v]) =>
            (c.attributes?.[k] ?? c[k]) === v
        );
    };

    // ── 应用规则 ──
    const changes = [];
    for (const c of comps) {
        for (const r of RULES) {
            if (!matchDes(c?.designator, r.designator)) continue;
            if (!matchWhere(c, r.where)) continue;
            for (const [k, v] of Object.entries(r.set ?? {})) {
                changes.push({ designator: c.designator, attr: k, from: c.attributes?.[k], to: v, comp: c });
            }
        }
    }

    log(`匹配 ${changes.length} 处改动${DRY_RUN ? ' (DRY RUN, 不实改)' : ''}`);
    for (const ch of changes) {
        log(`  ${ch.designator}.${ch.attr}: ${JSON.stringify(ch.from)} → ${JSON.stringify(ch.to)}`);
    }

    if (DRY_RUN) {
        eda.sys_MessageBox?.showInformationMessage?.(
            `[DRY RUN] ${changes.length} 处改动 (未实改).\n详见 F12 控制台.\n要实改请改 DRY_RUN=false`,
            'BOM 批量改'
        );
        return changes;
    }

    // ── 实改 ──
    let ok = 0, fail = 0;
    for (const ch of changes) {
        try {
            const setter = eda.pcb_PrimitiveComponent?.setAttribute ?? eda.sch_PrimitiveComponent?.setAttribute;
            if (setter) {
                await setter.call(
                    eda.pcb_PrimitiveComponent ?? eda.sch_PrimitiveComponent,
                    ch.comp.uuid, ch.attr, ch.to
                );
                ok++;
            } else {
                fail++;
            }
        } catch (e) {
            log('改失败', ch, e);
            fail++;
        }
    }
    eda.sys_MessageBox?.showInformationMessage?.(
        `成功 ${ok} / 失败 ${fail} / 总 ${changes.length}`,
        'BOM 批量改 完成'
    );
    return { changes, ok, fail };
})();
