"""DAO KiCad IDE bridge — 单网页归一 REST 服务.

Expose the whole daokicad engine (render / netlist / build / route / DRC /
ERC / fab) over a small localhost REST API so any single-page IDE surface —
the bundled VS Code extension, Devin Desktop, a plain browser tab — can drive
KiCad natively without the user ever opening the KiCad GUI.

    python -m bridge.ide_server --port 9931

Design: stdlib-only (http.server), threaded, CORS-open for webviews. Slow
operations (build / route) run as jobs: POST returns ``{"job": id}``
immediately and ``GET /api/job?id=`` polls until ``done``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from daokicad.live import LiveKiCad

_LK: LiveKiCad | None = None
_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.Lock()


def _lk() -> LiveKiCad:
    global _LK
    if _LK is None:
        _LK = LiveKiCad()
    return _LK


# ── project discovery ─────────────────────────────────────────────────


def api_tree(root: str) -> dict:
    """List KiCad projects under ``root`` (each with its sch/pcb/net files)."""
    rootp = Path(root).expanduser()
    if not rootp.is_dir():
        return {"ok": False, "error": f"not a directory: {root}"}
    projects = []
    for pro in sorted(rootp.rglob("*.kicad_pro"))[:500]:
        d = pro.parent
        projects.append({
            "name": pro.stem,
            "dir": str(d),
            "sch": [str(p) for p in sorted(d.glob("*.kicad_sch"))],
            "pcb": [str(p) for p in sorted(d.glob("*.kicad_pcb"))],
            "net": [str(p) for p in sorted(d.glob("*.net"))],
        })
    return {"ok": True, "root": str(rootp), "projects": projects}


# ── rendering (原理图 / PCB → SVG) ─────────────────────────────────────


def api_render_sch(path: str) -> tuple[bytes, str] | dict:
    src = Path(path)
    if not src.is_file():
        return {"ok": False, "error": f"no such schematic: {path}"}
    with tempfile.TemporaryDirectory() as td:
        r = _lk().cli("sch", "export", "svg", "--no-background-color",
                      "-o", td, str(src))
        svgs = sorted(Path(td).glob("*.svg"))
        if not svgs:
            return {"ok": False, "error": r.stderr[-500:] or "no svg produced"}
        return svgs[0].read_bytes(), "image/svg+xml"


def api_render_pcb(path: str, layers: str) -> tuple[bytes, str] | dict:
    src = Path(path)
    if not src.is_file():
        return {"ok": False, "error": f"no such board: {path}"}
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "board.svg"
        r = _lk().export_svg(src, out, layers=layers)
        if not out.is_file():
            return {"ok": False, "error": r.stderr[-500:] or "no svg produced"}
        return out.read_bytes(), "image/svg+xml"


# ── engine actions ─────────────────────────────────────────────────────


def api_netlist(body: dict) -> dict:
    if not body.get("sch"):
        return {"ok": False, "error": "missing 'sch' (path to .kicad_sch)"}
    sch = Path(body["sch"])
    if not sch.is_file():
        return {"ok": False, "error": f"no such schematic: {sch}"}
    out = Path(body.get("out") or sch.with_suffix(".net"))
    r = _lk().cli("sch", "export", "netlist", "--format", "kicadsexpr",
                  "-o", str(out), str(sch))
    return {"ok": r.ok and out.is_file(), "net": str(out),
            "stderr": r.stderr[-500:]}


def api_build(body: dict) -> dict:
    lk = _lk()
    return lk.build_from_netlist(
        body["netlist"], body["out"],
        layers=int(body.get("layers") or 2),
        project_dir=body.get("project_dir"))


def api_route(body: dict) -> dict:
    kw: dict = {"passes": int(body.get("passes") or 10)}
    if body.get("timeout"):
        kw["timeout"] = int(body["timeout"])
    return _lk().autoroute(body["pcb"], body.get("out") or body["pcb"], **kw)


def api_drc(body: dict) -> dict:
    r = _lk().drc(body["pcb"])
    r.pop("detail", None)
    return r


def api_erc(body: dict) -> dict:
    r = _lk().erc(body["sch"])
    r.pop("detail", None)
    return r


def api_fab(body: dict) -> dict:
    pcb, out = body["pcb"], Path(body["out"])
    g = _lk().export_gerbers(pcb, out / "gerbers")
    d = _lk().export_drill(pcb, out / "gerbers")
    p = _lk().export_pos(pcb, out / "pos.csv")
    return {"ok": g.ok and d.ok and p.ok,
            "gerbers": [str(a) for a in (g.artifacts or [])],
            "drill": [str(a) for a in (d.artifacts or [])],
            "pos": [str(a) for a in (p.artifacts or [])]}


def _set_stage(jid: str | None, stage: str) -> None:
    if jid:
        with _JOBS_LOCK:
            j = _JOBS.get(jid)
            if j is not None:
                j["stage"] = stage


_CU_RE = re.compile(r'\(\s*\d+\s+"([^"]+\.Cu)"', re.M)


def _reference_layers(project_dir: Path) -> int | None:
    """Copper layer count of the project's shipped board, if any.

    When replicating a real project the original ``.kicad_pcb`` is the truth
    for stackup: routing a 4-layer design on the default 2 layers just
    manufactures unconnected ratlines.
    """
    best = None
    for b in sorted(project_dir.glob("*.kicad_pcb")):
        try:
            head = b.read_text(encoding="utf-8", errors="ignore")[:20000]
        except OSError:
            continue
        n = len({m.group(1) for m in _CU_RE.finditer(head)})
        if n >= 2:
            best = max(best or 0, n)
    return best


def api_auto(body: dict, jid: str | None = None) -> dict:
    """One-shot closed loop: sch|netlist -> build -> route -> DRC [-> fab].

    The whole design-automation cycle a human would click through, run as a
    single job with live ``stage`` progress (一键闭环, 无为而无不为).
    """
    steps: dict[str, Any] = {}
    if body.get("sch") and not body.get("netlist"):
        _set_stage(jid, "netlist")
        n = api_netlist({"sch": body["sch"]})
        steps["netlist"] = n
        if not n["ok"]:
            return {"ok": False, "stage": "netlist", "steps": steps}
        body["netlist"] = n["net"]
    net = Path(body["netlist"])
    pcb = str(body.get("out") or net.with_name(net.stem + "_dao.kicad_pcb"))
    _set_stage(jid, "build")
    pdir = body.get("project_dir") or str(net.parent)
    layers = body.get("layers") or _reference_layers(Path(pdir))
    b = api_build({"netlist": str(net), "out": pcb, "layers": layers,
                   "project_dir": pdir})
    steps["build"] = b
    if not b.get("ok"):
        return {"ok": False, "stage": "build", "steps": steps}
    _set_stage(jid, "route")
    # Board-scaled routing budget: a fixed default silently abandons big
    # boards (a 682-net laptop motherboard needs far more than 600s).
    timeout = (int(body["timeout"]) if body.get("timeout")
               else _lk().route_timeout_for(b.get("nets")))
    r = api_route({"pcb": pcb, "passes": body.get("passes") or 10,
                   "timeout": timeout})
    steps["route"] = r
    if not r.get("ok"):
        return {"ok": False, "stage": "route", "steps": steps, "pcb": pcb}
    _set_stage(jid, "drc")
    d = api_drc({"pcb": pcb})
    steps["drc"] = d
    # Escalating finisher (same policy as the CLI): freerouting occasionally
    # leaves a few ratlines on a dense board. Retry with more passes into a
    # candidate board and adopt it only when DRC strictly improves, so the
    # board can never get worse than the first pass.
    if d.get("ok") and d.get("unconnected", 0) > 0:
        lk = _lk()
        pcbp = Path(pcb)
        retry_timeout = max(300, int(body.get("timeout") or 0)
                            or lk.route_timeout_for(steps["build"].get("nets")) // 2)
        passes = int(body.get("passes") or 10)
        while d.get("unconnected", 0) > 0 and passes < 32:
            passes += 12
            _set_stage(jid, f"finish(passes={passes})")
            cand = pcbp.with_name(pcbp.stem + ".retry.kicad_pcb")
            retry = lk.autoroute(pcbp, cand, passes=passes,
                                 timeout=retry_timeout)
            if not retry.get("ok"):
                break
            cand_drc = api_drc({"pcb": str(cand)})
            better = (cand_drc.get("unconnected", 0) < d.get("unconnected", 0)
                      and cand_drc.get("violations", 0) <= d.get("violations", 0))
            if better:
                shutil.move(str(cand), str(pcbp))
                rep = cand.with_suffix(".drc.json")
                if rep.is_file():
                    shutil.move(str(rep), str(pcbp.with_suffix(".drc.json")))
                d = cand_drc
                d["report"] = str(pcbp.with_suffix(".drc.json"))
                steps["drc"] = d
                steps["route"] = {**steps["route"],
                                  "tracks": retry.get("tracks"),
                                  "finish_passes": passes}
            else:
                cand.unlink(missing_ok=True)
        cand = pcbp.with_name(pcbp.stem + ".retry.kicad_pcb")
        cand.unlink(missing_ok=True)
        cand.with_suffix(".drc.json").unlink(missing_ok=True)
    if body.get("fab"):
        _set_stage(jid, "fab")
        steps["fab"] = api_fab({"pcb": pcb,
                                "out": str(Path(pcb).with_suffix("")) + "_fab"})
    return {"ok": bool(d.get("clean")), "pcb": pcb, "clean": d.get("clean"),
            "steps": steps}


_ACTIONS = {"netlist": api_netlist, "build": api_build, "route": api_route,
            "drc": api_drc, "erc": api_erc, "fab": api_fab, "auto": api_auto}
_SLOW = {"build", "route", "fab", "auto"}

_CAPABILITIES = {
    "service": "dao-kicad-ide",
    "description": "REST bridge to the DAO-KiCad engine: schematic/PCB "
                   "rendering, netlist->board build, freerouting autoroute, "
                   "DRC/ERC, fabrication outputs, one-shot auto pipeline.",
    "doc": "/api/doc",
    "tools": [
        {"method": "GET", "path": "/api/health", "params": {},
         "doc": "Service + KiCad availability/version."},
        {"method": "GET", "path": "/api/tree", "params": {"root": "dir"},
         "doc": "Discover KiCad projects (sch/pcb/net files) under root."},
        {"method": "GET", "path": "/api/render/sch",
         "params": {"path": ".kicad_sch"}, "doc": "Schematic as SVG."},
        {"method": "GET", "path": "/api/render/pcb",
         "params": {"path": ".kicad_pcb", "layers": "csv, optional"},
         "doc": "Board as SVG."},
        {"method": "POST", "path": "/api/netlist",
         "params": {"sch": ".kicad_sch", "out": "optional .net"},
         "doc": "Schematic -> netlist."},
        {"method": "POST", "path": "/api/build", "job": True,
         "params": {"netlist": ".net", "out": ".kicad_pcb",
                    "layers": "int=2", "project_dir": "optional"},
         "doc": "Netlist -> placed board (footprint auto-healing included)."},
        {"method": "POST", "path": "/api/route", "job": True,
         "params": {"pcb": ".kicad_pcb", "passes": "int=10",
                    "timeout": "secs, optional"},
         "doc": "Autoroute via freerouting (DSN->SES round-trip)."},
        {"method": "POST", "path": "/api/drc",
         "params": {"pcb": ".kicad_pcb"}, "doc": "KiCad DRC."},
        {"method": "POST", "path": "/api/erc",
         "params": {"sch": ".kicad_sch"}, "doc": "KiCad ERC."},
        {"method": "POST", "path": "/api/fab", "job": True,
         "params": {"pcb": ".kicad_pcb", "out": "dir"},
         "doc": "Gerbers + drill + placement CSV."},
        {"method": "POST", "path": "/api/auto", "job": True,
         "params": {"sch": "or netlist", "netlist": "or sch",
                    "out": "optional .kicad_pcb", "layers": "int=2",
                    "passes": "int=10", "timeout": "secs, optional",
                    "fab": "bool=false"},
         "doc": "Full closed loop: netlist->build->route->DRC[->fab]."},
        {"method": "GET", "path": "/api/job", "params": {"id": "job id"},
         "doc": "Poll a job: {done, stage?, result?}."},
    ],
}


def _run_job(jid: str, fn, body: dict) -> None:
    try:
        res = fn(body, jid) if fn is api_auto else fn(body)
    except Exception as e:  # surfaced to the client, never crashes the server
        res = {"ok": False, "error": f"{type(e).__name__}: {e}",
               "trace": traceback.format_exc()[-1000:]}
    with _JOBS_LOCK:
        _JOBS[jid] = {"done": True, "result": res}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self._send_raw(data, "application/json", code)

    def _send_raw(self, data: bytes, ctype: str, code=200):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        self.wfile.write(data)

    def _read_body(self) -> bytes:
        """Read a request body sent either with Content-Length or chunked.

        Node/fetch clients stream JSON with ``Transfer-Encoding: chunked``
        (no Content-Length), which a naive read would see as an empty body.
        """
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            out = b""
            while True:
                size = int(self.rfile.readline().split(b";")[0].strip(), 16)
                if size == 0:
                    self.rfile.readline()
                    return out
                out += self.rfile.read(size)
                self.rfile.readline()
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n)

    def do_OPTIONS(self):
        self._send_raw(b"", "text/plain", 204)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/health":
                e = _lk().env
                return self._send({"ok": True, "kicad": e.version,
                                   "cli": str(e.cli) if e.cli else None,
                                   "service": "dao-kicad-ide"})
            if u.path == "/api/tree":
                return self._send(api_tree(q.get("root", ".")))
            if u.path == "/api/render/sch":
                r = api_render_sch(q.get("path", ""))
                if isinstance(r, dict):
                    return self._send(r, 400)
                return self._send_raw(*r)
            if u.path == "/api/render/pcb":
                layers = q.get("layers",
                               "F.Cu,B.Cu,F.SilkS,Edge.Cuts,F.Mask")
                r = api_render_pcb(q.get("path", ""), layers)
                if isinstance(r, dict):
                    return self._send(r, 400)
                return self._send_raw(*r)
            if u.path == "/api/capabilities":
                return self._send(_CAPABILITIES)
            if u.path == "/api/doc":
                doc = Path(__file__).with_name("AGENT_BRIDGE.md")
                if doc.is_file():
                    return self._send_raw(doc.read_bytes(),
                                          "text/markdown; charset=utf-8")
                return self._send({"ok": False, "error": "doc missing"}, 404)
            if u.path == "/api/job":
                with _JOBS_LOCK:
                    j = _JOBS.get(q.get("id", ""))
                return self._send(j or {"done": False, "unknown": True})
            return self._send({"ok": False, "error": "not found"}, 404)
        except Exception as e:
            return self._send({"ok": False,
                               "error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        u = urlparse(self.path)
        name = u.path.rsplit("/", 1)[-1]
        fn = _ACTIONS.get(name) if u.path.startswith("/api/") else None
        if fn is None:
            return self._send({"ok": False, "error": "not found"}, 404)
        try:
            raw = self._read_body()
            body = json.loads(raw or b"{}")
        except Exception as e:
            return self._send({"ok": False, "error": f"bad json: {e}"}, 400)
        try:
            if name in _SLOW:
                jid = uuid.uuid4().hex[:12]
                with _JOBS_LOCK:
                    _JOBS[jid] = {"done": False}
                threading.Thread(target=_run_job, args=(jid, fn, body),
                                 daemon=True).start()
                return self._send({"ok": True, "job": jid})
            return self._send(fn(body))
        except KeyError as e:
            return self._send({"ok": False, "error": f"missing field {e}"}, 400)
        except Exception as e:
            return self._send({"ok": False,
                               "error": f"{type(e).__name__}: {e}"}, 500)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9931)
    a = ap.parse_args(argv)
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"dao-kicad-ide bridge on http://{a.host}:{a.port}", flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
