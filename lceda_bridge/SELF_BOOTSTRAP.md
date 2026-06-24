# SELF_BOOTSTRAP — 反者道之动 · 自循环自举

> **「道常无为而无不为. 侯王若能守之, 万物将自化.
> 化而欲作, 吾将镇之以无名之朴. 不欲以静, 天下将自正.」**
>
> ── v4.0.4 之主旨: **不强求当下接活, 静默种因, 待时自成**.

---

## 零、一行

```bash
python tests/self_bootstrap.py
```

**就这一行**. 用户什么都不做. 内置 30+ 检验项 + 自补 3 处 (桥启/快捷方式建/eext rebuild) + 自报 (events.jsonl + SELF_BOOTSTRAP_REPORT.md). 5 秒内全闭环.

**实证成绩** (v4.0.4, 2026-05-01):

```text
✅ PASS    :  15
❌ FAIL    :   0
⊖  SKIP    :   0
◐  TIER-2  :   3  (待一次用户准入, 非 FAIL)
────────────────
合计       :  18     耗时 4.96s
```

---

## 一、为何需要 self_bootstrap

### 1.1 旧痛点 (v4.0.0 及之前)

每起一次 agent 会话, 需用户手动:

```text
1. 检查 D:\lceda-pro\lceda-pro.exe 在否
2. 启动 EDA
3. 开另一终端: python lceda_bridge_server.py
4. EDA 顶部菜单 LCEDA Bridge → 启动桥接     ← 点
5. 验证 agent 可见 sessions > 0
6. 若无法见, 多半是扩展没导入, 再来:
   EDA → 高级 → 扩展管理器 → 导入 → 启用 → 重启 EDA
7. 重来步骤 1-5
```

**每次 7 步. agent 接入门槛高.**

### 1.2 v4.0.4 之反转 ── 道德经之应

> **「为无为, 事无事. 图难于其易, 为大于其细.
> 天下难事, 必作于易; 天下大事, 必作于细.」**

拆"接入" 为两层 ──

- **tier-1 静默层**: 可纯代码全自动化 (种因)
- **tier-2 一次准入**: 用户**总只做一次**的事 (破初壳)

| 层 | 任务 | 谁做 | 频次 |
| :---: | --- | :---: | :---: |
| tier-1 | 桥 :9907 长驻 | 代码 | 每次自动 |
| tier-1 | .eext v1.0.4 rebuild | 代码 | 源变即动 |
| tier-1 | Agent 准入快捷方式 | 代码 | 一次建好 |
| tier-1 | 通道/KG/全 31 工具验通 | 代码 | 每次自验 |
| **tier-2** | **启 EDA 含 debug port** | 用户 | **一次** (双击 Agent 准入) |
| **tier-2** | **.eext 导入+启用** | 用户 | **一次** (扩展管理器) |

**任一** tier-2 达成即 tier-2 → tier-1. 之后 .eext 的 auto-connect-on-load (v1.0.4 新功能) 自动连桥. **用户下次自然启 EDA, 一切自通.**

---

## 二、三根新柱 (v4.0.4)

### 2.1 `.eext` auto-connect-on-load

`L2_extension/dist/index.js` 尾加:

```javascript
async function autoConnectGracefully() {
    const maxRetries = 6;
    for (let i = 1; i <= maxRetries; i++) {
        if (state.running) return;
        if (await pingBridge()) {
            log(`[auto] 检测到 Python 桥已运行, 自连接 (${i}/${maxRetries})...`);
            await connectAndStart();
            return;
        }
        await new Promise(r => setTimeout(r, 1000 * i));
    }
    log('[auto] 桥未运行 — 静候用户.');
}
setTimeout(() => autoConnectGracefully(), 1500);
```

用户启 EDA 后, 扩展加载 1.5s 延时即自探桥 :9907. 桥在 → 自连; 桥不在 → 静候, 不报错不打扰.

**重建**: `python build_eext.py` → `dist/lceda-bridge.eext` (v1.0.4, 8.6 KB)

### 2.2 Agent 准入快捷方式 (`core/install.py`)

