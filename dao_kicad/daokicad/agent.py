"""DesignAgent — the closed loop (感→谋→行→验→记).

perceive → plan → act → verify → reflect, with feedback. This is the layer
that makes Dao-KiCad a *Cursor for KiCad*: it drives the real engine, reads
the diagnostics back, and iterates until the board converges (DRC-clean) or a
budget is exhausted.
"""
from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from . import dna as _dna
from .live import LiveKiCad

EventHook = Optional[Callable[[dict], None]]


@dataclass
class Step:
    phase: str
    info: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"phase": self.phase, **self.info}


@dataclass
class DesignResult:
    name: str
    pcb: Optional[str]
    clean: bool
    iterations: int
    drc: dict = field(default_factory=dict)
    fab: dict = field(default_factory=dict)
    trace: list = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "name": self.name, "pcb": self.pcb, "clean": self.clean,
            "iterations": self.iterations, "drc": self.drc, "fab": self.fab,
            "trace": [s.as_dict() for s in self.trace],
        }


class DesignAgent:
    def __init__(self, live: Optional[LiveKiCad] = None,
                 workdir: str | Path = "out", on_event: EventHook = None,
                 live_preview: bool = False):
        self.live = live or LiveKiCad()
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        # on_event(evt) is called as each phase completes so a UI can stream
        # the closed loop (感→谋→行→验→记) in real time. live_preview makes
        # the agent export a fast SVG snapshot after each build/route so the
        # human watches the board take shape (合二为一 的实时反馈).
        self.on_event = on_event
        self.live_preview = live_preview

    def _emit(self, step: "Step") -> "Step":
        if self.on_event:
            try:
                self.on_event(step.as_dict())
            except Exception:
                pass
        return step

    def _snapshot(self, pcb: Path, tag: str) -> None:
        """Export a fast SVG of the current board and announce it."""
        if not (self.live_preview and self.on_event and pcb.is_file()):
            return
        svg = pcb.with_name("preview.svg")
        try:
            self.live.export_svg(pcb, svg)
        except Exception:
            return
        if svg.is_file():
            try:
                self.on_event({"phase": "board", "tag": tag,
                               "svg": str(svg), "pcb": str(pcb)})
            except Exception:
                pass

    # ── reflect: turn DRC verdict into a board mutation ───────────────
    def _reflect(self, spec: dict, drc: dict) -> tuple[dict, str]:
        """Given DRC violations, propose a fixed spec. Returns (spec, note)."""
        new = copy.deepcopy(spec)
        fps = new["footprints"]
        # Scale placement outward from its centroid: this monotonically adds
        # spacing for both clearance violations AND routing congestion while
        # preserving the relative topology (a full re-grid would destabilise a
        # large module's layout and make freerouting oscillate run-to-run).
        xs = [fp.get("x", 20.0) for fp in fps]
        ys = [fp.get("y", 20.0) for fp in fps]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        factor = 1.18
        for fp in fps:
            fp["x"] = round(cx + (fp.get("x", 20.0) - cx) * factor, 3)
            fp["y"] = round(cy + (fp.get("y", 20.0) - cy) * factor, 3)
        if drc.get("unconnected", 0) > 0 and drc.get("violations", 0) == 0:
            return new, "spread components + more routing passes (unconnected relief)"
        return new, "spread components (clearance/congestion relief)"

    # ── design one board, iterating to convergence ────────────────────
    def design(self, template: str, max_iter: int = 6, attempts: int = 3,
               fabricate: bool = True, **template_kw) -> DesignResult:
        """Design until DRC-clean. Each attempt is a fresh perceive→plan→act→
        verify→reflect loop (≤max_iter); dense boards whose external router
        leaves a nondeterministic straggler self-heal by retrying the whole
        design (attempts), starting routing effort where the last attempt left
        off — 无为而无不为: keep acting until the board settles clean."""
        seed_spec = _dna.make(template, **template_kw)
        name = seed_spec.get("name", template)
        pcb = self.workdir / name / f"{name}.kicad_pcb"
        # boards that distribute every net through copper planes declare
        # autoroute="none" and need no point-to-point router at all.
        plane_routed = seed_spec.get("autoroute") == "none"
        use_freerouting = self.live.routing_available() and not plane_routed
        trace: list[Step] = [self._emit(Step("plan", {
            "template": template,
            "router": "freerouting" if use_freerouting else "daisy",
            "attempts": attempts}))]
        clean = False
        drc = {}
        it = 0
        passes = 12  # freerouting effort; escalated when nets stay unconnected
        for attempt in range(1, attempts + 1):
          spec = _dna.make(template, **template_kw)
          for it in range(1, max_iter + 1):
            # act: build placement-only when using a real router, else daisy
            build_spec = dict(spec)
            if use_freerouting:
                build_spec.pop("autoroute", None)
            elif plane_routed:
                build_spec["autoroute"] = "none"  # planes carry every net
            else:
                build_spec["autoroute"] = "daisy"
            build = self.live.build_board(build_spec, pcb)
            trace.append(self._emit(Step("act", {"iter": it, "build": build})))
            if not build.get("ok"):
                break
            self._snapshot(pcb, f"placed (iter {it})")
            # route (二生三): freerouting round-trip
            if use_freerouting:
                rt = self.live.autoroute(pcb, passes=passes)
                trace.append(self._emit(Step("route", {
                    "iter": it, "ok": rt.get("ok"), "tracks": rt.get("tracks"),
                    "passes": passes, "stage": rt.get("stage"),
                    "reason": rt.get("reason")})))
                self._snapshot(pcb, f"routed (iter {it})")
            # perceive
            summ = self.live.summary(pcb)
            trace.append(self._emit(Step("perceive", {
                "iter": it, "footprints": summ.get("footprint_count"),
                "nets": summ.get("net_count"),
                "tracks": summ.get("track_count")})))
            # verify
            drc = self.live.drc(pcb)
            trace.append(self._emit(Step("verify", {
                "iter": it, "violations": drc["violations"],
                "unconnected": drc["unconnected"], "clean": drc["clean"]})))
            if drc["clean"]:
                clean = True
                break
            # reflect -> mutate
            if drc.get("unconnected", 0) > 0:
                passes = min(passes + 12, 60)  # harder routing problem
            spec, note = self._reflect(spec, drc)
            trace.append(self._emit(Step("reflect", {
                "iter": it, "attempt": attempt, "note": note})))
          if clean:
              break
          passes = min(passes + 12, 60)  # next attempt routes harder

        fab: dict = {}
        if clean and fabricate:
            fab = self._fabricate(pcb)
            fab["bom"] = self._write_bom(spec, pcb)
            trace.append(self._emit(Step("fabricate", fab)))
            self._snapshot(pcb, "final")

        result = DesignResult(name, str(pcb) if pcb.is_file() else None,
                              clean, it, drc, fab, trace)
        if self.on_event:
            try:
                self.on_event({"phase": "done", "name": name, "clean": clean,
                               "iterations": it, "pcb": result.pcb})
            except Exception:
                pass
        return result

    def _fabricate(self, pcb: Path) -> dict:
        base = pcb.parent
        gerber = self.live.export_gerbers(pcb, base / "gerber")
        self.live.export_drill(pcb, base / "gerber")
        render = self.live.render(pcb, base / "render_top.png", "top")
        step = self.live.export_step(pcb, base / f"{pcb.stem}.step")
        return {
            "gerbers": len(gerber.artifacts),
            "gerber_dir": str(base / "gerber"),
            "render": str(render.artifacts[0]) if render.artifacts else None,
            "step": str(step.artifacts[0]) if step.artifacts else None,
        }

    def _write_bom(self, spec: dict, pcb: Path) -> str:
        """Generate a grouped BOM CSV from the board spec."""
        groups: dict[tuple[str, str, str], list[str]] = {}
        for fp in spec["footprints"]:
            lib = fp.get("lib", "daokicad")  # custom footprints have no lib
            key = (fp.get("value", ""), lib, fp.get("fp", fp["ref"]))
            groups.setdefault(key, []).append(fp["ref"])
        path = pcb.parent / "bom.csv"
        import csv as _csv
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = _csv.writer(fh)
            w.writerow(["Item", "Qty", "Value", "Footprint", "References"])
            for i, ((value, lib, fpn), refs) in enumerate(sorted(groups.items()), 1):
                refs_sorted = sorted(refs, key=lambda r: (r[0], int("".join(
                    filter(str.isdigit, r)) or 0)))
                w.writerow([i, len(refs), value, f"{lib}:{fpn}",
                            ",".join(refs_sorted)])
        return str(path)

    # ── batch: 道法自然的持续推进 ─────────────────────────────────────
    def design_all(self, **kw) -> dict:
        results = {}
        for name in _dna.TEMPLATES:
            r = self.design(name, **kw)
            results[name] = r.as_dict()
        clean = sum(1 for r in results.values() if r["clean"])
        return {"total": len(results), "clean": clean, "results": results}
