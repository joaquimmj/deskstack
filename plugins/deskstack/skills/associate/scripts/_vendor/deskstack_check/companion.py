"""Companion mode: read findings tables from other reviewers and merge them with ours.

The official financial-services plugin's `audit-xls` skill reports a markdown
table `| # | Sheet | Cell/Range | Severity | Category | Issue | Suggested Fix |`
(severity Critical / Warning / Info), optionally after a line
`Model type: ... — Overall: ... — N critical, N warnings, N info`.
We parse that shape, map its severities onto ours, and mark each finding as
found by deskstack, by the other reviewer, or by both (same sheet and cell).
"""

from __future__ import annotations

import re

SEVERITY_MAP = {"critical": "blocker", "warning": "major", "info": "minor"}
HEADER = ["#", "sheet", "cell/range", "severity", "category", "issue", "suggested fix"]
SEVERITY_ORDER = {"blocker": 0, "major": 1, "minor": 2, "info": 3}


def _strip(cell: str) -> str:
    """Remove markdown emphasis, code ticks and leading emoji/symbols: '**🔴 Critical**' -> 'Critical'."""
    c = cell.strip().replace("**", "").replace("__", "").strip("`* _")
    return re.sub(r"^[^\w#/]+", "", c).strip()


def _cells(line: str) -> list[str]:
    """Split a markdown table row on unescaped pipes. Outer pipes are optional."""
    s = line.strip()
    if "|" not in s.replace(r"\|", ""):
        return []
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith(r"\|"):
        s = s[:-1]
    return [c.strip().replace(r"\|", "|") for c in re.split(r"(?<!\\)\|", s)]


def parse_audit_table(text: str) -> dict:
    """Findings from an audit-xls style report. Rows we can't read are counted in `skipped`, never guessed."""
    findings, header, summary, skipped = [], None, None, 0
    for line in text.splitlines():
        if summary is None and re.search(r"model type\s*:", line, re.I):
            summary = line.strip()
        cells = _cells(line)
        if not cells:
            continue
        low = [_strip(c).lower() for c in cells]
        if low[: len(HEADER)] == HEADER:
            header = low
            continue
        if header is None or all(set(c) <= set("-: ") for c in cells):
            continue
        row = dict(zip(header, cells))
        sev = SEVERITY_MAP.get(_strip(row.get("severity", "")).lower().split(" ")[0] if row.get("severity") else "")
        if sev is None:
            skipped += 1
            continue
        findings.append({
            "sheet": _strip(row.get("sheet", "")),
            "cell": _strip(row.get("cell/range", "")),
            "severity": sev,
            "category": row.get("category", "").strip(),
            "issue": row.get("issue", "").strip(),
            "fix": row.get("suggested fix", "").strip(),
        })
    return {"summary": summary, "findings": findings, "skipped": skipped, "table_found": header is not None}


def _cell_ranges(sheet: str, cell: str) -> list[tuple[str, int, int, int, int]]:
    """(sheet, col1, row1, col2, row2) for each cell or range in a reference like 'C5:G5, B9' or 'DCF!B14'."""
    from openpyxl.utils import column_index_from_string

    cell = cell.replace("$", "").upper()
    sheet = sheet.strip("'").strip()
    if "!" in cell:
        sheet, cell = cell.rsplit("!", 1)
        sheet = sheet.strip("'")
    out = []
    for part in re.split(r"[,;\s]+", cell):
        m = re.fullmatch(r"([A-Z]{1,3})(\d+)(?::([A-Z]{1,3})(\d+))?", part)
        if not m:
            continue
        c1, r1 = column_index_from_string(m.group(1)), int(m.group(2))
        c2, r2 = (column_index_from_string(m.group(3)), int(m.group(4))) if m.group(3) else (c1, r1)
        out.append((sheet.lower(), min(c1, c2), min(r1, r2), max(c1, c2), max(r1, r2)))
    return out


def _overlap(a: list, b: list) -> bool:
    return any(x[0] == y[0] and x[1] <= y[3] and y[1] <= x[3] and x[2] <= y[4] and y[2] <= x[4] for x in a for y in b)


def merge(ours: dict, theirs: dict, their_name: str = "audit-xls") -> list[dict]:
    """Every finding from both reviewers, none dropped. Findings on overlapping cells are marked `both` on each side."""
    their = [(_cell_ranges(f["sheet"], f["cell"]), f) for f in theirs["findings"]]
    ours_r = [(_cell_ranges(*f["ref"].split("!", 1)) if "!" in f["ref"] else [], f) for f in ours["findings"]]
    rows = []
    for rr, f in ours_r:
        hit = any(_overlap(rr, tr) for tr, _ in their)
        rows.append({**f, "found_by": "both" if hit else "deskstack"})
    for tr, f in their:
        hit = any(_overlap(tr, rr) for rr, _ in ours_r)
        rows.append({
            "rule": their_name,
            "severity": f["severity"],
            "ref": f"{f['sheet']}!{f['cell']}",
            "message": f["issue"],
            "category": f["category"],
            "fix": f["fix"],
            "found_by": "both" if hit else their_name,
        })
    rows.sort(key=lambda r: (SEVERITY_ORDER.get(r["severity"], 9), r["ref"]))
    return rows
