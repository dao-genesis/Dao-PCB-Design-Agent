/* ============================================================
 * 嘉立创EDA 环境侦察 — Layer 1 独立脚本
 *
 * 用法:
 *   1. 打开嘉立创EDA专业版, 任意打开一个工程
 *   2. 顶部菜单 → 高级 → 运行脚本 (V3) 或 设置→扩展→独立脚本 (V2)
 *   3. 复制本文件全部内容 → 粘贴 → 运行
 *   4. F12 三次 → 控制台 → 看输出 (并自动复制到剪贴板)
 *
 * 输出: 编辑器版本 / 当前工程 / 当前文档 / 工作区 / 团队 等全维度信息
 * ============================================================ */
(async () => {
    const log = (...args) => console.log('[嘉立创直连·侦察]', ...args);
    const out = { _meta: { ts: new Date().toISOString(), source: 'L1_environment_recon' } };

    try {
        // ── 系统层 ──
        out.editor = {
            version: await eda.sys_Environment.getEditorVersion?.(),
            currentEditor: await eda.sys_Environment.getCurrentEditor?.(),
            language: await eda.sys_I18n?.getCurrentLanguage?.(),
            allLanguages: eda.sys_I18n?.getAllSupportedLanguages?.(),
        };

        // ── 工作区 / 团队 ──
        out.workspace = {
            current: await eda.dmt_Workspace?.getCurrentWorkspaceInfo?.(),
            all: await eda.dmt_Workspace?.getAllWorkspacesInfo?.(),
        };
        out.team = {
            current: await eda.dmt_Team?.getCurrentTeamInfo?.(),
            all: await eda.dmt_Team?.getAllTeamsInfo?.(),
            involved: await eda.dmt_Team?.getAllInvolvedTeamInfo?.(),
        };

        // ── 当前工程 ──
        out.currentProject = await eda.dmt_Project?.getCurrentProjectInfo?.();
        const allUuid = await eda.dmt_Project?.getAllProjectsUuid?.();
        out.allProjectsCount = allUuid?.length ?? 0;
        out.allProjectsUuid = allUuid;

        // ── 当前板/原理图/PCB/面板 ──
        out.currentBoard = await eda.dmt_Board?.getCurrentBoardInfo?.();
        out.allBoards = await eda.dmt_Board?.getAllBoardsInfo?.();
        out.currentSchematic = await eda.dmt_Schematic?.getCurrentSchematicInfo?.();
        out.currentSchematicPage = await eda.dmt_Schematic?.getCurrentSchematicPageInfo?.();
        out.allSchematics = await eda.dmt_Schematic?.getAllSchematicsInfo?.();
        out.currentPcb = await eda.dmt_Pcb?.getCurrentPcbInfo?.();
        out.allPcbs = await eda.dmt_Pcb?.getAllPcbsInfo?.();
        out.currentPanel = await eda.dmt_Panel?.getCurrentPanelInfo?.();

        // ── 当前选择/文档 ──
        out.currentDocument = await eda.dmt_SelectControl?.getCurrentDocumentInfo?.();

        // ── 编辑器分屏 ──
        out.splitScreenTree = await eda.dmt_EditorControl?.getSplitScreenTree?.();

        // ── eda 对象顶层快照 (键名) ──
        out.edaTopKeys = Object.keys(eda).sort();

    } catch (e) {
        out._error = { message: String(e), stack: e?.stack };
    }

    log('完整结果:', out);
    const json = JSON.stringify(out, null, 2);
    log('JSON长度:', json.length, '字符');

    // 自动复制到剪贴板 (浏览器环境)
    try {
        await navigator.clipboard.writeText(json);
        eda.sys_ToastMessage?.showMessage?.('环境侦察完成, JSON已复制剪贴板', 0);
        log('✅ 已复制到剪贴板, 粘贴到 Windsurf 即可');
    } catch (e) {
        log('⚠️ 剪贴板写入失败, 请手动复制控制台输出:', e);
    }

    // 屏幕弹窗
    eda.sys_MessageBox?.showInformationMessage?.(
        `编辑器: ${out.editor?.version ?? '?'}\n当前工程: ${out.currentProject?.friendlyName ?? out.currentProject?.name ?? '(无)'}\n工程数: ${out.allProjectsCount}\n\n详细 JSON 已复制到剪贴板`,
        '嘉立创直连·环境侦察',
        '了解'
    );

    return out;
})();
