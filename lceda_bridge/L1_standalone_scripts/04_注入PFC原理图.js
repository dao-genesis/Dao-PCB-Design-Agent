/* ============================================================
 * 嘉立创EDA 1500W图腾柱无桥PFC → 自动注入元件清单 — Layer 1
 *
 * 用法: 新建/打开一个空原理图 → 高级→运行脚本 → 粘贴运行
 * 效果: 把 23 种 PFC 关键元件以网格方式批量放置 + 编号 + 标注
 *       (作为占位/规划用, 真实符号库匹配仍需手动)
 * ============================================================ */
(async () => {
    const log = (...a) => console.log('[嘉立创直连·PFC注入]', ...a);

    const sch = await eda.dmt_Schematic?.getCurrentSchematicInfo?.();
    if (!sch) {
        eda.sys_MessageBox?.showInformationMessage?.(
            '请先打开/创建一个原理图', '嘉立创直连·PFC注入'
        );
        return;
    }
    log('当前原理图:', sch);

    // ── 1500W 图腾柱无桥 PFC 元件清单 ──
    const BOM = [
        // 输入保护
        { ref: 'F1',     name: 'Fuse',           value: 'T25A/250VAC',   group: '输入保护' },
        { ref: 'MOV1',   name: 'Varistor',       value: '14D471K',       group: '输入保护' },
        { ref: 'NTC1',   name: 'NTC',            value: '5R/15A',        group: '输入保护' },
        { ref: 'K1',     name: 'Relay',          value: '250VAC/25A',    group: '输入保护' },
        // EMI
        { ref: 'Lcm',    name: 'CMChoke',        value: '2x2mH/20A',     group: 'EMI滤波' },
        { ref: 'Cx',     name: 'X-Cap',          value: '0.47uF/275VAC', group: 'EMI滤波' },
        { ref: 'Cy1',    name: 'Y-Cap',          value: '2.2nF/Y1',      group: 'EMI滤波' },
        { ref: 'Cy2',    name: 'Y-Cap',          value: '2.2nF/Y1',      group: 'EMI滤波' },
        // 主功率
        { ref: 'Q1',     name: 'SiC-MOSFET',     value: '650V/40mΩ',     group: '主功率' },
        { ref: 'Q2',     name: 'SiC-MOSFET',     value: '650V/40mΩ',     group: '主功率' },
        { ref: 'Q3',     name: 'MOSFET',         value: '650V/工频',     group: '主功率' },
        { ref: 'Q4',     name: 'MOSFET',         value: '650V/工频',     group: '主功率' },
        { ref: 'L1',     name: 'PFC-Inductor',   value: '450uH/25A',     group: '主功率' },
        { ref: 'Cbus1',  name: 'E-Cap',          value: '470uF/450V',    group: '主功率' },
        { ref: 'Cbus2',  name: 'E-Cap',          value: '470uF/450V',    group: '主功率' },
        { ref: 'Rbleed', name: 'Resistor',       value: '220K/2W',       group: '主功率' },
        { ref: 'CS1',    name: 'CurrentSense',   value: '25A',           group: '主功率' },
        // 驱动+控制
        { ref: 'U1',     name: 'GateDriver',     value: 'UCC21520',      group: '驱动控制' },
        { ref: 'U2',     name: 'GateDriver',     value: 'iso-driver',    group: '驱动控制' },
        { ref: 'U5',     name: 'PFC-Controller', value: 'UCC28070',      group: '驱动控制' },
        { ref: 'U6',     name: 'AuxPower',       value: 'VIPer',         group: '驱动控制' },
        // 采样
        { ref: 'Rv1',    name: 'Resistor',       value: '1M/1206',       group: '采样' },
        { ref: 'NTC_T',  name: 'NTC',            value: '10K/3950',      group: '采样' },
    ];

    // ── 网格布局 ──
    const cols = 5;
    const dx = 30, dy = 25;
    const startX = 50, startY = 50;
    const placed = [];

    // 嘉立创EDA 专业版的原理图坐标单位是 mm.
    // 下面尝试用 sch_PrimitiveText 在画布上插入纯文字标记 (不需要符号库)
    // 真正的元件符号需要通过 sch_PrimitiveComponent 创建, 但需要预先存在符号 UUID.
    let i = 0;
    const groupColors = { '输入保护': '#FFB74D', 'EMI滤波': '#81D4FA', '主功率': '#E57373', '驱动控制': '#A5D6A7', '采样': '#CE93D8' };

    for (const item of BOM) {
        const col = i % cols, row = Math.floor(i / cols);
        const x = startX + col * dx;
        const y = startY + row * dy;
        i++;

        try {
            // 用文本图元放置占位标记 (不依赖符号库)
            const text = `${item.ref}\n${item.name}\n${item.value}`;
            await eda.sch_PrimitiveText?.create?.({
                x, y,
                text,
                fontSize: 1.5,
                color: groupColors[item.group] ?? '#FFFFFF',
            });
            placed.push({ ...item, x, y });
        } catch (e) {
            log(`放置 ${item.ref} 失败:`, e);
        }
    }

    log(`✅ 已放置 ${placed.length}/${BOM.length} 个占位标记`);
    log('placed:', placed);

    // 写入日志面板
    eda.sys_Log?.add?.(`PFC元件占位注入完成: ${placed.length}/${BOM.length}`, 0);

    eda.sys_MessageBox?.showInformationMessage?.(
        `已注入 ${placed.length}/${BOM.length} 个 PFC 元件占位标记到原理图\n\n` +
        `下一步:\n` +
        `  1. 双击每个占位 → 替换为真实符号\n` +
        `  2. 或克隆 oshwhub 3KW SiC PFC 模板:\n     https://oshwhub.com/leichaolin/3kw-totem-pole-pfc-with-silicon-`,
        '嘉立创直连·PFC注入',
        '了解'
    );

    return placed;
})();
