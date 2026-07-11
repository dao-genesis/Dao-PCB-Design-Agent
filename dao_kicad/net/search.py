"""
Network Search — Find PCB Resources in the Wild

Instead of maintaining dead templates, search the living ecosystem:
- GitHub repos with .kicad_pcb files
- Component databases for parts selection
- Community reference designs
- Datasheet and application note circuits

This is how a real engineer works — not from fixed templates,
but by researching, finding, and adapting existing work.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SearchResult:
    """A found PCB resource from the network."""
    title: str
    url: str
    source: str
    description: str = ""
    relevance: float = 0.0
    files: list[str] = field(default_factory=list)


class GitHubSearch:
    """Search GitHub for open-source KiCad projects.

    The world's largest collection of open-source PCB designs.
    Instead of maintaining our own templates, we find real projects.
    """

    API_BASE = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        self.token = token
        self.headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            self.headers["Authorization"] = f"token {token}"

    def search_repos(self, query: str, language: str = "",
                     max_results: int = 20) -> list[SearchResult]:
        """Search GitHub repositories for KiCad projects.

        Examples:
            search_repos("STM32 PCB")
            search_repos("ESP32 dev board kicad")
            search_repos("USB-C charger PCB")
            search_repos("4-layer HDI kicad")
        """
        q_parts = [query, "kicad"]
        if language:
            q_parts.append(f"language:{language}")

        q = " ".join(q_parts)
        params = urllib.parse.urlencode({
            "q": q,
            "sort": "stars",
            "per_page": min(max_results, 100),
        })

        url = f"{self.API_BASE}/search/repositories?{params}"
        try:
            data = self._get(url)
        except Exception:
            return []

        results = []
        for item in data.get("items", [])[:max_results]:
            results.append(SearchResult(
                title=item.get("full_name", ""),
                url=item.get("html_url", ""),
                source="github",
                description=item.get("description", "") or "",
                relevance=item.get("stargazers_count", 0),
            ))

        return results

    def search_code(self, query: str, extension: str = "kicad_pcb",
                    max_results: int = 20) -> list[SearchResult]:
        """Search GitHub code for specific KiCad files.

        This finds actual .kicad_pcb, .kicad_sch files matching a query.
        """
        q = f"{query} extension:{extension}"
        params = urllib.parse.urlencode({
            "q": q,
            "per_page": min(max_results, 100),
        })

        url = f"{self.API_BASE}/search/code?{params}"
        try:
            data = self._get(url)
        except Exception:
            return []

        results = []
        for item in data.get("items", [])[:max_results]:
            repo = item.get("repository", {})
            results.append(SearchResult(
                title=item.get("name", ""),
                url=item.get("html_url", ""),
                source="github_code",
                description=f"in {repo.get('full_name', '')}",
                files=[item.get("path", "")],
            ))

        return results

    def get_repo_kicad_files(self, owner: str, repo: str) -> list[str]:
        """List all KiCad files in a repository."""
        url = f"{self.API_BASE}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
        try:
            data = self._get(url)
        except Exception:
            return []

        kicad_exts = {".kicad_pcb", ".kicad_sch", ".kicad_sym", ".kicad_mod", ".kicad_pro"}
        files = []
        for item in data.get("tree", []):
            path = item.get("path", "")
            for ext in kicad_exts:
                if path.endswith(ext):
                    files.append(path)
                    break

        return files

    def download_file(self, owner: str, repo: str, path: str,
                      branch: str = "main") -> Optional[str]:
        """Download a raw file from a GitHub repository."""
        url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
        try:
            req = urllib.request.Request(url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="ignore")
        except Exception:
            return None

    def _get(self, url: str) -> dict:
        """Make a GET request to GitHub API."""
        req = urllib.request.Request(url, headers=self.headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())


class ComponentSearch:
    """Search component databases for parts.

    When building a board, we need real parts with real footprints.
    This searches component databases to find suitable parts.
    """

    # LCSC is the most accessible for automated queries
    LCSC_SEARCH = "https://wmsc.lcsc.com/ftts/wm/search"

    def search_lcsc(self, query: str, max_results: int = 10) -> list[dict]:
        """Search LCSC component database.

        Returns component info including:
        - Part number
        - Description
        - Package/footprint
        - Datasheet URL
        - Stock/price info
        """
        data = json.dumps({
            "keyword": query,
            "pageSize": max_results,
            "currentPage": 1,
        }).encode()

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        try:
            req = urllib.request.Request(self.LCSC_SEARCH, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
            return result.get("result", {}).get("tipProductList", [])
        except Exception:
            return []


class OshwSearch:
    """Search Open Source Hardware resources.

    OSHWA certified projects, KiCad community libraries,
    reference designs from IC manufacturers.
    """

    # Well-known sources of open-source PCB designs
    SOURCES = [
        "https://github.com/KiCad",
        "https://github.com/espressif",
        "https://github.com/raspberrypi",
        "https://github.com/adafruit",
        "https://github.com/sparkfun",
        "https://github.com/OLIMEX",
        "https://github.com/Seeed-Studio",
    ]

    def known_reference_designs(self) -> dict[str, list[str]]:
        """Return known high-quality reference design repositories."""
        return {
            "esp32": [
                "espressif/esp32-devkitc-v4",
                "espressif/esp32-s3-devkitc-1",
            ],
            "rp2040": [
                "raspberrypi/hardware/pico",
            ],
            "stm32": [
                "WeActStudio/WeActStudio.MiniSTM32F4x1",
                "STMicroelectronics/STM32CubeF4",
            ],
            "nrf52": [
                "NordicSemiconductor/nrf52840-mdk",
            ],
            "power": [
                "adafruit/Adafruit-USB-C-Power-Delivery-Board-PCB",
            ],
            "audio": [
                "sparkfun/SparkFun_I2S_Audio_Breakout",
            ],
        }
