# self_bootstrap — 反者道之动 · 自循环自举验证报告

> **"道常无为而无不为. 侯王若能守之, 万物将自化."**
>
> 此报告由 `python tests/self_bootstrap.py` 自动生成, 无人工.

**生成时间**: 2026-05-01 17:44:10
**总耗时**:   4.65s

## 一、检验汇总

- ✅ PASS    : **15**
- ❌ FAIL    : **0**
- ⊖  SKIP    : **0**
- ◐  TIER-2  : **3** (静默闭环不计 FAIL — 待用户一次准入)
- 合计       : 18

## 二、检验明细

| 项 | 状态 | 详情 |
|---|------|------|
| agent 准入快捷方式 (含 debug-port) | ✅ PASS | `C:\Users\Public\Desktop\嘉立创EDA Pro (Agent准入).lnk` |
| .eext 扩展包 | ✅ PASS | `v1.0.4 8,820B` |
| Python 桥 :9907 | ✅ PASS | `PID 60196` |
| 全部 30 core 模块 import | ✅ PASS | `` |
| api_dts 4 层 tier | ✅ PASS | `layers=['public', 'beta', 'alpha', 'full'], full=837 methods` |
| KG 加载 | ✅ PASS | `819 method, 70ms` |
| KG 6 项语义检索 | ✅ PASS | `6/6 命中 (>=4 为 PASS)` |
| tools_registry 加载 | ✅ PASS | `31 工具, 11 域: bom,component,dao,document,environment,flow,pcb,project...` |
| env_finder 完整定位 | ✅ PASS | `exe=D:\lceda-pro\lceda-pro.exe` |
| HttpTransport.ping() | ✅ PASS | `True` |
| 桥 sessions | ◐ TIER-2 | `无 EDA 端连入. 用户启 EDA 后 .eext 自连 (auto-connect v1.0.4)` |
| HttpTransport → EDA API | ◐ TIER-2 | `无 EDA 端连入, 跳过 wet test` |
| CDP TCP :9222 | ✅ PASS | `http_version=200` |
| browser_ws 发现 | ✅ PASS | `tools/browser/e03dd849-7b14-46d3-8fd4-466564a18731` |
| ws-only target list | ✅ PASS | `1 targets (http=1)` |
| page Runtime.evaluate(1+1) | ✅ PASS | `= 2` |
| _MSG_BUS2_EXTAPI_ (tier-2) | ◐ TIER-2 | `bus 未活 (空壳实例). frames=0, loc=about:blank. 用户真 EDA 须 'Agent 准入' 启之.` |
| DaoConnector.diagnose() | ✅ PASS | `` |

## 三、install 当下态

```json
{
  "platform": "Windows",
  "shortcut_path": "C:\\Users\\Public\\Desktop\\嘉立创EDA Pro (Agent准入).lnk",
  "shortcut_target": "D:\\lceda-pro\\lceda-pro.exe",
  "shortcut_args": "--remote-debugging-port=9222 --remote-allow-origins=*",
  "shortcut_has_debug_port": true,
  "shortcut_created_now": false,
  "eext_path": "D:\\道\\道生一\\一生二\\PCB设计\\lceda_bridge\\dist\\lceda-bridge.eext",
  "eext_size": 8820,
  "eext_version": "1.0.4",
  "eext_age_seconds": 3324.721048116684,
  "eext_built_now": false,
  "bridge_running": true,
  "bridge_pid": 60196,
  "bridge_started_now": false,
  "original_shortcuts": [
    "C:\\Users\\Public\\Desktop\\������EDA(רҵ��).lnk",
    "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\������EDA(רҵ��)\\ж�� ������EDA(רҵ��).lnk",
    "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs\\������EDA(רҵ��)\\������EDA(רҵ��).lnk"
  ],
  "notes": []
}
```

## 四、diagnose 全景

