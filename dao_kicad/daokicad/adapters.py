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


_KIBOT_FAB_CFG = """\
kibot:
  version: 1
outputs:
  - name: gerbers
    type: gerber
    dir: gerbers
  - name: drill
    type: excellon
    dir: gerbers
  - name: position
    type: position
    dir: assembly
    options: { format: CSV, units: millimeters }
"""


def _kibot_fab(pcb, out=None, *, config=None, timeout=300, **kw) -> dict:
    """Fabrication outputs (gerber/drill/pos) via KiBot — CI-grade, reproducible.

    KiBot is AGPL → invoked strictly as a subprocess. A board-only default
    config (no schematic needed) is written when none is supplied.
    """
    import subprocess
    from . import env
    pcb = Path(pcb)
    out = Path(out) if out else pcb.parent / "kibot"
    out.mkdir(parents=True, exist_ok=True)
    py = env.detect().python
    if not py:
        return {"ok": False, "reason": "KiCad bundled python not found"}
    cfg = Path(config) if config else out / "kibot_fab.yaml"
    if not config:
        cfg.write_text(_KIBOT_FAB_CFG)
    cp = subprocess.run([str(py), "-m", "kibot", "-c", str(cfg),
                         "-b", str(pcb), "-d", str(out)],
                        capture_output=True, text=True, timeout=timeout)
    gerbers = sorted(str(p) for p in (out / "gerbers").glob("*.gbr"))
    ok = len(gerbers) > 0
    return {"ok": ok, "dir": str(out) if ok else None, "gerbers": len(gerbers),
            "reason": "" if ok else (cp.stderr or cp.stdout)[-300:]}


def _kikit_panelize(pcb, out=None, *, rows=2, cols=2, space="2mm",
                    frame=True, mousebites=True, timeout=180, **kw) -> dict:
    """Panelize a board into an rows×cols array (inherited: KiKit).

    Wraps ``python -m kikit.ui panelize`` (KiKit is GPL → invoked as a
    subprocess, never linked) using KiCad's own interpreter.
    """
    import subprocess
    from . import env
    pcb = Path(pcb)
    out = Path(out) if out else pcb.with_name(pcb.stem + "_panel.kicad_pcb")
    out.parent.mkdir(parents=True, exist_ok=True)
    py = env.detect().python
    if not py:
        return {"ok": False, "reason": "KiCad bundled python not found"}
    cmd = [str(py), "-m", "kikit.ui", "panelize",
           "-l", f"grid; rows: {rows}; cols: {cols}; space: {space}"]
    if mousebites:
        cmd += ["-c", "mousebites; spacing: 0.8mm; offset: 0.2mm"]
    if frame:
        cmd += ["-r", "frame; width: 5mm; space: 2mm"]
    cmd += [str(pcb), str(out)]
    cp = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    ok = out.is_file() and out.stat().st_size > 0
    return {"ok": ok, "panel": str(out) if ok else None,
            "reason": "" if ok else (cp.stderr or cp.stdout)[-300:]}


def _render(pcb, out=None, *, side="top", width=1600, height=1000,
            quality="high", background="opaque", timeout=180, **kw) -> dict:
    """Render a board to a PNG via ``kicad-cli pcb render`` (ray-traced 3D).

    ``out`` may be a directory (a ``<board>_<side>.png`` is created inside) or
    an explicit ``.png`` path. Builtin engine — always present when KiCad is.
    """
    import subprocess
    from . import env
    pcb = Path(pcb)
    cli = env.detect().cli
    if not cli:
        return {"ok": False, "reason": "kicad-cli not found"}
    out = Path(out) if out else pcb.parent / "render"
    if out.suffix.lower() in (".png", ".jpg", ".jpeg"):
        png = out
        png.parent.mkdir(parents=True, exist_ok=True)
    else:
        out.mkdir(parents=True, exist_ok=True)
        png = out / f"{pcb.stem}_{side}.png"
    cp = subprocess.run([str(cli), "pcb", "render", "--side", side,
                         "--quality", quality, "--background", background,
                         "-w", str(width), "-h", str(height),
                         "-o", str(png), str(pcb)],
                        capture_output=True, text=True, timeout=timeout)
    ok = png.is_file() and png.stat().st_size > 0
    return {"ok": ok, "png": str(png) if ok else None,
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
        "AGPL-3.0", "https://github.com/INTI-CMNB/KiBot",
        Probe("python", module="kibot"), priority=50, invoke=_kibot_fab))

    # ---- bom ----
    reg.register(Backend(
        "dao-bom", "bom",
        "Builtin grouped BOM CSV from the board spec.",
        "repo", "daokicad.agent", Probe("builtin"), priority=40))
    reg.register(Backend(
        "kibot-bom", "bom",
        "KiBot BOM (XLSX/CSV/HTML with variants & sourcing).",
        "AGPL-3.0", "https://github.com/INTI-CMNB/KiBot",
        Probe("python", module="kibot"), priority=35))

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
        Probe("python", module="kikit"), priority=60, invoke=_kikit_panelize))

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
                                      label="kicad-cli present"), priority=55,
        invoke=_render))

    return reg


@lru_cache(maxsize=1)
def registry() -> Registry:
    return default_registry()
