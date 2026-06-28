"""The composable capability/tool registry over the live KiCad board.

Each capability is a small, single-purpose tool — like an IDE edit primitive,
but for a PCB — that the agent composes to satisfy a natural-language intent.
Capabilities fall into four Daoist phases:

* **sense (感)**  read the live board's real state & the user's selection.
* **edit  (行)**  mutate the live board; *every* mutation is wrapped in a native
  ``begin_commit``/``push_commit`` so it is a single **undoable** step the user
  sees on the canvas (Edit ▸ Undo).
* **act   (动)**  fire KiCad's own native commands (fill all zones, DRC, …).
* **verify(验)**  read back / measure to confirm the intent landed.

A capability always returns a JSON-able ``dict`` and never raises across the
boundary, so the panel UI and the agent loop stay alive regardless of board
state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import kipy.board_types as bt

from . import actions, exports, units
from .client import Fusion


@dataclass
class Capability:
    name: str
    group: str
    summary: str
    params: dict[str, str] = field(default_factory=dict)
    fn: Optional[Callable[..., dict]] = None

    def __call__(self, fusion: Fusion, **kw) -> dict:
        assert self.fn is not None
        try:
            return self.fn(fusion, **kw)
        except Exception as e:  # never cross the boundary as an exception
            return {"ok": False, "capability": self.name, "error": f"{type(e).__name__}: {e}"}


REGISTRY: dict[str, Capability] = {}


def capability(name: str, group: str, summary: str, params: Optional[dict] = None):
    def deco(fn: Callable[..., dict]) -> Callable[..., dict]:
        REGISTRY[name] = Capability(name, group, summary, params or {}, fn)
        return fn
    return deco


def catalog() -> list[dict]:
    """Machine-readable description of every tool (for agents / UIs)."""
    return [
        {"name": c.name, "group": c.group, "summary": c.summary, "params": c.params}
        for c in REGISTRY.values()
    ]


def call(fusion: Fusion, name: str, /, **kw) -> dict:
    cap = REGISTRY.get(name)
    if cap is None:
        return {"ok": False, "error": f"未知能力: {name!r}", "available": sorted(REGISTRY)}
    return cap(fusion, **kw)


# ── commit helper ─────────────────────────────────────────────────────
def _commit(board: Any, message: str, mutate: Callable[[], Any]) -> Any:
    """Run ``mutate`` inside one undoable KiCad commit; drop it on failure."""
    cmt = board.begin_commit()
    try:
        result = mutate()
        board.push_commit(cmt, message)
        return result
    except Exception:
        try:
            board.drop_commit(cmt)
        except Exception:
            pass
        raise


# ════════════════════════════════════════════════════════════════════
# sense (感)
# ════════════════════════════════════════════════════════════════════
@capability("sense.summary", "sense", "整体感知：层数/封装/网络/走线/过孔/铺铜/选中项 计数与板框")
def _summary(fusion: Fusion) -> dict:
    b = fusion.board()
    fps, nets = b.get_footprints(), b.get_nets()
    tracks, vias, zones = b.get_tracks(), b.get_vias(), b.get_zones()
    try:
        bbox = b.get_item_bounding_box(fps[0]) if fps else None
    except Exception:
        bbox = None
    return {
        "ok": True,
        "doc": getattr(b, "name", "") or "(unsaved)",
        "copper_layers": b.get_copper_layer_count(),
        "active_layer": units.layer_name(b.get_active_layer()),
        "counts": {
            "footprints": len(fps), "nets": len(nets), "tracks": len(tracks),
            "vias": len(vias), "zones": len(zones), "selection": len(b.get_selection()),
        },
    }


@capability("sense.footprints", "sense", "列出板上所有封装：位号/值/坐标/层/朝向")
def _footprints(fusion: Fusion) -> dict:
    b = fusion.board()
    out = []
    for f in b.get_footprints():
        x, y = units.xy_mm(f.position)
        out.append({
            "ref": f.reference_field.text.value,
            "value": f.value_field.text.value,
            "x_mm": x, "y_mm": y,
            "layer": units.layer_name(f.layer),
            "orientation_deg": round(f.orientation.degrees, 2),
        })
    return {"ok": True, "count": len(out), "footprints": out}


@capability("sense.nets", "sense", "列出所有网络：网络名与网络号")
def _nets(fusion: Fusion) -> dict:
    nets = [{"name": n.name, "code": n.code} for n in fusion.board().get_nets()]
    return {"ok": True, "count": len(nets), "nets": nets}


@capability("sense.tracks", "sense", "列出铜走线：起止坐标/层/线宽/网络")
def _tracks(fusion: Fusion) -> dict:
    b = fusion.board()
    out = []
    for t in b.get_tracks():
        sx, sy = units.xy_mm(t.start)
        ex, ey = units.xy_mm(t.end)
        out.append({"start": [sx, sy], "end": [ex, ey],
                    "layer": units.layer_name(t.layer),
                    "width_mm": units.to_mm(t.width),
                    "net": t.net.name if t.net else ""})
    return {"ok": True, "count": len(out), "tracks": out}


@capability("sense.zones", "sense", "列出铺铜区：层/网络/名称")
def _zones(fusion: Fusion) -> dict:
    out = []
    for z in fusion.board().get_zones():
        try:
            name = z.name
        except Exception:
            name = ""
        out.append({"name": name})
    return {"ok": True, "count": len(out), "zones": out}


@capability("sense.selection", "sense", "感知用户当前在 KiCad 里选中的对象（人机协同的关键）")
def _selection(fusion: Fusion) -> dict:
    b = fusion.board()
    items = b.get_selection()
    out = []
    for it in items:
        entry = {"type": type(it).__name__}
        pos = getattr(it, "position", None)
        if pos is not None:
            entry["x_mm"], entry["y_mm"] = units.xy_mm(pos)
        ref = getattr(it, "reference_field", None)
        if ref is not None:
            entry["ref"] = ref.text.value
        out.append(entry)
    return {"ok": True, "count": len(out), "selection": out}


@capability("sense.layers", "sense", "列出已启用的板层与当前活动层")
def _layers(fusion: Fusion) -> dict:
    b = fusion.board()
    try:
        enabled = [units.layer_name(l) for l in b.get_enabled_layers()]
    except Exception:
        enabled = []
    return {"ok": True, "active": units.layer_name(b.get_active_layer()),
            "copper_layers": b.get_copper_layer_count(), "enabled": enabled}


@capability("sense.vias", "sense", "列出过孔：坐标/外径/钻孔/网络")
def _vias(fusion: Fusion) -> dict:
    out = []
    for v in fusion.board().get_vias():
        x, y = units.xy_mm(v.position)
        entry = {"x_mm": x, "y_mm": y, "net": v.net.name if v.net else ""}
        try:
            entry["diameter_mm"] = units.to_mm(v.diameter)
            entry["drill_mm"] = units.to_mm(v.drill_diameter)
        except Exception:
            pass
        out.append(entry)
    return {"ok": True, "count": len(out), "vias": out}


@capability("sense.netclasses", "sense", "列出工程里的网络类，以及每个网络归属哪个类")
def _netclasses(fusion: Fusion) -> dict:
    b = fusion.board()
    try:
        proj = b.get_project()
        classes = [getattr(c, "name", str(c)) for c in proj.get_net_classes()]
    except Exception as e:
        return {"ok": False, "reason": f"无法读取网络类: {e}"}
    mapping: dict[str, str] = {}
    try:
        nets = [n for n in b.get_nets() if n.name]
        if nets:
            for net_name, nc in b.get_netclass_for_nets(nets).items():
                mapping[net_name] = getattr(nc, "name", str(nc))
    except Exception:
        pass
    return {"ok": True, "count": len(classes), "netclasses": classes,
            "net_to_class": mapping}


@capability("sense.board_size", "sense", "测量板框尺寸（Edge.Cuts 包围盒，mm）")
def _board_size(fusion: Fusion) -> dict:
    b = fusion.board()
    edge = units.layer_id("Edge.Cuts")
    xs: list[float] = []
    ys: list[float] = []
    try:
        shapes = b.get_shapes()
    except Exception:
        shapes = []
    for s in shapes:
        if getattr(s, "layer", None) != edge:
            continue
        try:
            bb = b.get_item_bounding_box(s)
        except Exception:
            bb = None
        if bb is None:
            continue
        x0, y0 = units.xy_mm(bb.pos)
        xs += [x0, x0 + units.to_mm(bb.size.x)]
        ys += [y0, y0 + units.to_mm(bb.size.y)]
    if not xs:
        return {"ok": True, "has_outline": False,
                "reason": "板上还没有 Edge.Cuts 板框"}
    w = round(max(xs) - min(xs), 3)
    h = round(max(ys) - min(ys), 3)
    return {"ok": True, "has_outline": True, "width_mm": w, "height_mm": h,
            "area_mm2": round(w * h, 2),
            "origin_mm": [round(min(xs), 3), round(min(ys), 3)]}


def _ref_key(ref: str) -> tuple:
    """Natural sort for refs: R1, R2, …, R10 (not R1, R10, R2)."""
    import re
    m = re.match(r"([A-Za-z]+)(\d+)?", ref or "")
    if not m:
        return (ref or "", 0)
    return (m.group(1), int(m.group(2)) if m.group(2) else 0)


def _bom_lines(board: Any) -> list[dict]:
    """Group the live board's footprints into a BOM (value + footprint -> refs)."""
    groups: dict[tuple, list[str]] = {}
    for f in board.get_footprints():
        ref = f.reference_field.text.value
        val = f.value_field.text.value
        try:
            fid = f.definition.id
            fpname = f"{fid.library_nickname}:{fid.entry_name}"
        except Exception:
            fpname = ""
        groups.setdefault((val, fpname), []).append(ref)
    lines = []
    for (val, fpname), refs in groups.items():
        lines.append({"value": val, "footprint": fpname, "qty": len(refs),
                      "refs": sorted(refs, key=_ref_key)})
    lines.sort(key=lambda d: (-d["qty"], d["value"]))
    return lines


