# -*- coding: utf-8 -*-
"""dao_unify — **统一门面**:一张声明式电路单,自动择活通道(桌面离线 29230 / web 在线 29229),
一套 build+export API 通吃两条通道。方向#3(工具调度/匹配哲学)沉淀为**可执行代码**。

道:大制无割。两条通道底层驱动异构——
  - 桌面离线:`dao_rpc_driver.DaoRpc.build_board(spec_dict, router=..)`(freerouting/几何布线)
  - web 在线:`dao_board.BoardBuilder().build(BoardSpec)`(原生自动布线)
且 spec 形态各异(桌面按器件挂 {焊盘:网};web 按网列 [(器件,脚)])。本模块用**单一规范
UnifiedSpec** 收口,两个适配器 `to_desktop()/to_web()` 各自翻译,`Orchestrator.build()`
探活择通道并归一化审计({channel, drc_total, exports}).无为:能用哪条用哪条,写一次跑两处。

用法:
    from dao_unify import UnifiedSpec, Orchestrator
    spec = UnifiedSpec("Demo",
        parts=[("R1","0603 10k",(200,200)), ("R2","0603 10k",(600,200))],
        nets={"A":[("R1","1"),("R2","1")], "GND":[("R1","2"),("R2","2")]})
    print(Orchestrator().build(spec))          # auto:优先 web,回落桌面
    python3 dao_unify.py detect                 # 打印活通道
    python3 dao_unify.py selftest               # 同一 spec 在**所有活通道**各建一板并断言
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DESKTOP_PORT = 29230
WEB_PORT = 29229

# 14 格式为两通道共同真字节谱(桌面另有 session-bound 的 autoroute_json;
# ipc_2581c/idx 两通道皆 NO_RESULT,getManufactureData 仅私有化版——见 HANDOFF)
COMMON_FMT = {"gerber", "bom", "pnp", "pdf", "dxf", "3d_step", "ipc_d356a",
              "odb", "ibom", "altium", "testpoint", "netlist", "pads", "flyprobe"}


def _cdp_editor_alive(port):
    """探 CDP /json 是否有已打开的 editor 页(通道活体判据,零副作用)。"""
    try:
        raw = urllib.request.urlopen("http://127.0.0.1:%d/json" % port, timeout=4).read()
        targets = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return False
    for t in targets or []:
        if t.get("type") == "page" and "editor" in (t.get("url") or ""):
            return True
    return False


def detect_channels():
    """{'desktop': bool, 'web': bool} —— 当前哪条通道活着。"""
    return {"desktop": _cdp_editor_alive(DESKTOP_PORT),
            "web": _cdp_editor_alive(WEB_PORT)}


class UnifiedSpec:
    """单一规范电路单(两通道公约数超集)。

    parts: [(ref, query, (x, y)[, rotation]), ...]  query 为社区检索词或具体料号
    nets:  {net_name: [(ref, pin), ...], ...}
    """

    def __init__(self, name, parts, nets, gnd_net="GND", ground_pour=True,
                 margin=120, track_width=10, copper_layers=None):
        self.name = name
        self.parts = parts
        self.nets = nets
        self.gnd_net = gnd_net
        self.ground_pour = ground_pour
        self.margin = margin
        self.track_width = track_width
        self.copper_layers = copper_layers

    def to_web(self):
        """→ dao_board.BoardSpec(web 原生自动布线通道)。"""
        from dao_board import BoardSpec
        parts = [(p[0], p[1], p[2]) for p in self.parts]
        return BoardSpec(name=self.name, parts=parts, nets=self.nets,
                         ground_pour=self.ground_pour)

    def to_desktop(self):
        """→ dao_rpc_driver 的 spec dict:把 {net:[(ref,pin)]} 反转为器件侧 {焊盘:网}。"""
        pinmap = {}
        for net, members in self.nets.items():
            for ref, pad in members:
                pinmap.setdefault(ref, {})[str(pad)] = net
        comps = []
        for p in self.parts:
            ref, query, (x, y) = p[0], p[1], p[2]
            rot = p[3] if len(p) > 3 else 0
            comps.append({"ref": ref, "query": query, "rotation": rot,
                          "x": x, "y": y, "pins": pinmap.get(ref, {})})
        spec = {"name": self.name, "gnd_net": self.gnd_net,
                "track_width": self.track_width, "margin": self.margin,
                "components": comps, "export_all": True}
        if self.copper_layers:
            spec["copper_layers"] = self.copper_layers
        return spec


def _drc_total(drc):
    if isinstance(drc, list):
        return len(drc)
    if isinstance(drc, dict):
        return drc.get("total", drc.get("count"))
    if isinstance(drc, (int, float)):
        return int(drc)
    return None


def _sizes(exp):
    return {k: (v.get("size") if isinstance(v, dict) and "size" in v else
                (v if isinstance(v, (int, float)) else None))
            for k, v in (exp or {}).items()}


class Orchestrator:
    """探活 → 择通道 → 建板 → 归一化审计。prefer: 'auto'|'web'|'desktop'。"""

    def __init__(self, prefer="auto"):
        self.prefer = prefer
        self.channels = detect_channels()
        self.channel = None

    def _pick(self, channel):
        if channel and channel != "auto":
            if not self.channels.get(channel):
                raise RuntimeError("通道 %s 不可达(detect=%s)" % (channel, self.channels))
            return channel
        order = ([self.prefer] if self.prefer in ("web", "desktop") else []) + ["web", "desktop"]
        for ch in order:
            if self.channels.get(ch):
                return ch
        raise RuntimeError("无活通道:桌面%d/web%d 均不可达" % (DESKTOP_PORT, WEB_PORT))

    def build(self, uspec, channel="auto", **kw):
        """在择定通道上端到端建板,返回 {channel, drc_total, exports:{fmt:size}, elapsed_s}。"""
        ch = self._pick(channel)
        self.channel = ch
        t0 = time.time()
        if ch == "web":
            # 强制 web 端口:eda_flow.Flow() 以 d.CDP_PORT(调用时读取)传给 connect_editor,
            # 故改模块属性即生效(os.environ 在 import 后设置已太晚,不可靠)。
            import dao_eda_cdp_driver
            dao_eda_cdp_driver.CDP_PORT = WEB_PORT
            from dao_board import BoardBuilder
            rep = BoardBuilder().build(uspec.to_web(), margin=uspec.margin)
            re_ = rep.get("route_export", {})
            out = {"drc_total": _drc_total(re_.get("drc")),
                   "exports": _sizes(re_.get("export"))}
        else:
            import dao_rpc_driver
            d = dao_rpc_driver.DaoRpc(port=DESKTOP_PORT)
            audit = d.build_board(uspec.to_desktop(),
                                  router=kw.get("router", "freerouting"),
                                  pour=kw.get("pour", False))
            out = {"drc_total": _drc_total(audit.get("steps", {}).get("drc")),
                   "exports": _sizes(audit.get("exports"))}
        out["channel"] = ch
        out["elapsed_s"] = round(time.time() - t0, 1)
        return out


_DEMO = UnifiedSpec(
    name="DaoUnify_Demo",
    parts=[("R1", "0603 10k", (200, 200)),
           ("R2", "0603 10k", (600, 200)),
           ("R3", "0603 10k", (1000, 200))],
    nets={"NET_A": [("R1", "1"), ("R3", "1")],
          "NET_B": [("R1", "2"), ("R3", "2")],
          "GND": [("R2", "1"), ("R2", "2")]},
    ground_pour=True,
)


def _selftest():
    """同一 UnifiedSpec 在**所有活通道**各建一板,断言每通道 DRC=0 且 12 格式真字节。"""
    chans = detect_channels()
    live = [c for c in ("web", "desktop") if chans[c]]
    print("[DETECT]", json.dumps(chans))
    if not live:
        print("[RESULT] SKIP(无活通道)")
        return 2
    results = {}
    for ch in live:
        try:
            r = Orchestrator().build(_DEMO, channel=ch)
            good = {k for k, v in r["exports"].items() if isinstance(v, (int, float)) and v > 0}
            missing = sorted(COMMON_FMT - good)
            ok = r["drc_total"] == 0 and not missing
            results[ch] = {"ok": ok, "drc": r["drc_total"], "exports": len(good),
                           "elapsed_s": r["elapsed_s"], "missing": missing}
            print("[CHAN %-7s] DRC=%s exports=%d %.0fs%s"
                  % (ch, r["drc_total"], len(good), r["elapsed_s"],
                     "" if not missing else " MISSING=%s" % missing))
        except Exception as ex:
            results[ch] = {"ok": False, "err": str(ex)[:180]}
            print("[CHAN %-7s] EXC %s" % (ch, results[ch]["err"]))
    allok = all(v["ok"] for v in results.values())
    print("[SUMMARY]", json.dumps(results, ensure_ascii=False))
    print("[RESULT]", "PASS" if allok else "FAIL")
    return 0 if allok else 1


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "detect"
    if cmd == "detect":
        print(json.dumps(detect_channels(), ensure_ascii=False))
        return 0
    if cmd == "selftest":
        return _selftest()
    print("用法: python3 dao_unify.py [detect|selftest]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
