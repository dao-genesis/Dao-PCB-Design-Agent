"""IDE bridge (单网页归一 REST 服务) smoke tests."""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from bridge import ide_server


def test_api_tree_lists_projects(tmp_path):
    (tmp_path / "boardA").mkdir()
    (tmp_path / "boardA" / "boardA.kicad_pro").write_text("{}")
    (tmp_path / "boardA" / "boardA.kicad_sch").write_text("(kicad_sch)")
    r = ide_server.api_tree(str(tmp_path))
    assert r["ok"] and len(r["projects"]) == 1
    p = r["projects"][0]
    assert p["name"] == "boardA" and len(p["sch"]) == 1


def test_api_tree_rejects_missing_dir():
    r = ide_server.api_tree("/no/such/dir/anywhere")
    assert not r["ok"]


def test_render_rejects_missing_file():
    r = ide_server.api_render_sch("/no/such.kicad_sch")
    assert isinstance(r, dict) and not r["ok"]
    r = ide_server.api_render_pcb("/no/such.kicad_pcb", "F.Cu")
    assert isinstance(r, dict) and not r["ok"]


@pytest.fixture()
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), ide_server.Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=30) as r:
        return r.status, json.loads(r.read())


def _post(url, body):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read())


def test_http_health_and_tree(server, tmp_path):
    code, j = _get(server + "/api/health")
    assert code == 200 and j["ok"] and j["service"] == "dao-kicad-ide"
    (tmp_path / "x.kicad_pro").write_text("{}")
    code, j = _get(server + "/api/tree?root=" + str(tmp_path))
    assert code == 200 and j["ok"] and j["projects"][0]["name"] == "x"


def test_http_slow_action_returns_job(server, tmp_path):
    net = tmp_path / "empty.net"
    net.write_text("(export (version E))")
    code, j = _post(server + "/api/build",
                    {"netlist": str(net), "out": str(tmp_path / "o.kicad_pcb")})
    assert code == 200 and j["ok"] and j["job"]
    import time
    for _ in range(60):
        _, s = _get(server + "/api/job?id=" + j["job"])
        if s.get("done"):
            break
        time.sleep(0.5)
    assert s["done"]
    # an empty netlist honestly fails — the job carries the engine's verdict.
    assert s["result"]["ok"] is False


def test_http_unknown_routes(server):
    for fn in (lambda: _get(server + "/api/nope"),
               lambda: _post(server + "/api/nope", {})):
        try:
            code, j = fn()
        except urllib.error.HTTPError as e:
            code, j = e.code, json.loads(e.read())
        assert code == 404 and not j["ok"]
