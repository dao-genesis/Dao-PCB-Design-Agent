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
import tempfile
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
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
    sch = Path(body["sch"])
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


_ACTIONS = {"netlist": api_netlist, "build": api_build, "route": api_route,
            "drc": api_drc, "erc": api_erc, "fab": api_fab}
_SLOW = {"build", "route", "fab"}


def _run_job(jid: str, fn, body: dict) -> None:
    try:
        res = fn(body)
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

    def do_OPTIONS(self):
        self._send_raw(b"", "text/plain", 204)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            if u.path == "/api/health":
                v = _lk().pcbnew_version()
                return self._send({"ok": True, "kicad": v.get("version"),
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
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
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
