"""
DRC Error Analyzer — Understand and Categorize DRC Violations

WISDOM from Practices 11-25: Every board generates DRC errors.
Understanding the pattern of errors is more valuable than the count.
A living system classifies, prioritizes, and suggests fixes.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


from dao_kicad.core.drc import DrcEngine


@dataclass
class DrcCategory:
    """A category of DRC errors with count and severity."""
    name: str
    count: int = 0
    severity: str = "warning"  # critical, error, warning, info
    fix_hint: str = ""
    examples: list[str] = field(default_factory=list)


@dataclass
class DrcReport:
    """Analyzed DRC report with categorized errors."""
    total_errors: int = 0
    total_warnings: int = 0
    categories: list[DrcCategory] = field(default_factory=list)
    fixable_count: int = 0
    critical_count: int = 0

    def summary(self) -> str:
        lines = [f"DRC Analysis: {self.total_errors}E/{self.total_warnings}W, "
                 f"{len(self.categories)} categories, "
                 f"{self.critical_count} critical, {self.fixable_count} auto-fixable"]
        for cat in sorted(self.categories, key=lambda c: c.count, reverse=True)[:5]:
            lines.append(f"  [{cat.severity}] {cat.name}: {cat.count}x — {cat.fix_hint}")
        return "\n".join(lines)


# Common DRC error patterns and their meanings
ERROR_PATTERNS = {
    r"Clearance violation": DrcCategory(
        "Clearance", severity="error",
        fix_hint="Increase spacing between traces/pads or reduce trace width",
    ),
    r"Track too close": DrcCategory(
        "Track Spacing", severity="error",
        fix_hint="Route tracks further apart or use narrower traces",
    ),
    r"Via too close": DrcCategory(
        "Via Spacing", severity="error",
        fix_hint="Space vias further apart",
    ),
    r"Pad too close": DrcCategory(
        "Pad Spacing", severity="warning",
        fix_hint="Increase component spacing in placement",
    ),
    r"Unconnected": DrcCategory(
        "Unconnected Nets", severity="critical",
        fix_hint="Add missing traces between pads",
    ),
    r"Drill too small": DrcCategory(
        "Drill Size", severity="error",
        fix_hint="Increase via drill size (min 0.15mm for most fabs)",
    ),
    r"Annular ring": DrcCategory(
        "Annular Ring", severity="error",
        fix_hint="Increase via pad size relative to drill",
    ),
    r"Courtyard overlap": DrcCategory(
        "Courtyard", severity="warning",
        fix_hint="Move overlapping components apart",
    ),
    r"Silk.*pad": DrcCategory(
        "Silkscreen on Pad", severity="info",
        fix_hint="Clip silkscreen near pads (cosmetic only)",
    ),
    r"Min.*width": DrcCategory(
        "Minimum Width", severity="error",
        fix_hint="Widen trace to meet minimum width rule",
    ),
    r"Zone.*fill": DrcCategory(
        "Zone Fill", severity="info",
        fix_hint="Re-fill zones after modifications",
    ),
}


class DrcAnalyzer:
    """Analyze DRC results and categorize errors."""

    def __init__(self, board_path: str | Path):
        self.board_path = Path(board_path)

    def analyze(self) -> DrcReport:
        """Run DRC and analyze results."""
        drc = DrcEngine()
        result = drc.check(self.board_path)

        report = DrcReport(
            total_errors=result.error_count,
            total_warnings=result.warning_count,
        )

        # Categorize from violations
        if result.violations:
            self._categorize_from_violations(result.violations, report)
        elif result.error_count > 0:
            report.categories.append(DrcCategory(
                "Clearance/Spacing", count=result.error_count,
                severity="error",
                fix_hint="Review component spacing and trace clearances",
            ))

        # Calculate fixable and critical
        for cat in report.categories:
            if cat.severity == "critical":
                report.critical_count += cat.count
            if cat.severity in ("info", "warning"):
                report.fixable_count += cat.count

        return report

    def _categorize_from_violations(self, violations: list, report: DrcReport):
        """Categorize errors from DRC violations."""
        counts: dict[str, int] = Counter()

        for v in violations:
            desc = f"{v.rule} {v.description}"
            matched = False
            for pattern, category in ERROR_PATTERNS.items():
                if re.search(pattern, desc, re.IGNORECASE):
                    counts[category.name] = counts.get(category.name, 0) + 1
                    matched = True
                    break
            if not matched:
                counts["Other"] = counts.get("Other", 0) + 1

        for name, count in counts.items():
            template = None
            for cat in ERROR_PATTERNS.values():
                if cat.name == name:
                    template = cat
                    break

            report.categories.append(DrcCategory(
                name=name,
                count=count,
                severity=template.severity if template else "warning",
                fix_hint=template.fix_hint if template else "Review manually",
            ))

    def suggest_fixes(self, report: DrcReport) -> list[str]:
        """Suggest concrete fixes based on DRC analysis."""
        fixes = []

        for cat in report.categories:
            if cat.count == 0:
                continue

            if cat.name == "Clearance" and cat.count > 50:
                fixes.append("Many clearance violations → likely component density too high. "
                            "Consider increasing board size or using finer pitch components.")
            elif cat.name == "Clearance":
                fixes.append(f"{cat.count} clearance violations → adjust routing clearance "
                           "or component spacing.")
            elif cat.name == "Unconnected Nets":
                fixes.append(f"{cat.count} unconnected nets → add missing traces. "
                           "Check if all nets in netlist are routed.")
            elif cat.name == "Courtyard":
                fixes.append(f"{cat.count} courtyard overlaps → spread components apart "
                           "by at least 0.5mm more.")
            elif cat.name == "Annular Ring":
                fixes.append(f"{cat.count} annular ring violations → increase via pad size "
                           "to at least 0.2mm larger than drill.")

        if not fixes:
            fixes.append("No critical issues found. DRC errors are within acceptable range.")

        return fixes
