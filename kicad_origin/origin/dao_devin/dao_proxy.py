"""dao_proxy — 外接第三方模型路由 (提炼自 devin-remote/core/dao-proxy-pro)。

dao-proxy-pro 本体是一个常驻本地 HTTP 网关 (端口由包名 FNV 定, pro=8937), 对外提供
OpenAI/Anthropic 兼容面, 把 Agent 的 LLM 请求路由到用户自配的第三方渠道, 并做底层
帛书 System Prompt 注入/隔离。在 KiCad 半原生 Devin Desktop 里, 我们无需照搬整座
网关 —— L1 只需要它的**数据面与选路策略**:

  * 渠道预设 (国内外主流 30 家, base URL + 协议 + 注册页), 提炼自 extension.js _PRESETS。
  * 渠道配置落盘 (base URL / key / model), 与账号池同域 ~/.dao, 明文 key 不入仓库。
  * 选路: 按活动渠道解析出 {base_url, protocol, api_key, model} 供上层驱动。

「填 Key → 自动 /v1/models 全量识别」的能力保留为可选联网探测 (probe_models), 与
dao-proxy-pro v9.9.311 同义 (无为而无不为: 用户只需选渠道+填 Key)。

反臆造: 预设 base URL / 注册页逐条照搬源 _PRESETS (extension.js:5258-5291), 不臆造。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import devin_cloud as dc


# ── 渠道预设 (提炼自 dao-proxy-pro extension.js:5258-5291 _PRESETS) ──────────
# n=名, t=协议(openai|anthropic), u=Base URL, r=注册/官网(去拿 API Key)
PRESETS: List[Dict[str, str]] = [
    # 测试/聚合
    {"n": "FreeModel(CC)", "t": "anthropic", "u": "https://cc.freemodel.dev", "r": "https://cc.freemodel.dev"},
    {"n": "OpenRouter (聚合)", "t": "openai", "u": "https://openrouter.ai/api/v1", "r": "https://openrouter.ai/keys"},
    {"n": "AiHubMix (聚合)", "t": "openai", "u": "https://aihubmix.com/v1", "r": "https://aihubmix.com/token"},
    # 国内主流
    {"n": "DeepSeek 深度求索", "t": "openai", "u": "https://api.deepseek.com/v1", "r": "https://platform.deepseek.com/api_keys"},
    {"n": "小米 MiMo (Xiaomi)", "t": "openai", "u": "https://api.xiaomimimo.com/v1", "r": "https://platform.xiaomimimo.com"},
    {"n": "智谱 GLM (Zhipu)", "t": "openai", "u": "https://open.bigmodel.cn/api/paas/v4", "r": "https://open.bigmodel.cn/usercenter/apikeys"},
    {"n": "Kimi 月之暗面 (Moonshot)", "t": "openai", "u": "https://api.moonshot.cn/v1", "r": "https://platform.moonshot.cn/console/api-keys"},
    {"n": "阿里云百炼 通义千问 (Bailian)", "t": "openai", "u": "https://dashscope.aliyuncs.com/compatible-mode/v1", "r": "https://bailian.console.aliyun.com/?apiKey=1"},
    {"n": "字节 豆包 火山方舟 (Doubao/Ark)", "t": "openai", "u": "https://ark.cn-beijing.volces.com/api/v3", "r": "https://console.volcengine.com/ark"},
    {"n": "腾讯 混元 (Hunyuan)", "t": "openai", "u": "https://api.hunyuan.cloud.tencent.com/v1", "r": "https://console.cloud.tencent.com/hunyuan/api-key"},
    {"n": "百度 文心千帆 (Qianfan)", "t": "openai", "u": "https://qianfan.baidubce.com/v2", "r": "https://console.bce.baidu.com/iam/#/iam/apikey/list"},
    {"n": "硅基流动 (SiliconFlow)", "t": "openai", "u": "https://api.siliconflow.cn/v1", "r": "https://cloud.siliconflow.cn/account/ak"},
    {"n": "魔搭 ModelScope", "t": "openai", "u": "https://api-inference.modelscope.cn/v1", "r": "https://modelscope.cn/my/myaccesstoken"},
    {"n": "MiniMax 稀宇", "t": "openai", "u": "https://api.minimaxi.com/v1", "r": "https://platform.minimaxi.com/user-center/basic-information/interface-key"},
    {"n": "讯飞星火 (iFlytek Spark)", "t": "openai", "u": "https://spark-api-open.xf-yun.com/v1", "r": "https://console.xfyun.cn/services/cbm"},
    {"n": "阶跃星辰 (StepFun)", "t": "openai", "u": "https://api.stepfun.com/v1", "r": "https://platform.stepfun.com/interface-key"},
    {"n": "零一万物 (01.AI Yi)", "t": "openai", "u": "https://api.lingyiwanwu.com/v1", "r": "https://platform.lingyiwanwu.com/apikeys"},
    {"n": "百川 (Baichuan)", "t": "openai", "u": "https://api.baichuan-ai.com/v1", "r": "https://platform.baichuan-ai.com/console/apikey"},
    # 国际主流
    {"n": "OpenAI", "t": "openai", "u": "https://api.openai.com/v1", "r": "https://platform.openai.com/api-keys"},
    {"n": "Anthropic Claude", "t": "anthropic", "u": "https://api.anthropic.com", "r": "https://console.anthropic.com/settings/keys"},
    {"n": "Google Gemini", "t": "openai", "u": "https://generativelanguage.googleapis.com/v1beta/openai", "r": "https://aistudio.google.com/apikey"},
    {"n": "xAI Grok", "t": "openai", "u": "https://api.x.ai/v1", "r": "https://console.x.ai"},
    {"n": "Groq (极速)", "t": "openai", "u": "https://api.groq.com/openai/v1", "r": "https://console.groq.com/keys"},
    {"n": "Mistral", "t": "openai", "u": "https://api.mistral.ai/v1", "r": "https://console.mistral.ai/api-keys"},
    {"n": "Together AI", "t": "openai", "u": "https://api.together.xyz/v1", "r": "https://api.together.xyz/settings/api-keys"},
    {"n": "Fireworks AI", "t": "openai", "u": "https://api.fireworks.ai/inference/v1", "r": "https://fireworks.ai/account/api-keys"},
    {"n": "Perplexity", "t": "openai", "u": "https://api.perplexity.ai", "r": "https://www.perplexity.ai/settings/api"},
    # 本地
    {"n": "Ollama (本地)", "t": "openai", "u": "http://localhost:11434/v1", "r": "https://ollama.com/download"},
]


def _proxy_path() -> Path:
    return dc._dao_home() / "devin-proxy.json"


@dataclass
class Channel:
    name: str                    # 展示名 (可取自预设 n)
    base_url: str                # OpenAI/Anthropic 兼容 base
    protocol: str = "openai"     # openai | anthropic
    api_key: str = ""            # 仅落用户本机 ~/.dao
    model: str = ""              # 选定模型 UID
    models: List[str] = field(default_factory=list)  # 该渠道全量模型 (probe 得)
    register_url: str = ""       # 去拿 Key 的官网

    def redacted(self) -> Dict[str, Any]:
        d = asdict(self)
        d["api_key"] = "(已设置)" if self.api_key else "(未设置)"
        return d


@dataclass
class ProxyConfig:
    channels: List[Channel] = field(default_factory=list)
    active_name: str = ""

    def find(self, name: str) -> Optional[Channel]:
        for c in self.channels:
            if c.name == name:
                return c
        return None


def load_config() -> ProxyConfig:
    raw = dc.read_json(_proxy_path(), {})
    chans = [Channel(**{k: v for k, v in c.items() if k in Channel.__dataclass_fields__})
             for c in (raw.get("channels") or [])]
    return ProxyConfig(channels=chans, active_name=raw.get("active_name", ""))


def save_config(cfg: ProxyConfig) -> None:
    dc.write_json(_proxy_path(), {
        "channels": [asdict(c) for c in cfg.channels],
        "active_name": cfg.active_name,
    })


def list_presets() -> List[Dict[str, str]]:
    return [dict(p) for p in PRESETS]


def add_channel(name: str, base_url: str = "", protocol: str = "openai",
                api_key: str = "", model: str = "", register_url: str = "",
                from_preset: str = "") -> ProxyConfig:
    """加/改渠道。from_preset 给出预设名时, base_url/protocol/register_url 自预设补全
    (对应 dao-proxy-pro「选渠道→填 Key」两步)。第一个渠道自动成活动渠道。"""
    cfg = load_config()
    if from_preset:
        p = next((x for x in PRESETS if x["n"] == from_preset), None)
        if p:
            base_url = base_url or p["u"]
            protocol = p["t"]
            register_url = register_url or p["r"]
            name = name or p["n"]
    if not name or not base_url:
        raise ValueError("渠道需 name 与 base_url")
    existing = cfg.find(name)
    if existing:
        existing.base_url = base_url or existing.base_url
        existing.protocol = protocol or existing.protocol
        if api_key:
            existing.api_key = api_key
        if model:
            existing.model = model
        if register_url:
            existing.register_url = register_url
    else:
        cfg.channels.append(Channel(name=name, base_url=base_url, protocol=protocol,
                                    api_key=api_key, model=model, register_url=register_url))
    if not cfg.active_name:
        cfg.active_name = name
    save_config(cfg)
    return cfg


def remove_channel(name: str) -> ProxyConfig:
    cfg = load_config()
    cfg.channels = [c for c in cfg.channels if c.name != name]
    if cfg.active_name == name:
        cfg.active_name = cfg.channels[0].name if cfg.channels else ""
    save_config(cfg)
    return cfg


def switch_channel(name: str) -> ProxyConfig:
    cfg = load_config()
    if not cfg.find(name):
        raise ValueError(f"无此渠道: {name}")
    cfg.active_name = name
    save_config(cfg)
    return cfg


def list_channels() -> List[Dict[str, Any]]:
    cfg = load_config()
    out = []
    for c in cfg.channels:
        v = c.redacted()
        v["active"] = c.name == cfg.active_name
        out.append(v)
    return out


def resolve_route(name: Optional[str] = None) -> Dict[str, Any]:
    """选路: 解析出 {base_url, protocol, api_key, model} 供上层驱动。
    name=None 用活动渠道 (对应 dao-proxy-pro 面板③ 模型路由)。"""
    cfg = load_config()
    ch = cfg.find(name) if name else (cfg.find(cfg.active_name) if cfg.active_name else None)
    if not ch:
        return {"ok": False, "error": "无活动渠道 / 未配置"}
    return {"ok": True, "name": ch.name, "base_url": ch.base_url, "protocol": ch.protocol,
            "api_key": ch.api_key, "model": ch.model, "has_key": bool(ch.api_key)}


def chat(messages: List[Dict[str, Any]], name: Optional[str] = None,
         model: str = "", **opts: Any) -> Dict[str, Any]:
    """经活动(或指定)渠道发一次多协议 completion (L2 行动面)。

    选路 (resolve_route) → proxy_adapters 按协议构造/发送/归一。回统一形态
    {ok, content, thinking, tool_calls, finish_reason, usage, protocol, model}。"""
    from . import proxy_adapters as pa
    route = resolve_route(name)
    if not route.get("ok"):
        return route
    prov_cfg = {"baseUrl": route["base_url"], "protocol": route["protocol"],
                "apiKey": route["api_key"], "model": model or route["model"]}
    if not prov_cfg["model"]:
        return {"ok": False, "error": "渠道未选定模型 (先 probe_models 或指定 model)"}
    return pa.chat(prov_cfg, messages, model=prov_cfg["model"], **opts)


def probe_models(name: str) -> Dict[str, Any]:
    """填 Key 后自动 /v1/models 全量识别该渠道模型 (对应 dao-proxy-pro v9.9.311)。
    仅 openai 协议; anthropic 无标准 models 列举端点则跳过。"""
    cfg = load_config()
    ch = cfg.find(name)
    if not ch:
        return {"ok": False, "error": f"无此渠道: {name}"}
    if not ch.api_key:
        return {"ok": False, "error": "未设置 API Key"}
    if ch.protocol != "openai":
        return {"ok": False, "error": f"{ch.protocol} 协议无标准 /v1/models 列举"}
    url = ch.base_url.rstrip("/") + "/models"
    r = dc.json_request("GET", url, {"Authorization": "Bearer " + ch.api_key})
    if r["status"] != 200:
        return {"ok": False, "error": f"/models HTTP {r['status']}"}
    data = r["json"] or {}
    ids = [m.get("id") for m in (data.get("data") or []) if isinstance(m, dict) and m.get("id")]
    ch.models = ids
    if ids and not ch.model:
        ch.model = ids[0]
    save_config(cfg)
    return {"ok": True, "models": ids, "count": len(ids)}
