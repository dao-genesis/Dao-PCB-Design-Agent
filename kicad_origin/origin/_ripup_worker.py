"""_ripup_worker — 子进程内 import pcbnew, 按网/层/类型筛选拆除铜 (走线/弧/过孔/覆铜), 落盘后重载实测。

这是布线迭代的逆原子: 与 native_track/arc/via/zonefill(落铜)相对, 本 worker 受控**拆铜**——
为重布、改网、清层而精确移除既有铜对象, 落盘后重载点数核验真删 (反臆造, 不臆称"已删")。

stdin  JSON: {board, out,
              nets:[..]|null,      # 限定网名; null/[]=任意网
              layers:[..]|null,    # 限定层名; null/[]=任意层
              types:[track,arc,via,zone]|null}  # 限定类型; null/[]=全部四类
stdout JSON: {ok, removed_total, removed:{track,arc,via,zone},
              remaining:{track,arc,via,zone}, error}

反臆造: removed/remaining 均取自 SaveBoard 后再 LoadBoard 的真实点数。
"""
import json
import os
import sys

_KINDS = ("track", "arc", "via", "zone")


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(0)


def _counts(pcbnew, b):
    c = {k: 0 for k in _KINDS}
    for t in b.GetTracks():
        tt = t.Type()
        if tt == pcbnew.PCB_VIA_T:
            c["via"] += 1
        elif tt == pcbnew.PCB_ARC_T:
            c["arc"] += 1
        else:
            c["track"] += 1
    c["zone"] = b.GetZoneCount() if hasattr(b, "GetZoneCount") else len(list(b.Zones()))
    return c


def _kind_of(pcbnew, item, is_zone=False):
    if is_zone:
        return "zone"
    tt = item.Type()
    if tt == pcbnew.PCB_VIA_T:
        return "via"
    if tt == pcbnew.PCB_ARC_T:
        return "arc"
    return "track"


def main():
    req = json.loads(sys.stdin.read())
    try:
        import pcbnew
    except Exception as e:  # noqa: BLE001
        _err(f"import pcbnew 失败: {e}")

    if not os.path.exists(req["board"]):
        _err(f"板文件不存在: {req['board']}")

    nets = set(req.get("nets") or [])
    layers = set(req.get("layers") or [])
    types = set(req.get("types") or _KINDS)
    bad = types - set(_KINDS)
    if bad:
        _err(f"未知类型 (限 track/arc/via/zone): {sorted(bad)}")

    board = pcbnew.LoadBoard(req["board"])

    # 网名校验 (反臆造: 给了不存在的网名就拒, 不静默删 0 个)
    if nets:
        known = {board.GetNetInfo().GetNetItem(i).GetNetname()
                 for i in range(board.GetNetInfo().GetNetCount())}
        miss = nets - known
        if miss:
            _err(f"板上无网名 {sorted(miss)} (反臆造, 拒)")

    def _match(item, is_zone=False):
        if _kind_of(pcbnew, item, is_zone) not in types:
            return False
        if nets and str(item.GetNetname()) not in nets:
            return False
        if layers:
            lname = board.GetLayerName(item.GetLayer())
            if lname not in layers:
                return False
        return True

    removed = {k: 0 for k in _KINDS}
    for t in list(board.GetTracks()):
        if _match(t):
            removed[_kind_of(pcbnew, t)] += 1
            board.Remove(t)
    if "zone" in types:
        for z in list(board.Zones()):
            if _match(z, is_zone=True):
                removed["zone"] += 1
                board.Remove(z)

    pcbnew.SaveBoard(req["out"], board)
    rb = pcbnew.LoadBoard(req["out"])
    remaining = _counts(pcbnew, rb)

    print(json.dumps({
        "ok": True,
        "removed_total": sum(removed.values()),
        "removed": removed,
        "remaining": remaining,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
