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

# Category and suggested fix per rule, for the audit-xls-compatible report.
RULE_INFO = {
    "DS000": ("Coverage", "Re-run after the noted fix (e.g. open and save the file in Excel)."),
    "DS001": ("Hardcode", "Move the number to a labeled, blue, cited input cell and reference it."),
    "DS002": ("Formula consistency", "Make the cell follow its row's formula, or label why it differs."),
    "DS003": ("Formatting", "Blue font for typed inputs, black for formulas, green for links to other sheets."),
    "DS004": ("Sourcing", "Add a Sources row citing the filing (accession) or the person who gave the number."),
    "DS005": ("External link", "Paste the linked values as cited inputs or bring the source sheet into the workbook."),
    "DS006": ("Error value", "Fix the broken reference or guard the division."),
    "DS007": ("Circularity", "Break the loop, or document why it exists and keep iterative calculation on."),
    "DS008": ("Balance sheet", "Find the plug: compare each period's asset and liability movements."),
    "DS009": ("Cash tie-out", "Link balance-sheet cash to the cash-flow ending cash."),
    "DS010": ("Terminal value", "Extend the forecast or test the terminal assumptions; show sensitivities."),
    "DS011": ("WACC vs growth", "Check both inputs; terminal growth should sit well below WACC."),
    "DS012": ("Terminal growth", "Use a long-run growth at or below nominal GDP, or justify it."),
    "DS013": ("Units", "Convert between thousands and millions explicitly, or use one unit everywhere."),
    "DS014": ("Sign convention", "Use one sign for capex and D&A across all periods."),
    "DS015": ("Discount timing", "Make the discount periods match the stated mid-year or end-of-year convention."),
    "DS016": ("Placeholder", "Find the filed figure (verify_value), or leave the cell empty and say it is missing; never a 0 or a guess."),
    "DS017": ("Synthetic series", "Check each typed figure against the filing; filed history rarely grows at one exact rate."),
    "DS018": ("Balancing plug", "Remove the plug and find the line that is off: compare each period's movements."),
    "DS019": ("Interest and debt", "Compute interest from the debt and cash balances, and give debt a repayment schedule."),
    "DS020": ("Share count", "Roll the share count forward: buybacks and dilution change it every period."),
    "DS021": ("Percent units", "Type the rate as a decimal (0.05 for 5%), like the model's other rates, or divide it by 100 where it is used."),
}

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


UNIT_WORDS = [
    (re.compile(r"\b(in |\()?(thousands)\b|\(0{3}s?\)|\bin 0{3}s?\b|\b0{3}s\b|[$€£]\s?k\b|\b(?:usd|eur|gbp)\s?k\b", re.I), "thousands"),
    (re.compile(r"\b(in |\()?(millions)\b|(?:US)?[$€£]\s?mm?\b|\b(?:usd|eur|gbp|chf)\s?mm?\b|\(mm?\)|\bin mm?\b", re.I), "millions"),
    (re.compile(r"\b(in |\()?(billions)\b|(?:US)?[$€£]\s?bn?\b|\b(?:usd|eur|gbp|chf)\s?bn\b|\(bn\)|\bin bn\b", re.I), "billions"),
]


def _sheet_unit(wb: Workbook, sheet: str) -> str | None:
    """The unit a sheet declares near its top: "(USD in millions)", "$mm", "EUR m", "(000s)", "€bn"..."""
    for c in list(wb.cells[sheet].values())[:60]:
        if isinstance(c.constant, str):
            for pat, unit in UNIT_WORDS:
                if pat.search(c.constant):
                    return unit
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



# ---- Rules for the errors AI-built models make (stars brief lot 2: Wall Street Prep 2026, deskstack's benchmarks) ----

PLACEHOLDER_STRONG = re.compile(
    r"\b(not found|placeholder|tbd|to be (confirmed|determined)|dummy|fictional|made[- ]up|lorem|xxx+|to replace|"
    r"missing|unavailable|no data)\b",
    re.I,
)
PLACEHOLDER_SOFT = re.compile(r"\b(estimated?|estimates|approx(imately|\.)?|roughly|ballpark|guess(ed)?|assumed)\b", re.I)
FILING_CITED = re.compile(r"\b(10-?K|10-?Q|20-?F|40-?F|annual report|ESEF|accession|0\d{9}-\d{2}-\d{6})\b", re.I)