@capability("sense.bom", "sense", "物料清单(BOM)：按 值+封装 归并，给出每种的数量与位号清单")
def _bom(fusion: Fusion) -> dict:
    lines = _bom_lines(fusion.board())
    return {"ok": True, "line_items": len(lines),
            "total_parts": sum(d["qty"] for d in lines), "bom": lines}


# ════════════════════════════════════════════════════════════════════
# edit (行) — every mutation is one undoable commit
# ════════════════════════════════════════════════════════════════════
@capability("edit.add_text", "edit", "在指定层放置文字（可撤销）",
            {"value": "文字内容", "x_mm": "X(mm)", "y_mm": "Y(mm)",
             "layer": "层名(默认F.SilkS)"})
def _add_text(fusion: Fusion, value: str, x_mm: float, y_mm: float,
              layer: str = "F.SilkS") -> dict:
    b = fusion.board()
    t = bt.BoardText()
    t.value = value
    t.position = units.vec_mm(x_mm, y_mm)
    t.layer = units.layer_id(layer)
    created = _commit(b, f"DAO: add text {value!r}", lambda: b.create_items(t))
    return {"ok": bool(created), "added": len(created or [])}


@capability("edit.add_track", "edit", "绘制一段铜走线（可撤销）",
            {"x1_mm": "起点X", "y1_mm": "起点Y", "x2_mm": "终点X", "y2_mm": "终点Y",
             "layer": "层(默认F.Cu)", "width_mm": "线宽(默认0.25)", "net": "网络名(可选)"})
