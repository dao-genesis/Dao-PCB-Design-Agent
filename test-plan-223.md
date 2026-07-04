# PR #223 测试计划 — 道之对话面板深化 (Copilot/Augment 式)

环境: 本机 serve-web VS Code (http://localhost:6789, token 文件鉴权), 工作区 = 仓库根;
bridge_server :9940 已连 CDP(29229) 且 JLCEDA 已登录 (aiotvr)。录屏全程。

## T1 上下文 chip 与历史回放 (It should show context chip and replay history)
1. 打开「道之对话」面板(底部面板容器 或 activitybar「嘉立创EDA」侧栏)。
   - 断言: 顶部 chip 显示「当前工程: 已连接 · 无打开工程」或工程名 — 若功能坏则 chip 缺失或恒为「…」。
2. 发送消息「当前工程信息」, 等作业完成。
3. 通过命令面板执行 Developer: Reload Window (或关闭再打开面板)。
   - 断言: 重开后对话流中仍能看到刚才的 user 消息与 bot 作业结果(历史持久化) — 旧版本重开即空。

## T2 斜杠命令目录 (It should list tools on "/")
1. 输入框键入 `/`。
   - 断言: 弹出下拉, 含 14 个工具项(如 `/project.create — 新建并切换到工程…`、`/pcb.drc — 设计规则检查`)。
2. 继续键入 `drc` 过滤 → 仅剩 `/pcb.drc`; Tab 补全后输入框为 `/pcb.drc `。
3. 回车发送 `/project.info`(先补全)。
   - 断言: bot 回复「已直调工具 project.info」且步骤流显示 ✔ project.info。

## T3 内联图像渲染 (It should render canvas.image inline)
前置: 先经对话「建工程」建一个新工程并打开图页(本身覆盖 project.create 流)。
1. 发送「画布截图」。
   - 断言: 作业完成后消息内直接出现画布 <img> 图像(非 base64 文本/非 `[图像]` 而无图) — 旧版只会打印被截断的 base64 字符串。

## T4 清空会话 (It should clear history)
1. 点 chip 右侧「清空会话」。
   - 断言: 对话流清空, 仅剩「(会话已清空)」; Reload Window 后仍为空(globalState 已清)。

## 兼道 (Regression)
- 中间面板 `DAO LCEDA: 打开嘉立创EDA` 仍可整块显示 EDA 画面且可点击(抽查一次)。