def _source_texts(wb: Workbook) -> dict[str, str]:
    """Sources-sheet text per cited cell ("Inputs!B7" -> the rest of its row)."""
    src = next((s for s in wb.sheet_order if s.lower().startswith("source")), None)
    if src is None:
        return {}
    by_row: dict[int, list] = defaultdict(list)
    for sc in wb.cells[src].values():
        by_row[sc.row].append(sc)
    out = {}
    for cells in by_row.values():
        texts = [str(c.constant) for c in sorted(cells, key=lambda c: c.col) if isinstance(c.constant, str)]
        joined = " ".join(texts)
        for m in re.findall(r"(?:'[^']+'|[A-Za-z_][A-Za-z0-9_.]*)!\$?[A-Z]{1,3}\$?\d+", joined):
            out[m.replace("$", "").replace("'", "")] = joined
    return out


def r_placeholders(wb: Workbook) -> list[Finding]:
    """DS016: a typed number whose source or label says it wasn't found (a placeholder 0, "TBD", "NOT FOUND")."""
    sources = _source_texts(wb)
    out = []
    for c in wb.all():
        if not (c.is_number_constant and _looks_like_model_number(wb, c)):
            continue
        text = f"{label_of(wb, c)} {sources.get(c.ref, '')}"
        v = wb.value(c)
        if PLACEHOLDER_STRONG.search(text):
            what = "a placeholder 0" if v == 0 else "a placeholder"
            out.append(Finding("DS016", "major", c.ref, f"Looks like {what}: its label or source says {PLACEHOLDER_STRONG.search(text).group(0)!r}."))
        elif PLACEHOLDER_SOFT.search(text) and not FILING_CITED.search(text):
            out.append(Finding("DS016", "minor", c.ref, f"An estimated figure ({PLACEHOLDER_SOFT.search(text).group(0)!r}) with no filing cited: confirm it is an assumption, not a missing filed number."))
    return out


# Rows that hold one financial line over time (not a comps row, where each column is another metric).
LINE_ITEM_RE = re.compile(r"\b(revenue|sales|ebitda?|operating income|net income|gross profit|capex|capital expenditure|d&a|depreciation|free cash flow)\b", re.I)


def r_synthetic_series(wb: Workbook) -> list[Finding]:
    """DS017: four or more typed figures on a row that grow at one exact rate, or are all round thousands."""
    out = []
    rows = defaultdict(list)
    for c in wb.all():
        if c.is_number_constant and _looks_like_model_number(wb, c):
            rows[(c.sheet, c.row)].append(c)
    for (_sheet, _row), cells in rows.items():
        cells.sort(key=lambda c: c.col)
        vals = [float(wb.value(c)) for c in cells]
        if len(vals) < 4 or any(v == 0 for v in vals):
            continue
        ratios = [b / a for a, b in zip(vals, vals[1:])]
        if all(abs(r - ratios[0]) < 1e-9 * max(1.0, abs(ratios[0])) for r in ratios) and abs(ratios[0] - 1) > 1e-9:
            out.append(Finding("DS017", "minor", cells[0].ref, f"{len(vals)} typed figures grow by exactly {ratios[0] - 1:.2%} every period: filed history rarely does."))
        elif LINE_ITEM_RE.search(label_of(wb, cells[0])) and all(abs(v) >= 1000 and v % 1000 == 0 for v in vals):
            out.append(Finding("DS017", "minor", cells[0].ref, f"{len(vals)} typed figures are all round thousands: check them against the filing."))
    return out


PLUG_RE = re.compile(r"\b(plug|balancing (item|figure|line|plug)|squeeze|check figure|cash (adjustment|plug)|adjusted cash)\b", re.I)


def r_balancing_plug(wb: Workbook) -> list[Finding]:
    """DS018: a line labeled as a plug or balancing item, with a value: the model balances only through it."""
    out = []
    for sheet, row, label in rows_labeled(wb, PLUG_RE):
        nums = [c for c in row_numbers(wb, sheet, row) if isinstance(wb.value(c), (int, float)) and wb.value(c) != 0]
        if nums:
            out.append(Finding("DS018", "major", nums[0].ref, f"{label!r} is a balancing plug: the model balances only through it."))
    return out


INTEREST_RE = re.compile(r"\binterest (expense|paid|cost|charge)s?\b|\bnet interest\b|\bfinance costs?\b", re.I)
DEBT_RE = re.compile(r"\b(debt|borrowings?|loans?|notes|bonds?|revolver|cash|interest rate|cost of debt)\b", re.I)
SCHEDULE_RE = re.compile(r"\b(repay(ment)?s?|issu(ance|ed)|maturit(y|ies)|amortization of debt|drawdowns?|refinanc)", re.I)


