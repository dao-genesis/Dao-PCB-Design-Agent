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
import time
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from daokicad.live import LiveKiCad

from bridge import tools as daotools
from bridge.brain import (api_brain_bom, api_brain_design, api_brain_guardian,
                          api_brain_intent, api_brain_pipeline,
                          api_brain_templates, api_brain_wugan)
from bridge.native import (api_ipc_board, api_ipc_run, api_ipc_status,
                           api_native_module, api_native_open,
                           api_native_start, api_native_status,
                           api_native_stop)

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
    syms = [str(p) for p in sorted(rootp.rglob("*.kicad_sym"))[:200]]
    fps = [str(p) for p in sorted(rootp.rglob("*.pretty"))[:200] if p.is_dir()]
    env = _lk().env
    if env.symbols and env.symbols.is_dir():
        syms += [str(p) for p in sorted(env.symbols.glob("*.kicad_sym"))]
    if env.footprints and env.footprints.is_dir():
        fps += [str(p) for p in sorted(env.footprints.glob("*.pretty")) if p.is_dir()]
    return {"ok": True, "root": str(rootp), "projects": projects,
            "sym_libs": syms, "fp_libs": fps}


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


def api_render_sym(lib: str, name: str) -> tuple[bytes, str] | dict:
    """Render one symbol of a .kicad_sym library to SVG (符号编辑器视图)."""
    src = Path(lib)
    if not src.is_file():
        return {"ok": False, "error": f"no such symbol lib: {lib}"}
    with tempfile.TemporaryDirectory() as td:
        args = ["sym", "export", "svg", "-o", td]
        if name:
            args += ["--symbol", name]
        r = _lk().cli(*args, str(src))
        svgs = sorted(Path(td).glob("*.svg"))
        if not svgs:
            return {"ok": False, "error": r.stderr[-500:] or "no svg produced"}
        return svgs[0].read_bytes(), "image/svg+xml"


def api_render_fp(lib: str, name: str) -> tuple[bytes, str] | dict:
    """Render one footprint of a .pretty library to SVG (封装编辑器视图)."""
    src = Path(lib)
    if not src.is_dir():
        return {"ok": False, "error": f"no such footprint lib: {lib}"}
    with tempfile.TemporaryDirectory() as td:
        args = ["fp", "export", "svg", "-o", td]
        if name:
            args += ["--footprint", name]
        r = _lk().cli(*args, str(src))
        svgs = sorted(Path(td).glob("*.svg"))
        if not svgs:
            return {"ok": False, "error": r.stderr[-500:] or "no svg produced"}
        pick = next((s for s in svgs if s.stem == name), svgs[0])
        return pick.read_bytes(), "image/svg+xml"


_SYM_RE = re.compile(r'\(symbol\s+"([^"]+)"')
_SYM_UNIT_RE = re.compile(r'_\d+_\d+$')


def api_sym_list(lib: str) -> dict:
    src = Path(lib)
    if not src.is_file():
        return {"ok": False, "error": f"no such symbol lib: {lib}"}
    names = [n for n in _SYM_RE.findall(src.read_text(errors="replace"))
             if ":" not in n and "_" != n[:1] and not _SYM_UNIT_RE.search(n)]
    return {"ok": True, "lib": str(src), "symbols": sorted(set(names))}


def api_fp_list(lib: str) -> dict:
    src = Path(lib)
    if not src.is_dir():
        return {"ok": False, "error": f"no such footprint lib: {lib}"}
    return {"ok": True, "lib": str(src),
            "footprints": sorted(p.stem for p in src.glob("*.kicad_mod"))}


_FILE_EXT = {".gbr", ".gbl", ".gtl", ".gba", ".gta", ".gbs", ".gts", ".gbo",
             ".gto", ".gbp", ".gtp", ".gm1", ".drl", ".csv", ".net", ".rpt",
             ".json", ".pos", ".txt", ".md", ".kicad_mod"}


def api_file(path: str) -> tuple[bytes, str] | dict:
    """Read a fabrication/text artifact (Gerber 查看器等板块的文本直读)."""
    src = Path(path)
    if src.suffix.lower() not in _FILE_EXT:
        return {"ok": False, "error": f"unsupported file type: {src.suffix}"}
    if not src.is_file():
        return {"ok": False, "error": f"no such file: {path}"}
    if src.stat().st_size > 2_000_000:
        return {"ok": False, "error": "file too large (>2MB)"}
    return src.read_bytes(), "text/plain; charset=utf-8"


# ── KiCad 启动器板块本源 (工程文件树 / 图框 / 图片转换 / 扩展内容管理) ──
# 对齐 KiCad 工程管理器: 左侧工程文件树 + 九大编辑器入口, 内容全部取自 KiCad 本体.

_TREE_SKIP = {".git", "__pycache__", "node_modules", ".venv", "venv",
              "-backups", ".pcm_cache"}


