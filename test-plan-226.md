# PR #226 闭环实测计划 (VS Code 桌面版 · bridge :9940 · aiotvr 已登录)

前置(已完成, 不录): VS Code 1.x 桌面版已装 dao-lceda-0.1.0.vsix; bridge_server :9940 在线; EDA 编辑器页 CDP 29229。

## T1 · 状态栏健康轮询
1. 打开 VS Code(工作区 /home/ubuntu/repos/Dao-PCB-Design-Agent)。
- PASS: 状态栏左侧显示 `嘉立创EDA`(circuit-board 图标, 桥在线态), 而非 `嘉立创EDA(桥断)`。
- 破坏性区分: 旧版无轮询逻辑, 但文本相同 → 追加验证: shell `pkill -f bridge_server`, 等 ≤20s, 状态栏变 `嘉立创EDA(桥断)`; 重启 bridge 后 ≤20s 恢复。旧版永不变化。

## T2 · 工程树节点点击直调 (doc.open)
1. 左侧活动栏/资源管理器展开「嘉立创EDA 工程」视图, 当前工程下点一条「原理图: …」。
- PASS: 出现进度通知「打开文档…」; EDA 中间面板(命令 DAO LCEDA: 打开嘉立创EDA)切到该原理图文档。旧版树节点无 command, 点击无任何反应。

## T3 · 对话面板快捷指令行
1. 打开面板容器「道之对话」。
- PASS: chip 下方出现按钮行 `工程信息 / 画布截图 / DRC / 全链路`(旧版无此行)。
2. 点「工程信息」。
- PASS: 无需手输, 自动作为用户消息发送, 步骤流返回当前工程名(DaoIDE_* 或实际工程)且状态 done。

## T4 · 画布截图命令 (新命令)
1. Ctrl+Shift+P → `DAO LCEDA: 画布截图`。
- PASS: 进度通知「嘉立创EDA 画布截图…」后, 打开标题为「EDA 画布截图」的标签页并渲染出画布位图(可见原理图内容)。旧版无此命令(面板中找不到)。

## T5 · 后端 plan 通道 + verb.call (shell 证据, 不录屏)
已实测通过(留存输出): 直调 editor.version → `3.2.148`; 未知工具 → 400; 2 步 plan(editor.version + verb.call dmt_Project.getAllProjectsUuid) → done。

## 回归 (Regression)
- 中间面板 EDA 整块显示仍可用; 聊天输入 `/` 仍弹工具目录(现 19 项, 含 verb.call / project.open / doc.open / sch.list / editor.version — 旧版 14 项)。