def _add_track(fusion: Fusion, x1_mm: float, y1_mm: float, x2_mm: float, y2_mm: float,
               layer: str = "F.Cu", width_mm: float = 0.25, net: Optional[str] = None) -> dict:
    b = fusion.board()
    t = bt.Track()
    t.start = units.vec_mm(x1_mm, y1_mm)
    t.end = units.vec_mm(x2_mm, y2_mm)
    t.width = units.mm(width_mm)
    t.layer = units.layer_id(layer)
    if net:
        n = _find_net(b, net)
        if n is not None:
            t.net = n
    created = _commit(b, "DAO: add track", lambda: b.create_items(t))
    return {"ok": bool(created), "added": len(created or []),
            "length_mm": round(((x2_mm - x1_mm) ** 2 + (y2_mm - y1_mm) ** 2) ** 0.5, 4)}


@capability("edit.add_via", "edit", "放置一个过孔（可撤销）",
            {"x_mm": "X", "y_mm": "Y", "net": "网络名(可选)",
             "diameter_mm": "过孔外径(默认0.8)", "drill_mm": "钻孔(默认0.4)"})
def _add_via(fusion: Fusion, x_mm: float, y_mm: float, net: Optional[str] = None,
             diameter_mm: float = 0.8, drill_mm: float = 0.4) -> dict:
    b = fusion.board()
    v = bt.Via()
    v.position = units.vec_mm(x_mm, y_mm)
    try:
        v.diameter = units.mm(diameter_mm)
        v.drill_diameter = units.mm(drill_mm)
    except Exception:
        pass
    if net:
        n = _find_net(b, net)
        if n is not None:
            v.net = n
    created = _commit(b, "DAO: add via", lambda: b.create_items(v))
    return {"ok": bool(created), "added": len(created or [])}


