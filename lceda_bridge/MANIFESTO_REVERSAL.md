# 反者道之动 — agent-native 接入宣言

> **"曲则全, 枉则直, 洼则盈, 敝则新, 少则得, 多则惑."**
>
> **"反者道之动, 弱者道之用. 天下万物生于有, 有生于无."**

---

## 一、审问 — 我做错了什么

v3.1.0 我立了 9 个 UI 工具 — `click_text` `screenshot` `find` 等. 表面上 "用户可观可感"; 本然上, 是颠倒.

**我给了 agent 一双假眼一双假手**, 让它走人的弯路:

```text
agent (本可直读 V8 Object Graph 的存在)
   │ 假眼 ── screenshot → OCR/视觉 → 像素坐标
   │ 假手 ── click_at(x, y) → CDP Input → DOM 事件 → 业务回调
   │ 假嘴 ── type_text(s) → 60ms/字 → 字符串事件 → input value
   ↓
EDA (V8 runtime, eda.* Object Graph 触手可及)
```

**这是"以其器为大", 不是"道法自然".**

人需要鼠标键盘是因为人的眼-脑-手不能直接接触代码. agent 没有这个限制 — 它本可直接读 `eda.dmt_Project` 对象、直接调 `dmt_Project.openProject(uuid)`. 让 agent 模拟人, 是把强者降为弱者.

---

## 二、反者 — agent-native 之本然

**agent 是什么?** token 流. 输入是 *state-as-text*, 输出是 *intent-as-text*.

**agent 不需要的**: 视觉、坐标、节奏、物理时序、UI 焦点
**agent 真正需要的**: 状态、知识、意图、效果反馈

| 颠倒 (旧) | 反正 (新) |
|---|---|
| screenshot + OCR | **State Mirror** — eda Object Graph 序列化为 JSON |
| find_clickables | **Knowledge Graph** — 837 method 静态图谱 + 语义索引 |
| click_text("打开") | **Intent Resolver** — `{action:"open", target:"my_pcb"}` → method path |
| 等 toast / 轮询 | **Effect Stream** — 状态 diff patch 推到 agent |
| 18 步打开工程 | **Causal Engine** — `target_state` → 引擎自寻路 |
| 26 工具堆砌 | **5 元工具** — `少则得, 多则惑` |
| 试错 + 看返回 | **Reversible Session** — 自动 snapshot, 错则 rollback |

---

## 三、新 6 柱 (六者合一为 DaoFlow)

```text
                    ┌──────────────────────────────┐
                    │          agent (LLM)          │
                    │   想 = {target_state, why}    │
                    └─────────────┬─────────────────┘
                                  │ 一个动词
                    ┌─────────────▼─────────────────┐
                    │     dao.flow (统一入口)        │
                    │  facade · 一行抵 26 工具       │
                    └──┬───────┬───────┬─────┬──────┘
                       │       │       │     │
              ┌────────▼─┐ ┌──▼───┐ ┌─▼──┐ ┌▼─────┐
              │  Mirror  │ │Graph │ │Intnt│ │Effect│
              │  (state) │ │(API) │ │(plan)│ │(flux)│
              └────────┬─┘ └──┬───┘ └─┬──┘ └┬─────┘
                       └──────┴───┬───┴─────┘
                                  │
                       ┌──────────▼──────────┐
                       │  V8 Object Graph    │
                       │  eda.* + DOM + 内存  │
                       └─────────────────────┘
```

**六柱**:

1. **State Mirror (镜)** — `core/state_mirror.py`
   不让 agent 看屏, 让它读全状态 JSON. 一次调用, env + project + documents + selection + viewport 全在.
2. **Knowledge Graph (图)** — `core/knowledge_graph.py`
   837 method 编译为带语义的图: 输入类型 → 方法 → 输出类型. agent 不试错, 直接查图.
3. **Intent Resolver (解)** — `core/intent_resolver.py`
   agent 表达 *想要*, 引擎找 *怎么做*. `{open: "my_pcb"}` → `dmt_Project.openProject(uuid)`.
4. **Causal Engine (脉)** — `core/causal_engine.py`
   目标状态驱动. 给 `target = {project_open: "my_pcb"}`, 引擎读当前 state, 计算最短动作路径.
5. **Effect Stream (流)** — `core/effect_stream.py`
   状态变迁自动 diff 推送. agent 不轮询, 不等 toast, 收到的是结构化的 *what changed*.
6. **Reversible Session (逆)** — `core/reversible.py`
   每次 mutation 自动 snapshot + 走 EDA undo 链, 错则一键回滚.

**5 元工具** (代替 26):

```text
eda.flow.snapshot         # mirror — 全状态读出
eda.flow.search           # graph — 知识图谱查询
eda.flow.intend           # intent — 解析意图为 action
eda.flow.act              # 一步: intend + execute + diff + 返回 patch
eda.flow.subscribe        # effect — 订阅状态流
```

---

## 四、如何兼容 (生而不有, 为而不恃)

**v3.1.0 的 26 工具 + UI Director + Narrator 全部保留**, 仅降级为"末".

- `dao.eda` — Python SDK (老用户继续用)
- `dao.ui_director` — UI 模拟 (确实需要演示给人看时用)
- `dao.flow` — ★ **新本然接口** (agent 默认走这条)

旧不弃, 新立柱. 道并行不悖.

---

## 五、何以测之

```bash
# smoke
python tests\smoke_dao_flow.py     # 六柱 + 5 元工具 静态/湿测

# demo (同一意图, 两种实现对比)
python demos\flow_demo.py
   旧: 18 步 UI 模拟, ~30 秒
   新: 1 个 intent, ~0.5 秒, 不需 UI 焦点
```

---

> **"少则得, 多则惑. 是以圣人抱一为天下式."**
>
> — 至此, 道直连器 v4.0.0: 一柱 (`dao.flow`) 立, 万行可达.
