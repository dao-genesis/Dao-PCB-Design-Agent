# dao-proxy-pro · vendored 副本

真源: `dao-genesis/windsurf-assistant` → `plugins/dao-proxy-pro`(v9.9.347)。

- 职责: 反代替换官方系统提示词(invert/passthrough/custom) + 外接第三方 API
  (多 Key/多端点加权负载均衡 + 故障转移 + 模型路由/解锁 + 本地 OpenAI/Anthropic 反代端点)。
- 在本仓的角色: PCB 归一交付 = `vscode-dao-pcb`(领域四态/双桥/ACP 并列) **+** 本插件
  (第三方 provider 层)。两插同装互不干扰(道并行而不相悖); `vscode-dao-pcb` 的
  dao/kicad/lceda 模式负责领域提示词与工具, 本插件负责底层模型请求路由到第三方渠道。
- 控制面: `http://127.0.0.1:8937`(VS Code) / `:37808`(Devin Desktop), 全 API 见
  `API_LOCAL_AGENT.md`。配置落盘 `~/.codeium/dao-byok/配.json`。
- 改核心一律改真源(windsurf-assistant)后再 vendor, 勿在此直接改。