@capability("edit.move_selection", "edit", "把当前选中的对象整体平移 dx,dy（可撤销）",
            {"dx_mm": "X位移", "dy_mm": "Y位移"})
def _move_selection(fusion: Fusion, dx_mm: float, dy_mm: float) -> dict:
    b = fusion.board()
    items = b.get_selection()
    if not items:
        return {"ok": False, "reason": "没有选中任何对象（请先在 KiCad 里框选）"}
    dx, dy = units.mm(dx_mm), units.mm(dy_mm)
    for it in items:
        pos = getattr(it, "position", None)
        if pos is not None:
            it.position = units.vec_mm(units.to_mm(pos.x) + dx_mm, units.to_mm(pos.y) + dy_mm)
        elif hasattr(it, "move"):
            it.move(units.vec_mm(dx_mm, dy_mm))
    moved = _commit(b, "DAO: move selection", lambda: b.update_items(items))
    return {"ok": True, "moved": len(moved or items)}


@capability("edit.rotate_selection", "edit", "旋转当前选中的对象（可撤销）",
            {"degrees": "旋转角度（度）"})
def _rotate_selection(fusion: Fusion, degrees: float) -> dict:
    b = fusion.board()
    items = b.get_selection()
    if not items:
        return {"ok": False, "reason": "没有选中任何对象"}
    for it in items:
        if hasattr(it, "orientation"):
            try:
                it.orientation = units.angle_deg(it.orientation.degrees + degrees)
                continue
            except Exception:
                pass
        if hasattr(it, "rotate"):
            center = getattr(it, "position", units.vec_mm(0, 0))
            it.rotate(center, units.angle_deg(degrees))
    rotated = _commit(b, "DAO: rotate selection", lambda: b.update_items(items))
    return {"ok": True, "rotated": len(rotated or items)}


@capability("edit.delete_selection", "edit", "删除当前选中的对象（可撤销）")
def _delete_selection(fusion: Fusion) -> dict:
    b = fusion.board()
    items = b.get_selection()
    if not items:
        return {"ok": False, "reason": "没有选中任何对象"}
    _commit(b, "DAO: delete selection", lambda: b.remove_items(items))
    return {"ok": True, "deleted": len(items)}


@capability("edit.assign_net", "edit", "把当前选中的走线/过孔赋到某个已有网络（可撤销）",
            {"net": "网络名（须为板上已存在的网络）"})
def _assign_net(fusion: Fusion, net: str) -> dict:
    b = fusion.board()
    items = b.get_selection()
    if not items:
        return {"ok": False, "reason": "没有选中任何对象（请先在 KiCad 里框选走线/过孔）"}
    n = _find_net(b, net)
    if n is None:
        return {"ok": False, "reason": f"板上没有名为 {net!r} 的网络",
                "available": [x.name for x in b.get_nets() if x.name]}
    targets = [it for it in items if hasattr(it, "net")]
    if not targets:
        return {"ok": False, "reason": "选中的对象都不能赋网（仅走线/过孔/焊盘可赋网）"}
    for it in targets:
        it.net = n
    updated = _commit(b, f"DAO: assign net {net}", lambda: b.update_items(targets))
    return {"ok": True, "assigned": len(updated or targets), "net": net}


@capability("edit.set_track_width", "edit", "把当前选中的走线改成指定线宽（可撤销）",
            {"width_mm": "线宽(mm)"})
def _set_track_width(fusion: Fusion, width_mm: float) -> dict:
    b = fusion.board()
    items = [it for it in b.get_selection() if type(it).__name__ == "Track"]
    if not items:
        return {"ok": False, "reason": "没有选中任何走线"}
    w = units.mm(width_mm)
    for t in items:
        t.width = w
    updated = _commit(b, f"DAO: set track width {width_mm}mm",
                      lambda: b.update_items(items))
    return {"ok": True, "updated": len(updated or items), "width_mm": width_mm}


