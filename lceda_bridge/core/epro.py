"""读写 .epro — 嘉立创EDA 工程导出包 (ZIP).

ZIP 结构 (实证):
    SHEET/<uuid>/N.esch
    PCB/<uuid>.epcb
    SYMBOL/<uuid>.esym
    FOOTPRINT/<uuid>.efoo
    POUR/        ← 大铺铜独立文件
    PANEL/
    BLOB/
    FONT/
    INSTANCE/

各 .esch / .epcb / .esym / .efoo 内部都是**明文 NDJSON 指令文档**,
头一行 ["DOCTYPE", "<TYPE>", "<VERSION>"].
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional

from . import doc as docmod


@dataclass
class EproEntry:
    """ZIP 内一项."""
    name: str       # 完整 ZIP 路径
    size: int
    folder: str     # SHEET / PCB / SYMBOL / FOOTPRINT / ...
    doc_uuid: str   # 从路径提取的 UUID (若可)


class EproReader:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        self.zip = zipfile.ZipFile(self.path, "r")

    def close(self) -> None:
        self.zip.close()

    def __enter__(self) -> "EproReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def entries(self) -> list[EproEntry]:
        out: list[EproEntry] = []
        for info in self.zip.infolist():
            if info.is_dir():
                continue
            parts = info.filename.split("/")
            folder = parts[0] if parts else ""
            stem = Path(info.filename).stem
            out.append(EproEntry(name=info.filename, size=info.file_size, folder=folder, doc_uuid=stem))
        return out

    def by_folder(self, folder: str) -> list[EproEntry]:
        prefix = folder.rstrip("/") + "/"
        return [e for e in self.entries() if e.name.startswith(prefix)]

    def read_text(self, name: str) -> str:
        return self.zip.read(name).decode("utf-8")

    def read_doc(self, name: str) -> docmod.Document:
        return docmod.loads(self.read_text(name))

    def schematics(self) -> list[EproEntry]:
        return [e for e in self.entries() if e.name.startswith("SHEET/") and e.name.endswith(".esch")]

    def pcbs(self) -> list[EproEntry]:
        return [e for e in self.entries() if e.name.startswith("PCB/") and e.name.endswith(".epcb")]

    def symbols(self) -> list[EproEntry]:
        return [e for e in self.entries() if e.name.startswith("SYMBOL/") and e.name.endswith(".esym")]

    def footprints(self) -> list[EproEntry]:
        return [e for e in self.entries() if e.name.startswith("FOOTPRINT/") and e.name.endswith(".efoo")]

    def summary(self) -> dict[str, object]:
        all_entries = self.entries()
        from collections import Counter
        c = Counter(e.folder for e in all_entries)
        return {
            "path": str(self.path),
            "size_bytes": self.path.stat().st_size,
            "entries_total": len(all_entries),
            "by_folder": dict(c),
            "schematics": len(self.schematics()),
            "pcbs": len(self.pcbs()),
            "symbols": len(self.symbols()),
            "footprints": len(self.footprints()),
        }


class EproWriter:
    """构造 / 重新打包 .epro."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED)

    def close(self) -> None:
        self.zip.close()

    def __enter__(self) -> "EproWriter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def write_text(self, name: str, text: str) -> None:
        self.zip.writestr(name, text.encode("utf-8"))

    def write_doc(self, name: str, doc: docmod.Document) -> None:
        self.write_text(name, doc.dumps())
