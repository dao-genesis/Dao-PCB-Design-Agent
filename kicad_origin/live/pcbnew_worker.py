"""
pcbnew_worker — 常驻 KiCad-python 内的 pcbnew 原生 API 工人 (进程内嫁接)

"溶接 · 嫁接" — 此脚本运行在 **KiCad 自带的 Python** 里 (只有它能 import pcbnew),
以 stdin/stdout 上的逐行 JSON-RPC 长驻服务: 一次加载板, 多次查询/改写, 免去每次
操作都重启进程 + 重新 LoadBoard 的固定开销 —— 提升流畅度/稳定性/效率。

协议 (每行一个 JSON 对象, 响应行带 RPC 前缀以隔离 pcbnew 自身的 C 层 stdout 噪声):
  req : {"id": <int>, "method": <str>, "params": {...}}
  resp: \x01RPC {"id": <int>, "ok": true,  "result": {...}}
        \x01RPC {"id": <int>, "ok": false, "error": "<msg>"}

宿主侧管理器见 live/pcbnew_session.py。本文件只依赖 pcbnew + 标准库,
不 import 本仓任何模块 (保证在裸 KiCad python 下可独立运行)。
"""
import json
import sys
import traceback

# 响应行前缀: pcbnew 的 LoadBoard 等会向 stdout 吐 C 层消息, 用唯一前缀把
# 真正的 RPC 响应与噪声隔开, 宿主只认带前缀的行。
_RPC = "\x01RPC "

try:
    import pcbnew
except Exception as _e:  # noqa: BLE001 — 无 pcbnew 时退出, 宿主判不可用
    sys.stderr.write("pcbnew import failed: %s\n" % _e)
    sys.exit(2)


_STATE = {"board": None, "path": None}


def _to_mm(iu):
    return round(pcbnew.ToMM(iu), 4)


def _board():
    b = _STATE["board"]
    if b is None:
        raise RuntimeError("no board loaded (call 'load' first)")
    return b


def m_ping(_p):
    return {"pong": True}


def m_version(_p):
    return {"version": pcbnew.GetBuildVersion()}


def m_load(p):
    path = p["path"]
    b = pcbnew.LoadBoard(path)
    _STATE["board"] = b
    _STATE["path"] = path
    return m_stats({})


def m_stats(_p):
    b = _board()
    return {
        "path": _STATE["path"],
        "footprints": len(b.GetFootprints()),
        "nets": b.GetNetCount(),
        "tracks": len(b.GetTracks()),
        "vias": sum(1 for t in b.GetTracks()
                    if t.GetClass() == "PCB_VIA"),
        "zones": b.GetAreaCount() if hasattr(b, "GetAreaCount") else 0,
        "layers": b.GetCopperLayerCount(),
    }


def m_bbox(_p):
    b = _board()
    bb = b.GetBoardEdgesBoundingBox()
    return {
        "x_mm": _to_mm(bb.GetX()), "y_mm": _to_mm(bb.GetY()),
        "w_mm": _to_mm(bb.GetWidth()), "h_mm": _to_mm(bb.GetHeight()),
    }


def m_footprints(_p):
    b = _board()
    out = []
    for fp in b.GetFootprints():
        pos = fp.GetPosition()
        out.append({
            "ref": fp.GetReference(),
            "value": fp.GetValue(),
            "x_mm": _to_mm(pos.x), "y_mm": _to_mm(pos.y),
            "rot_deg": round(fp.GetOrientationDegrees(), 2),
            "layer": fp.GetLayerName(),
            "pads": fp.GetPadCount(),
        })
    return {"count": len(out), "footprints": out}


def m_nets(_p):
    b = _board()
    nets = []
    for code, ni in b.GetNetInfo().NetsByNetcode().items():
        nets.append({"code": int(code), "name": ni.GetNetname()})
    return {"count": len(nets), "nets": nets}


def m_connectivity(_p):
    """逆向连通保真用: net → 接入该网的 pad 端点 (ref.padname) 列表。"""
    b = _board()
    groups = {}
    for fp in b.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            net = pad.GetNetname()
            if not net:
                continue
            groups.setdefault(net, []).append(
                "%s.%s" % (ref, pad.GetPadName()))
    return {"net_groups": len(groups),
            "endpoints": sum(len(v) for v in groups.values()),
            "groups": {k: sorted(v) for k, v in groups.items()}}


def m_save(p):
    b = _board()
    out = p["path"]
    b.Save(out)
    return {"saved": out}


def m_eval(p):
    """受限自省: 返回某 pcbnew 类的方法名 (能力面深挖, 只读)。"""
    name = p["symbol"]
    obj = getattr(pcbnew, name, None)
    if obj is None:
        raise RuntimeError("no such pcbnew symbol: %s" % name)
    methods = [m for m in dir(obj) if not m.startswith("__")]
    return {"symbol": name, "method_count": len(methods),
            "methods": sorted(methods)}


_METHODS = {
    "ping": m_ping, "version": m_version, "load": m_load, "stats": m_stats,
    "bbox": m_bbox, "footprints": m_footprints, "nets": m_nets,
    "connectivity": m_connectivity, "save": m_save, "eval": m_eval,
}


def _emit(obj):
    sys.stdout.write(_RPC + json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    # 启动握手, 宿主据此确认工人已活
    _emit({"id": 0, "ok": True,
           "result": {"ready": True, "version": pcbnew.GetBuildVersion()}})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        rid = req.get("id")
        method = req.get("method")
        params = req.get("params") or {}
        if method == "shutdown":
            _emit({"id": rid, "ok": True, "result": {"bye": True}})
            return
        fn = _METHODS.get(method)
        if fn is None:
            resp = {"id": rid, "ok": False,
                    "error": "unknown method: %s" % method}
        else:
            try:
                resp = {"id": rid, "ok": True, "result": fn(params)}
            except Exception as e:  # noqa: BLE001
                resp = {"id": rid, "ok": False,
                        "error": "%s: %s" % (type(e).__name__, e),
                        "trace": traceback.format_exc()[-400:]}
        _emit(resp)


if __name__ == "__main__":
    main()
