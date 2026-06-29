"""
Library Manager — Dynamic Community Library Integration

Wisdom from Practice 5: Standard KiCad has 15,415 footprints but misses
many popular modules. The network provides unlimited resources.

Pipeline: Search → Download → Cache → Register → Use
This is the LIVING library: grows from the world, never static.
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CachedLibrary:
    """A downloaded community library."""
    name: str
    source_url: str
    local_path: Path
    footprints: list[str] = field(default_factory=list)
    last_updated: str = ""


class LibraryManager:
    """Manage community footprint/symbol libraries.

    Downloads from GitHub, caches locally, registers in KiCad.
    The system GROWS by absorbing community resources.
    """

    CACHE_DIR = Path.home() / ".local" / "share" / "kicad" / "9.0" / "3rdparty" / "footprints"
    FP_LIB_TABLE = Path.home() / ".local" / "share" / "kicad" / "9.0" / "fp-lib-table"

    KNOWN_SOURCES = {
        "espressif": {
            "repo": "espressif/kicad-libraries",
            "path": "footprints/Espressif.pretty",
            "description": "Official Espressif ESP32/ESP8266 footprints",
        },
        "sparkfun": {
            "repo": "sparkfun/SparkFun-KiCad-Libraries",
            "path": "Footprints",
            "description": "SparkFun's KiCad library",
        },
        "adafruit": {
            "repo": "adafruit/Adafruit-Fritzing-Library",
            "path": "",
            "description": "Adafruit component library",
        },
    }

    def __init__(self, token: str = "", cache_dir: Optional[Path] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN", "")
        self.cache_dir = cache_dir or self.CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cached: dict[str, CachedLibrary] = {}
        self._discover_cached()

    def _discover_cached(self):
        """Find already-downloaded libraries."""
        for d in self.cache_dir.iterdir():
            if d.suffix == ".pretty" and d.is_dir():
                fps = [f.stem for f in d.glob("*.kicad_mod")]
                self._cached[d.stem] = CachedLibrary(
                    name=d.stem,
                    source_url="",
                    local_path=d,
                    footprints=fps,
                )

    def search_github(self, query: str, per_page: int = 5) -> list[dict]:
        """Search GitHub for KiCad footprint files."""
        encoded = urllib.parse.quote(f"extension:kicad_mod {query}")
        url = f"https://api.github.com/search/code?q={encoded}&per_page={per_page}"

        try:
            data = self._github_get(url)
            return data.get("items", [])
        except Exception:
            return []

    def download_library(self, repo: str, path: str,
                         lib_name: Optional[str] = None) -> Optional[CachedLibrary]:
        """Download an entire .pretty directory from GitHub.

        Args:
            repo: "owner/repo" format
            path: Path to .pretty directory in the repo
            lib_name: Local name (defaults to directory name)
        """
        if not lib_name:
            lib_name = Path(path).stem

        local_dir = self.cache_dir / f"{lib_name}.pretty"
        local_dir.mkdir(parents=True, exist_ok=True)

        # List directory contents
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        try:
            items = self._github_get(url)
        except Exception:
            return None

        if not isinstance(items, list):
            return None

        downloaded = []
        for item in items:
            if item.get("name", "").endswith(".kicad_mod"):
                try:
                    content = self._download_file(item["download_url"])
                    fp_path = local_dir / item["name"]
                    fp_path.write_text(content)
                    downloaded.append(item["name"].replace(".kicad_mod", ""))
                except Exception:
                    continue

        if downloaded:
            lib = CachedLibrary(
                name=lib_name,
                source_url=f"https://github.com/{repo}/tree/main/{path}",
                local_path=local_dir,
                footprints=downloaded,
            )
            self._cached[lib_name] = lib
            return lib

        return None

    def download_footprint(self, repo: str, file_path: str,
                           lib_name: str = "community") -> Optional[Path]:
        """Download a single footprint file.

        Returns the local .pretty directory path containing the footprint.
        """
        local_dir = self.cache_dir / f"{lib_name}.pretty"
        local_dir.mkdir(parents=True, exist_ok=True)

        url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
        try:
            data = self._github_get(url)
            content = self._download_file(data["download_url"])
            fp_name = Path(file_path).name
            fp_path = local_dir / fp_name
            fp_path.write_text(content)

            # Update cache
            if lib_name not in self._cached:
                self._cached[lib_name] = CachedLibrary(
                    name=lib_name,
                    source_url=f"https://github.com/{repo}",
                    local_path=local_dir,
                    footprints=[],
                )
            fp_stem = fp_name.replace(".kicad_mod", "")
            if fp_stem not in self._cached[lib_name].footprints:
                self._cached[lib_name].footprints.append(fp_stem)

            return local_dir
        except Exception:
            return None

    def install_known(self, source_name: str) -> Optional[CachedLibrary]:
        """Install a known community library by name."""
        if source_name not in self.KNOWN_SOURCES:
            return None

        src = self.KNOWN_SOURCES[source_name]
        return self.download_library(src["repo"], src["path"], source_name)

    def register_in_kicad(self, lib: CachedLibrary) -> bool:
        """Register a downloaded library in KiCad's fp-lib-table."""
        entry = f'  (lib (name "{lib.name}")(type "KiCad")(uri "{lib.local_path}")(options "")(descr "Community: {lib.source_url}"))\n'

        if self.FP_LIB_TABLE.exists():
            content = self.FP_LIB_TABLE.read_text()
            if lib.name in content:
                return True  # Already registered

            # Insert before closing paren
            content = content.rstrip()
            if content.endswith(")"):
                content = content[:-1] + entry + ")\n"
                self.FP_LIB_TABLE.write_text(content)
                return True
        else:
            # Create new fp-lib-table
            content = f"(fp_lib_table\n{entry})\n"
            self.FP_LIB_TABLE.parent.mkdir(parents=True, exist_ok=True)
            self.FP_LIB_TABLE.write_text(content)
            return True

        return False

    @property
    def available_libraries(self) -> dict[str, CachedLibrary]:
        return dict(self._cached)

    def search_cached(self, query: str) -> list[tuple[str, str]]:
        """Search cached community libraries for a footprint."""
        results = []
        q = query.lower()
        for lib_name, lib in self._cached.items():
            for fp in lib.footprints:
                if q in fp.lower():
                    results.append((lib_name, fp))
        return results

    def _github_get(self, url: str) -> dict | list:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        req = urllib.request.Request(url, headers=headers)
        ctx = ssl.create_default_context()
        resp = urllib.request.urlopen(req, timeout=30, context=ctx)
        return json.loads(resp.read())

    def _download_file(self, url: str) -> str:
        ctx = ssl.create_default_context()
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=60, context=ctx)
        return resp.read().decode("utf-8", errors="ignore")