@capability("edit.set_active_layer", "edit", "切换当前活动层", {"layer": "层名"})
def _set_active_layer(fusion: Fusion, layer: str) -> dict:
    b = fusion.board()
    b.set_active_layer(units.layer_id(layer))
    return {"ok": True, "active": units.layer_name(b.get_active_layer())}


@capability("edit.add_board_outline", "edit", "在 Edge.Cuts 画一个矩形板框（可撤销）",
            {"x_mm": "左下角X", "y_mm": "左下角Y", "w_mm": "宽", "h_mm": "高"})
def _add_outline(fusion: Fusion, x_mm: float, y_mm: float, w_mm: float, h_mm: float) -> dict:
    b = fusion.board()
    pts = [(x_mm, y_mm), (x_mm + w_mm, y_mm), (x_mm + w_mm, y_mm + h_mm), (x_mm, y_mm + h_mm)]
    edge = units.layer_id("Edge.Cuts")
    segs = []
    for i in range(4):
        s = bt.BoardSegment()
        s.start = units.vec_mm(*pts[i])
        s.end = units.vec_mm(*pts[(i + 1) % 4])
        s.layer = edge
        segs.append(s)
    created = _commit(b, "DAO: board outline", lambda: b.create_items(segs))
    return {"ok": bool(created), "segments": len(created or [])}


@capability("edit.add_zone", "edit", "在指定铜层放置矩形铺铜区并可选灌注（可撤销）",
            {"x_mm": "左下角X", "y_mm": "左下角Y", "w_mm": "宽", "h_mm": "高",
             "layer": "铜层(默认F.Cu)", "net": "网络名(可选)", "name": "区名(默认GND)",
             "fill": "是否立即灌注(默认True)"})
def _add_zone(fusion: Fusion, x_mm: float, y_mm: float, w_mm: float, h_mm: float,
              layer: str = "F.Cu", net: Optional[str] = None, name: str = "GND",
              fill: bool = True) -> dict:
    b = fusion.board()
    z = bt.Zone()
    poly = z._proto.outline.polygons.add()
    for (px, py) in [(x_mm, y_mm), (x_mm + w_mm, y_mm), (x_mm + w_mm, y_mm + h_mm), (x_mm, y_mm + h_mm)]:
        node = poly.outline.nodes.add()
        node.point.x_nm = units.mm(px)
        node.point.y_nm = units.mm(py)
    z._proto.layers.append(units.layer_id(layer))
    z.name = name
    if net:
        n = _find_net(b, net)
        if n is not None:
            z.net = n
    created = _commit(b, f"DAO: zone {name}", lambda: b.create_items(z))
    if fill:
        b.refill_zones()
    zones = b.get_zones()
    filled = bool(zones and zones[-1].filled)
    return {"ok": bool(created), "zones": len(zones), "filled": filled}


@capability("edit.clear_board", "edit", "清空板上所有封装/走线/过孔/铺铜/图形（可撤销）")
def _clear_board(fusion: Fusion) -> dict:
    b = fusion.board()
    items = []
    for getter in (b.get_footprints, b.get_tracks, b.get_vias, b.get_zones,
                   b.get_shapes, b.get_text):
        try:
            items.extend(getter())
        except Exception:
            pass
    if not items:
        return {"ok": True, "removed": 0}
    _commit(b, "DAO: clear board", lambda: b.remove_items(items))
    return {"ok": True, "removed": len(items)}


