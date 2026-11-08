"""Deterministic model checks. Public, widely known spreadsheet-modeling practices only.

Each rule returns findings: (rule id, severity, cell ref, one-line message).
Severities: blocker (the model is wrong or broken), major (likely wrong or
unreviewable), minor (convention), info (a check that could not run).
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from .model import (
    BLUE,
    ERROR_VALUES,
    Workbook,
    label_of,
    references,
    relative_form,
    row_numbers,
    rows_labeled,
    strip_strings,
)


@dataclass(frozen=True)
class Finding:
    rule: str
    severity: str
    ref: str
    message: str


SEVERITY_ORDER = {"blocker": 0, "major": 1, "minor": 2, "info": 3}

# Numbers that are fine inside formulas: 0/1/-1, percentages base, periods per year, days.
ALLOWED_LITERALS = {0.0, 1.0, -1.0, 2.0, 100.0, 12.0, 4.0, 365.0, 360.0, 1000.0, 1000000.0, 0.5}
NUMBER_IN_FORMULA = re.compile(r"(?<![A-Za-z0-9_.$!:\]])(\d+(?:\.\d+)?)(?![A-Za-z0-9_(!:\[])")


def r_hardcode_in_formula(wb: Workbook) -> list[Finding]:
    """DS001: a number typed into a formula (=B5*1.05) hides an assumption from the inputs."""
    out = []
    for c in wb.all():
        if c.formula is None:
            continue
        body = strip_strings(c.formula)
        # Remove cell references and ranges so their row numbers aren't read as literals.
        body = re.sub(r"(?:'[^']+'|[A-Za-z_][A-Za-z0-9_.]*)?!?\$?[A-Z]{1,3}\$?\d{1,7}", " ", body)
        lits = {float(x) for x in NUMBER_IN_FORMULA.findall(body)}
        bad = sorted(v for v in lits if v not in ALLOWED_LITERALS)
        if bad:
            shown = ", ".join(f"{v:g}" for v in bad[:3])
            out.append(Finding("DS001", "major", c.ref, f"Hardcoded number(s) {shown} inside a formula; move them to a labeled input cell."))
    return out


def r_inconsistent_row(wb: Workbook) -> list[Finding]:
    """DS002: in a row of formulas, one cell doesn't follow the pattern of its neighbours."""
    out = []
    for s in wb.sheet_order:
        rows: dict[int, list] = defaultdict(list)
        for c in wb.cells[s].values():
            if c.formula is not None:
                rows[c.row].append(c)
        for row, cells in rows.items():
            cells.sort(key=lambda c: c.col)
            if len(cells) < 4:
                continue
            forms = [relative_form(c.formula, c.row, c.col) for c in cells]
            common, n = Counter(forms).most_common(1)[0]
            if n < max(3, math.ceil(len(cells) * 0.6)):
                continue  # no dominant pattern (e.g. a header row of different formulas)
            # The first column of a projection often differs (it links to history): only flag interior/last cells.
            for i, (c, f) in enumerate(zip(cells, forms)):
                if f != common and i > 0:
                    out.append(Finding("DS002", "major", c.ref, f"Formula breaks the row pattern ({c.formula}); check it matches its neighbours."))
    return out


def r_input_formatting(wb: Workbook) -> list[Finding]:
    """DS003: blue font = typed input, black = formula (banking convention)."""
    out = []
    for c in wb.all():
        blue = (c.font_color or "") in BLUE
        if c.is_number_constant and not blue and _looks_like_model_number(wb, c):
            out.append(Finding("DS003", "minor", c.ref, "Typed number not formatted as an input (blue font)."))
        elif c.formula is not None and blue:
            out.append(Finding("DS003", "minor", c.ref, "Formula formatted as an input (blue font); inputs should be typed values only."))
    return out


def _looks_like_model_number(wb: Workbook, c) -> bool:
    # Years in header rows (2024, 2025...) and the Sources sheet are not model inputs.
    if c.sheet.lower().startswith("source"):
        return False
    if isinstance(c.constant, (int, float)) and float(c.constant).is_integer() and 1990 <= c.constant <= 2100:
        label = label_of(wb, c)
        if not label or re.search(r"\b(year|fy|period|fiscal)\b", label, re.I):
            return False
    return True


