"""Live board builder — runs *inside* the running KiCad PCB editor.

This is the native, in-app counterpart of :mod:`daokicad._pcbworker`. Instead of
creating a board in memory and saving a ``.kicad_pcb`` to disk, it mutates the
board the user currently has **open** in pcbnew, calling a refresh hook after
each phase so the copper, footprints and pours appear live on the canvas.

It deliberately reuses the *exact same* geometry helpers as the headless worker
(``_make_footprint``, ``_outline_iu``, ``_add_zone``, ``_stitch_vias``,
``_fill_zones`` …) so a board built live is identical to one built headless —
one engine, two front-ends (道生一).
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Callable, Optional

import pcbnew

from .. import _pcbworker as W
from .. import route

MM = pcbnew.FromMM
Hook = Optional[Callable[[str, dict], None]]


def _noop(phase: str, info: dict) -> None:  # pragma: no cover - default hook
    pass


def _safe_remove(board: pcbnew.BOARD, item) -> None:
    """Remove a board item, tolerating pcbnew's SWIG wrapper glitches.

    ``board.Remove`` calls ``RemoveNative`` (the real C++ removal) and then sets
    ``item.thisown = 1`` for Python-side ownership. After some in-process board
    I/O (e.g. ``ImportSpecctraSES`` from the freerouting pass) the items handed
    back by the iterators can be bare ``SwigPyObject``s with no ``thisown``
    attribute, which makes the ownership step raise. ``RemoveNative`` itself
    still works on them, so we fall back to it.
    """
    try:
        board.Remove(item)
    except AttributeError:
        board.RemoveNative(item)


def _safe_list(accessor) -> list:
    """Materialise a pcbnew item iterator, tolerating SWIG glitches.

    After a freerouting ``ImportSpecctraSES`` the board's container accessors can
    momentarily come back as a bare ``SwigPyObject`` that is not iterable, so
    ``list(board.GetDrawings())`` raises ``TypeError`` deep inside pcbnew. We
    treat that as "nothing to iterate" rather than letting it abort the run.
    """
    try:
        return list(accessor())
    except (TypeError, AttributeError):
        return []


def clear_board(board: pcbnew.BOARD) -> None:
    """Reset the open document to a blank board (footprints/tracks/zones/drawings).

    Net records are left in place — :func:`_net` reuses any existing net by name
    (via ``FindNet``), so re-running a design never duplicates nets, and stale
    empty nets from a previous template are harmless (no pads, no copper).

    Every removal goes through :func:`_safe_remove`/:func:`_safe_list` so a board
    left in pcbnew's post-Specctra SWIG-glitch state still clears instead of
    aborting the whole design.
    """
    try:
        board.DeleteAllFootprints()
    except Exception:
        for fp in _safe_list(board.GetFootprints):
            _safe_remove(board, fp)
    for t in _safe_list(board.Tracks):
        _safe_remove(board, t)
    for z in _safe_list(board.Zones):
        _safe_remove(board, z)
    for fp in _safe_list(board.GetFootprints):
        _safe_remove(board, fp)
    for d in _safe_list(board.GetDrawings):
        _safe_remove(board, d)
    board.BuildConnectivity()


def _fill_zones_safe(board: pcbnew.BOARD, workdir: Path) -> float:
    """Pour copper zones directly on the live board.

    Inside the running pcbnew the open document is a fully-resolved board with
    an active connectivity engine, so ``ZONE_FILLER`` pours real copper exactly
    like the editor's *Fill All Zones* (B) command — no disk round-trip needed
    (that was only required for the *headless* worker, where a bare in-memory
    board has no resolved connectivity and pours zero area).

    Crucially we must **not** call ``pcbnew.LoadBoard`` in-process: it swaps the
    global IO-plugin behind ``pcbnew.FootprintLoad``, leaving a bare
    ``SwigPyObject`` so every *subsequent* design fails to place library parts
    (``'SwigPyObject' object has no attribute 'FootprintLoad'``). Filling the
    open board directly keeps the plugin state intact across designs.

    ``workdir`` is accepted for call-site symmetry but unused.
    """
    return W._fill_zones(board)


def _load_footprint(lib: str, name: str):
    """Load a library footprint, resilient to pcbnew's IO-plugin SWIG glitch.

    ``pcbnew.FootprintLoad`` resolves the plugin through
    ``PCB_IO_MGR.FindPlugin``; after certain in-process board operations that
    cached plugin can come back as a bare ``SwigPyObject`` (no ``FootprintLoad``
    attribute). When that happens we fall back to a freshly constructed, fully
    typed ``PCB_IO_KICAD_SEXPR`` plugin, which is immune to the glitch.
    """
    libdir = W._fp_dir(lib)
    try:
        return pcbnew.FootprintLoad(libdir, name)
    except AttributeError:
        io = pcbnew.PCB_IO_KICAD_SEXPR()
        return io.FootprintLoad(libdir, name)


def _net(board, name, cache):
    """Get-or-create a net by name on the live board (no duplicates)."""
    if name in cache:
        return cache[name]
    ni = board.FindNet(name)
    if ni is None:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
    cache[name] = ni
    return ni


def build_live(board: pcbnew.BOARD, spec: dict, hook: Hook = None,
               workdir: Optional[Path] = None, route_passes: int = 10) -> dict:
    """Build ``spec`` onto the live ``board``, refreshing after each phase.

    ``hook(phase, info)`` is called at every milestone so the front-end (the
    chat panel) can log progress and repaint the canvas:
    ``clear → place → connect → outline → stitch → pour → route → done``.
    """
    hook = hook or _noop
    v = W._v
    layer = W._layer

    clear_board(board)
    hook("clear", {})

    rules = spec.get("design_rules", {})
    default_tw = MM(rules.get("track_width", 0.25))
    default_via_d = MM(rules.get("via_drill", 0.4))
    default_via_s = MM(rules.get("via_size", 0.8))
    net_widths = {nm: MM(w) for nm, w in rules.get("net_widths", {}).items()}

    layer_count = int(spec.get("layers", 2))
    board.SetCopperLayerCount(layer_count if layer_count in (2, 4) else 2)

    bds = board.GetDesignSettings()
    min_hole = MM(rules.get("min_hole", 0.15))
    for attr in ("m_MinThroughDrill", "m_HolesMinSize"):
        if hasattr(bds, attr):
            try:
                setattr(bds, attr, min_hole)
            except Exception:
                pass

    # ── place footprints ────────────────────────────────────────────────
    placed = {}
    auto_x, auto_y = 20.0, 20.0
    for fpspec in spec.get("footprints", []):
        ref = fpspec["ref"]
        if fpspec.get("pads"):
            fp = W._make_footprint(board, fpspec)
        else:
            fp = _load_footprint(fpspec["lib"], fpspec["fp"])
        if fp is None:
            return {"ok": False, "error": f"footprint not found: {fpspec.get('lib')}/{fpspec.get('fp')}"}
        if not hasattr(fp, "SetReference"):
            # pcbnew's global SWIG type registry has been corrupted by a prior
            # in-process freerouting ``ImportSpecctraSES`` in this same session:
            # every newly created object now comes back as a bare ``SwigPyObject``
            # with no typed methods, and there is no in-process way to recover it.
            return {"ok": False, "error": (
                "pcbnew 的 Python 类型状态已被本会话先前的 freerouting 布线"
                "（ImportSpecctraSES）破坏，无法在同一会话内再布线一块新板。"
                "这是 KiCAD/SWIG 的已知限制——请重启 KiCAD 后再设计下一块需要"
                "freerouting 的板子（非 freerouting 模板可无限次重复运行）。")}
        fp.SetReference(ref)
        if "value" in fpspec:
            fp.SetValue(str(fpspec["value"]))
        fp.SetPosition(v(fpspec.get("x", auto_x), fpspec.get("y", auto_y)))
        if fpspec.get("rot"):
            fp.SetOrientationDegrees(float(fpspec["rot"]))
        if fpspec.get("side") == "bottom":
            fp.Flip(fp.GetPosition(), False)
        board.Add(fp)
        placed[ref] = fp
        auto_x += fpspec.get("pitch", 10.0)
        if auto_x > 120:
            auto_x, auto_y = 20.0, auto_y + 12.0
    board.BuildConnectivity()
    hook("place", {"footprints": len(placed)})

    # ── nets + pad assignment ───────────────────────────────────────────
    cache: dict = {}
    netnames = set(spec.get("nets", []))
    for c in spec.get("connections", []):
        netnames.add(c["net"])
    for t in spec.get("tracks", []):
        if t.get("net"):
            netnames.add(t["net"])
    for nm in sorted(netnames):
        _net(board, nm, cache)
    for c in spec.get("connections", []):
        fp = placed.get(c["ref"])
        if fp is None:
            return {"ok": False, "error": f"connection refs unknown footprint {c['ref']}"}
        pad = W._find_pad(fp, c["pad"])
        if pad is None:
            return {"ok": False, "error": f"pad {c['ref']}.{c['pad']} not found"}
        pad.SetNet(_net(board, c["net"], cache))
    board.BuildConnectivity()
    hook("connect", {"nets": len(netnames)})

    def _resolve_point(p):
        if isinstance(p, dict):
            return W._find_pad(placed[p["ref"]], p["pad"]).GetPosition()
        return v(p[0], p[1])

    # ── built-in daisy router (fallback / no-freerouting path) ──────────
    if spec.get("autoroute") == "daisy":
        by_net: dict = {}
        for fp in placed.values():
            for pad in fp.Pads():
                code = pad.GetNetCode()
                if code > 0:
                    by_net.setdefault(code, []).append(pad)
        code_to_name = {n.GetNetCode(): nm for nm, n in cache.items()}
        for code, pads in by_net.items():
            if len(pads) < 2:
                continue
            width = net_widths.get(code_to_name.get(code), default_tw)
            pads.sort(key=lambda p: (p.GetPosition().x, p.GetPosition().y))
            for i in range(len(pads) - 1):
                seg = pcbnew.PCB_TRACK(board)
                seg.SetStart(pads[i].GetPosition())
                seg.SetEnd(pads[i + 1].GetPosition())
                seg.SetWidth(width)
                seg.SetLayer(pcbnew.F_Cu)
                seg.SetNetCode(code)
                board.Add(seg)

    for t in spec.get("tracks", []):
        seg = pcbnew.PCB_TRACK(board)
        seg.SetStart(_resolve_point(t["start"]))
        seg.SetEnd(_resolve_point(t["end"]))
        seg.SetWidth(MM(t["width"]) if "width" in t else default_tw)
        seg.SetLayer(layer(t.get("layer", "F.Cu")))
        if t.get("net") and t["net"] in cache:
            seg.SetNet(cache[t["net"]])
        board.Add(seg)

    for vspec in spec.get("vias", []):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(_resolve_point(vspec["at"]))
        via.SetDrill(MM(vspec.get("drill", 0)) or default_via_d)
        via.SetWidth(MM(vspec.get("size", 0)) or default_via_s)
        if vspec.get("net") and vspec["net"] in cache:
            via.SetNet(cache[vspec["net"]])
        board.Add(via)

    # ── board outline ───────────────────────────────────────────────────
    outline = spec.get("outline")
    if outline is None:
        bbox = board.GetBoundingBox()
        m = MM(5)
        W._outline_iu(board, [
            (bbox.GetLeft() - m, bbox.GetTop() - m),
            (bbox.GetRight() + m, bbox.GetTop() - m),
            (bbox.GetRight() + m, bbox.GetBottom() + m),
            (bbox.GetLeft() - m, bbox.GetBottom() + m),
        ])
    elif outline.get("type") == "rect":
        x, y, w, h = outline["x"], outline["y"], outline["w"], outline["h"]
        W._outline_iu(board, [(MM(x), MM(y)), (MM(x + w), MM(y)),
                              (MM(x + w), MM(y + h)), (MM(x), MM(y + h))])
    elif outline.get("type") == "poly":
        W._outline_iu(board, [(MM(px), MM(py)) for px, py in outline["points"]])
    board.BuildConnectivity()
    hook("outline", {})

    # ── via stitching + copper pours ────────────────────────────────────
    for s in spec.get("stitching", []):
        W._stitch_vias(board, s, cache, default_via_d, default_via_s)
    if spec.get("stitching"):
        hook("stitch", {})

    has_zones = bool(spec.get("zones"))
    if has_zones:
        default_poly = W._board_bbox_poly(board)
        for z in spec.get("zones", []):
            W._add_zone(board, z, cache, default_poly)
        _fill_zones_safe(board, Path(workdir or (Path.home() / ".dao_kicad_live")))
        hook("pour", {"zones": board.GetAreaCount()})

    # ── freerouting (optional, professional path) ───────────────────────
    routed = None
    if spec.get("route") == "freerouting" and route.available() and workdir:
        hook("route_start", {})
        routed = route_live(board, workdir, route_passes)
        hook("route", {"ok": routed.ok, "reason": routed.reason})

    board.BuildConnectivity()
    return {
        "ok": True,
        "footprints": len(list(board.GetFootprints())),
        "tracks": len(list(board.Tracks())),
        "nets": board.GetNetCount(),
        "zones": board.GetAreaCount(),
        "vias": sum(1 for t in board.Tracks() if isinstance(t, pcbnew.PCB_VIA)),
        "routed": bool(routed and routed.ok),
    }


def route_live(board: pcbnew.BOARD, workdir: Path, passes: int = 10):
    """Route the *live* board through freerouting via the Specctra channel.

    Exports the open board to ``.dsn``, runs freerouting headless, then imports
    the ``.ses`` back onto the same board so the routed copper lands on-canvas.
    """
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    dsn = workdir / "live.dsn"
    ses = workdir / "live.ses"
    pcbnew.ExportSpecctraDSN(board, str(dsn))
    res = route.route_dsn(dsn, ses, passes=passes)
    if res.ok:
        pcbnew.ImportSpecctraSES(board, str(ses))
        if board.GetAreaCount():
            _fill_zones_safe(board, workdir)
    return res


def _reflect_spread(spec: dict, factor: float = 1.18) -> dict:
    """Spread footprints outward from their centroid (clearance/congestion relief).

    Same monotone relaxation the headless :class:`DesignAgent` uses — preserves
    topology while adding spacing, so the closed loop converges to DRC-clean.
    """
    new = copy.deepcopy(spec)
    fps = new["footprints"]
    xs = [fp.get("x", 20.0) for fp in fps]
    ys = [fp.get("y", 20.0) for fp in fps]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    for fp in fps:
        fp["x"] = round(cx + (fp.get("x", 20.0) - cx) * factor, 3)
        fp["y"] = round(cy + (fp.get("y", 20.0) - cy) * factor, 3)
    return new


def design_live(board: pcbnew.BOARD, spec: dict, hook: Hook = None,
                workdir: Optional[Path] = None, max_iter: int = 6,
                attempts: int = 3) -> dict:
    """The full closed loop, *live* in KiCad: 感→谋→行→验→记 until DRC-clean.

    Each iteration rebuilds the open board (placement → route → pour), verifies
    with ``kicad-cli`` DRC on a temp save of the live board, and — if not clean —
    reflects (spreads parts) and rebuilds, refreshing the canvas throughout. This
    mirrors the headless :class:`DesignAgent`, but the board the human watches in
    KiCAD *is* the board being iterated.
    """
    hook = hook or _noop
    from ..live import LiveKiCad

    lk = LiveKiCad()
    workdir = Path(workdir or (Path.home() / ".dao_kicad_live"))
    workdir.mkdir(parents=True, exist_ok=True)
    use_fr = route.available() and spec.get("autoroute") != "none"
    orig_file = board.GetFileName()
    passes = 12
    clean = False
    drc: dict = {}
    last: dict = {"ok": False}
    it = 0
    for attempt in range(1, attempts + 1):
        cur = spec
        for it in range(1, max_iter + 1):
            build_spec = dict(cur)
            if use_fr:
                build_spec.pop("autoroute", None)
                build_spec["route"] = "freerouting"
            last = build_live(board, build_spec, hook=hook, workdir=workdir,
                              route_passes=passes)
            if not last.get("ok"):
                last.update({"clean": False, "drc": drc, "iterations": it})
                return last
            tmp = workdir / "_verify.kicad_pcb"
            pcbnew.SaveBoard(str(tmp), board)
            if orig_file:
                board.SetFileName(orig_file)  # keep the GUI's file association
            drc = lk.drc(str(tmp))
            hook("verify", {"iter": it, "violations": drc.get("violations"),
                            "unconnected": drc.get("unconnected"),
                            "clean": drc.get("clean")})
            if drc.get("clean"):
                clean = True
                break
            if drc.get("unconnected", 0) > 0:
                passes = min(passes + 12, 60)
            cur = _reflect_spread(cur)
            hook("reflect", {"iter": it, "attempt": attempt})
        if clean:
            break
        passes = min(passes + 12, 60)

    last.update({"clean": clean, "drc": drc, "iterations": it})
    return last
