"""Reverse engineering — recover a finished board's *source* (反者道之动).

A manufactured ``.kicad_pcb`` is a finished product; this module walks it
backwards to the design intent it grew from: the **netlist** (what connects to
what), the **BOM** (what parts and how many), the **placement** (where each
part sits), the **stackup / design rules** (how many copper layers, clearances,
track/via geometry), and **routing stats** (track length, via count).

The recovered netlist is emitted in the exact spec shape ``netlist.parse_netlist``
produces (``footprints`` / ``nets`` / ``connections``), so it can be fed
straight back into the build engine. ``roundtrip`` does exactly that and diffs
the rebuild against the original — every divergence is a defect in our own
extract→rebuild chain, which is the whole point of working backwards.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pcbnew


def _mm(v) -> float:
    return round(pcbnew.ToMM(v), 4)


def extract(pcb_path: str | Path) -> dict[str, Any]:
    """Recover the design source from a finished board.

    Returns a dict with a round-trippable ``spec`` (footprints/nets/connections)
    plus ``bom``, ``stackup``, ``rules`` and ``routing`` sections recovered from
    the copper itself.
    """
    pcb_path = str(pcb_path)
    board = pcbnew.LoadBoard(pcb_path)

    footprints: list[dict[str, Any]] = []
    connections: list[dict[str, Any]] = []
    placement: list[dict[str, Any]] = []
    bom_groups: dict[tuple[str, str], list[str]] = defaultdict(list)
    netnames: set[str] = set()

    for fp in board.GetFootprints():
        ref = fp.GetReference()
        fpid = fp.GetFPIDAsString()
        lib, name = (fpid.split(":", 1) if ":" in fpid else ("", fpid))
        value = fp.GetValue()
        pos = fp.GetPosition()
        flipped = fp.IsFlipped()
        # fold placement straight into the footprint spec — a rebuild then
        # reuses the recovered coordinates instead of re-running the O(n²)
        # auto-placer (which does not scale to 1000+ part industrial boards).
        footprints.append({
            "ref": ref, "lib": lib, "fp": name, "value": value,
            "x": _mm(pos.x), "y": _mm(pos.y),
            "rot": round(fp.GetOrientationDegrees(), 2),
            "side": "bottom" if flipped else "top",
        })
        bom_groups[(value, fpid)].append(ref)
        placement.append({
            "ref": ref,
            "x": _mm(pos.x), "y": _mm(pos.y),
            "rot": round(fp.GetOrientationDegrees(), 2),
            "layer": "B.Cu" if flipped else "F.Cu",
        })
        for pad in fp.Pads():
            net = pad.GetNetname()
            if not net:
                continue
            netnames.add(net)
            connections.append({"ref": ref, "pad": pad.GetPadName(), "net": net})

    bom = [{"value": v, "fpid": f, "qty": len(refs), "refs": sorted(refs)}
           for (v, f), refs in sorted(bom_groups.items(),
                                      key=lambda kv: -len(kv[1]))]

    # ---- copper / routing recovered straight from the geometry ----
    # tracks and vias are recovered with full fidelity (absolute mm coords,
    # integer layer ids, width, net name) so a rebuild can reconstruct the
    # finished board's *routing*, not just its connectivity + placement.
    track_len_nm = 0
    track_count = via_count = 0
    tracks_geom: list[dict[str, Any]] = []
    vias_geom: list[dict[str, Any]] = []
    for t in board.Tracks():
        if t.Type() == pcbnew.PCB_VIA_T:
            via_count += 1
            pos = t.GetPosition()
            # KiCad 10 vias are padstacks: GetWidth() needs a layer (asserts
            # otherwise). Read the diameter on the via's top copper layer.
            vias_geom.append({
                "at": [_mm(pos.x), _mm(pos.y)],
                "drill": _mm(t.GetDrillValue()),
                "size": _mm(t.GetWidth(t.TopLayer())),
                "net": t.GetNetname() or None,
            })
        else:
            track_count += 1
            track_len_nm += t.GetLength()
            s, e = t.GetStart(), t.GetEnd()
            tracks_geom.append({
                "start": [_mm(s.x), _mm(s.y)],
                "end": [_mm(e.x), _mm(e.y)],
                "width": _mm(t.GetWidth()),
                "layer": t.GetLayer(),
                "net": t.GetNetname() or None,
            })

    bds = board.GetDesignSettings()
    bbox = board.GetBoardEdgesBoundingBox()
    stackup = {
        "copper_layers": board.GetCopperLayerCount(),
        "size_mm": [_mm(bbox.GetWidth()), _mm(bbox.GetHeight())],
        "zones": board.GetAreaCount(),
    }
    rules = {
        "clearance_mm": _mm(getattr(bds, "m_MinClearance", 0) or 0),
        "track_width_mm": _mm(getattr(bds, "m_TrackMinWidth", 0) or 0),
        "via_dia_mm": _mm(getattr(bds, "m_ViasMinSize", 0) or 0),
        "via_drill_mm": _mm(getattr(bds, "m_MinThroughDrill", 0) or 0),
        "edge_clearance_mm": _mm(getattr(bds, "m_CopperEdgeClearance", 0) or 0),
    }

    return {
        "ok": True,
        "path": pcb_path,
        "spec": {
            "footprints": footprints,
            "nets": sorted(netnames),
            "connections": connections,
        },
        "placement": placement,
        "bom": bom,
        "stackup": stackup,
        "rules": rules,
        "routing": {
            "tracks": track_count,
            "vias": via_count,
            "track_length_mm": round(_mm(track_len_nm), 2),
        },
        "routing_geometry": {
            "tracks": tracks_geom,
            "vias": vias_geom,
        },
        "counts": {
            "footprints": len(footprints),
            "nets": len(netnames),
            "pins": len(connections),
        },
    }


def harvest_footprints(pcb_path: str | Path,
                       pretty_dir: str | Path) -> dict[str, str]:
    """Recover the part library *from the product itself* (逆推回本源).

    A finished ``.kicad_pcb`` embeds each footprint's full geometry inline, but
    its library reference (``lib:name``) often points at a footprint that no
    longer exists in any local ``.pretty`` (it came from a global lib, or was
    hand-edited). Rather than fail the rebuild, walk the board and write every
    *unique* footprint out to ``pretty_dir`` as a ``.kicad_mod``. Returns a map
    ``{original_fpid: harvested_name}`` so callers can re-point the spec at the
    harvested library. Names are de-duplicated when two libs share a footprint
    name with different geometry.
    """
    pretty_dir = Path(pretty_dir)
    pretty_dir.mkdir(parents=True, exist_ok=True)
    board = pcbnew.LoadBoard(str(pcb_path))
    io = pcbnew.PCB_IO_KICAD_SEXPR()

    mapping: dict[str, str] = {}
    used: set[str] = set()
    for fp in board.GetFootprints():
        fpid = fp.GetFPIDAsString()
        if fpid in mapping:
            continue
        base = str(fp.GetFPID().GetLibItemName()) or fp.GetReference()
        name = base
        i = 1
        while name in used:                      # distinct geometry, same name
            name = f"{base}__{i}"
            i += 1
        used.add(name)
        fp.SetFPID(pcbnew.LIB_ID("harvested", name))
        io.FootprintSave(str(pretty_dir), fp)
        mapping[fpid] = name
    return mapping


def _recover_buildable_spec(pcb_path, out_path, harvest):
    """Shared front half of every reverse rebuild: extract → re-point parts at a
    harvested library (or the project's) → heal → check for unbuildable parts.

    Returns ``(src, spec, lib_dirs, live, subs, blocked)``; ``blocked`` is a
    ready-to-return error dict when footprints can't be resolved, else ``None``.
    """
    from . import fplib as _fplib
    from .live import LiveKiCad

    src = extract(pcb_path)
    spec = dict(src["spec"])
    spec["footprints"] = [dict(f) for f in spec["footprints"]]
    spec["layers"] = src["stackup"]["copper_layers"]

    if harvest:
        # recover the part library from the product itself, then re-point every
        # footprint at it — stale/global lib refs no longer block the rebuild.
        pretty = Path(out_path).with_suffix("").parent / "harvested.pretty"
        mapping = harvest_footprints(pcb_path, pretty)
        for f in spec["footprints"]:
            fpid = f"{f['lib']}:{f['fp']}" if f["lib"] else f["fp"]
            f["lib"], f["fp"] = "harvested", mapping.get(fpid, f["fp"])
        lib_dirs = {"harvested": str(pretty)}
        spec["fp_lib_dirs"] = lib_dirs
    else:
        lib_dirs = _fplib.resolve_lib_dirs(Path(str(pcb_path)).parent)
        if lib_dirs:
            spec["fp_lib_dirs"] = lib_dirs

    live = LiveKiCad()
    subs = live.heal_footprints(spec["footprints"], lib_dirs)
    missing = live.missing_footprints(spec["footprints"], lib_dirs)
    blocked = None
    if missing:
        blocked = {"ok": False, "reason": "rebuild blocked: footprints not in libs",
                   "missing": missing[:20], "missing_count": len(missing),
                   "original_counts": src["counts"]}
    return src, spec, lib_dirs, live, subs, blocked


def reroute_eval(pcb_path: str | Path, out_path: str | Path,
                 harvest: bool = True) -> dict[str, Any]:
    """Strip a finished board's copper, re-route it with our own engine, and
    grade the result against the human-routed original (反者道之动).

    Recover netlist + placement (no tracks) → build an *unrouted* board → run
    our autorouter (freerouting) → DRC. Comparing the re-routed board's DRC
    cleanliness and track/via counts against the original measures whether our
    engine reproduces human-grade routing — and exposes where it falls short.
    """
    src, spec, lib_dirs, live, subs, blocked = _recover_buildable_spec(
        pcb_path, out_path, harvest)
    if blocked:
        return blocked

    out_path = Path(out_path)
    unrouted = out_path.with_name(out_path.stem + "_unrouted.kicad_pcb")
    build = live.build_board(spec, unrouted)
    if not build.get("ok"):
        return {"ok": False, "reason": "rebuild failed", "build": build,
                "original_counts": src["counts"]}

    nets = src["counts"]["nets"]
    routed = live.autoroute(unrouted, out_path,
                            timeout=live.route_timeout_for(nets))
    if not routed.get("ok"):
        return {"ok": False, "reason": "autoroute failed", "route": routed,
                "original_counts": src["counts"], "nets": nets}

    ours = live.drc(out_path)
    human = live.drc(pcb_path)
    rebuilt = extract(out_path)
    return {
        "ok": True,
        "nets": nets,
        "original_routing": src["routing"],
        "rerouted_routing": rebuilt["routing"],
        "human_drc": {"clean": human["clean"], "violations": human["violations"],
                      "unconnected": human["unconnected"]},
        "our_drc": {"clean": ours["clean"], "violations": ours["violations"],
                    "unconnected": ours["unconnected"]},
        "matches_human_cleanliness": ours["clean"] and human["clean"],
    }


def roundtrip(pcb_path: str | Path, out_path: str | Path,
              harvest: bool = True, route: bool = True) -> dict[str, Any]:
    """Recover a finished board's source, rebuild from it, and diff.

    extract → feed the recovered spec back through the build engine → re-extract
    the rebuild → compare connectivity. Any divergence is a defect in our own
    extract/rebuild chain. Footprints resolve against the original project's
    fp-lib-table so real (non-standard-library) parts build.

    When ``route`` is set the recovered track/via geometry is folded into the
    rebuild spec, so the rebuilt board reconstructs the original's *routing*
    (not just its connectivity + placement); the diff then also reports how
    faithfully tracks/vias were reproduced.
    """
    src, spec, lib_dirs, live, subs, blocked = _recover_buildable_spec(
        pcb_path, out_path, harvest)
    if blocked:
        return blocked
    if route:
        spec["tracks"] = src["routing_geometry"]["tracks"]
        spec["vias"] = src["routing_geometry"]["vias"]

    build = live.build_board(spec, out_path)
    if not build.get("ok"):
        return {"ok": False, "reason": "rebuild failed", "build": build,
                "original_counts": src["counts"]}

    rebuilt = extract(out_path)
    diff = diff_specs(src["spec"], rebuilt["spec"])
    return {
        "ok": True,
        "original_counts": src["counts"],
        "rebuilt_counts": rebuilt["counts"],
        "healed_footprints": len(subs),
        "skipped_connections": len(build.get("skipped_connections") or []),
        "diff": diff,
        "routing": {
            "original": src["routing"],
            "rebuilt": rebuilt["routing"],
            "tracks_identical": src["routing"]["tracks"] == rebuilt["routing"]["tracks"],
            "vias_identical": src["routing"]["vias"] == rebuilt["routing"]["vias"],
        } if route else None,
    }


def _connection_key(c: dict) -> tuple[str, str]:
    return (c["ref"], str(c["pad"]))


def diff_specs(original: dict, rebuilt: dict) -> dict[str, Any]:
    """Compare two recovered specs by *connectivity*, not coordinates.

    Connectivity is the design's true invariant — a rebuild that preserves which
    pads share a net (up to net renaming) is electrically the same board. We
    compare the partition of pins into nets, which is rename-invariant.
    """
    def partition(spec):
        by_net: dict[str, set] = defaultdict(set)
        for c in spec["connections"]:
            by_net[c["net"]].add(_connection_key(c))
        # canonical: a frozenset of pin-groups, ignoring net names
        return {frozenset(g) for g in by_net.values() if len(g) > 1}

    refs_o = {f["ref"] for f in original["footprints"]}
    refs_r = {f["ref"] for f in rebuilt["footprints"]}
    part_o = partition(original)
    part_r = partition(rebuilt)

    return {
        "footprints_only_in_original": sorted(refs_o - refs_r),
        "footprints_only_in_rebuilt": sorted(refs_r - refs_o),
        "net_groups_original": len(part_o),
        "net_groups_rebuilt": len(part_r),
        "net_groups_lost": len(part_o - part_r),
        "net_groups_added": len(part_r - part_o),
        "connectivity_identical": part_o == part_r and refs_o == refs_r,
    }