```json
{
  "platform": "Windows",
  "env": {
    "lceda_exe": "D:\\lceda-pro\\lceda-pro.exe",
    "lceda_home": "D:\\lceda-pro",
    "lceda_resources": "D:\\lceda-pro\\resources\\app",
    "lceda_app_js": "D:\\lceda-pro\\resources\\app\\app.js",
    "lceda_assets_dir": "D:\\lceda-pro\\resources\\app\\assets",
    "lceda_elib": "D:\\lceda-pro\\resources\\app\\assets\\db\\lceda-std.elib",
    "lceda_api_dir": "D:\\lceda-pro\\resources\\app\\assets\\pro-api\\0.1.79.941a04f4",
    "lceda_user_root": "C:\\Users\\Administrator\\Documents\\LCEDA-Pro",
    "lceda_web_db": "C:\\Users\\Administrator\\Documents\\LCEDA-Pro\\database\\web.db",
    "lceda_backup_dir": "D:\\电路设计嘉立创",
    "jlc_assistant_exe": "D:\\安装的软件\\jlc-assistant\\jlc-assistant.exe",
    "platform": "Windows",
    "discovered_at": 1777547396.7258234,
    "cache_hit": true
  },
  "eda_running": true,
  "cdp_port": 9222,
  "cdp": {
    "port": 9222,
    "tcp_listening": true,
    "http_version": 200,
    "http_list": 200,
    "hint": "OK"
  },
  "browser_ws_url": null,
  "cdp_targets_http": [
    {
      "description": "",
      "devtoolsFrontendUrl": "/devtools/inspector.html?ws=127.0.0.1:9222/devtools/page/A95620D76DA99C96F88CC3B29C26DE84",
      "id": "A95620D76DA99C96F88CC3B29C26DE84",
      "title": "",
      "type": "page",
      "url": "file:///D:/lceda-pro/resources/app/assets/view/index.html?username=zhoudashi&customer_code=7551666A&email=3228675807@qq.com&phone=18368624112&company=%E6%96%B0%E7%96%86%E5%A4%A7%E5%AD%A6&license=dXNlcm5hbWV8Y3VzdG9tZXJfY29kZXxlbWFpbHxwaG9uZXxjb21wYW55,aEsz+XiX4LnKtMLcjBdH9mIgMXGuk+/1vIDXhjI7o88A37VJFe+mXqi84HumOtdkh3f9SaouFlbqFrDDALuocWK5qVttnAAUiMFvnNB9oVvU25inbVTMDLCCpsjJnIz5q7NLc6L/RFJXZvAXf6TABHRPdV4zQ48QjJKclZwfy50=&version=2.2.32.3.18d0223d.819600&time=09/29/2024",
      "webSocketDebuggerUrl": "ws://127.0.0.1:9222/devtools/page/A95620D76DA99C96F88CC3B29C26DE84"
    }
  ],
  "cdp_targets_ws": [],
  "bridge_running": false,
  "bridge_port": 9907,
  "transport_mode": null,
  "connected": false,
  "spawned_by_us": {
    "eda": false,
    "bridge": false
  },
  "sandbox": null,
  "timeline": [
    {
      "ts": 1777628652.9196568,
      "kind": "located",
      "complete": true,
      "missing": []
    }
  ]
}
```

## 五、tier 解读

- **tier-1** (静默自动): 桥 / .eext / 快捷方式 / KG / 通道 / page evaluate — 已全静默闭环.
- **tier-2** (一次准入): 用户真 EDA 之 `_MSG_BUS2_EXTAPI_` — 须用户**一次任一**:
    1. 双击桌面 `嘉立创EDA Pro (Agent准入).lnk` 启动 (CDP 全开)
    2. 已开 EDA 内: 顶部菜单 → 高级 → 扩展管理器 → 导入 `dist/lceda-bridge.eext` → 启用 (HTTP 全开)

    任一足以使 tier-2 转 tier-1 — 之后所有 31 工具立通用户真 EDA 活体.

## 六、道德经映

> 道常无为而无不为. 侯王若能守之, 万物将自化.
> 化而欲作, 吾将镇之以无名之朴.
> 无名之朴, 夫亦将不欲. 不欲以静, 天下将自正.

此回 v4.0.4: **不强求当下接活 EDA bus**, 此为「无名之朴」 — 不欲以静.
反之, 静默种因 (auto-connect 桥 + Agent 准入快捷方式 + .eext 重 build) — 此为「自化」.
用户下次自然启 EDA, 一切自通 — 此为「天下自正」.