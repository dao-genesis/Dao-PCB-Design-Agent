"""
DRC Integration — Design Rule Check as Part of the Living Workflow

Exposed by Practice 1: Board was exported without validation.
A living system must self-verify at every step.

Integrates KiCad's native DRC through:
1. kicad-cli drc (headless, most reliable)
2. pcbnew SWIG DRC markers (in-memory, instant feedback)

The WISDOM: DRC is not a final gate — it's continuous feedback.
Run it early, run it often, use violations to guide the design.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DrcViolation:
    """A single DRC violation."""
    severity: str  # error, warning, exclusion
    rule: str
    description: str
    x_mm: float = 0
    y_mm: float = 0
    items: list[str] = field(default_factory=list)


@dataclass
class DrcResult:
    """Complete DRC result."""
    violations: list[DrcViolation] = field(default_factory=list)
    unresolved_count: int = 0
    schematic_parity: bool = True
    passed: bool = True

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (f"DRC [{status}]: {self.error_count} errors, "
                f"{self.warning_count} warnings, "
                f"{self.unresolved_count} unresolved")


class DrcEngine:
    """Run DRC via kicad-cli and parse results.

    Usage:
        drc = DrcEngine()
        result = drc.check("/path/to/board.kicad_pcb")
        if not result.passed:
            for v in result.violations:
                print(f"  {v.severity}: {v.description}")
    """

    def __init__(self, kicad_cli: str = "kicad-cli"):
        self.kicad_cli = kicad_cli

    def check(self, board_path: str | Path,
              severity_all: bool = True) -> DrcResult:
        """Run DRC on a board file using kicad-cli.

        Returns structured results parsed from the JSON report.
        """
        board_path = Path(board_path)
        if not board_path.exists():
            result = DrcResult(passed=False)
            result.violations.append(DrcViolation(
                severity="error",
                rule="file_not_found",
                description=f"Board file not found: {board_path}",
            ))
            return result

        # Create temp file for JSON output
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            report_path = Path(f.name)

        try:
            cmd = [
                self.kicad_cli, "pcb", "drc",
                "--output", str(report_path),
                "--format", "json",
            ]
            if severity_all:
                cmd.append("--severity-all")
            cmd.append(str(board_path))

            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120
            )

            # Parse the JSON report
            if report_path.exists() and report_path.stat().st_size > 0:
                return self._parse_report(report_path)

            # If no report, check return code
            if proc.returncode != 0:
                result = DrcResult(passed=False)
                result.violations.append(DrcViolation(
                    severity="error",
                    rule="drc_failed",
                    description=f"DRC execution failed: {proc.stderr.strip()}",
                ))
                return result

            return DrcResult(passed=True)

        except FileNotFoundError:
            result = DrcResult(passed=False)
            result.violations.append(DrcViolation(
                severity="error",
                rule="kicad_cli_not_found",
                description="kicad-cli not found in PATH",
            ))
            return result
        except subprocess.TimeoutExpired:
            result = DrcResult(passed=False)
            result.violations.append(DrcViolation(
                severity="error",
                rule="timeout",
                description="DRC timed out after 120 seconds",
            ))
            return result
        finally:
            report_path.unlink(missing_ok=True)

    def check_in_memory(self, board) -> DrcResult:
        """Run DRC on an in-memory pcbnew.BOARD object.

        Faster than CLI (no file I/O) but requires pcbnew SWIG.
        Reads existing DRC markers from the board.
        """
        import pcbnew  # noqa: F401

        result = DrcResult()

        # Get existing DRC markers
        try:
            markers = board.GetMarkers() if hasattr(board, 'GetMarkers') else []
        except Exception:
            markers = []

        for marker in markers:
            try:
                severity = "error"
                if hasattr(marker, 'GetSeverity'):
                    sev = marker.GetSeverity()
                    if sev == 1:
                        severity = "warning"

                description = ""
                if hasattr(marker, 'GetComment'):
                    description = marker.GetComment()

                pos = marker.GetPosition() if hasattr(marker, 'GetPosition') else None
                x_mm = pcbnew.ToMM(pos.x) if pos else 0
                y_mm = pcbnew.ToMM(pos.y) if pos else 0

                result.violations.append(DrcViolation(
                    severity=severity,
                    rule="drc_marker",
                    description=description,
                    x_mm=x_mm,
                    y_mm=y_mm,
                ))
            except Exception:
                continue

        result.passed = result.error_count == 0
        return result

    def _parse_report(self, report_path: Path) -> DrcResult:
        """Parse a kicad-cli DRC JSON report."""
        result = DrcResult()

        try:
            data = json.loads(report_path.read_text())
        except (json.JSONDecodeError, OSError):
            result.passed = False
            result.violations.append(DrcViolation(
                severity="error",
                rule="parse_error",
                description="Failed to parse DRC report",
            ))
            return result

        # Parse violations from the report
        for violation_set in data.get("violations", []):
            if isinstance(violation_set, dict):
                severity = violation_set.get("severity", "error")
                description = violation_set.get("description", "")
                rule = violation_set.get("type", "unknown")

                items = []
                for item in violation_set.get("items", []):
                    if isinstance(item, dict):
                        items.append(item.get("description", ""))

                pos = violation_set.get("pos", {})
                x_mm = pos.get("x", 0) / 1_000_000 if isinstance(pos.get("x"), (int, float)) else 0
                y_mm = pos.get("y", 0) / 1_000_000 if isinstance(pos.get("y"), (int, float)) else 0

                result.violations.append(DrcViolation(
                    severity=severity,
                    rule=rule,
                    description=description,
                    x_mm=x_mm,
                    y_mm=y_mm,
                    items=items,
                ))

        # Parse unconnected items (open nets). kicad-cli emits these under
        # "unconnected_items" — the old code read "unresolved", a key KiCad
        # never writes, so unresolved_count was always 0 and open circuits
        # went unreported.
        unconnected = data.get("unconnected_items", [])
        result.unresolved_count = (
            len(unconnected) if isinstance(unconnected, list) else 0)

        # Schematic parity is a LIST of parity violations (empty = clean), not
        # a bool. Treating the list itself as the bool was inverted: an empty
        # (clean) list is falsy → reported as failing parity. Clean iff empty.
        parity = data.get("schematic_parity", [])
        result.schematic_parity = (
            len(parity) == 0 if isinstance(parity, list) else bool(parity))

        result.passed = result.error_count == 0
        return result


# ═══════════════════════════════════════════════════════════════════════════════
# Validated Export — Only export if DRC passes
# ═══════════════════════════════════════════════════════════════════════════════

def validated_export(board_path: str | Path, output_dir: str | Path,
                     allow_warnings: bool = True) -> tuple[bool, str]:
    """Export manufacturing files ONLY if DRC passes.

    This is the LIVING workflow: design → validate → export.
    Never blindly export without verification.

    Returns (success, message).
    """
    from .export import ExportEngine
    import pcbnew

    board_path = Path(board_path)
    output_dir = Path(output_dir)

    # Step 1: Run DRC
    drc = DrcEngine()
    result = drc.check(board_path)

    if not result.passed:
        if not allow_warnings or result.error_count > 0:
            msg = f"DRC FAILED — {result.error_count} errors, {result.warning_count} warnings. Cannot export."
            for v in result.violations[:5]:
                msg += f"\n  • [{v.severity}] {v.description}"
            return False, msg

    # Step 2: Load and export
    board = pcbnew.LoadBoard(str(board_path))
    engine = ExportEngine(board)
    mfg = engine.full_manufacturing(output_dir)
    total = sum(len(files) for files in mfg.values())

    msg = f"DRC {result.summary()} — Exported {total} manufacturing files to {output_dir}"
    return True, msg