def r_interest_and_debt(wb: Workbook) -> list[Finding]:
    """DS019: interest typed or not computed from debt and cash; debt held flat with no schedule."""
    sources = _source_texts(wb)
    out = []
    for sheet, row, label in rows_labeled(wb, INTEREST_RE):
        nums = row_numbers(wb, sheet, row)
        if len(nums) < 2:
            continue
        typed = [c for c in nums if c.formula is None and not FILING_CITED.search(sources.get(c.ref, ""))]
        if typed:
            out.append(Finding("DS019", "major", typed[0].ref, f"{label!r} is typed in {len(typed)} period(s) instead of computed from debt and cash."))
            continue
        linked = False
        for c in nums:
            for ref_sheet, ref in references(c.formula or "", sheet):
                other = wb.get(ref_sheet, ref)
                if other is not None and DEBT_RE.search(label_of(wb, other)):
                    linked = True
        if not linked:
            out.append(Finding("DS019", "major", nums[0].ref, f"{label!r} formulas don't reference any debt or cash balance."))
    has_schedule = bool(rows_labeled(wb, SCHEDULE_RE))
    for sheet, row, label in rows_labeled(wb, re.compile(r"^(total )?(debt|borrowings|gross debt)$", re.I)):
        vals = [wb.value(c) for c in row_numbers(wb, sheet, row)]
        vals = [v for v in vals if isinstance(v, (int, float))]
        if len(vals) >= 3 and len(set(vals)) == 1 and not has_schedule:
            out.append(Finding("DS019", "minor", row_numbers(wb, sheet, row)[0].ref, f"{label!r} is flat across {len(vals)} periods with no repayment or issuance schedule."))
    return out


SHARES_RE = re.compile(r"\b(diluted shares|shares outstanding|share count|weighted average shares)\b", re.I)
BUYBACK_RE = re.compile(r"\b(buy ?backs?|share repurchases?|repurchases?)\b", re.I)


def r_flat_share_count(wb: Workbook) -> list[Finding]:
    """DS020: a share count that stays flat across periods while the model has buybacks."""
    buybacks = any(
        any(isinstance(wb.value(c), (int, float)) and wb.value(c) != 0 for c in row_numbers(wb, s, r))
        for s, r, _ in rows_labeled(wb, BUYBACK_RE)
    )
    if not buybacks:
        return []
    out = []
    for sheet, row, label in rows_labeled(wb, SHARES_RE):
        cells = row_numbers(wb, sheet, row)
        vals = [wb.value(c) for c in cells if isinstance(wb.value(c), (int, float))]
        if len(vals) >= 3 and len(set(vals)) == 1:
            out.append(Finding("DS020", "minor", cells[0].ref, f"{label!r} stays at {vals[0]:g} for {len(vals)} periods while the model has buybacks."))
    return out

# Rows that hold a rate. Their typed values should share one convention: decimals (0.05) or whole percents (5).
RATE_RE = re.compile(
    r"\b(growth|margin|tax rate|wacc|discount rate|cost of (equity|debt|capital)|equity risk premium|erp|risk[- ]free|"
    r"inflation|payout|cagr|yield)\b|%",
    re.I,
)


def r_percent_units(wb: Workbook) -> list[Finding]:
    """DS021: a rate typed as a whole number (5 for 5%): shown as 500% in a % cell, or out of line with the model's
    other rates, which are decimals. A model that types every rate as a whole percent is left alone."""
    rates = [c for c in wb.all() if c.is_number_constant and _looks_like_model_number(wb, c) and RATE_RE.search(label_of(wb, c))]
    decimals = sum(1 for c in rates if 0 < abs(c.constant) < 1)
    out = []
    for c in rates:
        v = c.constant
        if abs(v) <= 1:
            continue
        label = label_of(wb, c)
        if c.number_format and "%" in c.number_format:
            out.append(Finding("DS021", "major", c.ref, f"{label!r} is typed as {v:g} in a percent cell, so it shows as {v * 100:.0f}%: a rate typed as a whole number?"))
        elif abs(v) <= 100 and decimals >= 2:
            out.append(Finding("DS021", "major", c.ref, f"{label!r} is typed as {v:g} while the model's other {decimals} rates are decimals (e.g. 0.05 for 5%): it reads as {v * 100:.0f}%."))
    return out


STRUCTURAL = [
    r_hardcode_in_formula,
    r_inconsistent_row,
    r_input_formatting,
    r_unsourced_hardcodes,
    r_external_links,
    r_error_values,
    r_circular,
    r_units_mix,
    r_placeholders,
    r_synthetic_series,
    r_interest_and_debt,
    r_percent_units,
]
# These read results; for formula cells they need the values Excel cached on save.
VALUE_BASED = [r_balance_sheet, r_cash_tie, r_dcf_sanity, r_sign_flips, r_discount_timing, r_balancing_plug, r_flat_share_count]
