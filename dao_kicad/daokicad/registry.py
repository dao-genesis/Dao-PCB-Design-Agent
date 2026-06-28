"""Capability registry — 道生一·一生万物 的工具归一总线.

The re-anchoring (反者道之动): stop reinventing every PCB stage from scratch and
instead become an *orchestrator* — a "KiCad Devin Desktop" — that inherits the
best tool the world already has for each capability and calls it behind one
uniform interface. Just as Devin itself integrates many tools rather than only
an editor, this registry lets each capability domain of the full PCB chain
(design-as-code → schematic → netlist → place → route → DRC → fab → BOM →
panelize → sourcing) carry several interchangeable *backends*:

  * ``builtin``  — our own real-KiCad engine (always present),
  * ``python``   — an inheritable pip library (SKiDL, KiKit, kicad-skip…),
  * ``cli``      — an external program invoked as a subprocess (KiBot, atopile,
                   freerouting, kicad-cli…), so GPL tools stay at arm's length,
  * ``cloud``    — an optional hosted engine gated on an API key (DeepPCB,
                   Quilter…), used only when the user provides credentials.

A backend declares *how to detect itself* (``Probe``) so an absent tool simply
reports unavailable instead of crashing — graceful degradation, no hard deps.
The registry then answers two questions the agent and UI need: *what can this
machine do right now*, and *which backend should run a given capability* (the
highest-priority available one, or a caller-named choice). This makes the system
honestly extensible: inheriting a new tool == registering one ``Backend``.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Optional

# The capability domains of the whole PCB flow. Order mirrors the chain so a
# ``describe()`` reads top-to-bottom like the pipeline itself.
CAPABILITIES: tuple[str, ...] = (
    "design_as_code",   # text/code -> circuit (SKiDL, atopile, JITX)
    "schematic_import",  # read/edit existing schematics (kicad-skip, IPC)
    "netlist",          # produce a netlist (kicad-cli, SKiDL, builtin)
    "place",            # component placement / floorplanning
    "route",            # autorouting (freerouting, DeepPCB, Quilter)
    "drc",              # design-rule + connectivity check
    "fabricate",        # gerber/drill/pos/STEP fab outputs
    "bom",              # bill of materials
    "interactive_bom",  # interactive HTML BOM
    "panelize",         # array/panelize for production (KiKit)
    "sourcing",         # part availability/pricing (LCSC, Octopart)
    "render",           # board image / 3D render
    "reverse_engineer",  # recover a finished board's source (netlist/BOM/...)
)


@dataclass(frozen=True)
class Probe:
    """How to detect whether an inheritable tool is actually installed."""
    kind: str                 # builtin | python | cli | cloud | func
    module: str = ""          # python: import name to find
    cli: str = ""             # cli: executable expected on PATH
    env: str = ""             # cloud: env var holding the key/endpoint
    func: Optional[Callable[[], bool]] = None  # func: custom availability test
    label: str = ""           # func: human label for the test

    def check(self) -> tuple[bool, str]:
        if self.kind == "builtin":
            return True, "builtin"
        if self.kind == "python":
            ok = importlib.util.find_spec(self.module) is not None
            return ok, f"python: import {self.module}"
        if self.kind == "cli":
            path = shutil.which(self.cli)
            return path is not None, f"cli: {self.cli}" + (f" ({path})" if path else " (not found)")
        if self.kind == "cloud":
            return bool(os.environ.get(self.env)), f"cloud: ${self.env}"
        if self.kind == "func":
            try:
                ok = bool(self.func()) if self.func else False
            except Exception:
                ok = False
            return ok, self.label or "func"
        return False, f"unknown probe kind: {self.kind}"


@dataclass
class Backend:
    """One interchangeable implementation of a capability."""
    name: str
    capability: str
    summary: str
    license: str
    source: str
    probe: Probe
    priority: int = 50                       # higher wins when several available
    invoke: Optional[Callable[..., dict]] = None  # adapter; None == declared-only

    def available(self) -> bool:
        return self.probe.check()[0]

    def status(self) -> dict:
        ok, how = self.probe.check()
        return {
            "name": self.name, "capability": self.capability,
            "available": ok, "how": how, "kind": self.probe.kind,
            "license": self.license, "priority": self.priority,
            "runnable": ok and self.invoke is not None,
            "summary": self.summary, "source": self.source,
        }


class CapabilityError(RuntimeError):
    """Raised when a capability has no available/runnable backend."""


class Registry:
    """Holds backends and selects among them per capability."""

    def __init__(self) -> None:
        self._backends: list[Backend] = []

    def register(self, backend: Backend) -> Backend:
        if backend.capability not in CAPABILITIES:
            raise ValueError(f"unknown capability: {backend.capability}")
        self._backends.append(backend)
        return backend

    def backends(self, capability: Optional[str] = None) -> list[Backend]:
        bs = [b for b in self._backends
              if capability is None or b.capability == capability]
        return sorted(bs, key=lambda b: -b.priority)

    def available(self, capability: str) -> list[Backend]:
        return [b for b in self.backends(capability) if b.available()]

    def best(self, capability: str, prefer: Optional[str] = None) -> Optional[Backend]:
        """Highest-priority available backend, or the named one if available."""
        avail = self.available(capability)
        if prefer:
            for b in avail:
                if b.name == prefer:
                    return b
        return avail[0] if avail else None

    def run(self, capability: str, *args, prefer: Optional[str] = None,
            **kwargs) -> dict:
        """Run a capability with its best available *runnable* backend."""
        candidates = self.available(capability)
        if prefer:
            candidates = ([b for b in candidates if b.name == prefer]
                          + [b for b in candidates if b.name != prefer])
        for b in candidates:
            if b.invoke is not None:
                out = b.invoke(*args, **kwargs)
                if isinstance(out, dict):
                    out.setdefault("backend", b.name)
                return out
        raise CapabilityError(
            f"no runnable backend for '{capability}'"
            + (f" (preferred '{prefer}')" if prefer else ""))

    def describe(self) -> dict:
        """A full map of the integrated tool stack, per capability."""
        out: dict[str, dict] = {}
        for cap in CAPABILITIES:
            bs = self.backends(cap)
            best = self.best(cap)
            out[cap] = {
                "selected": best.name if best else None,
                "backends": [b.status() for b in bs],
            }
        return out