# ════════════════════════════════════════════════════════════════════
# verify (验) — measure the live board with KiCad's own DRC engine
# ════════════════════════════════════════════════════════════════════
@capability("verify.drc", "verify", "用 kicad-cli 在当前板上跑无头 DRC，返回违例 JSON")
def _verify_drc(fusion: Fusion) -> dict:
    import json
    import subprocess
    import tempfile
    from pathlib import Path

    from .. import env as _env

    b = fusion.board()
    tmp = Path(tempfile.mkdtemp(prefix="dao_drc_"))
    pcb = tmp / "live.kicad_pcb"
    try:
        b.save_as(str(pcb))
    except Exception as e:
        return {"ok": False, "reason": f"无法导出当前板: {e}"}
    cli = _env.detect().cli
    if not cli:
        return {"ok": False, "reason": "未找到 kicad-cli"}
    report = tmp / "drc.json"
    try:
        subprocess.run([str(cli), "pcb", "drc", "--format", "json", "--output", str(report),
                        "--exit-code-violations", str(pcb)],
                       capture_output=True, text=True, timeout=120)
    except Exception as e:
        return {"ok": False, "reason": f"kicad-cli 运行失败: {e}"}
    if not report.is_file():
        return {"ok": False, "reason": "DRC 报告未生成"}
    data = json.loads(report.read_text(encoding="utf-8"))
    viol = data.get("violations", [])
    unconnected = data.get("unconnected_items", [])
    return {"ok": True, "violations": len(viol), "unconnected": len(unconnected),
            "clean": (len(viol) == 0 and len(unconnected) == 0),
            "detail": [v.get("description", "") for v in viol[:10]]}


# ════════════════════════════════════════════════════════════════════
# act (动) — drive KiCad's own native commands
# ════════════════════════════════════════════════════════════════════
@capability("act.fill_zones", "act", "调用 KiCad 原生「全部铺铜灌注」并刷新连通性")
def _fill_zones(fusion: Fusion) -> dict:
    b = fusion.board()
    b.refill_zones()
    actions.run(fusion.kicad, "fill_all_zones")
    return {"ok": True, "zones": len(b.get_zones())}


@capability("act.zoom_fit", "act", "让 KiCad 缩放到适配整板（便于用户观察）")
def _zoom_fit(fusion: Fusion) -> dict:
    return actions.run(fusion.kicad, "zoom_fit")


@capability("act.run_drc", "act", "在 KiCad 内运行原生 DRC（弹出 DRC 面板）")
def _run_drc(fusion: Fusion) -> dict:
    return actions.run(fusion.kicad, "run_drc")


@capability("act.unfill_zones", "act", "调用 KiCad 原生「取消全部铺铜灌注」")
def _unfill_zones(fusion: Fusion) -> dict:
    return actions.run(fusion.kicad, "unfill_all_zones")


@capability("act.select_all", "act", "在 KiCad 里全选当前板上的对象")
def _select_all(fusion: Fusion) -> dict:
    return actions.run(fusion.kicad, "select_all")


@capability("act.deselect_all", "act", "在 KiCad 里取消全部选中")
def _deselect_all(fusion: Fusion) -> dict:
    return actions.run(fusion.kicad, "deselect_all")


@capability("act.redraw", "act", "强制 KiCad 重绘画布（让最新改动立即可见）")
def _redraw(fusion: Fusion) -> dict:
    return actions.run(fusion.kicad, "zoom_redraw")


@capability("act.autoroute", "act",
            "把当前(已布局)板存盘→freerouting 自动布线→把走线/过孔作为一次可撤销提交回填到实时板",
            {"passes": "freerouting 优化遍数(默认10)", "timeout": "布线秒数预算(可选)"})
def _autoroute(fusion: Fusion, passes: int = 10, timeout: Optional[int] = None) -> dict:
    import tempfile
    from pathlib import Path as _P

    from .. import live as _live

    b = fusion.board()
    lk = _live.LiveKiCad()
    if not lk.routing_available():
        return {"ok": False, "reason": "freerouting 未就绪（需 Java + freerouting.jar）"}
    tmp = _P(tempfile.mkdtemp(prefix="dao_route_"))
    src, out = tmp / "in.kicad_pcb", tmp / "routed.kicad_pcb"
    try:
        b.save_as(str(src))
    except Exception as e:
        return {"ok": False, "reason": f"无法导出当前板: {e}"}
    rr = lk.autoroute(src, out, passes=passes, timeout=timeout)
    if not rr.get("ok"):
        return {"ok": False, "stage": rr.get("stage"), "detail": rr}
    tk = lk.read_tracks(out)
    if not tk.get("ok"):
        return {"ok": False, "stage": "read_tracks", "detail": tk}
    reflected = _reflect_tracks(b, tk.get("items", []))
    return {"ok": True, "routed_tracks": rr.get("tracks"),
            "reflected": reflected, "items": tk.get("count")}


def _bind_net(board: Any, item: Any, net_name: Optional[str]) -> None:
    if not net_name:
        return
    n = _find_net(board, net_name)
    if n is not None:
        try:
            item.net = n
        except Exception:
            pass