自动在**公共桌面** (`C:\Users\Public\Desktop\`) 建:

```text
嘉立创EDA Pro (Agent准入).lnk

TargetPath : D:\lceda-pro\lceda-pro.exe
Arguments  : --remote-debugging-port=9222 --remote-allow-origins=*
IconLocation: D:\lceda-pro\lceda-pro.exe, 0
Description: 嘉立创EDA Pro (Agent 准入版) — 启 CDP debug 端口, agent 可深接管.
```

**不动**原快捷方式 (并列副本). 用户欲深用 agent 时双击之. 幂等 — 已建者不重建.

### 2.3 `tests/self_bootstrap.py`

一文闭环. 六阶段:

| 阶段 | 用途 | 典型耗时 |
| :---: | --- | :---: |
| **seed** | `install.survey_and_seed()` — 种因 (桥起/lnk 建/eext rebuild) | 3.10s |
| **static** | 30 模块 import + api_dts + KG 819 method + tools_registry 31 + env_finder | 0.60s |
| **bridge** | HttpTransport.ping / 桥 /status (sessions tier-2 闸口) | 0.22s |
| **cdp** | :9222 探/browser_ws/page Runtime.evaluate(1+1)/_MSG_BUS2_EXTAPI_ 探 | 0.07s |
| **diagnose** | DaoConnector.diagnose() 全景 | 0.97s |
| **report** | events.jsonl + SELF_BOOTSTRAP_REPORT.md | <0.1s |

总 ~5s.

---

## 三、闭环全图

```ascii
                    ┌─────────────────────────────────────┐
                    │   python tests/self_bootstrap.py    │
                    │            (一行)                     │
                    └─────────────────┬───────────────────┘
                                      │
                     ┌────────────────┴───────────────┐
                     │                                │
                [自检]                            [自补]
                     │                                │
        ┌────────────┼────────────┐        ┌──────────┼──────────┐
        ▼            ▼            ▼        ▼          ▼          ▼
     env_finder   桥 :9907     :9222     桥启      快捷方式    .eext
     定位 EDA    alive?       alive?    后台       公共桌面    源变重建
        │            │            │        │          │          │
        └────────────┼────────────┘        └──────────┼──────────┘
                     │                                │
                [自验 tier-1]                    [自验 tier-2]
                     │                                │
       ┌─────────────┼─────────────┐       ┌────────┴────────┐
       ▼             ▼             ▼       ▼                 ▼
    30 模块     KG 检索 6/6    CDP 通道   桥 sessions  _MSG_BUS2_EXTAPI_
    import     命中             + eval    连入数       活否
       │             │             │       │                 │
       └─────────────┼─────────────┘       └────────┬────────┘
                     │                              │
                  PASS ✅                      TIER-2 ◐
                     │                              │
                     └──────────────┬───────────────┘
                                    │
                              [自报 落笔]
                                    │
                     ┌──────────────┴───────────────┐
                     ▼                              ▼
           ~/.lceda_dao/events.jsonl    SELF_BOOTSTRAP_REPORT.md
                  (append)                    (覆写)
```

---

## 四、用户下一步 (破 tier-2)

`self_bootstrap.py` 已自建一切 tier-1. 现用户**任一**即破 tier-2:

### 选项 A ── 最简 (推荐): 双击 Agent 准入

```text
桌面 -> 嘉立创EDA Pro (Agent准入).lnk  (自动已建)
  双击之
  ↓
lceda-pro.exe --remote-debugging-port=9222 --remote-allow-origins=*
  ↓
EDA 启动, CDP 全开
  ↓
agent 可通过 CDP 直入 _MSG_BUS2_EXTAPI_ (full 31 工具)
```

⚠️ **注意**: 若用户原 EDA 进程 (无 debug port) 还在跑, Electron **single-instance lock** 会唤醒原实例 (忽略新 args). 用户需**先彻底关闭原 EDA**, 再双击 Agent 准入.

### 选项 B ── EDA 内一次导入 .eext

```text
(用户任意方式启 EDA)
顶部菜单 → 高级 → 扩展管理器 → 导入
  选择: lceda_bridge/dist/lceda-bridge.eext (v1.0.4)
  ↓
已安装列表中勾选:
  ✓ 启用扩展
  ✓ 外部交互 (必须)
  ✓ 顶部显示 (推荐)
  ↓
重启 EDA (一次)
  ↓
.eext v1.0.4 含 auto-connect, 加载后 1.5s 内自探桥并自连
  ↓
桥 /status 显示 sessions=1, agent 可通过 HTTP 直调 eda.*
```

### 选项 C ── 不需活 EDA 之场景

若只用:

- 离线 .eprj/.elib 解析 (`core/eprj.py`, `core/elib.py`)
- API tier 检索 (`core/api_dts.py` 837 methods)
- KG 语义搜索 (`core/knowledge_graph.py` 819 methods)
- 工具 schema 输出 (`core/tools_registry.py` 31 工具)

则 **tier-1 已足用, 无须 tier-2**.

---

## 五、实证成绩 (2026-05-01 SELF_BOOTSTRAP_REPORT.md)

```text
| 项                                   | 状态     | 详情                                           |
|--------------------------------------|----------|------------------------------------------------|
| agent 准入快捷方式 (含 debug-port)    | ✅ PASS  | C:\Users\Public\Desktop\嘉立创EDA Pro (Agent准入).lnk |
| .eext 扩展包                         | ✅ PASS  | v1.0.4 8,820B                                 |
| Python 桥 :9907                      | ✅ PASS  | PID 60196                                     |
| 全部 30 core 模块 import             | ✅ PASS  |                                                |
| api_dts 4 层 tier                    | ✅ PASS  | full=837 methods                              |
| KG 加载                              | ✅ PASS  | 819 method, 106ms                             |
| KG 6 项语义检索                      | ✅ PASS  | 6/6 命中                                       |
| tools_registry 加载                  | ✅ PASS  | 31 工具, 11 域                                 |
| env_finder 完整定位                  | ✅ PASS  | exe=D:\lceda-pro\lceda-pro.exe                |
| HttpTransport.ping()                 | ✅ PASS  | True                                          |
| 桥 sessions                         | ◐ TIER-2 | 无 EDA 端连入                                  |
| HttpTransport → EDA API              | ◐ TIER-2 | 无 EDA 端连入, 跳过 wet                        |
| CDP TCP :9222                        | ✅ PASS  | http_version=200                              |
| browser_ws 发现                     | ✅ PASS  | tools/browser/e03dd849-...                    |
| ws-only target list                  | ✅ PASS  | 1 targets                                     |
| page Runtime.evaluate(1+1)           | ✅ PASS  | = 2                                           |
| _MSG_BUS2_EXTAPI_ (tier-2)           | ◐ TIER-2 | bus 未活 (isolated 空壳). 待 Agent 准入       |
| DaoConnector.diagnose()              | ✅ PASS  |                                                |
```

---

## 六、故障指北

### Q1. self_bootstrap 报 "lceda_exe 找不到"

`env_finder.discover()` 未定位 EDA. 两解:

```bash
# 方法 1: 环境变量显式指
setx LCEDA_HOME "D:\lceda-pro"

# 方法 2: 清缓存重扫
python -m core.env_finder --clear
python -m core.env_finder
```

### Q2. self_bootstrap 报 "桥启动失败"

端口 :9907 可能被占, 或 `lceda_bridge_server.py` 报错. 手动起看日志:

```bash
python lceda_bridge_server.py
```

### Q3. Agent 准入快捷方式**已建**但启 EDA 后 :9222 无活

用户原 EDA 进程仍在跑 (无 debug port), 新启被 single-instance 锁唤醒为旧实例. 关之再双击:

```powershell
Get-Process lceda-pro -EA 0 | Stop-Process -Force
# 然后双击桌面 "嘉立创EDA Pro (Agent准入).lnk"
```

### Q4. .eext 导入后扩展不出现在顶部菜单

EDA → 高级 → 扩展管理器 → 找到 "LCEDA Bridge", 勾选 ✓ **启用** + ✓ **顶部显示** + ✓ **外部交互** (必须).

### Q5. `_MSG_BUS2_EXTAPI_` 仍 undefined

确认**既非** isolated 实例 (PID 60792 之类) **亦非** 空壳页 (about:blank). 做:

```bash
python tests/self_bootstrap.py --json | python -c "import json,sys; d=json.load(sys.stdin); print(d['diagnose']['cdp_targets_http'])"
```

看 target URL. 若为 `about:blank` → 是 isolated 空壳, kill 它:

```powershell
Get-Process lceda-pro | Where-Object { $_.MainWindowTitle -eq '' } | Stop-Process -Force
```

再双击 Agent 准入.

---

## 七、变更清单 (v4.0.4)

```text
新建:
  core/install.py              — Agent 准入 lnk / eext fresh / 桥长驻 之统一 API
  tests/self_bootstrap.py      — 一行六阶段闭环
  SELF_BOOTSTRAP.md            — 本文 (人可读)
  SELF_BOOTSTRAP_REPORT.md     — 自动生成 (每跑一次覆写)

改:
  L2_extension/dist/index.js   v1.0.0 → v1.0.4 (auto-connect-on-load)
  L2_extension/extension.json  version 字段
  core/__init__.py             __version__ = "4.0.4", __all__ 加 'install'
  dist/lceda-bridge.eext       从 8,415B → 8,820B (含 auto-connect)

不动:
  core/* 其他 (sdk/cdp_transport/dao_connector/tools_registry 等)
  tests/smoke_*.py (旧测试仍全绿)
  CLI / MCP / HTTP 协议 (向前兼容)
```

---

## 八、道德经映

```text
一曰  ── "道常无为而无不为. 侯王若能守之, 万物将自化."
         v4.0.4 不强求接活 bus (无为). 而静默种因 (不为).
         用户一触发即化 — 一次准入后 31 工具自通 (无不为).

二曰  ── "化而欲作, 吾将镇之以无名之朴."
         化是 agent 欲深用 eda 活体. 无名之朴是此三柱:
         auto-connect, Agent 准入 lnk, self_bootstrap.
         皆 idempotent 不增烦恼 — 是"无名".

三曰  ── "无名之朴, 夫亦将不欲. 不欲以静, 天下将自正."
         这三柱本身不欲用户关注 (不欲). 静待之 (以静).
         用户下次自然启 EDA, tier-2 自动变 tier-1.
         一切自正.

四曰  ── "图难于其易, 为大于其细; 天下大事, 必作于细."
         原来"让任意 agent 在任意机器接入 EDA"是大事.
         分 tier-1/tier-2 后, tier-1 全细, 自动化. tier-2 一次.
         大事拆作许多细事, 易之以无为. 无难.
```

---

**→ 再跑一次**: `python tests/self_bootstrap.py`
**→ 自动报告**: `SELF_BOOTSTRAP_REPORT.md` (覆写)
**→ 事件追加**: `~/.lceda_dao/events.jsonl`
