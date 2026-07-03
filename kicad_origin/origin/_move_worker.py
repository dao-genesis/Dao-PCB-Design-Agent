"""_move_worker — 子进程内 import pcbnew, 按 ref 对封装施显式变换 (定位/平移/旋转/翻面), 落盘后重载实测。

与 native_place (按网表 HPWL 自收敛的**自动**布局) 互补: 本 worker 做**显式、确定性**的逐件变换 ——
"把 U1 放到 (x,y) / 平移 dx,dy / 转 deg / 翻到背面"这种人明确知道要怎么摆的操作, 落到本源只是
`FOOTPRINT.SetPosition / SetOrientationDegrees / Flip`。落盘后重载读回各件真实坐标/角度/所在面 (反臆造)。

stdin  JSON: {board, out, moves:[{ref, x, y, dx, dy, rotate_deg, flip}]}
  · x,y 给则**绝对定位**(mm); dx,dy 给则在此基础上**相对平移**(mm)
  · rotate_deg 给则**设为**该绝对角度(度); flip=True 则翻到另一面
stdout JSON: {ok, moved, footprints:[{ref, x_mm, y_mm, orientation_deg, layer, flipped}], error}

反臆造: footprints 各值取自 SaveBoard 后再 LoadBoard 的真实读数。
"""
import json
import os
import sys


def _err(msg):
    print(json.dumps({"ok": False, "error": msg}, ensure_ascii=False))
    sys.exit(0)


def main():
    req = json.loads(sys.stdin.read())
    moves = req.get("moves") or []
    if not moves:
        _err("moves 为空 (拒空做)")
    try:
        import pcbnew
    except Exception as e:  # noqa: BLE001
        _err(f"import pcbnew 失败: {e}")

    if not os.path.exists(req["board"]):
        _err(f"板文件不存在: {req['board']}")

    mm = pcbnew.FromMM
    board = pcbnew.LoadBoard(req["board"])

    # 先校验所有 ref 存在 (反臆造: 缺件即拒, 不静默跳过)
    refs = [str(m.get("ref", "")) for m in moves]
    for ref in refs:
        if not ref:
            _err("move 缺 ref")
        if board.FindFootprintByReference(ref) is None:
            _err(f"板上无此元件 ref (拒): {ref}")

    moved = 0
    for m in moves:
        fp = board.FindFootprintByReference(str(m["ref"]))
        pos = fp.GetPosition()
        x = pos.x if m.get("x") is None else mm(float(m["x"]))
        y = pos.y if m.get("y") is None else mm(float(m["y"]))
        if m.get("dx") is not None:
            x += mm(float(m["dx"]))
        if m.get("dy") is not None:
            y += mm(float(m["dy"]))
        fp.SetPosition(pcbnew.VECTOR2I(x, y))
        if m.get("rotate_deg") is not None:
            fp.SetOrientationDegrees(float(m["rotate_deg"]))
        if m.get("flip"):
            fp.Flip(fp.GetPosition(), False)
        moved += 1

    pcbnew.SaveBoard(req["out"], board)

    rb = pcbnew.LoadBoard(req["out"])
    out = []
    for ref in refs:
        fp = rb.FindFootprintByReference(ref)
        out.append({
            "ref": ref,
            "x_mm": round(pcbnew.ToMM(fp.GetPosition().x), 4),
            "y_mm": round(pcbnew.ToMM(fp.GetPosition().y), 4),
            "orientation_deg": round(fp.GetOrientationDegrees(), 3),
            "layer": rb.GetLayerName(fp.GetLayer()),
            "flipped": bool(fp.IsFlipped()),
        })

    print(json.dumps({"ok": True, "moved": moved, "footprints": out},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
