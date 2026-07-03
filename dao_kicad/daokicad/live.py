"""LiveKiCad — the multi-channel facade that drives a real KiCad install.

类比 Cursor 对 VS Code 的程序化控制层。本类不挑通道, 自适应择优:

* **CLI 通道**  — ``kicad-cli`` 做 DRC/ERC/导出/渲染 (无需 GUI, 最稳)。
* **SWIG 通道** — 把 board 构建/读取派发给 KiCad 自带 Python 的 :mod:`_pcbworker`。
* **IPC 通道**  — (可选) 当有活体 KiCad GUI 且开启 API server 时, 经 kipy 实时操作。

道法自然: 上层 agent 只调高层语义方法, 由本类决定走哪条通道。
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import env as _env
from . import route as _route

_WORKER = Path(__file__).with_name("_pcbworker.py")


@dataclass
class CliResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    artifacts: list[Path]


class LiveKiCad:
    """Adaptive controller over a real KiCad install."""

    def __init__(self, kenv: Optional[_env.KiCadEnv] = None):
        self.env = kenv or _env.require()

    # ── introspection ────────────────────────────────────────────────
    def info(self) -> dict:
        d = self.env.as_dict()
        d["ipc_available"] = self.ipc_available()
        return d

    # ── raw cli ───────────────────────────────────────────────────────
    def cli(self, *args: str, timeout: int = 600) -> CliResult:
        cp = subprocess.run(
            [str(self.env.cli), *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return CliResult(cp.returncode == 0, cp.returncode, cp.stdout, cp.stderr, [])

    # ── SWIG worker (pcbnew) ──────────────────────────────────────────
    def _worker(self, *args: str, timeout: int = 300) -> dict:
        if not self.env.can_script:
            raise RuntimeError("KiCad bundled Python with pcbnew not found")
        try:
            cp = subprocess.run(
                [str(self.env.python), str(_WORKER), *args],
                capture_output=True, text=True, timeout=timeout,
                env=self._worker_env(),
            )
        except subprocess.TimeoutExpired:
            # A single pathological board (e.g. KiCad's tiny_tapeout: 150 fp on a
            # 178 mm board makes ExportSpecctraDSN run for many minutes) must not
            # crash the whole pipeline with an unhandled traceback. Report it as a
            # clean, catchable result so callers/batches keep going.
            return {"ok": False, "error": "worker timeout",
                    "op": args[0] if args else None, "timeout": timeout}
        out = (cp.stdout or "").strip()
        if not out:
            return {"ok": False, "error": "empty worker output", "stderr": cp.stderr}
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            return {"ok": False, "error": "bad worker json", "raw": out, "stderr": cp.stderr}

    def _worker_env(self) -> dict:
        import os
        e = dict(os.environ)
        if self.env.footprints:
            e["DAOKICAD_FP_DIR"] = str(self.env.footprints)
        return e

    def pcbnew_version(self) -> dict:
        return self._worker("version")

    @staticmethod
    def build_timeout_for(spec: dict) -> int:
        """Worker wall-clock budget (seconds) for a build, scaled to board size.

        A fixed 300s cap silently abandons large industrial boards: rebuilding
        vme-wren (1508 footprints / 6828 pads / 12 layers) needs to load and
        save a 68 MB board and overruns 300s. Give big boards proportionally
        more time (footprints, connections AND reconstructed routing all drive
        the cost), clamped to a sane ceiling so a genuinely stuck worker still
        fails."""
        fps = len(spec.get("footprints") or [])
        conns = len(spec.get("connections") or [])
        # reconstructed routing: each track/via is another board item to add.
        routing = len(spec.get("tracks") or []) + len(spec.get("vias") or [])
        return max(300, min(5400, fps + conns // 5 + routing // 20))

    def build_board(self, spec: dict, out_path: str | Path,
                    *, timeout: Optional[int] = None) -> dict:
        """Build a real .kicad_pcb from a declarative spec (二生三)."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                         encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False)
            spec_path = f.name
        try:
            return self._worker("build", spec_path, str(out_path),
                                timeout=timeout or self.build_timeout_for(spec))
        finally:
            Path(spec_path).unlink(missing_ok=True)

    def build_from_netlist(self, netlist: str | Path, out_path: str | Path,
                           *, layers: int = 2, project_dir: str | Path | None = None,
                           extra_spec: Optional[dict] = None) -> dict:
        """Build a real ``.kicad_pcb`` from an arbitrary KiCad ``.net`` file.

        The universal construction path: parse the schematic's netlist into the
        worker spec (library footprints + full net connectivity), then build.
        Placement falls back to the worker's grid; route with :meth:`autoroute`.
        ``extra_spec`` is shallow-merged so callers can add outline/zones/rules.
        """
        from . import fplib as _fplib
        from . import netlist as _nl

        spec = _nl.parse_netlist_file(netlist)
        warnings = spec.pop("warnings", [])
        spec["layers"] = layers
        # resolve project-local footprint libraries (fp-lib-table) so real
        # projects — not just standard-library parts — build.
        pdir = project_dir if project_dir is not None else Path(netlist).parent
        lib_dirs = _fplib.resolve_lib_dirs(pdir)
        if lib_dirs:
            spec["fp_lib_dirs"] = lib_dirs
        # real board engineering: route power/ground nets on a fatter Power
        # netclass (both KiCad and freerouting honour it). Caller-supplied
        # design_rules via extra_spec still win (merged below).
        pnets = _nl.power_nets(spec.get("nets", []))
        if pnets:
            spec.setdefault("design_rules", {}).setdefault("netclasses", [{
                "name": "Power", "track_width": 0.5,
                "via_size": 0.9, "via_drill": 0.45, "nets": pnets,
            }])
        if extra_spec:
            spec.update(extra_spec)
        if not spec.get("footprints"):
            return {"ok": False, "reason": "网表里没有可用封装(组件都未分配 footprint)",
                    "warnings": warnings}
        # auto-heal well-known KiCad library renames (e.g. connector
        # "..._Female_..." -> "..._Socket_...") so stale-but-valid real
        # projects still build; every substitution is reported in warnings.
        subs = self.heal_footprints(spec["footprints"], lib_dirs)
        for s in subs:
            warnings.append(
                f"封装名自动修正: {s['ref']} {s['lib']}:{s['from']} → {s['to']}")
        missing = self.missing_footprints(spec["footprints"], lib_dirs)
        if missing:
            return {"ok": False, "reason": "部分封装在库中找不到(请在原理图里换用库内封装)",
                    "missing": missing, "warnings": warnings,
                    "from_netlist": str(netlist)}
        res = self.build_board(spec, out_path)
        sk = res.get("skipped_connections") or []
        if sk:
            warnings.append(f"跳过 {len(sk)} 个无法连接的焊盘(封装缺该焊盘): "
                            + ", ".join(sk[:8]) + (" …" if len(sk) > 8 else ""))
        res["warnings"] = warnings
        res["from_netlist"] = str(netlist)
        return res

    def build_from_schematic(self, sch: str | Path, out_path: str | Path,
                             **kwargs) -> dict:
        """Build a board straight from a ``.kicad_sch`` (一步到板).

        Exports the schematic's netlist with ``kicad-cli`` (so project-local
        footprint libraries resolve against the schematic's own directory),
        then runs the universal :meth:`build_from_netlist` path.
        """
        sch = Path(sch)
        if not sch.is_file():
            return {"ok": False, "reason": f"原理图不存在: {sch}"}
        net = Path(out_path).with_suffix(".net")
        net.parent.mkdir(parents=True, exist_ok=True)
        cli = self.cli("sch", "export", "netlist", "--format", "kicadsexpr",
                       "-o", str(net), str(sch))
        if not cli.ok or not net.is_file():
            return {"ok": False, "reason": "kicad-cli 导出网表失败",
                    "stderr": cli.stderr, "from_schematic": str(sch)}
        kwargs.setdefault("project_dir", sch.parent)
        res = self.build_from_netlist(net, out_path, **kwargs)
        res["from_schematic"] = str(sch)
        return res

    # KiCad library gender renames are *directional* pairs, not a single
    # interchangeable class: a v6 rename turned connector "_Male_" into
    # "_Pins_" and "_Female_" into "_Socket_" (both directions seen in the
    # wild). Collapsing all of them to one key is ambiguous (Male would match
    # both Pins and Socket), so substitute each token for its specific synonym.
    _GENDER_SYNONYMS = (
        ("Male", "Pins"), ("Female", "Socket"),
        ("Pin", "Socket"),  # older single "_Pin_" → "_Socket_"
    )

    @classmethod
    def _gender_candidates(cls, name: str) -> list[str]:
        """All distinct names produced by swapping one gender token for its
        known synonym (both directions), case-insensitively."""
        out: list[str] = []
        for a, b in cls._GENDER_SYNONYMS:
            for x, y in ((a, b), (b, a)):
                pat = re.compile(rf"(?<![A-Za-z]){re.escape(x)}(?![A-Za-z])")
                cand = pat.sub(y, name)
                if cand != name and cand not in out:
                    out.append(cand)
        return out

    # Newer KiCad libraries dropped the explicit hand-solder pad-dimension
    # annotation that older names carried — e.g. the tantalum-cap rename
    # ``..._Kemet-B_Pad1.50x2.35mm_HandSolder`` → ``..._Kemet-B_HandSolder``
    # (the video demo regression). Removing a ``_Pad<W>x<H>mm`` token is a
    # high-confidence, directional repair: only a name that exists verbatim in
    # the library is accepted, so it can never invent a footprint.
    _PAD_DIM_RE = re.compile(r"_Pad[0-9.]+x[0-9.]+mm")

    @classmethod
    def _depad_candidates(cls, name: str) -> list[str]:
        """Names produced by removing pad-dimension annotation token(s)."""
        out: list[str] = []
        cand = cls._PAD_DIM_RE.sub("", name)
        if cand != name:
            out.append(cand)
        return out

    # Imperial chip-package code -> KiCad's metric body-size suffix. These are
    # the IPC-standard equivalences (0402 imperial == 1005 metric, ...), so the
    # remap is exact, not a guess.
    _IMP_TO_METRIC = {
        "0201": "0603Metric", "0402": "1005Metric", "0603": "1608Metric",
        "0805": "2012Metric", "1206": "3216Metric", "1210": "3225Metric",
        "1812": "4532Metric", "2010": "5025Metric", "2512": "6332Metric",
    }
    # EasyEDA / easyeda2kicad export the overwhelmingly-common chip passives as
    # bare ``C0402`` / ``R0805`` / ``L0603`` / ``LED0603`` in an ``easyeda2kicad``
    # library that the importing machine almost never has. Their geometry IS the
    # industry-standard chip package, so they map verbatim onto KiCad's stock
    # ``Capacitor_SMD`` / ``Resistor_SMD`` / ``Inductor_SMD`` / ``LED_SMD`` libs.
    _GENERIC_CHIP_RE = re.compile(r"^(C|R|L|LED)(0201|0402|0603|0805|1206|1210|1812|2010|2512)$")
    _GENERIC_CHIP_LIB = {
        "C": ("Capacitor_SMD", "C"), "R": ("Resistor_SMD", "R"),
        "L": ("Inductor_SMD", "L"), "LED": ("LED_SMD", "LED"),
    }

    # Metric body code (tenths-of-mm L+W, e.g. 3216 == 3.2x1.6mm) -> imperial.
    # Reverse of _IMP_TO_METRIC; lets us read IPC-7351 geometric names.
    _METRIC_TO_IMP = {
        "0603": "0201", "1005": "0402", "1608": "0603", "2012": "0805",
        "3216": "1206", "3225": "1210", "4532": "1812", "5025": "2010",
        "6332": "2512",
    }
    # IPC-7351 / Ultra-Librarian / SamacSys geometric chip names
    # (``CAPC3216X140N`` = chip cap 3.2x1.6mm body, 1.40mm tall). The CAPC/RESC/
    # INDC prefix + metric body code is an exact, standards-defined description
    # of a stock chip passive, so it maps verbatim onto KiCad's metric libs.
    _IPC_CHIP_RE = re.compile(r"^(CAPC|RESC|INDC)(\d{4})X\d+[A-Z]?$")
    _IPC_PREFIX = {"CAPC": "C", "RESC": "R", "INDC": "L"}

    # IPC-7351 polarized radial THT cap (``CAPPRB254-500X840`` = 2.54mm pitch,
    # 5.00mm body Ø, 8.40mm tall). Lead pitch and body Ø in hundredths-of-mm
    # fully fix KiCad's ``CP_Radial_D<Ø>mm_P<pitch>mm``; height is silk-only.
    _IPC_RADIAL_RE = re.compile(r"^CAP(?:PRD|PRB|PRR|AE|RR)(\d{3,4})-(\d{3,4})X\d+$")
    # 0.1-inch imperial pitches round to KiCad's metric radial grid.
    _RADIAL_PITCH = {"2.54": "2.50", "5.08": "5.00", "7.62": "7.50",
                     "10.16": "10.00"}
    # IPC-7351 small-outline IC (``SOIC127P600X175-8N`` = 1.27mm pitch, 6.00mm
    # lead span, 8 pins). At 1.27mm pitch a ~6mm span is the narrow 3.9mm body;
    # pin count fixes the body length in KiCad's stock ``Package_SO`` library.
    _IPC_SOIC_RE = re.compile(r"^SOIC127P(\d{3,4})X\d+-(\d+)N?$")
    _SOIC_NARROW_LEN = {"8": "4.9", "14": "8.7", "16": "9.9"}

    # IPC-7351 small-outline transistor (``SOT95P240X110-3N`` = 0.95mm pitch, 3
    # leads). Lead pitch + pin count name the part exactly: 0.95mm pitch is the
    # SOT-23 family, 0.65mm pitch is the SC-70 family — both in KiCad's stock
    # ``Package_TO_SOT_SMD``. Body span/height are silk-only.
    _IPC_SOT_RE = re.compile(r"^SOT(\d{2,3})P\d+X\d+-(\d+)N?$")
    _IPC_SOT_MAP = {
        "95": {"3": "SOT-23", "5": "SOT-23-5", "6": "SOT-23-6", "8": "SOT-23-8"},
        "65": {"3": "SOT-323_SC-70", "5": "SOT-353_SC-70-5",
               "6": "SOT-363_SC-70-6"},
    }

    # Discrete-package prefixes that EasyEDA emits with a trailing land-pattern
    # detail (``SOD-123_L2.7-W1.6-...``, ``SOT-23-6_L2.9-...``). The leading
    # token fully determines the standard KiCad footprint; the discarded suffix
    # is only silk/orientation detail that DRC/routing don't depend on.
    _GENERIC_PKG_RE = re.compile(
        r"^(SOD-(?:123|323|523)|SOT-23(?:-[0-9])?)(?:_|$)")
    _GENERIC_PKG_LIB = {"SOD": "Diode_SMD", "SOT": "Package_TO_SOT_SMD"}

    @classmethod
    def _generic_candidates(cls, name: str) -> list[tuple[str, str]]:
        """Map a generic/EasyEDA footprint name to KiCad-standard ``(lib, fp)``
        pairs. High-confidence, industry-standard package equivalences only —
        anything unrecognised yields nothing (so it is reported missing, never
        invented)."""
        m = cls._GENERIC_CHIP_RE.match(name)
        if m:
            lib, prefix = cls._GENERIC_CHIP_LIB[m.group(1)]
            size = m.group(2)
            return [(lib, f"{prefix}_{size}_{cls._IMP_TO_METRIC[size]}")]
        ipc = cls._IPC_CHIP_RE.match(name)
        if ipc:
            lib, prefix = cls._GENERIC_CHIP_LIB[cls._IPC_PREFIX[ipc.group(1)]]
            imp = cls._METRIC_TO_IMP.get(ipc.group(2))
            if imp:
                return [(lib, f"{prefix}_{imp}_{ipc.group(2)}Metric")]
        rad = cls._IPC_RADIAL_RE.match(name)
        if rad:
            pitch = f"{int(rad.group(1)) / 100:.2f}"
            dia = f"{int(rad.group(2)) / 100:.1f}"
            # try the KiCad metric-grid pitch first, then the verbatim value;
            # existence in heal_footprints picks whichever the lib actually has.
            pitches = [p for p in (cls._RADIAL_PITCH.get(pitch), pitch) if p]
            return [("Capacitor_THT", f"CP_Radial_D{dia}mm_P{p}mm")
                    for p in dict.fromkeys(pitches)]
        soic = cls._IPC_SOIC_RE.match(name)
        if soic:
            length = cls._SOIC_NARROW_LEN.get(soic.group(2))
            if length:
                return [("Package_SO",
                         f"SOIC-{soic.group(2)}_3.9x{length}mm_P1.27mm")]
        sot = cls._IPC_SOT_RE.match(name)
        if sot:
            fp = cls._IPC_SOT_MAP.get(sot.group(1), {}).get(sot.group(2))
            if fp:
                return [("Package_TO_SOT_SMD", fp)]
        p = cls._GENERIC_PKG_RE.match(name)
        if p:
            token = p.group(1)
            lib = cls._GENERIC_PKG_LIB[token[:3]]
            fp = token if token.startswith("SOT") else "D_" + token
            return [(lib, fp)]
        return []

    def _stock_fp_lib(self, fp_name: str):
        """Stock KiCad library that uniquely owns ``fp_name`` (or ``None``).

        Real projects (e.g. KiCad's jetson-agx-thor-baseboard demo) vendor every
        part into one private library — ``antmicro-footprints`` — whose ``.pretty``
        the distribution doesn't ship, so the cited lib can't resolve. But the
        footprint *names* are verbatim KiCad-stock names (``R_0402_1005Metric``,
        ``TP_SMD_0.75mm``). Index the install's stock libraries once (name -> lib)
        and, when a name is owned by exactly one stock lib, that lib is an exact,
        existence-proven home. Ambiguous names (in several libs) return ``None``
        so we never guess. The index is built lazily and cached per instance.
        """
        idx = getattr(self, "_stock_idx", None)
        if idx is None:
            import os
            idx = {}
            root = self.env.footprints
            try:
                pretties = [e for e in os.scandir(root)
                            if e.is_dir() and e.name.endswith(".pretty")]
            except OSError:
                pretties = []
            for pretty in pretties:
                lib = pretty.name[:-len(".pretty")]
                try:
                    for ent in os.scandir(pretty.path):
                        if ent.name.endswith(".kicad_mod"):
                            stem = ent.name[:-len(".kicad_mod")]
                            # mark ambiguous names (own >1 lib) as None
                            idx[stem] = None if stem in idx else lib
                except OSError:
                    continue
            self._stock_idx = idx
        return idx.get(fp_name)

    def heal_footprints(self, footprints: list[dict],
                        lib_dirs: Optional[dict] = None) -> list[dict]:
        """Repair footprints whose name was renamed in the library, in place.

        Five safe, high-confidence strategies. The first three repair a renamed
        entry *within the declared lib*; the last two remap across libraries when
        the declared lib itself is unavailable:
        1. **Gender-rename** (KiCad v6: ``_Female_``→``_Socket_``,
           ``_Male_``→``_Pins_``) — substitute the gender token for its
           specific synonym and accept a name that exists verbatim in the lib.
        2. **Pad-dimension drop** (newer libs dropped ``_Pad<W>x<H>mm`` from
           hand-solder names) — remove the token and accept a verbatim hit.
        3. **Near-identical** typo — a single ``difflib`` match at ratio ≥ 0.92.
        4. **Generic/EasyEDA chip remap** — bare ``C0402``/``R0805``/``LED0603``
           from an absent ``easyeda2kicad`` lib, plus IPC-7351 geometric names
           (``CAPC3216X140N``/``RESC3216X65N``) from vendor/Ultra-Librarian
           exports, map onto KiCad's stock ``Capacitor_SMD``/``Resistor_SMD``/…
           by the IPC imperial↔metric equivalence, accepted only if the target
           ``.kicad_mod`` really exists.
        5. **Stock-name relibrary** — when the cited lib is unavailable but the
           footprint's own name is a KiCad-stock name owned by exactly one
           install library (vendored libs like jetson's ``antmicro-footprints``),
           keep the name and fix only the library. Ambiguous names are left
           untouched so we never guess.

        Returns the list of substitutions made (``ref``/``lib``/``from``/``to``)
        so the caller can record them; footprints with their own ``pads`` or an
        exact library hit are left untouched.
        """
        import difflib

        from . import fplib as _fplib

        subs: list[dict] = []
        for f in footprints:
            if f.get("pads"):
                continue
            libdir = _fplib.footprint_dir(f["lib"], lib_dirs, self.env.footprints)
            in_lib = libdir.is_dir()
            if in_lib and (libdir / (f["fp"] + ".kicad_mod")).is_file():
                continue
            repl = None      # in-lib rename (fp only)
            remap = None     # cross-lib remap (lib, fp)
            if in_lib:
                names = [p.stem for p in libdir.glob("*.kicad_mod")]
                nameset = set(names)
                # 1) directional gender-synonym swap that hits an existing name
                hits = [c for c in self._gender_candidates(f["fp"]) if c in nameset]
                # 2) pad-dimension annotation drop that hits an existing name
                depad = [c for c in self._depad_candidates(f["fp"]) if c in nameset]
                if len(set(hits)) == 1:
                    repl = hits[0]
                elif len(set(depad)) == 1:
                    repl = depad[0]
                else:
                    # 3) near-identical typo (single high-confidence difflib match)
                    close = difflib.get_close_matches(f["fp"], names, n=1, cutoff=0.92)
                    if close:
                        repl = close[0]
            if not repl:
                # 4) cross-library generic/EasyEDA chip-package remap, accepted
                #    only when the standard target footprint genuinely exists.
                for cand_lib, cand_fp in self._generic_candidates(f["fp"]):
                    cdir = _fplib.footprint_dir(cand_lib, lib_dirs,
                                                self.env.footprints)
                    if (cdir / (cand_fp + ".kicad_mod")).is_file():
                        remap = (cand_lib, cand_fp)
                        break
                # 5) verbatim stock-name relibrary — the cited lib is unavailable
                #    but the footprint's own name is a KiCad-stock name owned by
                #    exactly one install library (vendored libs, e.g. jetson's
                #    ``antmicro-footprints``). Keep the name, fix only the lib.
                if not remap and not in_lib and f["lib"] not in (lib_dirs or {}):
                    stock = self._stock_fp_lib(f["fp"])
                    if stock and stock != f["lib"]:
                        remap = (stock, f["fp"])
            if remap:
                subs.append({"ref": f.get("ref"), "lib": f["lib"],
                             "from": f["fp"], "to": f"{remap[0]}:{remap[1]}"})
                f["lib"], f["fp"] = remap
            elif repl and repl != f["fp"]:
                subs.append({"ref": f.get("ref"), "lib": f["lib"],
                             "from": f["fp"], "to": repl})
                f["fp"] = repl
        return subs

    def missing_footprints(self, footprints: list[dict],
                           lib_dirs: Optional[dict] = None) -> list[dict]:
        """Return the specs whose ``lib:fp`` is absent from the library.

        ``lib_dirs`` (from :func:`daokicad.fplib.resolve_lib_dirs`) maps
        project-local nicknames to directories; anything else falls back to the
        install footprint dir. Each missing entry carries up to three closest
        in-library names so the caller can tell the user *what to use instead*.
        """
        import difflib

        from . import fplib as _fplib

        missing: list[dict] = []
        for f in footprints:
            if f.get("pads"):
                continue  # generated from scratch, no library needed
            libdir = _fplib.footprint_dir(f["lib"], lib_dirs, self.env.footprints)
            if (libdir / (f["fp"] + ".kicad_mod")).is_file():
                continue
            names = ([p.stem for p in libdir.glob("*.kicad_mod")]
                     if libdir.is_dir() else [])
            missing.append({
                "ref": f.get("ref"), "lib": f["lib"], "fp": f["fp"],
                "lib_exists": libdir.is_dir(),
                "suggestions": difflib.get_close_matches(f["fp"], names, n=3, cutoff=0.3),
            })
        return missing

    def summary(self, pcb: str | Path) -> dict:
        """Perceive: read back a board's state (感)."""
        return self._worker("summary", str(pcb))

    # ── autorouting via freerouting (二生三 的真布线器) ───────────────
    def export_dsn(self, pcb: str | Path, dsn: str | Path,
                   margin_nm: int = 0, *, timeout: int = 300) -> dict:
        return self._worker("dsn", str(pcb), str(dsn), str(margin_nm),
                            timeout=timeout)

    def import_ses(self, pcb: str | Path, ses: str | Path,
                   out: str | Path) -> dict:
        return self._worker("ses", str(pcb), str(ses), str(out))

    def read_tracks(self, pcb: str | Path, *, timeout: int = 120) -> dict:
        """Serialize a board's tracks + vias (nm coords) — used to reflect a
        freerouting result back onto the live IPC board."""
        return self._worker("tracks", str(pcb), timeout=timeout)

    def routing_available(self) -> bool:
        return _route.available()

    @staticmethod
    def _safe_stem(stem: str) -> str:
        """Filesystem stem safe to hand to freerouting's CLI: spaces and other
        shell-hostile characters break its input-file resolution (KiCad demo
        'sonde xilinx' routed to nothing until sanitised)."""
        return re.sub(r"[^A-Za-z0-9._-]+", "_", stem) or "board"

    @staticmethod
    def _inset_dsn_boundary(dsn: str | Path, clearance: int) -> bool:
        """Shrink an axis-aligned rectangular ``(boundary (path pcb 0 ...))`` in
        a Specctra DSN inward by ``clearance`` DSN units (µm), in pure text.

        Done on the file (no pcbnew) to avoid the SWIG board-mutation teardown
        hang. Only rectangles are reshaped — anything else is left untouched, so
        the worst case is the prior behaviour. Returns True if it reshaped.
        """
        clearance = int(clearance or 0)
        if clearance <= 0:
            return False
        dsn = Path(dsn)
        text = dsn.read_text(encoding="utf-8")
        m = re.search(r"\(boundary\s*\(path\s+pcb\s+\d+\s+(.*?)\)\s*\)",
                      text, re.DOTALL)
        if not m:
            return False
        nums = m.group(1).split()
        if len(nums) % 2 or len(nums) < 8:
            return False
        try:
            pts = [(float(nums[i]), float(nums[i + 1]))
                   for i in range(0, len(nums), 2)]
        except ValueError:
            return False
        xs = sorted({p[0] for p in pts})
        ys = sorted({p[1] for p in pts})
        # axis-aligned rectangle == exactly two distinct x and two distinct y
        if len(xs) != 2 or len(ys) != 2:
            return False
        if (xs[1] - xs[0]) <= 2 * clearance or (ys[1] - ys[0]) <= 2 * clearance:
            return False  # too small to inset safely
        xlo, xhi = xs[0] + clearance, xs[1] - clearance
        ylo, yhi = ys[0] + clearance, ys[1] - clearance
        def fix(v, lo_in, hi_in, lo_out, hi_out):
            return lo_out if v == lo_in else hi_out
        new_pts = [(fix(x, xs[0], xs[1], xlo, xhi),
                    fix(y, ys[0], ys[1], ylo, yhi)) for x, y in pts]
        body = "  ".join(f"{int(x)} {int(y)}" for x, y in new_pts)
        new_block = f"(boundary\n      (path pcb 0  {body})\n    )"
        text = text[:m.start()] + new_block + text[m.end():]
        dsn.write_text(text, encoding="utf-8")
        return True

    @staticmethod
    def route_timeout_for(nets: Optional[int]) -> int:
        """Freerouting wall-clock budget (seconds) scaled to board size.

        A fixed 600s budget silently abandons large boards (e.g. coldfire,
        279 nets, left fully unrouted). Give big boards proportionally more
        time, clamped to a sane ceiling."""
        n = nets or 0
        return max(600, min(2700, n * 10))

    def autoroute(self, pcb: str | Path, out: Optional[str | Path] = None, *,
                  margin_nm: int = 5000, passes: int = 10,
                  timeout: Optional[int] = None, seed: int = 0) -> dict:
        """Round-trip a placed board through freerouting -> routed board.

        margin_nm widens netclass clearance only in the DSN handed to the
        router, so freerouting keeps a hair of slack and the re-imported board
        still passes KiCad DRC. ``timeout`` (seconds) bounds freerouting; when
        ``None`` the router's own default applies. Big boards need more — see
        :func:`route_timeout_for`. ``seed`` picks a deterministic DSN ordering
        so retries can sample a different routing basin reproducibly.
        """
        pcb = Path(pcb)
        out = Path(out) if out else pcb
        safe = self._safe_stem(pcb.stem)
        dsn = pcb.with_name(safe + ".dsn")
        ses = pcb.with_name(safe + ".ses")
        # ExportSpecctraDSN cost scales super-linearly with board size; give it
        # at least the routing budget so a board that just needs longer than the
        # 300s default isn't cut off mid-export (it then reports a clean error).
        exp_to = max(300, timeout or 0)
        exp = self.export_dsn(pcb, dsn, margin_nm, timeout=exp_to)
        if not exp.get("ok"):
            return {"ok": False, "stage": "export_dsn", "detail": exp}
        # freerouting keeps only netclass clearance from the boundary it routes
        # against, which is below KiCad's copper_edge_clearance rule -> copper
        # lands too close to the edge (interf_u/stickhub DRC). Inset the DSN
        # boundary by that clearance so the routed copper stays legal.
        self._inset_dsn_boundary(dsn, exp.get("edge_clearance") or 0)
        kw = {"passes": passes, "seed": seed}
        if timeout is not None:
            kw["timeout"] = timeout
        rr = _route.route_dsn(dsn, ses, **kw)
        if not rr.ok:
            return {"ok": False, "stage": "freerouting", "reason": rr.reason,
                    "stderr": rr.stderr[-500:]}
        imp = self.import_ses(pcb, ses, out)
        return {"ok": bool(imp.get("ok")), "stage": "import_ses",
                "tracks": imp.get("tracks"), "ses": rr.ses, "path": str(out)}

    # ── verification (验) ─────────────────────────────────────────────
    def drc(self, pcb: str | Path, report: Optional[str | Path] = None,
            severity_error: bool = False) -> dict:
        pcb = Path(pcb)
        report = Path(report) if report else pcb.with_suffix(".drc.json")
        args = ["pcb", "drc", "--format", "json", "-o", str(report)]
        if severity_error:
            args.append("--severity-error")
        args.append(str(pcb))
        res = self.cli(*args)
        data: dict[str, Any] = {}
        if report.is_file():
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        viol = data.get("violations", [])
        unconnected = data.get("unconnected_items", [])
        errors = [v for v in viol if v.get("severity") == "error"]
        warnings = [v for v in viol if v.get("severity") == "warning"]
        # cleanliness gates on errors + real unconnected nets; warnings (e.g.
        # a from-scratch footprint's missing-library note) are reported but do
        # not block — exactly how a fab house treats them.
        return {
            "ok": res.ok,
            "violations": len(errors),
            "warnings": len(warnings),
            "unconnected": len(unconnected),
            "clean": len(errors) == 0 and len(unconnected) == 0,
            "report": str(report),
            "detail": data,
            "stdout": res.stdout.strip(),
        }

    def erc(self, sch: str | Path, report: Optional[str | Path] = None) -> dict:
        sch = Path(sch)
        report = Path(report) if report else sch.with_suffix(".erc.json")
        res = self.cli("sch", "erc", "--format", "json", "-o", str(report), str(sch))
        data = {}
        if report.is_file():
            try:
                data = json.loads(report.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        viol = data.get("violations", [])
        return {"ok": res.ok, "violations": len(viol), "report": str(report),
                "detail": data}

    # ── fabrication outputs (成器) ────────────────────────────────────
    def export_gerbers(self, pcb: str | Path, out_dir: str | Path) -> CliResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        res = self.cli("pcb", "export", "gerbers", "-o", str(out_dir) + "/", str(pcb))
        res.artifacts = sorted(out_dir.glob("*.g*"))
        return res

    def export_drill(self, pcb: str | Path, out_dir: str | Path) -> CliResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        res = self.cli("pcb", "export", "drill", "-o", str(out_dir) + "/", str(pcb))
        res.artifacts = sorted(out_dir.glob("*.drl"))
        return res

    def export_pos(self, pcb: str | Path, out_file: str | Path) -> CliResult:
        out_file = Path(out_file)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        res = self.cli("pcb", "export", "pos", "--format", "csv", "--units", "mm",
                       "-o", str(out_file), str(pcb))
        if out_file.is_file():
            res.artifacts = [out_file]
        return res

    def export_step(self, pcb: str | Path, out_file: str | Path) -> CliResult:
        out_file = Path(out_file)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        res = self.cli("pcb", "export", "step", "-o", str(out_file), str(pcb))
        if out_file.is_file():
            res.artifacts = [out_file]
        return res

    def render(self, pcb: str | Path, out_file: str | Path,
               side: str = "top") -> CliResult:
        out_file = Path(out_file)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        res = self.cli("pcb", "render", "--side", side, "-o", str(out_file), str(pcb))
        if out_file.is_file():
            res.artifacts = [out_file]
        return res

    def export_svg(self, pcb: str | Path, out_file: str | Path,
                   layers: str = "F.Cu,B.Cu,F.SilkS,Edge.Cuts,F.Mask",
                   timeout: int = 120) -> CliResult:
        """Fast 2D SVG snapshot of the board (no raytracing).

        Used by the live workspace to show the board updating after every
        agent step — orders of magnitude faster than ``render`` so the human
        sees the copper move in near real time (实时反馈).
        """
        out_file = Path(out_file)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        res = self.cli("pcb", "export", "svg", "--layers", layers,
                       "--page-size-mode", "2", "--exclude-drawing-sheet",
                       "-o", str(out_file), str(pcb), timeout=timeout)
        if out_file.is_file():
            res.artifacts = [out_file]
        return res

    # ── live bridge: hand a built board to the KiCad GUI ──────────────
    def open_in_editor(self, pcb: str | Path) -> dict:
        """Open ``pcb`` in the KiCad PCB editor GUI (the live bridge).

        The universal-construction path (the headless worker builds/routes a
        board) meets the human here: launch ``pcbnew`` on the freshly built
        file so the user sees and can keep editing it.

        Boundary (verified): KiCad's IPC API exposes no "open this file"
        action, and a launched ``pcbnew`` runs as its *own* instance — the API
        server stays bound to the editor it started in. So IPC fusion keeps
        driving whatever board is open in the API-connected instance; to also
        automate this freshly built board over IPC, open it *inside* that
        instance (File ▸ Open). This method is the human-facing bridge, not an
        IPC re-attach.
        """
        import subprocess

        pcb = Path(pcb)
        if not pcb.is_file():
            return {"ok": False, "reason": f"board not found: {pcb}"}
        exe = self.env.cli.parent / ("pcbnew.exe" if self.env.cli.suffix == ".exe"
                                     else "pcbnew")
        if not exe.is_file():
            return {"ok": False, "reason": f"pcbnew executable not found: {exe}"}
        try:
            subprocess.Popen([str(exe), str(pcb)])
        except Exception as e:
            return {"ok": False, "reason": f"无法启动 pcbnew: {e}"}
        return {"ok": True, "opened": str(pcb), "editor": str(exe)}

    # ── IPC channel (optional, live GUI) ──────────────────────────────
    def ipc_available(self) -> bool:
        try:
            from kipy import KiCad  # noqa: F401
        except Exception:
            return False
        try:
            from kipy import KiCad
            KiCad()
            return True
        except Exception:
            return False