def r_unsourced_hardcodes(wb: Workbook) -> list[Finding]:
    """DS004: every typed number needs a row in the Sources sheet (cited to the filing or the user)."""
    src = next((s for s in wb.sheet_order if s.lower().startswith("source")), None)
    inputs = [c for c in wb.all() if c.is_number_constant and _looks_like_model_number(wb, c)]
    if not inputs:
        return []
    if src is None:
        return [Finding("DS004", "major", f"{inputs[0].ref}", f"No Sources sheet: {len(inputs)} typed number(s) have no citation.")]
    # Read each Sources cell on its own (joined text would glue words onto sheet names).
    cited = set()
    for sc in wb.cells[src].values():
        if isinstance(sc.constant, str):
            for m in re.findall(r"(?:'[^']+'|[A-Za-z_][A-Za-z0-9_.]*)!\$?[A-Z]{1,3}\$?\d+", sc.constant):
                cited.add(m.replace("$", "").replace("'", ""))
    out = []
    for c in inputs:
        if f"{c.sheet}!{c.coord}" not in cited:
            out.append(Finding("DS004", "major", c.ref, "Typed number with no matching row in the Sources sheet."))
    return out


def r_external_links(wb: Workbook) -> list[Finding]:
    """DS005: links to other workbooks break when the file moves and can't be reviewed."""
    out = []
    for c in wb.all():
        if c.formula is not None and re.search(r"\[[^\]]+\]|\.xls[xm]?['!]", c.formula):
            out.append(Finding("DS005", "blocker", c.ref, "Formula links to another workbook; paste the value with a source instead."))
    if wb.external_links and not out:
        out.append(Finding("DS005", "blocker", f"{wb.sheet_order[0]}!A1", f"Workbook contains {wb.external_links} external link(s)."))
    return out


def r_error_values(wb: Workbook) -> list[Finding]:
    """DS006: #REF!, #DIV/0!, #N/A... in formulas or results."""
    out = []
    for c in wb.all():
        v = wb.value(c)
        if (c.formula and "#REF!" in c.formula) or (isinstance(v, str) and v.strip() in ERROR_VALUES):
            shown = "#REF!" if c.formula and "#REF!" in c.formula else str(v).strip()
            out.append(Finding("DS006", "blocker", c.ref, f"Error value {shown}."))
    return out


def r_circular(wb: Workbook) -> list[Finding]:
    """DS007: circular references (and whether Excel's iterative calculation is on)."""
    graph: dict[str, list[str]] = {}
    for c in wb.all():
        if c.formula is not None:
            graph[c.ref] = [f"{s}!{k}" for s, k in references(c.formula, c.sheet)]
    seen: dict[str, int] = {}  # 0 = visiting, 1 = done
    cycles: list[list[str]] = []

    def visit(n: str, path: list[str]) -> None:
        if len(cycles) >= 5:
            return
        state = seen.get(n)
        if state == 1:
            return
        if state == 0:
            cycles.append(path[path.index(n):] if n in path else [n])
            return
        seen[n] = 0
        path.append(n)
        for m in graph.get(n, []):
            if m in graph:
                visit(m, path)
        path.pop()
        seen[n] = 1

    import sys

    old = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old, 20000))
    try:
        for n in list(graph):
            visit(n, [])
    finally:
        sys.setrecursionlimit(old)
    sev = "major" if wb.iterate else "blocker"
    note = "iterative calculation is ON (intended circularity, e.g. interest on average debt?)" if wb.iterate else "iterative calculation is OFF, so Excel cannot resolve it"
    return [Finding("DS007", sev, cyc[0], f"Circular reference: {' -> '.join(cyc[:6])}{' ...' if len(cyc) > 6 else ''}; {note}.") for cyc in cycles]


# ---- value-based checks (need cached values) -------------------------------------------

def _num(v) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _row_values(wb: Workbook, sheet: str, row: int) -> dict[int, float]:
    out = {}
    for c in row_numbers(wb, sheet, row):
        v = _num(wb.value(c))
        if v is not None:
            out[c.col] = v
    return out


