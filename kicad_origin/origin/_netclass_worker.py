#!/usr/bin/env python3
"""_netclass_worker — 在 pcbnew 内建网类并按模式绑网 (线宽/间距/过孔参数驱动 DRC+布线)。

stdin JSON: {board, out, classes:[{name,track_mm,clearance_mm,via_dia_mm,via_drill_mm}],
             assignments:[{pattern,class}]}
  · classes: 建/改网类, 仅下发给定字段 (其余继承 Default)。
  · assignments: 按网名(或模式)把网绑到某网类。
stdout JSON: {ok, classes_added, reload_classes:[...], nets:[{net,class,track_mm,
              clearance_mm,via_dia_mm}], error}
              (落盘后重载, 对每条真实网逐一解析其生效网类与实际参数, 反臆造)
"""
import json
import sys


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}))
    return 1


def main():
    try:
        req = json.loads(sys.stdin.read())
    except Exception as e:                                  # noqa: BLE001
        return _err(f"bad json: {e}")
    try:
        import pcbnew
    except Exception as e:                                  # noqa: BLE001
        return _err(f"import pcbnew failed: {e}")
    try:
        board = pcbnew.LoadBoard(req["board"])
    except Exception as e:                                  # noqa: BLE001
        return _err(f"加载板失败: {e}")

    classes = list(req.get("classes") or [])
    assignments = list(req.get("assignments") or [])
    if not classes and not assignments:
        return _err("classes 与 assignments 均空 (无可下发项)")

    mm = pcbnew.FromMM
    ns = board.GetDesignSettings().m_NetSettings
    added = 0
    for c in classes:
        name = c["name"]
        nc = pcbnew.NETCLASS(name)
        if "track_mm" in c:
            nc.SetTrackWidth(mm(float(c["track_mm"])))
        if "clearance_mm" in c:
            nc.SetClearance(mm(float(c["clearance_mm"])))
        if "via_dia_mm" in c:
            nc.SetViaDiameter(mm(float(c["via_dia_mm"])))
        if "via_drill_mm" in c:
            nc.SetViaDrill(mm(float(c["via_drill_mm"])))
        ns.SetNetclass(name, nc)
        added += 1

    for a in assignments:
        ns.SetNetclassPatternAssignment(a["pattern"], a["class"])

    try:
        board.SynchronizeNetsAndNetClasses(False)
    except TypeError:
        board.SynchronizeNetsAndNetClasses()

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    ns2 = b2.GetDesignSettings().m_NetSettings
    reload_classes = sorted(str(k) for k in ns2.GetNetclasses().keys())
    if "Default" not in reload_classes:
        reload_classes = ["Default"] + reload_classes

    nets = []
    ni = b2.GetNetInfo()
    for code in range(b2.GetNetCount()):
        item = ni.GetNetItem(code)
        if item is None:
            continue
        nm = str(item.GetNetname())
        if not nm:
            continue
        eff = ns2.GetEffectiveNetClass(nm)
        nets.append({
            "net": nm,
            "class": str(eff.GetName()),
            "track_mm": round(pcbnew.ToMM(eff.GetTrackWidth()), 4),
            "clearance_mm": round(pcbnew.ToMM(eff.GetClearance()), 4),
            "via_dia_mm": round(pcbnew.ToMM(eff.GetViaDiameter()), 4),
        })

    print(json.dumps({
        "ok": True,
        "classes_added": added,
        "reload_classes": reload_classes,
        "nets": nets,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