def _reflect_tracks(board: Any, items: list[dict]) -> int:
    """Replace the live board's copper tracks/vias with a routed set, as one
    undoable commit. Net is bound by name — the routed board was saved from this
    very board, so the names line up."""
    old = list(board.get_tracks()) + list(board.get_vias())
    new: list[Any] = []
    for it in items:
        if it.get("kind") == "via":
            v = bt.Via()
            v.position = units.vec_nm(it["x"], it["y"])
            try:
                v.diameter = int(it["dia"])
                v.drill_diameter = int(it["drill"])
            except Exception:
                pass
            _bind_net(board, v, it.get("net"))
            new.append(v)
        else:
            t = bt.Track()
            t.start = units.vec_nm(it["x1"], it["y1"])
            t.end = units.vec_nm(it["x2"], it["y2"])
            t.width = int(it["width"])
            try:
                t.layer = units.layer_id(it["layer"])
            except Exception:
                t.layer = units.layer_id("F.Cu")
            _bind_net(board, t, it.get("net"))
            new.append(t)

    def mutate():
        if old:
            board.remove_items(old)
        return board.create_items(new)

    created = _commit(board, "DAO: autoroute reflect", mutate)
    return len(created or new)


# ════════════════════════════════════════════════════════════════════
# export (器) — turn the live board into real fabrication deliverables
# ════════════════════════════════════════════════════════════════════
@capability("export.fab", "export",
            "把当前板导出整套制造文件（Gerber+钻孔+贴片+STEP+SVG）到目录",
            {"out_dir": "输出目录（默认 ~/.dao_kicad_live/fab）"})
def _export_fab(fusion: Fusion, out_dir: Optional[str] = None) -> dict:
    return exports.export(fusion, ["gerbers", "drill", "pos", "step", "svg"],
                          out_dir or _default_out("fab"))


@capability("export.gerbers", "export", "导出 Gerber + Excellon 钻孔到目录",
            {"out_dir": "输出目录"})
def _export_gerbers(fusion: Fusion, out_dir: Optional[str] = None) -> dict:
    return exports.export(fusion, ["gerbers", "drill"], out_dir or _default_out("gerber"))


@capability("export.step", "export", "导出 STEP 3D 模型", {"out_dir": "输出目录"})
def _export_step(fusion: Fusion, out_dir: Optional[str] = None) -> dict:
    return exports.export(fusion, ["step"], out_dir or _default_out("step"))


@capability("export.pos", "export", "导出贴片坐标 (placement)", {"out_dir": "输出目录"})
def _export_pos(fusion: Fusion, out_dir: Optional[str] = None) -> dict:
    return exports.export(fusion, ["pos"], out_dir or _default_out("pos"))


@capability("export.snapshot", "export", "渲染当前板的一张 SVG 快照（供实时预览）",
            {"dest": "目标 svg 路径"})
def _export_snapshot(fusion: Fusion, dest: Optional[str] = None) -> dict:
    return exports.snapshot_svg(fusion, dest or (_default_out("") + "/live.svg"))


@capability("export.bom", "export", "导出物料清单(BOM)为 CSV（按 值+封装 归并）",
            {"dest": "目标 csv 路径（默认 ~/.dao_kicad_live/bom/bom.csv）"})
def _export_bom(fusion: Fusion, dest: Optional[str] = None) -> dict:
    import csv
    from pathlib import Path

    lines = _bom_lines(fusion.board())
    target = Path(dest or (_default_out("bom") + "/bom.csv"))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Item", "Qty", "Value", "Footprint", "References"])
        for i, ln in enumerate(lines, 1):
            w.writerow([i, ln["qty"], ln["value"], ln["footprint"], " ".join(ln["refs"])])
    return {"ok": target.is_file(), "csv": str(target), "line_items": len(lines),
            "total_parts": sum(d["qty"] for d in lines)}


# ── helpers ───────────────────────────────────────────────────────────
def _default_out(leaf: str) -> str:
    from pathlib import Path
    base = Path.home() / ".dao_kicad_live"
    p = base / leaf if leaf else base
    p.mkdir(parents=True, exist_ok=True)
    return str(p)



def _find_net(board: Any, name: str) -> Optional[Any]:
    for n in board.get_nets():
        if n.name == name:
            return n
    return None