TOTAL_ASSETS = re.compile(r"^total assets$", re.I)
TOTAL_L_E = re.compile(r"^total (liabilities (and|&) (shareholders'? |stockholders'? )?equity|equity and liabilities)$", re.I)
CF_END_CASH = re.compile(r"^(ending cash|cash (at|,) end of (the )?(period|year)|closing cash)", re.I)
BS_CASH = re.compile(r"^cash( and cash equivalents)?$", re.I)


def r_balance_sheet(wb: Workbook) -> list[Finding]:
    """DS008: total assets must equal total liabilities + equity in every period."""
    out = []
    ta = rows_labeled(wb, TOTAL_ASSETS)
    tle = rows_labeled(wb, TOTAL_L_E)
    for s, r, _ in ta:
        match = [x for x in tle if x[0] == s]
        if not match:
            continue
        a, le = _row_values(wb, s, r), _row_values(wb, s, match[0][1])
        for col, av in a.items():
            lv = le.get(col)
            if lv is not None and abs(av - lv) > max(0.5, 1e-6 * abs(av)):
                out.append(Finding("DS008", "blocker", f"{s}!{_letter(col)}{r}", f"Balance sheet doesn't balance: assets {av:,.2f} vs liabilities + equity {lv:,.2f}."))
    return out


def r_cash_tie(wb: Workbook) -> list[Finding]:
    """DS009: cash-flow ending cash must equal balance-sheet cash."""
    out = []
    ends = rows_labeled(wb, CF_END_CASH)
    cash = rows_labeled(wb, BS_CASH)
    if not ends or not cash:
        return out
    (s1, r1, _), (s2, r2, _) = ends[0], cash[0]
    a, b = _row_values(wb, s1, r1), _row_values(wb, s2, r2)
    for col, av in a.items():
        bv = b.get(col)
        if bv is not None and abs(av - bv) > max(0.5, 1e-6 * abs(av)):
            out.append(Finding("DS009", "major", f"{s1}!{_letter(col)}{r1}", f"Ending cash {av:,.2f} doesn't tie to balance-sheet cash {bv:,.2f} ({s2}!{_letter(col)}{r2})."))
    return out


def _labeled_value(wb: Workbook, pattern: str) -> tuple[float, str] | None:
    """The first numeric value on the first row whose label matches."""
    rows = rows_labeled(wb, re.compile(pattern, re.I))
    for s, r, _ in rows:
        vals = row_numbers(wb, s, r)
        for c in vals:
            v = _num(wb.value(c))
            if v is not None:
                return v, c.ref
    return None


def _pct(v: float) -> float:
    return v / 100 if v > 1 else v  # 9.5 (percent) or 0.095 (decimal)


def r_dcf_sanity(wb: Workbook) -> list[Finding]:
    """DS010-DS012: terminal value share of EV, WACC vs terminal growth, terminal growth vs long-run GDP."""
    out = []
    pv_tv = _labeled_value(wb, r"^(pv|present value) of (the )?terminal value")
    ev = _labeled_value(wb, r"^enterprise value")
    if pv_tv and ev and ev[0] > 0:
        share = pv_tv[0] / ev[0]
        if share > 0.75:
            out.append(Finding("DS010", "major", pv_tv[1], f"Terminal value is {share:.0%} of enterprise value (> 75%): the valuation rests on the terminal assumptions."))
    wacc = _labeled_value(wb, r"^(wacc|discount rate|weighted average cost of capital)")
    g = _labeled_value(wb, r"^(terminal|perpetu(al|ity)|long[- ]term) growth")
    if wacc and g:
        w, gg = _pct(wacc[0]), _pct(g[0])
        if w - gg < 0.02:
            out.append(Finding("DS011", "major", g[1], f"WACC {w:.1%} minus terminal growth {gg:.1%} is under 2 points: the terminal value explodes; check both."))
        if gg > 0.04:
            out.append(Finding("DS012", "major", g[1], f"Terminal growth {gg:.1%} is above a long-run nominal GDP proxy (~4%)."))
    return out


UNIT_RE = re.compile(r"\b(in |\()?(thousands|millions|billions|\$?k\b|\$?m{1,2}\b|\$?bn?\b)", re.I)


def _sheet_unit(wb: Workbook, sheet: str) -> str | None:
    for c in list(wb.cells[sheet].values())[:60]:
        if isinstance(c.constant, str):
            m = re.search(r"\b(in |\()?(thousands|millions|billions)\b", c.constant, re.I)
            if m:
                return m.group(2).lower()
    return None


