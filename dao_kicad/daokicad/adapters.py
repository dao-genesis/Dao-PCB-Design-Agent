"""Adapters — bind each capability to concrete tools (继承一切·归一调用).

This is where the system *inherits* the world's tools. Each adapter wraps one
implementation behind the uniform ``Backend.invoke`` contract and declares how
to detect it. The builtin backends drive our own real-KiCad engine and are
always present; the rest are best-in-class projects we inherit when installed:

  design-as-code  SKiDL (MIT, pip) · atopile (MIT, ``ato`` CLI)
  schematic edit  kicad-skip (pip) · official IPC bindings (kipy, pip)
  netlist         kicad-cli (builtin) · SKiDL
  route           freerouting (builtin, bundled jar) · DeepPCB/Quilter (cloud)
  drc             kicad-cli / pcbnew (builtin)
  fabricate       kicad-cli (builtin) · KiBot (GPL, CLI)
  interactive_bom InteractiveHtmlBom (pip/plugin)
  panelize        KiKit (pip/CLI)
  sourcing        LCSC / Octopart (cloud, API key)

Absent tools degrade gracefully (the probe just reports unavailable). Inheriting
a new tool is one ``reg.register(Backend(...))`` call — nothing else changes.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from .registry import Backend, Probe, Registry


# ── builtin engine invokes (lazy imports keep the registry import-light) ──
def _route_builtin(dsn, ses, **kw) -> dict:
    from .route import route_dsn
    r = route_dsn(dsn, ses, **kw)
    return {"ok": r.ok, "ses": r.ses, "reason": r.reason}


def _freerouting_ready() -> bool:
    from .route import find_freerouting, find_java
    return bool(find_java()) and bool(find_freerouting())


def _kicad_ready() -> bool:
    from . import env
    return env.detect().available


def _kicad_can_script() -> bool:
    from . import env
    return env.detect().can_script


def _ibom_script() -> Optional[Path]:
    """Locate InteractiveHtmlBom's standalone CLI shim next to KiCad's python."""
    from . import env
    e = env.detect()
    if not e.python:
        return None
    exe = e.python.parent / "Scripts" / "generate_interactive_bom.exe"
    if exe.is_file():
        return exe
    posix = e.python.parent / "generate_interactive_bom"
    return posix if posix.is_file() else None


def _ibom(pcb, *, dest_dir=None, dark=True, **kw) -> dict:
    """Generate an interactive HTML BOM for a board (inherited: InteractiveHtmlBom)."""
    import subprocess
    pcb = Path(pcb)
    script = _ibom_script()
    if not script:
        return {"ok": False, "reason": "generate_interactive_bom not found"}
    # ibom resolves --dest-dir relative to the *board's* folder, so anchor to
    # an absolute path to keep the result location unambiguous.
    dest = (Path(dest_dir) if dest_dir else pcb.parent / "bom_ibom").resolve()
    cmd = [str(script), "--no-browser", "--dest-dir", str(dest),
           "--name-format", "ibom", str(pcb)]
    if dark:
        cmd.insert(1, "--dark-mode")
    cp = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    html = dest / "ibom.html"
    ok = html.is_file()
    return {"ok": ok, "html": str(html) if ok else None,
            "reason": "" if ok else (cp.stderr or cp.stdout)[-200:]}


def _symbol_dir() -> Optional[str]:
    from . import env
    e = env.detect()
    return str(e.symbols) if e.symbols else None


def _skidl(script, netlist=None, *, symbol_dir=None, timeout=120, **kw) -> dict:
    """Run a SKiDL script (design-as-code) and capture its KiCad netlist.

    The script receives the destination netlist path as ``sys.argv[1]`` and is
    run with KiCad's own interpreter; the symbol-library dir is wired in so
    ``Part("Device","R")`` resolves without manual env setup (继承 SKiDL).
    """
    import os
    import subprocess
    from . import env
    script = Path(script)
    netlist = Path(netlist) if netlist else script.with_suffix(".net")
    netlist.parent.mkdir(parents=True, exist_ok=True)
    py = env.detect().python
    if not py:
        return {"ok": False, "reason": "KiCad bundled python not found"}
    envv = dict(os.environ)
    sym = symbol_dir or _symbol_dir()
    if sym:
        for k in ("KICAD_SYMBOL_DIR", "KICAD8_SYMBOL_DIR", "KICAD9_SYMBOL_DIR"):
            envv[k] = sym
    cp = subprocess.run([str(py), str(script), str(netlist)],
                        capture_output=True, text=True, timeout=timeout, env=envv)
    ok = netlist.is_file() and netlist.stat().st_size > 0
    return {"ok": ok, "netlist": str(netlist) if ok else None,
            "reason": "" if ok else (cp.stderr or cp.stdout)[-300:]}


def default_registry() -> Registry:
    """Build the registry of every capability backend this project knows about.

    Declared even when a tool is absent, so ``describe()`` is an honest map of
    *what could be inherited* and *what is live right now* on this machine.
    """
    reg = Registry()

    # ---- design-as-code: code/text -> circuit ----
    reg.register(Backend(
        "skidl", "design_as_code",
        "Python-described schematics/netlists (textual circuits).",
        "MIT", "https://github.com/devbisme/skidl",
        Probe("python", module="skidl"), priority=60, invoke=_skidl))
    reg.register(Backend(
        "atopile", "design_as_code",
        "Modular hardware-as-code toolchain (.ato), git-friendly.",
        "MIT", "https://github.com/atopile/atopile",
        Probe("cli", cli="ato"), priority=55))
    reg.register(Backend(
        "dna", "design_as_code",
        "Builtin parametric circuit DNA templates (AMS1117/ESP32/RC…).",
        "repo", "daokicad.dna", Probe("builtin"), priority=40))

    # ---- schematic import / edit ----
    reg.register(Backend(
        "kicad-skip", "schematic_import",
        "Friendly Python over KiCad 7+ s-expression sch/pcb/netlist.",
        "GPL-2.0", "https://github.com/psychogenic/kicad-skip",
        Probe("python", module="skip"), priority=60))
    reg.register(Backend(
        "kicad-ipc", "schematic_import",
        "Official KiCad IPC API bindings (live board over a socket).",
        "GPL-3.0", "https://gitlab.com/kicad/code/kicad-python",
        Probe("python", module="kipy"), priority=55))

    # ---- netlist ----
    reg.register(Backend(
        "kicad-cli", "netlist",
        "Export netlist from a schematic via kicad-cli (builtin engine).",
        "GPL-3.0", "kicad-cli", Probe("func", func=_kicad_ready,
                                      label="kicad-cli present"), priority=60))

    # ---- place ----
    reg.register(Backend(
        "dao-place", "place",
        "Connectivity-aware placer: greedy+force order, aspect-ratio swept.",
        "repo", "daokicad._pcbworker", Probe("func", func=_kicad_can_script,
                                             label="pcbnew scriptable"),
        priority=50))

    # ---- route ----
    reg.register(Backend(
        "freerouting", "route",
        "Headless freerouting (Specctra DSN/SES) — bundled jar.",
        "GPL-3.0", "https://github.com/freerouting/freerouting",
        Probe("func", func=_freerouting_ready, label="java+freerouting.jar"),
        priority=60, invoke=_route_builtin))
    reg.register(Backend(
        "deeppcb", "route",
        "DeepPCB cloud autorouter (InstaDeep) — needs API key.",
        "commercial", "https://www.deeppcb.ai/",
        Probe("cloud", env="DEEPPCB_API_KEY"), priority=70))
    reg.register(Backend(
        "quilter", "route",
        "Quilter.ai ML layout/route service — needs API key.",
        "commercial", "https://www.quilter.ai/",
        Probe("cloud", env="QUILTER_API_KEY"), priority=72))
    reg.register(Backend(
        "daisy", "route",
        "Builtin point-to-point daisy router (always-available fallback).",
        "repo", "daokicad._pcbworker", Probe("func", func=_kicad_can_script,
                                             label="pcbnew scriptable"),
        priority=20))

    # ---- drc ----
    reg.register(Backend(
        "kicad-drc", "drc",
        "DRC + connectivity via kicad-cli / pcbnew (builtin engine).",
        "GPL-3.0", "kicad-cli", Probe("func", func=_kicad_ready,
                                      label="kicad-cli present"), priority=60))

    # ---- fabricate ----
    reg.register(Backend(
        "kicad-fab", "fabricate",
        "Gerber/drill/pos/STEP via kicad-cli (builtin engine).",
        "GPL-3.0", "kicad-cli", Probe("func", func=_kicad_ready,
                                      label="kicad-cli present"), priority=55))
    reg.register(Backend(
        "kibot", "fabricate",
        "KiBot fab-output/documentation automation (CI-grade).",
        "GPL-3.0", "https://github.com/INTI-CMNB/KiBot",
        Probe("cli", cli="kibot"), priority=60))

    # ---- bom ----
    reg.register(Backend(
        "dao-bom", "bom",
        "Builtin grouped BOM CSV from the board spec.",
        "repo", "daokicad.agent", Probe("builtin"), priority=40))
    reg.register(Backend(
        "kibot-bom", "bom",
        "KiBot BOM (XLSX/CSV/HTML with variants & sourcing).",
        "GPL-3.0", "https://github.com/INTI-CMNB/KiBot",
        Probe("cli", cli="kibot"), priority=55))

    # ---- interactive_bom ----
    reg.register(Backend(
        "ibom", "interactive_bom",
        "InteractiveHtmlBom — clickable assembly BOM.",
        "MIT", "https://github.com/openscopeproject/InteractiveHtmlBom",
        Probe("python", module="InteractiveHtmlBom"), priority=55,
        invoke=_ibom))

    # ---- panelize ----
    reg.register(Backend(
        "kikit", "panelize",
        "KiKit panelization/array for production.",
        "MIT", "https://github.com/yaqwsx/KiKit",
        Probe("python", module="kikit"), priority=60))

    # ---- sourcing ----
    reg.register(Backend(
        "lcsc", "sourcing",
        "LCSC catalogue (price/stock) — needs API access.",
        "commercial", "https://www.lcsc.com/", Probe("cloud", env="LCSC_API_KEY"),
        priority=55))
    reg.register(Backend(
        "octopart", "sourcing",
        "Octopart/Nexar part search — needs API key.",
        "commercial", "https://nexar.com/", Probe("cloud", env="OCTOPART_API_KEY"),
        priority=50))

    # ---- render ----
    reg.register(Backend(
        "kicad-render", "render",
        "Board PNG/SVG and ray-traced 3D via kicad-cli (builtin engine).",
        "GPL-3.0", "kicad-cli", Probe("func", func=_kicad_ready,
                                      label="kicad-cli present"), priority=55))

    return reg


@lru_cache(maxsize=1)
def registry() -> Registry:
    return default_registry()
