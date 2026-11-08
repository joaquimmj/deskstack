"""deskstack_check: deterministic checks for financial models in .xlsx (openpyxl).

Usage:  python -m deskstack_check model.xlsx [--json]
Only public, widely known modeling practices are checked (formatting
conventions, standard model sanity checks). It never grades a person.
"""

from __future__ import annotations

from .model import load
from .rules import SEVERITY_ORDER, STRUCTURAL, VALUE_BASED, Finding

__version__ = "0.1.0"
__all__ = ["check", "Finding", "__version__"]


def check(path: str) -> dict:
    wb = load(path)
    findings: list[Finding] = []
    for rule in STRUCTURAL + VALUE_BASED:
        try:
            findings.extend(rule(wb))
        except Exception as e:  # noqa: BLE001 - one broken rule must not hide the others
            findings.append(Finding("DS000", "info", f"{wb.sheet_order[0]}!A1", f"Check {rule.__name__} could not run: {e}"))
    if not wb.has_cached_values and any(c.formula for c in wb.all()):
        findings.append(
            Finding(
                "DS000",
                "info",
                f"{wb.sheet_order[0]}!A1",
                "No cached formula results (the file was not saved by Excel): balance, cash tie-out, DCF and "
                "discount-factor checks only saw typed values. Open and save the file in Excel, then re-run.",
            )
        )
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.rule, f.ref))
    counts = {s: sum(1 for f in findings if f.severity == s) for s in SEVERITY_ORDER}
    return {
        "file": path,
        "checker": f"deskstack_check {__version__}",
        "counts": counts,
        "findings": [f.__dict__ for f in findings],
    }


def to_markdown(report: dict) -> str:
    c = report["counts"]
    lines = [
        f"## Model check: {report['file']}",
        f"{c['blocker']} blocker, {c['major']} major, {c['minor']} minor ({report['checker']}).",
        "",
        "| Severity | Rule | Cell | Finding |",
        "|---|---|---|---|",
    ]
    for f in report["findings"]:
        lines.append(f"| {f['severity']} | {f['rule']} | `{f['ref']}` | {f['message']} |")
    if not report["findings"]:
        lines.append("| - | - | - | No findings. |")
    return "\n".join(lines)
