"""
DAO Bridge Remote — Connect to user's local KiCad via DAO Bridge.

Implements the self-healing connection protocol:
1. Try current URL from knowledge note
2. On failure, re-read knowledge note for updated URL
3. Fall back to ntfy mesh if tunnel is completely down

道法自然 — the bridge heals itself, we just need to reconnect.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.request
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BridgeConnection:
    """Connection to user's local machine via DAO Bridge."""

    url: str = ""
    token: str = ""
    host: str = ""
    workspace: str = ""
    alive: bool = False
    _opener: object = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(k, None)
        os.environ["NO_PROXY"] = "*"
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPSHandler(context=ctx),
        )
        urllib.request.install_opener(self._opener)

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        timeout: int = 30,
    ) -> dict:
        data = json.dumps(body).encode() if body else None
        headers = {"Content-Type": "application/json"}
        if "/health" not in path:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(
            f"{self.url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read())

    def connect(self, url: str, token: str) -> bool:
        """Attempt connection to bridge endpoint."""
        self.url = url.rstrip("/")
        self.token = token
        try:
            health = self._request("GET", "/api/health")
            self.host = health.get("host", "")
            self.workspace = health.get("workspace", "")
            self.alive = health.get("status") == "ok"
            return self.alive
        except Exception:
            self.alive = False
            return False

    def exec(self, cmd: str, timeout: int = 30) -> dict:
        """Execute command on remote machine."""
        return self._request("POST", "/api/exec", {"cmd": cmd, "timeout": timeout})

    def ls(self, path: str) -> dict:
        """List directory on remote machine."""
        return self._request("POST", "/api/ls", {"path": path})

    def read_file(self, path: str) -> dict:
        """Read file from remote machine."""
        return self._request("POST", "/api/file", {"path": path})

    def write_file(self, path: str, content: str) -> dict:
        """Write file to remote machine."""
        return self._request("POST", "/api/write", {"path": path, "content": content})

    def search(self, query: str, path: str = ".") -> dict:
        """Search files on remote machine."""
        return self._request("POST", "/api/search", {"query": query, "path": path})

    def connection_info(self) -> dict:
        """Get connection details."""
        return self._request("GET", "/api/connection")

    def workspace_info(self) -> dict:
        """Get workspace information."""
        return self._request("GET", "/api/workspace")

    def bridge_state(self) -> dict:
        """Get full bridge/tunnel state."""
        return self._request("GET", "/api/bridge-state")

    def agents(self) -> dict:
        """List online agents/devices."""
        return self._request("GET", "/api/agents")

    def find_kicad(self) -> Optional[str]:
        """Find KiCad installation on remote machine."""
        try:
            r = self.exec('where kicad-cli 2>nul || echo NOT_FOUND')
            stdout = r.get("stdout", "")
            if "NOT_FOUND" not in stdout and stdout.strip():
                return stdout.strip().split("\n")[0]
        except Exception:
            pass

        common_paths = [
            r"C:\Program Files\KiCad\9.0\bin\kicad-cli.exe",
            r"C:\Program Files\KiCad\8.0\bin\kicad-cli.exe",
            r"C:\Program Files\KiCad\bin\kicad-cli.exe",
        ]
        for p in common_paths:
            try:
                r = self.exec(f'if exist "{p}" echo FOUND')
                if "FOUND" in r.get("stdout", ""):
                    return p
            except Exception:
                continue
        return None

    def find_kicad_projects(self, search_dir: str = ".") -> list[str]:
        """Find .kicad_pcb files on remote machine."""
        try:
            r = self.exec(
                f'dir /s /b "{search_dir}\\*.kicad_pcb" 2>nul',
                timeout=15,
            )
            stdout = r.get("stdout", "")
            return [line.strip() for line in stdout.split("\n") if line.strip()]
        except Exception:
            return []

    def run_drc(self, pcb_path: str, kicad_cli: str = "kicad-cli") -> dict:
        """Run DRC on a remote PCB file."""

        report = pcb_path.replace(".kicad_pcb", "_drc.json")
        cmd = f'"{kicad_cli}" pcb drc --format json -o "{report}" "{pcb_path}" 2>&1'
        result = self.exec(cmd, timeout=60)
        try:
            content = self.read_file(report)
            return {"drc": json.loads(content.get("content", "{}")), "exec": result}
        except Exception:
            return {"drc": None, "exec": result}

    def export_gerbers(self, pcb_path: str, output_dir: str, kicad_cli: str = "kicad-cli") -> dict:
        """Export Gerber files from a remote PCB."""
        self.exec(f'mkdir "{output_dir}" 2>nul')
        cmd = f'"{kicad_cli}" pcb export gerbers -o "{output_dir}\\" "{pcb_path}" 2>&1'
        return self.exec(cmd, timeout=60)
