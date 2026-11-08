"""deskstack_check: deterministic checks for financial models in .xlsx (openpyxl).

Usage:  python -m deskstack_check model.xlsx [--json]
Only public, widely known modeling practices are checked (formatting
conventions, standard model sanity checks). It never grades a person.
"""

from __future__ import annotations

from .model import file_sha256, load
from .rules import RULE_INFO, SEVERITY_ORDER, STRUCTURAL, VALUE_BASED, Finding

__version__ = "0.2.0"
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
        "report": "review",
        "file": path,
        "model_sha256": file_sha256(path),
        "checker": f"deskstack_check {__version__}",
        "counts": counts,
        "findings": [f.__dict__ for f in findings],
    }


AUDIT_SEVERITY = {"blocker": "Critical", "major": "Warning", "minor": "Info", "info": "Info"}


def to_markdown(report: dict, merged: list[dict] | None = None) -> str:
    """The audit-xls table (# | Sheet | Cell/Range | Severity | Category | Issue | Suggested Fix) plus Rule and Found by.

    Severity shows ours and the audit-xls equivalent (blocker = Critical, major = Warning, minor/info = Info).
    """
    rows = merged if merged is not None else report["findings"]
    c = {s: sum(1 for f in rows if f["severity"] == s) for s in SEVERITY_ORDER}
    overall = "Major Issues" if c["blocker"] else ("Minor Issues" if c["major"] or c["minor"] else "Clean")
    lines = [
        f"## Model check: {report['file']}",
        f"Overall: {overall} — {c['blocker']} blocker, {c['major']} major, {c['minor']} minor, {c['info']} info ({report['checker']}).",
        "",
        "| # | Sheet | Cell/Range | Severity | Category | Issue | Suggested Fix | Rule | Found by |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, f in enumerate(rows, start=1):
        sheet, _, cell = f["ref"].partition("!")
        cat, fix = RULE_INFO.get(f["rule"], (f.get("category", ""), f.get("fix", "")))
        sev = f"{f['severity']} ({AUDIT_SEVERITY[f['severity']]})"
        msg = f["message"].replace("|", "/")
        lines.append(f"| {i} | {sheet} | `{cell}` | {sev} | {cat} | {msg} | {fix} | {f['rule']} | {f.get('found_by', 'deskstack')} |")
    if not rows:
        lines.append("| - | - | - | - | - | No findings. | - | - | - |")
    return "\n".join(lines)
