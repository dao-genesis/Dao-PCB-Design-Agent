#!/usr/bin/env python3
"""_group_worker — 在 pcbnew 内把封装聚成命名分组 (PCB_GROUP)。

stdin JSON: {board, out, groups:[{name, refs:[...]}]}
  · 每组按封装 ref 聚拢成一个 PCB_GROUP, 命名后挂到板上。
stdout JSON: {ok, groups_added, reload_groups:[{name, members}], error}
             (落盘后重载实测组数与各组成员数, 反臆造)
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

    groups = req.get("groups") or []
    if not groups:
        return _err("groups 为空: 无可聚拢的分组")
    try:
        board = pcbnew.LoadBoard(req["board"])
    except Exception as e:                                  # noqa: BLE001
        return _err(f"加载板失败: {e}")

    by_ref = {fp.GetReference(): fp for fp in board.GetFootprints()}
    added = 0
    for spec in groups:
        name = str(spec.get("name") or "").strip()
        refs = spec.get("refs") or []
        if not name:
            return _err("分组缺 name")
        members = [by_ref[r] for r in refs if r in by_ref]
        if not members:
            return _err(f"分组 {name!r} 无命中成员 (refs={refs})")
        g = pcbnew.PCB_GROUP(board)
        g.SetName(name)
        for fp in members:
            g.AddItem(fp)
        board.Add(g)
        added += 1

    try:
        pcbnew.SaveBoard(req["out"], board)
    except Exception as e:                                  # noqa: BLE001
        return _err(f"落盘失败: {e}")

    b2 = pcbnew.LoadBoard(req["out"])
    reload_groups = []
    for gr in b2.Groups():
        reload_groups.append({"name": str(gr.GetName()),
                              "members": len(gr.GetItems())})
    reload_groups.sort(key=lambda d: d["name"])

    print(json.dumps({
        "ok": True,
        "groups_added": added,
        "reload_groups": reload_groups,
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
