# Dao-PCB-Design-Agent

> 让 Agent 像 Cursor 写代码一样进入 EDA 底层,代替人类全流程、全模块推进 PCB 设计。
> 道法自然 · 无为而无不为。

一个仓库,**两条并行且互不耦合的演化路线**(鸡犬相闻,老死不相往来):各自独立入口、
各自依赖、互不破坏,可单独演进,也可在数据层串联。

```
                         Dao-PCB-Design-Agent
                                  │
          ┌───────────────────────┴───────────────────────┐
          ▼                                                 ▼
  路线 A · 嘉立创EDA 直连                          路线 B · KiCad / 代码化
  (在线 Web 编辑器, CDP 直驱)                      (本地引擎, 代码生成 PCB)
          │                                                 │
   lceda_bridge/                                  pcb_brain/   (21 DNA 模板 → .kicad_pcb/Gerber/BOM)
     └ cdp_studio/  ← 冷启动底座                  schematic_dao/ (原理图道 → 四件套资料包)
       (CDP 直驱 _EXTAPI_ROOT_ + 登录态固化)       kicad_origin/  (KiCad 本源直连)
```

---

## 路线 A · 嘉立创EDA 直连(在线 Web · CDP)

经 Chrome 远程调试(CDP)在 `pro.lceda.cn/editor` 主页面上下文直接调用官方扩展 API
(挂在 `window._EXTAPI_ROOT_`,91 个命名空间),无需安装扩展/沙箱,执行→反馈→呈现三面归一。

- **冷启动底座**:[`lceda_bridge/cdp_studio/`](./lceda_bridge/cdp_studio/README.md) ——
  全新 VM 一条命令落到"已登录、可直驱"状态:
  ```bash
  python lceda_bridge/cdp_studio/cold_start.py
  ```
  登录态/凭据走加密 secret(`JLC_PHONE` / `JLC_PASSWORD` / `JLC_SESSION_B64`)注入,
  仓库内不存任何明文。后续会话只需手机号+密码即可承接。
- **桥接全景**:[`lceda_bridge/README.md`](./lceda_bridge/README.md)(五层穿透)。

## 路线 B · KiCad / 代码化(本地引擎)

代码即电路:从 DNA 模板/原理图工程一键生成可打样的 PCB 与全套制造资料。

- **PCBBrain**:[`pcb_brain/`](./pcb_brain/) —— 21 个 DNA 模板 → `.kicad_pcb`/Gerber/BOM/iBoM。
  ```python
  from pcb_core import PCB        # 统一门面
  ```
- **原理图道**:[`schematic_dao/`](./schematic_dao/) —— `SchematicProject` → 论文级四件套。
  ```bash
  python -m schematic_dao build <project>
  ```
- **KiCad 本源**:[`kicad_origin/`](./kicad_origin/)。

> 两线可在数据层串联:SchematicProject(论文级)→ DNA(布局级)→ PCB 打样下单。

---

## 仓库导航

| 目录 | 路线 | 说明 |
|---|---|---|
| `lceda_bridge/` | A | 嘉立创EDA 直连 + 冷启动底座(`cdp_studio/`) |
| `pcb_brain/` | B | DNA 模板 + 全闭环流水线(PCB) |
| `schematic_dao/` | B | 原理图道(四件套资料包) |
| `kicad_origin/` | B | KiCad 本源直连 |
| `_JLC_READY/` | 共用 | 23 个成品板模板(嘉立创打样就绪) |
| `实战/` | 共用 | 实战项目(1500W PFC、物流车控制系统等) |
| `docs/` | — | 总体方案与调研(全链路实现方案、线上资源参考) |
| `_local_launchers/` | — | 用户本机桌面启动器(指向本地 `D:\`/`Z:\` 路径,仅本机可用) |

- 架构与资源总览:[`_INDEX.md`](./_INDEX.md)
- Agent 操作手册:[`_AGENT_GUIDE.md`](./_AGENT_GUIDE.md)
- 交接说明:[`HANDOFF.md`](./HANDOFF.md)

## 仓库内入口脚本

- `lceda.cmd` / `lceda.ps1` —— LCEDA Bridge CLI(`lceda <subcmd>`,任意目录可用)。