def r_units_mix(wb: Workbook) -> list[Finding]:
    """DS013: a formula reads a sheet declared in other units without converting."""
    units = {s: _sheet_unit(wb, s) for s in wb.sheet_order}
    out = []
    for c in wb.all():
        if c.formula is None or units.get(c.sheet) is None:
            continue
        for s, _ in references(c.formula, c.sheet):
            u = units.get(s)
            if s != c.sheet and u and u != units[c.sheet] and not re.search(r"[*/]\s*(1000|1e3|1000000|1e6)\b", c.formula):
                out.append(Finding("DS013", "major", c.ref, f"Reads {s} (in {u}) from a sheet in {units[c.sheet]} without converting."))
                break
    return out


def r_sign_flips(wb: Workbook) -> list[Finding]:
    """DS014: capex or D&A changing sign across periods (usually a sign-convention slip)."""
    out = []
    for s, r, label in rows_labeled(wb, re.compile(r"^(capex|capital expenditures?|d&a|depreciation( and|&) amortization)", re.I)):
        vals = [v for _, v in sorted(_row_values(wb, s, r).items()) if v != 0]
        if len(vals) >= 3 and any(v > 0 for v in vals) and any(v < 0 for v in vals):
            out.append(Finding("DS014", "major", f"{s}!A{r}", f"{label}: values change sign across periods; keep one sign convention."))
    return out


def r_discount_timing(wb: Workbook) -> list[Finding]:
    """DS015: discount factors must match the stated convention (mid-year: n - 0.5; end-of-year: n)."""
    out = []
    wacc = _labeled_value(wb, r"^(wacc|discount rate|weighted average cost of capital)")
    rows = rows_labeled(wb, re.compile(r"^discount factor", re.I))
    if not wacc or not rows:
        return out
    w = _pct(wacc[0])
    mid = any(re.search(r"mid[- ]year", str(c.constant or ""), re.I) and _truthy(wb, c) for c in wb.all())
    s, r, _ = rows[0]
    periods = []
    for col, df in sorted(_row_values(wb, s, r).items()):
        if 0 < df < 1:
            periods.append((col, -math.log(df) / math.log(1 + w)))
    if len(periods) < 2:
        return out
    fracs = [n - math.floor(n) for _, n in periods]
    looks_mid = all(abs(f - 0.5) < 0.05 for f in fracs)
    looks_end = all(f < 0.05 or f > 0.95 for f in fracs)
    if mid and not looks_mid:
        out.append(Finding("DS015", "major", f"{s}!{_letter(periods[0][0])}{r}", "Mid-year convention is stated but discount factors use whole periods."))
    elif not mid and looks_mid:
        out.append(Finding("DS015", "minor", f"{s}!{_letter(periods[0][0])}{r}", "Discount factors use half periods (mid-year) but no mid-year convention is stated."))
    elif not looks_mid and not looks_end:
        out.append(Finding("DS015", "major", f"{s}!{_letter(periods[0][0])}{r}", "Discount factors don't match the WACC with a consistent period count."))
    return out


def _truthy(wb: Workbook, label_cell) -> bool:
    # "Mid-year convention" with a value to its right: TRUE / Yes / 1 means it is used.
    row = [c for c in wb.cells[label_cell.sheet].values() if c.row == label_cell.row and c.col > label_cell.col]
    if not row:
        return "mid" in str(label_cell.constant).lower() and "not" not in str(label_cell.constant).lower()
    v = wb.value(sorted(row, key=lambda c: c.col)[0])
    return v is True or str(v).strip().lower() in {"yes", "true", "1", "y", "oui"}


def _letter(col: int) -> str:
    from openpyxl.utils import get_column_letter

    return get_column_letter(col)


STRUCTURAL = [
    r_hardcode_in_formula,
    r_inconsistent_row,
    r_input_formatting,
    r_unsourced_hardcodes,
    r_external_links,
    r_error_values,
    r_circular,
    r_units_mix,
]
# These read results; for formula cells they need the values Excel cached on save.
VALUE_BASED = [r_balance_sheet, r_cash_tie, r_dcf_sanity, r_sign_flips, r_discount_timing]