def api_files(root: str) -> dict:
    """工程文件树 — 对齐 KiCad 工程管理器左侧「工程文件」窗格."""
    rootp = Path(root).expanduser()
    if not rootp.is_dir():
        return {"ok": False, "error": f"not a directory: {root}"}

    def walk(d: Path, depth: int) -> list:
        out = []
        try:
            entries = sorted(d.iterdir(),
                             key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return out
        for p in entries[:400]:
            if p.name.startswith(".") or any(s in p.name for s in _TREE_SKIP):
                continue
            if p.is_dir():
                node = {"name": p.name, "path": str(p), "dir": True}
                if depth < 6:
                    node["children"] = walk(p, depth + 1)
                out.append(node)
            else:
                out.append({"name": p.name, "path": str(p), "dir": False,
                            "ext": p.suffix.lower()})
        return out

    return {"ok": True, "root": str(rootp), "tree": walk(rootp, 0)}


def api_wks_list(root: str) -> dict:
    """图框 (.kicad_wks) 一览: 工程内 + KiCad 系统模板目录."""
    found: list[str] = []
    rootp = Path(root).expanduser() if root else None
    if rootp and rootp.is_dir():
        found += [str(p) for p in sorted(rootp.rglob("*.kicad_wks"))[:100]]
    for sysdir in ("/usr/share/kicad/template",
                   "C:/Program Files/KiCad/9.0/share/kicad/template",
                   "D:/KICAD/share/kicad/template",
                   str(Path.home() / ".local/share/kicad")):
        d = Path(sysdir)
        if d.is_dir():
            found += [str(p) for p in sorted(d.rglob("*.kicad_wks"))[:100]]
    seen: list[str] = []
    for f in found:
        if f not in seen:
            seen.append(f)
    return {"ok": True, "sheets": seen}


_BLANK_SCH = ('(kicad_sch (version 20231120) (generator "dao")\n'
              '  (uuid "00000000-0000-0000-0000-000000000000")'
              ' (paper "A4"))\n')


def api_render_wks(path: str) -> tuple[bytes, str] | dict:
    """图框编辑器视图: 用 KiCad 本体在空原理图上渲染工作表."""
    wks = Path(path)
    if not wks.is_file():
        return {"ok": False, "error": f"no such drawing sheet: {path}"}
    with tempfile.TemporaryDirectory() as td:
        blank = Path(td) / "blank.kicad_sch"
        blank.write_text(_BLANK_SCH, encoding="utf-8")
        r = _lk().cli("sch", "export", "svg", "--no-background-color",
                      "--drawing-sheet", str(wks), "-o", td, str(blank))
        svgs = sorted(Path(td).glob("*.svg"))
        if not svgs:
            return {"ok": False, "error": r.stderr[-500:] or "no svg produced"}
        return svgs[0].read_bytes(), "image/svg+xml"


def api_convert(body: dict) -> dict:
    """图片转换器: 位图 → KiCad 原生 .kicad_mod / .kicad_sym (多边形走线).

    与 KiCad bitmap2component 同源思路: 阈值化 → 行程合并为矩形填充区.
    """
    import base64 as _b64
    try:
        from PIL import Image
    except ImportError:
        return {"ok": False, "error": "需要 Pillow: pip install pillow"}
    raw = body.get("image_b64") or ""
    if "," in raw[:80]:
        raw = raw.split(",", 1)[1]
    try:
        data = _b64.b64decode(raw)
    except Exception as e:
        return {"ok": False, "error": f"bad image_b64: {e}"}
    import io
    img = Image.open(io.BytesIO(data)).convert("L")
    if img.width > 400:
        img = img.resize((400, max(1, img.height * 400 // img.width)))
    thr = int(body.get("threshold") or 128)
    invert = bool(body.get("invert"))
    mm = float(body.get("mm_per_px") or 0.1)
    px = img.load()
    name = re.sub(r"[^\w.-]", "_", body.get("name") or "dao_image") or "img"
    kind = body.get("format") or "fp"
    layer = body.get("layer") or "F.SilkS"
    rects = []
    for y in range(img.height):
        x = 0
        while x < img.width:
            on = (px[x, y] < thr) != invert
            if on:
                x0 = x
                while x < img.width and ((px[x, y] < thr) != invert):
                    x += 1
                rects.append((x0, y, x, y + 1))
            else:
                x += 1
    if not rects:
        return {"ok": False, "error": "阈值下没有前景像素, 调整 threshold/invert"}
    if kind == "sym":
        polys = "".join(
            f'    (polyline (pts (xy {x0*mm:.3f} {-y0*mm:.3f}) '
            f'(xy {x1*mm:.3f} {-y0*mm:.3f}) (xy {x1*mm:.3f} {-y1*mm:.3f}) '
            f'(xy {x0*mm:.3f} {-y1*mm:.3f}) (xy {x0*mm:.3f} {-y0*mm:.3f}))\n'
            f'      (stroke (width 0)) (fill (type outline)))\n'
            for x0, y0, x1, y1 in rects)
        text = (f'(kicad_symbol_lib (version 20231120) (generator "dao")\n'
                f'  (symbol "{name}" (in_bom no) (on_board no)\n'
                f'   (symbol "{name}_0_1"\n{polys}   )))\n')
        fname = f"{name}.kicad_sym"
    else:
        polys = "".join(
            f'  (fp_poly (pts (xy {x0*mm:.3f} {y0*mm:.3f}) '
            f'(xy {x1*mm:.3f} {y0*mm:.3f}) (xy {x1*mm:.3f} {y1*mm:.3f}) '
            f'(xy {x0*mm:.3f} {y1*mm:.3f}))\n'
            f'    (stroke (width 0) (type solid)) (fill solid) '
            f'(layer "{layer}"))\n'
            for x0, y0, x1, y1 in rects)
        text = (f'(footprint "{name}" (version 20240108) (generator "dao")\n'
                f'  (layer "F.Cu") (attr board_only exclude_from_pos_files '
                f'exclude_from_bom)\n{polys})\n')
        fname = f"{name}.kicad_mod"
    out = body.get("out")
    saved = None
    if out:
        outp = Path(out).expanduser()
        outp.mkdir(parents=True, exist_ok=True)
        (outp / fname).write_text(text, encoding="utf-8")
        saved = str(outp / fname)
    return {"ok": True, "name": fname, "rects": len(rects),
            "saved": saved, "content": text if len(text) < 400_000 else None}


# ── 扩展内容管理器 (对齐 KiCad PCM: 官方仓库 + 已安装 3rdparty) ──

_PCM_REPO = "https://repository.kicad.org/repository.json"
_PCM_CACHE: dict[str, Any] = {}


def _pcm_dir() -> Path:
    for c in (Path.home() / ".local/share/kicad",
              Path.home() / "Documents/KiCad"):
        if c.is_dir():
            vers = sorted((p for p in c.iterdir()
                           if re.match(r"\d+\.\d+", p.name)), reverse=True)
            if vers:
                return vers[0] / "3rdparty"
    return Path.home() / ".local/share/kicad/9.0/3rdparty"


_UA = {"User-Agent": "KiCad/9.0 dao-kicad-ide"}


def _http_json(url: str) -> Any:
    import urllib.request
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def api_pcm_list(_q: dict | None = None) -> dict:
    base = _pcm_dir()
    installed = []
    for kind in ("plugins", "symbols", "footprints", "templates", "colors"):
        d = base / kind
        if d.is_dir():
            installed += [{"id": p.name, "kind": kind, "path": str(p)}
                          for p in sorted(d.iterdir()) if p.is_dir()]
    remote = _PCM_CACHE.get("packages")
    if remote is None:
        try:
            repo = _http_json(_PCM_REPO)
            pk = _http_json(repo["packages"]["url"])
            remote = [{"id": p["identifier"], "name": p["name"],
                       "type": p["type"],
                       "description": p.get("description", "")[:200],
                       "versions": [v.get("version") for v in
                                    p.get("versions", [])][:3]}
                      for p in pk.get("packages", [])]
            _PCM_CACHE["packages"] = remote
            _PCM_CACHE["raw"] = {p["identifier"]: p
                                 for p in pk.get("packages", [])}
        except Exception as e:
            remote = []
            _PCM_CACHE.setdefault("error", str(e))
    return {"ok": True, "dir": str(base), "installed": installed,
            "repository": remote, "repo_error": _PCM_CACHE.get("error")}


def api_pcm_install(body: dict) -> dict:
    ident = body.get("id") or ""
    api_pcm_list()
    pkg = (_PCM_CACHE.get("raw") or {}).get(ident)
    if not pkg:
        return {"ok": False, "error": f"unknown package: {ident}"}
    vers = pkg.get("versions") or []
    ver = next((v for v in vers if v.get("download_url")), None)
    if not ver:
        return {"ok": False, "error": "package has no downloadable version"}
    import io
    import urllib.request
    import zipfile
    req = urllib.request.Request(ver["download_url"], headers=_UA)
    with urllib.request.urlopen(req, timeout=300) as r:
        blob = r.read()
    safe = ident.replace(".", "_")
    base = _pcm_dir()
    extracted = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for m in z.namelist():
            parts = Path(m).parts
            if not parts or m.endswith("/") or ".." in parts:
                continue
            top = parts[0]
            if top == "metadata.json":
                continue
            dest = base / top / safe / Path(*parts[1:])
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(m))
            extracted.append(str(dest))
    return {"ok": True, "id": ident, "version": ver.get("version"),
            "files": len(extracted), "dir": str(base)}


def api_pcm_remove(body: dict) -> dict:
    ident = (body.get("id") or "").replace(".", "_")
    base = _pcm_dir()
    removed = []
    for kind in ("plugins", "symbols", "footprints", "templates", "colors"):
        d = base / kind / ident
        if d.is_dir():
            shutil.rmtree(d)
            removed.append(str(d))
    if not removed:
        return {"ok": False, "error": f"not installed: {body.get('id')}"}
    return {"ok": True, "removed": removed}


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


def _alias_path(body) -> None:
    """路径字段互通: path ↔ pcb/sch (按后缀), 外部调用者不必背每个端点的字段名."""
    if not isinstance(body, dict):
        return
    p = body.get("path")
    if isinstance(p, str) and p:
        key = {"kicad_pcb": "pcb", "kicad_sch": "sch"}.get(
            Path(p).suffix.lstrip("."))
        if key and not body.get(key):
            body[key] = p
    if not body.get("path"):
        alt = body.get("pcb") or body.get("sch")
        if isinstance(alt, str) and alt:
            body["path"] = alt


def api_drc(body: dict) -> dict:
    r = _lk().drc(body["pcb"])
    r.pop("detail", None)
    return r


def api_erc(body: dict) -> dict:
    r = _lk().erc(body["sch"])
    r.pop("detail", None)
    return r


def api_fab(body: dict) -> dict:
    pcb = body["pcb"]
    out = Path(body.get("out") or Path(pcb).parent / "fab")
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
        # Tail stitcher: close the last few same-net gaps with clearance-checked
        # direct/L tracks (the stubs a human closes by hand). Same DRC guard.
        if d.get("unconnected", 0) > 0:
            _set_stage(jid, "stitch")
            cand = pcbp.with_name(pcbp.stem + ".stitch.kicad_pcb")
            st = lk.stitch(pcbp, cand)
            if st.get("ok") and st.get("added"):
                cand_drc = api_drc({"pcb": str(cand)})
                if (cand_drc.get("unconnected", 0) < d.get("unconnected", 0)
                        and cand_drc.get("violations", 0)
                        <= d.get("violations", 0)):
                    shutil.move(str(cand), str(pcbp))
                    rep = cand.with_suffix(".drc.json")
                    if rep.is_file():
                        shutil.move(str(rep), str(pcbp.with_suffix(".drc.json")))
                    d = cand_drc
                    d["report"] = str(pcbp.with_suffix(".drc.json"))
                    steps["drc"] = d
                    steps["route"] = {**steps["route"],
                                      "stitched": st.get("added")}
            cand.unlink(missing_ok=True)
            cand.with_suffix(".drc.json").unlink(missing_ok=True)
    if body.get("fab"):
        _set_stage(jid, "fab")
        steps["fab"] = api_fab({"pcb": pcb,
                                "out": str(Path(pcb).with_suffix("")) + "_fab"})
    return {"ok": bool(d.get("clean")), "pcb": pcb, "clean": d.get("clean"),
            "steps": steps}


# \b sits between two word chars when CJK text abuts an English keyword
# ("跑个ERC"), so keyword isolation uses ASCII-letter lookarounds instead.
def _kw(*words: str) -> re.Pattern:
    alts = "|".join(f"(?<![a-zA-Z]){w}(?![a-zA-Z])" if w.isascii() else w
                    for w in words)
    return re.compile(alts, re.I)


_INTENTS = [
    ("auto", _kw("全链路", "闭环", "复刻", "一键", "auto")),
    ("erc", _kw("erc", "电气规则", "原理图检查")),
    ("drc", _kw("drc", "设计规则", "板子检查")),
    ("route", _kw("布线", "走线", "route")),
    ("build", _kw("建板", "搭板", "build")),
    ("netlist", _kw("网表", "netlist")),
    ("fab", _kw("制造", "生产", "gerber", "fab")),
]

_PATH_RE = re.compile(r"[\w~./\\:-]+\.(?:kicad_sch|kicad_pcb|net)\b")

# 对话直驱底层意图 — 全部落在 KiCad 原生板块的同一份内存文档上,
# 用户在本体前端实时看到每一步变动 (不经 GUI 表层, 经官方 IPC)。
_BRAIN_INTENTS = [
    ("design", _kw("生成", "搭建工程", "design")),
    ("guardian", _kw("守护", "风险", "guardian")),
    ("wugan", _kw("五感", "wugan")),
    ("bom", _kw("bom", "成本", "物料")),
]
_IPC_INTENTS = [
    ("add_track", _kw("铜线", "track")),
    ("add_via", _kw("过孔", "via")),
    ("move_footprint", _kw("移件", "移动封装")),
    ("refill_zones", _kw("铺铜", "refill")),
    ("save", _kw("保存", "save")),
]
_ALL_INTENTS = _INTENTS + _IPC_INTENTS + _BRAIN_INTENTS
_XY_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*[,\uff0c]\s*(-?\d+(?:\.\d+)?)")
_REF_RE = re.compile(r"\b([A-Z]{1,4}\d{1,4})\b")


def _native_show(pcb: str) -> dict:
    """确保产物板在本体原生前端可见 (已开着则不重复开)."""
    try:
        st = api_native_status({})
        name = Path(pcb).name
        if any(name in (w.get("title") or "")
               for w in st.get("windows", [])):
            return {"ok": True, "already_open": True}
        if not st.get("live"):
            return api_native_start({"path": pcb})
        return api_native_open({"path": pcb})
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def _agent_brain(op: str, text: str) -> dict:
    """对话→智枢: 意图解析选模板→生成/守护/五感/BOM; 生成后自动在本体打开."""
    r = api_brain_intent({"text": text})
    tpl = r.get("template")
    if not tpl:
        return {"ok": False, "action": op,
                "reply": "没识别到 DNA 模板 — 把需求说具体些 (如: 生成 无人机飞控)。"}
    fn = {"design": api_brain_design, "guardian": api_brain_guardian,
          "wugan": api_brain_wugan, "bom": api_brain_bom}[op]
    res = fn({"template": tpl})
    pcb = res.get("pcb_path") or res.get("pcb")
    native = None
    if op == "design" and pcb:
        native = _native_show(pcb)
    reply = f"{op}({tpl}) 完成。"
    if pcb:
        reply += f"\n已在本体原生板块打开: {pcb}"
    return {"ok": bool(res.get("ok")), "action": op, "template": tpl,
            "result": res, "pcb": pcb, "native": native, "reply": reply}


def _agent_ipc(op: str, text: str) -> dict:
    """对话→IPC 直驱: 落在本体活动文档上, 原生前端实时可见."""
    body: dict = {"op": op}
    m = _PATH_RE.search(text)
    if m and m.group(0).endswith(".kicad_pcb"):
        body["board"] = m.group(0)
    xys = [(float(a), float(b)) for a, b in _XY_RE.findall(text)]
    if op == "add_track":
        if len(xys) < 2:
            return {"ok": False, "action": op,
                    "reply": "铜线要两个坐标, 如: 铜线 10,20 到 30,20"}
        body["start"], body["end"] = list(xys[0]), list(xys[1])
    elif op == "add_via":
        if not xys:
            return {"ok": False, "action": op,
                    "reply": "过孔要一个坐标, 如: 过孔 25,30"}
        body["at"] = list(xys[0])
    elif op == "move_footprint":
        ref = _REF_RE.search(text)
        if not (ref and xys):
            return {"ok": False, "action": op,
                    "reply": "移件要位号和坐标, 如: 移件 C1 到 12,18"}
        body["ref"], body["at"] = ref.group(1), list(xys[0])
    res = api_ipc_run(body)
    reply = (f"{op} 已经底层 IPC 落在本体活动文档上, 前端实时可见。"
             if res.get("ok") else f"{op} 失败: {res.get('error')}")
    return {"ok": bool(res.get("ok")), "action": op, "result": res,
            "reply": reply}


def _agent_paths(text: str, root: str | None) -> dict[str, str]:
    """Resolve schematic/board/netlist paths cited (or implied) by a chat turn.

    Explicit paths in the message win; otherwise the workspace root is scanned
    and a lone match per kind is used — the copilot UX is "just say 全链路",
    not "paste absolute paths".
    """
    out: dict[str, str] = {}
    kinds = {".kicad_sch": "sch", ".kicad_pcb": "pcb", ".net": "netlist"}
    for m in _PATH_RE.finditer(text):
        p = Path(m.group(0)).expanduser()
        if not p.is_absolute() and root:
            p = Path(root) / p
        if p.is_file():
            out.setdefault(kinds[p.suffix], str(p))
    if root and Path(root).is_dir():
        for suf, kind in kinds.items():
            if kind in out:
                continue
            found = [p for p in sorted(Path(root).rglob(f"*{suf}"))
                     if "_dao" not in p.name][:2]
            if len(found) == 1:
                out[kind] = str(found[0])
    return out


# ── AI 管理 (对齐 devin-remote Proxy Pro 本源: 渠道配置 / 模型路由 / 对话数据) ──
# 底层全部替换为 KiCad 板块路由: 意图词直达引擎, 其余经第三方 OpenAI 兼容渠道。

_DAO_DIR = Path.home() / ".dao"
_AI_CFG = _DAO_DIR / "kicad_ai.json"
_CHATS = _DAO_DIR / "kicad_chats.json"
_STORE_LOCK = threading.Lock()


def _store_read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def _store_write(p: Path, obj) -> None:
    _DAO_DIR.mkdir(exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def _mask(key: str) -> str:
    return key[:4] + "…" + key[-4:] if len(key) > 10 else "…"


def api_ai_config_get(_q: dict) -> dict:
    with _STORE_LOCK:
        cfg = _store_read(_AI_CFG, {"channels": [], "active": "", "system": ""})
    chans = [{**c, "key": _mask(c.get("key", ""))} for c in cfg.get("channels", [])]
    accts = [{**a, "token": _mask(a.get("token", ""))}
             for a in cfg.get("accounts", [])]
    return {"ok": True, "channels": chans, "active": cfg.get("active", ""),
            "accounts": accts, "active_account": cfg.get("active_account", ""),
            "system": cfg.get("system", "")}


def api_ai_config(body: dict) -> dict:
    with _STORE_LOCK:
        cfg = _store_read(_AI_CFG, {"channels": [], "active": "", "system": ""})
        op = body.get("op", "")
        if op == "add":
            ch = {"name": body.get("name", "").strip(),
                  "endpoint": body.get("endpoint", "").rstrip("/"),
                  "key": body.get("key", ""), "model": body.get("model", "")}
            if not (ch["name"] and ch["endpoint"]):
                return {"ok": False, "error": "渠道需要 name + endpoint"}
            cfg["channels"] = [c for c in cfg["channels"] if c["name"] != ch["name"]]
            cfg["channels"].append(ch)
            if not cfg.get("active"):
                cfg["active"] = ch["name"]
        elif op == "del":
            cfg["channels"] = [c for c in cfg["channels"]
                               if c["name"] != body.get("name")]
            if cfg.get("active") == body.get("name"):
                cfg["active"] = cfg["channels"][0]["name"] if cfg["channels"] else ""
        elif op == "activate":
            cfg["active"] = body.get("name", "")
        elif op == "system":
            cfg["system"] = body.get("system", "")
        elif op == "acct_add":
            a = {"name": body.get("name", "").strip(),
                 "email": body.get("email", "").strip(),
                 "token": body.get("token", "")}
            if not a["name"]:
                return {"ok": False, "error": "账号需要 name"}
            cfg["accounts"] = [x for x in cfg.get("accounts", [])
                               if x["name"] != a["name"]]
            cfg["accounts"].append(a)
            if not cfg.get("active_account"):
                cfg["active_account"] = a["name"]
        elif op == "acct_del":
            cfg["accounts"] = [x for x in cfg.get("accounts", [])
                               if x["name"] != body.get("name")]
            if cfg.get("active_account") == body.get("name"):
                accts = cfg.get("accounts", [])
                cfg["active_account"] = accts[0]["name"] if accts else ""
        elif op == "acct_use":
            cfg["active_account"] = body.get("name", "")
        else:
            return {"ok": False, "error": f"unknown op: {op}"}
        _store_write(_AI_CFG, cfg)
    return api_ai_config_get({})


def api_chat_list(_q: dict) -> dict:
    with _STORE_LOCK:
        chats = _store_read(_CHATS, {"chats": []})["chats"]
    return {"ok": True, "chats": [{"id": c["id"], "title": c.get("title", ""),
                                   "ts": c.get("ts", 0), "n": len(c.get("messages", []))}
                                  for c in chats]}


def api_chat_get(q: dict) -> dict:
    with _STORE_LOCK:
        chats = _store_read(_CHATS, {"chats": []})["chats"]
    c = next((c for c in chats if c["id"] == q.get("id")), None)
    return {"ok": bool(c), "chat": c} if c else {"ok": False, "error": "no such chat"}


def api_chat_del(body: dict) -> dict:
    with _STORE_LOCK:
        store = _store_read(_CHATS, {"chats": []})
        if body.get("all"):
            store["chats"] = []
        else:
            store["chats"] = [c for c in store["chats"] if c["id"] != body.get("id")]
        _store_write(_CHATS, store)
    return {"ok": True, "n": len(store["chats"])}


def _chat_append(chat_id: str, title_hint: str, msgs: list) -> str:
    with _STORE_LOCK:
        store = _store_read(_CHATS, {"chats": []})
        c = next((c for c in store["chats"] if c["id"] == chat_id), None)
        if c is None:
            c = {"id": chat_id or uuid.uuid4().hex[:12],
                 "title": title_hint[:40], "ts": int(time.time()), "messages": []}
            store["chats"].append(c)
        c["messages"] += msgs
        c["ts"] = int(time.time())
        store["chats"] = store["chats"][-100:]
        _store_write(_CHATS, store)
        return c["id"]


_AI_SYSTEM = ("你是 DAO KiCad 归一面板的 AI 助手, 底层是 KiCad 原生引擎的 REST 桥。"
              "你拥有一套 function-calling 工具 (对照 Devin Desktop 工具体系): "
              "渲染/网表/建板/布线/DRC/ERC/制造/全链路/本体 IPC 直驱/DNA 生成/"
              "扩展管理/PCB 领域网络搜索。需要动引擎或查资料时直接调用工具; "
              "慢操作会返回 {job}, 用 job_status 轮询。回答用中文, 简洁专业。")

_TOOL_ROUNDS = 6  # function-calling 循环上限 (对照 Devin Desktop agent loop)


def _chat_endpoint(ch: dict) -> str:
    url = ch["endpoint"]
    if not url.endswith("/chat/completions"):
        url = url.rstrip("/") + "/chat/completions"
    return url


def _llm_post(ch: dict, msgs: list, with_tools: bool) -> dict:
    import urllib.request
    body: dict = {"model": ch.get("model") or "gpt-4o-mini", "messages": msgs}
    if with_tools:
        body["tools"] = daotools.tools_payload()
    payload = json.dumps(body, ensure_ascii=True).encode()
    req = urllib.request.Request(_chat_endpoint(ch), data=payload,
                                 method="POST", headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + ch.get("key", "")})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read())


def _llm_call(ch: dict, system: str, history: list, text: str,
              trace: list | None = None) -> str:
    """对话补全 + 工具调用循环: 模型可自主调 KiCad 工具驱动引擎.

    渠道不支持 tools 时自动回退纯对话 (400/422 → 无工具重发)。
    """
    msgs = [{"role": "system", "content": system or _AI_SYSTEM}]
    msgs += [{"role": m["role"], "content": m["content"]} for m in history[-20:]]
    msgs.append({"role": "user", "content": text})
    with_tools = True
    for _ in range(_TOOL_ROUNDS):
        try:
            out = _llm_post(ch, msgs, with_tools)
        except Exception:
            if not with_tools:
                raise
            with_tools = False  # 渠道不支持 function-calling → 纯对话回退
            out = _llm_post(ch, msgs, False)
        m = out["choices"][0]["message"]
        calls = m.get("tool_calls") or []
        if not calls:
            return m.get("content") or ""
        msgs.append(m)
        for tc in calls:
            name, args = daotools.parse_tool_call(tc)
            res = daotools.call(name, args)
            if trace is not None:
                trace.append({"tool": name, "args": args,
                              "ok": bool(isinstance(res, dict)
                                         and res.get("ok"))})
            msgs.append({"role": "tool",
                         "tool_call_id": tc.get("id", ""),
                         "content": json.dumps(res, ensure_ascii=False)[:8000]})
    return "(工具循环达到上限, 已停止)"


def api_ai_chat(body: dict) -> dict:
    """AI 对话归一入口: 意图词 → KiCad 引擎直达; 其余 → 第三方渠道 (Proxy Pro 式路由)。

    对话全量沉淀到 ~/.dao/kicad_chats.json (对话数据管理)。
    """
    text = (body.get("text") or "").strip()
    if not text:
        return {"ok": False, "reply": "说点什么吧。"}
    chat_id = body.get("chat_id") or ""
    if next((a for a, rx in _ALL_INTENTS if rx.search(text)), None):
        res = api_agent(body)
        cid = _chat_append(chat_id, text,
                           [{"role": "user", "content": text},
                            {"role": "assistant", "content": res.get("reply", "")}])
        return {**res, "chat_id": cid, "via": "kicad-engine"}
    with _STORE_LOCK:
        cfg = _store_read(_AI_CFG, {"channels": [], "active": "", "system": ""})
    ch = next((c for c in cfg["channels"] if c["name"] == cfg.get("active")), None)
    if ch is None:
        res = api_agent(body)
        cid = _chat_append(chat_id, text,
                           [{"role": "user", "content": text},
                            {"role": "assistant", "content": res.get("reply", "")}])
        return {**res, "chat_id": cid, "via": "kicad-engine"}
    with _STORE_LOCK:
        chats = _store_read(_CHATS, {"chats": []})["chats"]
    prev = next((c for c in chats if c["id"] == chat_id), None)
    history = prev["messages"] if prev else []
    trace: list = []
    try:
        reply = _llm_call(ch, cfg.get("system", ""), history, text, trace)
    except Exception as e:
        return {"ok": False, "reply": f"渠道 {ch['name']} 调用失败: {e}",
                "via": "channel:" + ch["name"]}
    cid = _chat_append(chat_id, text,
                       [{"role": "user", "content": text},
                        {"role": "assistant", "content": reply}])
    return {"ok": True, "reply": reply, "chat_id": cid,
            "tools": trace, "via": "channel:" + ch["name"]}


def api_agent(body: dict) -> dict:
    """Copilot-style chat turn: natural language in, chain actions out.

    Deterministic intent routing into the same handlers the REST endpoints
    use — the dialog box is just another face of the one bridge (归一).
    Slow actions come back as ``{job}`` for the caller to poll via /api/job.
    """
    text = (body.get("text") or "").strip()
    if not text:
        return {"ok": False, "reply": "说点什么吧 — 例如“对这个工程跑全链路”、“ERC”、“布线”。"}
    action = next((a for a, rx in _INTENTS if rx.search(text)), None)
    if action is None:
        ipc_op = next((a for a, rx in _IPC_INTENTS if rx.search(text)), None)
        if ipc_op:
            return _agent_ipc(ipc_op, text)
        brain_op = next((a for a, rx in _BRAIN_INTENTS if rx.search(text)),
                        None)
        if brain_op:
            return _agent_brain(brain_op, text)
        tools = ", ".join(a for a, _ in _ALL_INTENTS)
        return {"ok": True, "reply": f"我能直接干的活: {tools}。"
                                     "把意图说出来(可带文件路径), 我路由到引擎。"}
    paths = _agent_paths(text, body.get("root"))
    req: dict = {}
    need = {"auto": ["sch"], "erc": ["sch"], "netlist": ["sch"],
            "build": ["netlist"], "route": ["pcb"], "drc": ["pcb"],
            "fab": ["pcb"]}[action]
    for k in need:
        if k not in paths:
            return {"ok": False, "action": action,
                    "reply": f"要跑 {action} 需要 {k} 文件。工作区里没找到唯一候选,"
                             " 把路径直接写在消息里即可。"}
        req[k] = paths[k]
    if action == "build":
        req["out"] = str(Path(req["netlist"]).with_suffix("")) + "_dao.kicad_pcb"
    if action == "auto":
        req["fab"] = bool(re.search(r"制造|gerber|fab", text, re.I))
    raw = _ACTIONS[action]

    def fn(r, _raw=raw):
        res = _raw(r)
        pcb = res.get("pcb") or (res.get("steps", {}).get("build") or {}).get("path") if isinstance(res, dict) else None
        if pcb:
            res["native"] = _native_show(pcb)
        return res

    if action in _SLOW:
        jid = uuid.uuid4().hex[:12]
        with _JOBS_LOCK:
            _JOBS[jid] = {"done": False}
        threading.Thread(target=_run_job, args=(jid, fn, req),
                         daemon=True).start()
        return {"ok": True, "action": action, "job": jid, "request": req,
                "reply": f"{action} 已启动 (job {jid}), 轮询 /api/job 到出结果。"}
    res = fn(req)
    return {"ok": bool(res.get("ok")), "action": action, "result": res,
            "reply": f"{action} 完成。"}


# 底层突破: KiCad 底座本身也可由桥自行挂载 (tools/install_kicad.py) ——
# 用户只装插件, 缺引擎时一键落地, 无需预装任何版本的 KiCad。


def _install_kicad_module():
    import importlib.util
    path = Path(__file__).resolve().parents[1] / "tools" / "install_kicad.py"
    spec = importlib.util.spec_from_file_location("install_kicad", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def api_engine_status(q: dict | None = None) -> dict:
    from daokicad import env as kenv
    kenv.detect.cache_clear()
    e = kenv.detect()
    mode = "absent"
    if e.available:
        mounted = any(str(m) in str(e.root or "")
                      for m in kenv._mount_roots())
        mode = "mounted" if mounted else "system"
        if not e.version:
            mode = "broken"    # cli found but not answering — remount to heal
    return {"ok": True, "mode": mode, **e.as_dict()}


def api_engine_mount(body: dict) -> dict:
    global _LK
    mod = _install_kicad_module()
    res = mod.ensure_kicad(body.get("version") or mod.DEFAULT_VERSION,
                           bool(body.get("force")))
    _LK = None  # rebuild LiveKiCad against the freshly mounted engine
    return res


def _tool_job(fn) -> Any:
    """慢工具 → 后台 job (与 POST 慢端点同一套 _JOBS 机制)."""
    def run(body: dict) -> dict:
        jid = uuid.uuid4().hex[:12]
        with _JOBS_LOCK:
            _JOBS[jid] = {"done": False}
        threading.Thread(target=_run_job, args=(jid, fn, body),
                         daemon=True).start()
        return {"ok": True, "job": jid,
                "note": "慢操作已后台启动, 用 job_status 轮询"}
    return run


def _tool_job_status(a: dict) -> dict:
    with _JOBS_LOCK:
        j = _JOBS.get(a.get("id", ""))
    return j or {"done": False, "unknown": True}


def _register_tools() -> None:
    """工具名 → handler 注入 (对照 Devin Desktop 工具注册表)."""
    reg = daotools.register
    reg("engine_status", api_engine_status)
    reg("engine_mount", _tool_job(api_engine_mount))
    reg("project_tree", lambda a: api_tree(a.get("root", ".")))
    reg("project_files", lambda a: api_files(a.get("root", ".")))
    reg("read_artifact", lambda a: api_file(a.get("path", "")))
    reg("render_schematic", lambda a: api_render_sch(a.get("path", "")))
    reg("render_pcb", lambda a: api_render_pcb(
        a.get("path", ""),
        a.get("layers") or "F.Cu,B.Cu,F.SilkS,Edge.Cuts,F.Mask"))
    reg("render_symbol", lambda a: api_render_sym(a.get("lib", ""),
                                                  a.get("name", "")))
    reg("render_footprint", lambda a: api_render_fp(a.get("lib", ""),
                                                    a.get("name", "")))
    reg("list_symbols", lambda a: api_sym_list(a.get("lib", "")))
    reg("list_footprints", lambda a: api_fp_list(a.get("lib", "")))
    reg("netlist", api_netlist)
    reg("build_board", _tool_job(api_build))
    reg("autoroute", _tool_job(api_route))
    reg("drc", api_drc)
    reg("erc", api_erc)
    reg("fabricate", _tool_job(api_fab))
    reg("auto_pipeline", _tool_job(api_auto))
    reg("job_status", _tool_job_status)
    reg("native_status", api_native_status)
    reg("native_start", api_native_start)
    reg("native_open", api_native_open)
    reg("native_module", api_native_module)
    reg("native_stop", api_native_stop)
    reg("ipc_status", api_ipc_status)
    reg("ipc_board", api_ipc_board)
    reg("ipc_run", api_ipc_run)
    reg("brain_templates", api_brain_templates)
    reg("brain_design", api_brain_design)
    reg("brain_guardian", api_brain_guardian)
    reg("brain_wugan", api_brain_wugan)
    reg("brain_bom", api_brain_bom)
    reg("pcm_list", api_pcm_list)
    reg("pcm_install", api_pcm_install)
    reg("pcm_remove", api_pcm_remove)
    reg("image_convert", api_convert)
    reg("web_search", daotools.api_search)


_register_tools()


def api_tools_call(body: dict) -> dict:
    return daotools.call(body.get("name", ""), body.get("args") or {})


_ACTIONS = {"netlist": api_netlist, "build": api_build, "route": api_route,
            "drc": api_drc, "erc": api_erc, "fab": api_fab, "auto": api_auto,
            "agent": api_agent, "chat": api_ai_chat, "config": api_ai_config,
            "del": api_chat_del, "convert": api_convert,
            "install": api_pcm_install, "remove": api_pcm_remove,
            "mount": api_engine_mount}
_SLOW = {"build", "route", "fab", "auto", "mount"}

# 全路径 POST 路由 (KiCad 软件本体承接 + IPC 底层直连)
_POST_PATHS = {"/api/tools/call": api_tools_call,
               "/api/search": daotools.api_search,
               "/api/native/start": api_native_start,
               "/api/native/open": api_native_open,
               "/api/native/module": api_native_module,
               "/api/native/stop": api_native_stop,
               "/api/ipc/run": api_ipc_run,
               "/api/brain/intent": api_brain_intent,
               "/api/brain/design": api_brain_design,
               "/api/brain/guardian": api_brain_guardian,
               "/api/brain/wugan": api_brain_wugan,
               "/api/brain/bom": api_brain_bom,
               "/api/brain/pipeline": api_brain_pipeline}

_CAPABILITIES = {
    "service": "dao-kicad-ide",
    "description": "REST bridge to the DAO-KiCad engine: schematic/PCB "
                   "rendering, netlist->board build, freerouting autoroute, "
                   "DRC/ERC, fabrication outputs, one-shot auto pipeline.",
    "doc": "/api/doc",
    "tools": [
        {"method": "GET", "path": "/api/engine/status", "params": {},
         "desc": "resolved KiCad engine locations (cli/python/libs)"},
        {"method": "POST", "path": "/api/engine/mount", "job": True,
         "params": {"version": "KiCad version (Windows installer)",
                    "force": "remount even if already available"},
         "desc": "mount a self-contained KiCad runtime under tools/kicad"},
        {"method": "GET", "path": "/api/health", "params": {},
         "doc": "Service + KiCad availability/version."},
        {"method": "GET", "path": "/api/tree", "params": {"root": "dir"},
         "doc": "Discover KiCad projects (sch/pcb/net files) under root."},
        {"method": "GET", "path": "/api/files", "params": {"root": "dir"},
         "doc": "工程文件树 (对齐 KiCad 工程管理器左侧窗格)."},
        {"method": "GET", "path": "/api/wks/list", "params": {"root": "dir"},
         "doc": "图框 (.kicad_wks) 一览: 工程内 + KiCad 系统模板."},
        {"method": "GET", "path": "/api/render/wks",
         "params": {"path": ".kicad_wks"},
         "doc": "图框编辑器视图: KiCad 本体渲染工作表为 SVG."},
        {"method": "POST", "path": "/api/convert",
         "params": {"image_b64": "png/jpg", "format": "fp|sym",
                    "name": "...", "threshold": "0-255", "invert": "bool",
                    "mm_per_px": "float=0.1", "layer": "F.SilkS",
                    "out": "optional dir"},
         "doc": "图片转换器: 位图 → KiCad 原生 .kicad_mod/.kicad_sym."},
        {"method": "GET", "path": "/api/pcm/list", "params": {},
         "doc": "扩展内容管理器: 官方仓库 + 已安装 3rdparty 包."},
        {"method": "POST", "path": "/api/pcm/install",
         "params": {"id": "package identifier"},
         "doc": "从官方 PCM 仓库安装扩展包."},
        {"method": "POST", "path": "/api/pcm/remove",
         "params": {"id": "package identifier"},
         "doc": "卸载已安装扩展包."},
        {"method": "GET", "path": "/api/render/sch",
         "params": {"path": ".kicad_sch"}, "doc": "Schematic as SVG."},
        {"method": "GET", "path": "/api/render/pcb",
         "params": {"path": ".kicad_pcb", "layers": "csv, optional"},
         "doc": "Board as SVG."},
        {"method": "GET", "path": "/api/render/sym",
         "params": {"lib": ".kicad_sym", "name": "symbol, optional"},
         "doc": "Symbol (符号编辑器视图) as SVG."},
        {"method": "GET", "path": "/api/render/fp",
         "params": {"lib": ".pretty dir", "name": "footprint, optional"},
         "doc": "Footprint (封装编辑器视图) as SVG."},
        {"method": "GET", "path": "/api/sym/list",
         "params": {"lib": ".kicad_sym"},
         "doc": "List symbols inside a symbol library."},
        {"method": "GET", "path": "/api/fp/list",
         "params": {"lib": ".pretty dir"},
         "doc": "List footprints inside a footprint library."},
        {"method": "GET", "path": "/api/file",
         "params": {"path": "gerber/drill/csv/net/report file"},
         "doc": "Read a fabrication/text artifact (Gerber 查看器)."},
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
        {"method": "POST", "path": "/api/agent",
         "params": {"text": "natural language", "root": "workspace dir"},
         "doc": "Copilot chat turn: intent-routed into the endpoints above; "
                "slow actions return {job}."},
        {"method": "GET", "path": "/api/job", "params": {"id": "job id"},
         "doc": "Poll a job: {done, stage?, result?}."},
        {"method": "POST", "path": "/api/ai/chat",
         "params": {"text": "message", "chat_id": "optional", "root": "dir"},
         "doc": "归一 AI 对话: 意图词直达 KiCad 引擎, 其余经激活的第三方渠道; "
                "对话沉淀可管理."},
        {"method": "GET", "path": "/api/ai/config", "params": {},
         "doc": "AI 渠道配置 (key 脱敏)."},
        {"method": "POST", "path": "/api/ai/config",
         "params": {"op": "add|del|activate|system", "name": "...",
                    "endpoint": "OpenAI 兼容 base", "key": "...", "model": "..."},
         "doc": "渠道配置管理 (Proxy Pro 式)."},
        {"method": "GET", "path": "/api/chat/list", "params": {},
         "doc": "对话数据管理: 列出沉淀的对话."},
        {"method": "GET", "path": "/api/chat/get", "params": {"id": "chat id"},
         "doc": "读取一条对话全量消息."},
        {"method": "POST", "path": "/api/chat/del",
         "params": {"id": "chat id", "all": "bool"},
         "doc": "删除一条/全部对话."},
        {"method": "GET", "path": "/api/native/status", "params": {},
         "doc": "KiCad 软件本体会话状态: xpra 窗口协议路由 + IPC socket + 窗口清单."},
        {"method": "POST", "path": "/api/native/start",
         "params": {"path": "optional .kicad_pro/.kicad_sch/.kicad_pcb"},
         "doc": "启动 KiCad 本体(xpra 会话内), 窗口协议级路由到 HTML5 客户端; 同时开启 IPC API."},
        {"method": "POST", "path": "/api/native/open",
         "params": {"path": "file to open"},
         "doc": "在运行中的 KiCad 本体里打开文件/工程."},
        {"method": "POST", "path": "/api/native/module",
         "params": {"module": "kicad|eeschema|pcbnew|gerbview|pcb_calculator|"
                              "bitmap2component|pl_editor",
                    "path": "optional file"},
         "doc": "拉起指定 KiCad 原生模块 (归一面板标签直达)."},
        {"method": "POST", "path": "/api/native/stop", "params": {},
         "doc": "停止 KiCad 本体会话."},
        {"method": "GET", "path": "/api/tools/catalog", "params": {},
         "doc": "工具清单 (OpenAI function-calling 格式, 1:1 对照 Devin Desktop 工具体系)."},
        {"method": "POST", "path": "/api/tools/call",
         "params": {"name": "工具名 (含别名)", "args": "工具参数 object"},
         "doc": "按名直调任意工具; 慢工具返回 {job}."},
        {"method": "GET", "path": "/api/search",
         "params": {"query": "搜索词", "max_results": "int=8"},
         "doc": "PCB 领域网络搜索 (元器件/datasheet/封装/参考设计)."},
        {"method": "GET", "path": "/api/ipc/status", "params": {},
         "doc": "IPC 底层直连状态 (kicad-python ping/version)."},
        {"method": "GET", "path": "/api/ipc/board", "params": {},
         "doc": "活动 PCB 文档全息 (与 GUI 同一份内存文档): nets/footprints/tracks/vias."},
        {"method": "POST", "path": "/api/ipc/run",
         "params": {"op": "action|save|refill_zones", "name": "action name"},
         "doc": "agent 直驱 KiCad 本体: 执行动作/保存/重灸铺铜 — 不经 GUI."},
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
            if u.path in ("/", "/index.html", "/webui.html"):
                page = Path(__file__).with_name("webui.html")
                if page.is_file():
                    return self._send_raw(page.read_bytes(),
                                          "text/html; charset=utf-8")
                return self._send({"ok": False, "error": "webui missing"}, 404)
            if u.path == "/api/health":
                e = _lk().env
                return self._send({"ok": True, "kicad": e.version,
                                   "cli": str(e.cli) if e.cli else None,
                                   "service": "dao-kicad-ide"})
            if u.path == "/api/engine/status":
                return self._send(api_engine_status(q))
            if u.path == "/api/tree":
                return self._send(api_tree(q.get("root", ".")))
            if u.path == "/api/files":
                return self._send(api_files(q.get("root", ".")))
            if u.path == "/api/wks/list":
                return self._send(api_wks_list(q.get("root", "")))
            if u.path == "/api/render/wks":
                r = api_render_wks(q.get("path", ""))
                if isinstance(r, dict):
                    return self._send(r, 400)
                return self._send_raw(*r)
            if u.path == "/api/pcm/list":
                return self._send(api_pcm_list(q))
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
            if u.path == "/api/render/sym":
                r = api_render_sym(q.get("lib", ""), q.get("name", ""))
                if isinstance(r, dict):
                    return self._send(r, 400)
                return self._send_raw(*r)
            if u.path == "/api/render/fp":
                r = api_render_fp(q.get("lib", ""), q.get("name", ""))
                if isinstance(r, dict):
                    return self._send(r, 400)
                return self._send_raw(*r)
            if u.path == "/api/sym/list":
                return self._send(api_sym_list(q.get("lib", "")))
            if u.path == "/api/fp/list":
                return self._send(api_fp_list(q.get("lib", "")))
            if u.path == "/api/file":
                r = api_file(q.get("path", ""))
                if isinstance(r, dict):
                    return self._send(r, 400)
                return self._send_raw(*r)
            if u.path == "/api/tools/catalog":
                return self._send(daotools.catalog())
            if u.path == "/api/search":
                return self._send(daotools.api_search(q))
            if u.path == "/api/capabilities":
                return self._send(_CAPABILITIES)
            if u.path == "/api/doc":
                doc = Path(__file__).with_name("AGENT_BRIDGE.md")
                if doc.is_file():
                    return self._send_raw(doc.read_bytes(),
                                          "text/markdown; charset=utf-8")
                return self._send({"ok": False, "error": "doc missing"}, 404)
            if u.path == "/api/ai/config":
                return self._send(api_ai_config_get(q))
            if u.path == "/api/chat/list":
                return self._send(api_chat_list(q))
            if u.path == "/api/chat/get":
                return self._send(api_chat_get(q))
            if u.path == "/api/native/status":
                return self._send(api_native_status(q))
            if u.path == "/api/ipc/status":
                return self._send(api_ipc_status(q))
            if u.path == "/api/brain/templates":
                return self._send(api_brain_templates(q))
            if u.path == "/api/ipc/board":
                return self._send(api_ipc_board(q))
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
        fn = _POST_PATHS.get(u.path) or (
            _ACTIONS.get(name) if u.path.startswith("/api/") else None)
        if fn is None:
            return self._send({"ok": False, "error": "not found"}, 404)
        try:
            raw = self._read_body()
            body = json.loads(raw or b"{}")
        except Exception as e:
            return self._send({"ok": False, "error": f"bad json: {e}"}, 400)
        _alias_path(body)
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
