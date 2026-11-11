"""Build banking-convention workbooks from a JSON spec: a quick DCF and a comps table.

Every typed number comes from the spec with its source, is formatted as an
input (blue) and gets a row in the Sources sheet. Everything else is a formula
(black). Formula results are computed here too and cached in the file, so the
workbook shows numbers in any viewer and the value checks can run.

Spec formats: see `plugins/deskstack/skills/analyst/references/specs.md`.
"""

from __future__ import annotations

import datetime as _dt
import json
import math
import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter as L

from .xlsxio import inject_values

BLUE = Font(color="FF0000FF")
BLACK = Font(color="FF000000")
GREEN = Font(color="FF008000")
BOLD = Font(bold=True)
HEAD = PatternFill("solid", fgColor="FFDDEBF7")
DISCLAIMER = "Draft for human review. Not investment advice."
SCALES = {"units", "thousands", "millions", "billions"}

HIST_LABELS = {
    "revenue": "Revenue",
    "operating_income": "EBIT (operating income)",
    "d_and_a": "D&A",
    "capex": "Capex",
}


class SpecError(ValueError):
    pass


# Plausible bounds for each rate (decimals). Outside them the spec most likely has percents typed as whole numbers.
RATE_RANGES = {
    "revenue_growth": (-0.9, 2.0),
    "ebit_margin": (-1.0, 1.0),
    "tax_rate": (-0.0001, 0.6),
    "da_pct_revenue": (-0.0001, 1.0),
    "capex_pct_revenue": (-0.0001, 1.0),
    "wacc": (0.0, 0.5),
    "terminal_growth": (-0.05, 0.1),
}


def _period_label(p) -> str:
    """'FY2024', 'LTM' or an ISO end date. A bare year (2024) becomes 'FY2024'."""
    if isinstance(p, int) and not isinstance(p, bool) and 1990 <= p <= 2100:
        return f"FY{p}"
    if isinstance(p, str):
        t = p.strip()
        if re.fullmatch(r"\d{4}", t):
            return f"FY{t}"
        if re.fullmatch(r"FY\d{4}|LTM|\d{4}-\d{2}-\d{2}", t):
            return t
    raise SpecError(f"history.periods: {p!r} is not a period. Use 'FY2024', 'LTM' or an end date 'YYYY-MM-DD'.")


@dataclass
class _Sheet:
    """Cells to write plus the value each formula evaluates to."""

    name: str
    ws: object
    cached: dict = field(default_factory=dict)


@dataclass
class _Book:
    wb: Workbook
    sources: list = field(default_factory=list)  # (ref, item, period, value, source)
    cached: dict = field(default_factory=dict)

    def sheet(self, name: str):
        return self.wb[name] if name in self.wb.sheetnames else self.wb.create_sheet(name)

    def text(self, s: str, coord: str, v: str, bold: bool = False) -> None:
        c = self.sheet(s)[coord]
        c.value = v
        if bold:
            c.font = BOLD

    def inp(self, s: str, coord: str, v, item: str, period: str, source: str, fmt: str | None = None) -> None:
        if not isinstance(source, str) or not source.strip():
            raise SpecError(f"{item} ({period}) has no source: every typed number needs one.")
        c = self.sheet(s)[coord]
        c.value = v
        c.font = BLUE
        if fmt:
            c.number_format = fmt
        self.sources.append((f"{s}!{coord}", item, period, v, source.strip()))

    def f(self, s: str, coord: str, formula: str, value, fmt: str | None = None, link: bool = False) -> None:
        c = self.sheet(s)[coord]
        c.value = formula
        c.font = GREEN if link else BLACK
        if fmt:
            c.number_format = fmt
        self.cached[(s, coord)] = value

    def save(self, out: str | Path) -> Path:
        ws = self.sheet("Sources")
        for i, h in enumerate(["Cell", "Item", "Period", "Value", "Source"], start=1):
            ws.cell(1, i, h).font = BOLD
        for r, (ref, item, period, v, src) in enumerate(self.sources, start=2):
            ws.cell(r, 1, ref)
            ws.cell(r, 2, item)
            ws.cell(r, 3, period)
            ws.cell(r, 4, v)  # a copy for reading; DS004 ignores the Sources sheet
            ws.cell(r, 5, src)
        ws.column_dimensions["A"].width = 14
        ws.column_dimensions["B"].width = 28
        ws.column_dimensions["E"].width = 90
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        self.wb.save(out)
        inject_values(out, self.cached, self.wb.sheetnames)
        return out


def _need(d: dict, key: str, where: str):
    if not isinstance(d, dict):
        raise SpecError(f"{where} must be an object with '{key}', not {type(d).__name__} {d!r:.60}.")
    if key not in d:
        raise SpecError(f"Missing '{key}' in {where}.")
    return d[key]


def _val(d: dict, key: str, where: str):
    """The value of a {"value": ..., "source": ...} field, with a clear error when the field is a bare number or text."""
    item = _need(d, key, where)
    if not isinstance(item, dict) or "value" not in item:
        raise SpecError(f'{where}.{key} must be an object like {{"value": 123, "source": "..."}}, not {item!r:.60}.')
    return item["value"]


def _num(x, where: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x):
        raise SpecError(f"{where} must be a number, got {x!r}.")
    return float(x)


def _cover(b: _Book, title: str, spec: dict, what: str) -> None:
    s = "Cover"
    b.text(s, "A1", title, bold=True)
    b.text(s, "A2", DISCLAIMER)
    b.text(s, "A3", f"Currency: {spec['currency']}. Figures in {spec['scale']} except per-share data and ratios.")
    b.text(s, "A4", f"{what} Every typed number (blue) is cited in the Sources sheet; formulas are black, links green.")
    b.text(s, "A5", f"Built {_dt.date.today().isoformat()} with deskstack. Review with /associate and /vp-review before use.")
    b.sheet(s).column_dimensions["A"].width = 110


# ---- DCF ---------------------------------------------------------------------------------

from .model import LAYOUT_SHEET  # noqa: E402


def dcf_math(rev0: float, growth: list[float], a: dict, mid: bool, net_debt: float, shares: float) -> dict:
    """The DCF the workbook's formulas compute, in Python: per-year rows and the valuation.

    `a` holds ebit_margin, tax_rate, da_pct_revenue, capex_pct_revenue, wacc, terminal_growth (decimals).
    Used to cache the formula results and by `sensitivity` (which re-runs it with shocked inputs).
    """
    rows = {k: [] for k in ("revenue", "ebit", "tax", "nopat", "da", "capex", "fcf", "df", "pv")}
    rev = rev0
    for j, gr in enumerate(growth):
        rev = rev * (1 + gr)
        ebit = rev * a["ebit_margin"]
        tax = ebit * a["tax_rate"]
        da, cx = rev * a["da_pct_revenue"], rev * a["capex_pct_revenue"]
        fcf = ebit - tax + da - cx
        df = 1 / (1 + a["wacc"]) ** ((j + 1) - (0.5 if mid else 0))
        for k, v in zip(rows, (rev, ebit, tax, ebit - tax, da, cx, fcf, df, fcf * df)):
            rows[k].append(v)
    n = len(growth)
    w, g = a["wacc"], a["terminal_growth"]
    tv = rows["fcf"][-1] * (1 + g) / (w - g)
    pv_tv = tv / (1 + w) ** n
    sum_pv = math.fsum(rows["pv"])  # correctly rounded: sum() changed in Python 3.12, and cached values are hashed
    ev = pv_tv + sum_pv
    eq = ev - net_debt
    return {**rows, "tv": tv, "pv_tv": pv_tv, "sum_pv": sum_pv, "ev": ev, "equity": eq,
            "per_share": eq / shares, "tv_share": pv_tv / ev if ev else None}

def build_dcf(spec: dict, out: str | Path, tamper=None) -> Path:
    """`tamper(book)` runs just before saving; tests use it to plant errors."""
    for k in ("company", "ticker", "currency", "scale", "history", "assumptions", "bridge"):
        _need(spec, k, "the DCF spec")
    if spec["scale"] not in SCALES:
        raise SpecError(f"scale must be one of {sorted(SCALES)}.")
    hist, a, br = spec["history"], spec["assumptions"], spec["bridge"]
    periods = [_period_label(p) for p in _need(hist, "periods", "history")]
    lines = _need(hist, "lines", "history")
    for k in HIST_LABELS:
        if k not in lines:
            raise SpecError(f"history.lines needs '{k}'.")
    growth = a["revenue_growth"]["values"] if "revenue_growth" in a else None
    if not growth or len(growth) < 3:
        raise SpecError("assumptions.revenue_growth.values needs one growth rate per projected year (3 to 10).")
    n = len(growth)
    if n > 10:
        raise SpecError("At most 10 projected years.")
    single = ["ebit_margin", "tax_rate", "da_pct_revenue", "capex_pct_revenue", "wacc", "terminal_growth"]
    av = {k: _num(_val(a, k, "assumptions"), f"assumptions.{k}.value") for k in single}
    g = [_num(x, "revenue_growth") for x in growth]
    mid = a.get("mid_year", False)
    if not isinstance(mid, bool):
        raise SpecError("assumptions.mid_year must be true or false (not a string).")
    for k, (lo, hi) in RATE_RANGES.items():
        vals = g if k == "revenue_growth" else [av[k]]
        for v in vals:
            if not lo < v < hi:
                raise SpecError(f"assumptions.{k} = {v} is outside {lo} to {hi}. Rates are decimals: 0.09 means 9%.")
    for key, line in lines.items():
        if line.get("sources") is not None and len(line["sources"]) != len(periods):
            raise SpecError(f"history.lines.{key}.sources needs {len(periods)} entries (one per period).")
    if a["revenue_growth"].get("sources") is not None and len(a["revenue_growth"]["sources"]) != n:
        raise SpecError(f"assumptions.revenue_growth.sources needs {n} entries (one per projected year).")
    if a.get("projection_labels") is not None and len(a["projection_labels"]) != n:
        raise SpecError(f"assumptions.projection_labels needs {n} labels (one per growth rate).")
    nd = _num(_val(br, "net_debt", "bridge"), "bridge.net_debt.value")
    sh = _num(_val(br, "diluted_shares", "bridge"), "bridge.diluted_shares.value")
    if av["wacc"] <= av["terminal_growth"]:
        raise SpecError("WACC must be above terminal growth (the Gordon formula has no finite value otherwise).")
    if sh <= 0:
        raise SpecError("diluted_shares must be positive.")

    b = _Book(Workbook())
    b.wb.remove(b.wb.active)
    cur, scale = spec["currency"], spec["scale"]
    _cover(b, f"{spec['company']} ({spec['ticker']}): quick DCF", spec, "Unlevered DCF, Gordon growth terminal value.")
    num = "#,##0;(#,##0)" if scale != "units" else "#,##0.00"
    pct = "0.0%"

    # Inputs
    s = "Inputs"
    b.text(s, "A1", f"Inputs ({cur} in {scale})", bold=True)
    b.text(s, "A3", "Historical financials (from the filings)", bold=True)
    b.text(s, "A4", "Line item")
    for j, p in enumerate(periods):
        b.text(s, f"{L(2 + j)}4", str(p), bold=True)
    hist_row = {}
    for i, (key, label) in enumerate(HIST_LABELS.items()):
        r = 5 + i
        hist_row[key] = r
        b.text(s, f"A{r}", label)
        line = lines[key]
        vals = _need(line, "values", f"history.lines.{key}")
        if len(vals) != len(periods):
            raise SpecError(f"history.lines.{key}.values needs {len(periods)} values (one per period).")
        srcs = line.get("sources") or [line.get("source")] * len(periods)
        for j, v in enumerate(vals):
            if v is None:
                continue
            b.inp(s, f"{L(2 + j)}{r}", _num(v, f"history.lines.{key}"), label, str(periods[j]), srcs[j], num)
    last_col = L(1 + len(periods))
    r0 = 5 + len(HIST_LABELS) + 1
    b.text(s, f"A{r0}", "Assumptions", bold=True)
    proj_labels = a.get("projection_labels") or [f"Year {i + 1}" for i in range(n)]
    b.text(s, f"A{r0 + 1}", "Projected year")
    for j in range(n):
        b.text(s, f"{L(2 + j)}{r0 + 1}", str(proj_labels[j]), bold=True)
    rg = r0 + 2
    b.text(s, f"A{rg}", "Revenue growth")
    gsrc = a["revenue_growth"].get("sources") or [a["revenue_growth"].get("source")] * n
    for j, v in enumerate(g):
        b.inp(s, f"{L(2 + j)}{rg}", v, "Revenue growth", str(proj_labels[j]), gsrc[j], pct)
    names = {
        "ebit_margin": "EBIT margin",
        "tax_rate": "Tax rate",
        "da_pct_revenue": "D&A % revenue",
        "capex_pct_revenue": "Capex % revenue",
        "wacc": "WACC",
        "terminal_growth": "Terminal growth",
    }
    arow = {}
    for i, k in enumerate(single):
        r = rg + 1 + i
        arow[k] = r
        b.text(s, f"A{r}", names[k])
        b.inp(s, f"B{r}", av[k], names[k], "Projection", a[k].get("source"), pct)
    rm = rg + 1 + len(single)
    b.text(s, f"A{rm}", "Mid-year convention")
    b.text(s, f"B{rm}", "Yes" if mid else "No")
    rb = rm + 2
    b.text(s, f"A{rb}", "Equity bridge", bold=True)
    b.text(s, f"A{rb + 1}", "Net debt")
    b.inp(s, f"B{rb + 1}", nd, "Net debt", br["net_debt"].get("period", "latest"), br["net_debt"].get("source"), num)
    b.text(s, f"A{rb + 2}", f"Diluted shares ({scale})")
    b.inp(s, f"B{rb + 2}", sh, "Diluted shares", br["diluted_shares"].get("period", "latest"), br["diluted_shares"].get("source"), "#,##0.000")
    b.sheet(s).column_dimensions["A"].width = 28

    # DCF
    d = "DCF"
    cols = [L(3 + j) for j in range(n)]
    first, lastc = cols[0], cols[-1]
    W = f"Inputs!$B${arow['wacc']}"
    b.text(d, "A1", f"DCF ({cur} in {scale})", bold=True)
    b.text(d, "A2", "Fiscal year")
    b.text(d, "B2", f"{periods[-1]} (last filed)", bold=True)
    for j, c in enumerate(cols):
        b.text(d, f"{c}2", str(proj_labels[j]), bold=True)
    b.text(d, "A3", "Period")
    for j, c in enumerate(cols):
        b.f(d, f"{c}3", f"=COLUMN()-COLUMN($B$3)", j + 1)
    labels = ["Revenue", "EBIT", "Taxes on EBIT", "NOPAT", "D&A", "Capex", "Unlevered free cash flow", "Discount factor", "PV of FCF"]
    for i, lab in enumerate(labels):
        b.text(d, f"A{4 + i}", lab)
    rev0 = _num(lines["revenue"]["values"][-1], "last revenue")
    b.f(d, "B4", f"=Inputs!{last_col}{hist_row['revenue']}", rev0, num, link=True)
    ebit0 = lines["operating_income"]["values"][-1]
    if ebit0 is not None:
        b.f(d, "B5", f"=Inputs!{last_col}{hist_row['operating_income']}", float(ebit0), num, link=True)
    m = dcf_math(rev0, g, av, mid, nd, sh)
    for j, c in enumerate(cols):
        prev = "B" if j == 0 else cols[j - 1]
        b.f(d, f"{c}4", f"={prev}4*(1+Inputs!{L(2 + j)}{rg})", m["revenue"][j], num)
        b.f(d, f"{c}5", f"={c}4*Inputs!$B${arow['ebit_margin']}", m["ebit"][j], num)
        b.f(d, f"{c}6", f"={c}5*Inputs!$B${arow['tax_rate']}", m["tax"][j], num)
        b.f(d, f"{c}7", f"={c}5-{c}6", m["nopat"][j], num)
        b.f(d, f"{c}8", f"={c}4*Inputs!$B${arow['da_pct_revenue']}", m["da"][j], num)
        b.f(d, f"{c}9", f"={c}4*Inputs!$B${arow['capex_pct_revenue']}", m["capex"][j], num)
        b.f(d, f"{c}10", f"={c}7+{c}8-{c}9", m["fcf"][j], num)
        b.f(d, f"{c}11", f"=1/(1+{W})^({c}3-0.5)" if mid else f"=1/(1+{W})^{c}3", m["df"][j], "0.0000")
        b.f(d, f"{c}12", f"={c}10*{c}11", m["pv"][j], num)
    tv, pv_tv, sum_pv, ev, eq = m["tv"], m["pv_tv"], m["sum_pv"], m["ev"], m["equity"]
    G = f"Inputs!B{arow['terminal_growth']}"
    rows = [
        ("Terminal value", f"={lastc}10*(1+{G})/(Inputs!B{arow['wacc']}-{G})", tv, num),
        ("PV of terminal value", f"=B14/(1+{W})^{lastc}3", pv_tv, num),
        ("Sum of PV of FCF", f"=SUM({first}12:{lastc}12)", sum_pv, num),
        ("Enterprise value", "=B15+B16", ev, num),
        ("Net debt", f"=Inputs!B{rb + 1}", nd, num),
        ("Equity value", "=B17-B18", eq, num),
        (f"Diluted shares ({scale})", f"=Inputs!B{rb + 2}", sh, "#,##0.000"),
        (f"Value per share ({cur})", "=B19/B20", eq / sh, "#,##0.00"),
    ]
    for i, (lab, form, val, fmt) in enumerate(rows):
        r = 14 + i
        b.text(d, f"A{r}", lab, bold=lab in ("Enterprise value", f"Value per share ({cur})"))
        b.f(d, f"B{r}", form, val, fmt, link=form.startswith("=Inputs!"))
    b.text(d, "A23", "Terminal value share of EV")
    b.f(d, "B23", "=B15/B17", pv_tv / ev if ev else "#DIV/0!", pct)
    b.text(d, "A24", "Implied EV / last filed EBIT")
    if ebit0:
        b.f(d, "B24", "=B17/B5", ev / float(ebit0), "0.0x")
    b.sheet(d).column_dimensions["A"].width = 30
    for c in ["B"] + cols:
        b.sheet(d).column_dimensions[c].width = 14
    layout = {
        "version": 1, "kind": "dcf", "company": spec["company"], "ticker": spec["ticker"], "currency": cur, "scale": scale,
        "inputs": {
            "revenue0": f"Inputs!{last_col}{hist_row['revenue']}",
            "revenue_growth": [f"Inputs!{L(2 + j)}{rg}" for j in range(n)],
            **{k: f"Inputs!B{arow[k]}" for k in single},
            "mid_year": f"Inputs!B{rm}",
            "net_debt": f"Inputs!B{rb + 1}",
            "diluted_shares": f"Inputs!B{rb + 2}",
        },
        "outputs": {"enterprise_value": "DCF!B17", "equity_value": "DCF!B19", "value_per_share": "DCF!B21"},
    }
    # The row label each input sits on, so a moved or deleted row is detected instead of read as the wrong number.
    layout["labels"] = {
        "revenue0": "Revenue", "revenue_growth": "Revenue growth", **{k: names[k] for k in single},
        "mid_year": "Mid-year convention", "net_debt": "Net debt", "diluted_shares": f"Diluted shares ({scale})",
    }
    ws = b.sheet(LAYOUT_SHEET)
    ws["A1"] = "deskstack layout (read by the review scripts; do not edit)"
    ws["A2"] = json.dumps(layout)
    ws.sheet_state = "hidden"
    if tamper:
        tamper(b)
    return b.save(out)


# ---- comps -------------------------------------------------------------------------------

COMPS_COLS = [
    ("revenue", "Revenue"),
    ("ebitda", "EBITDA"),
    ("net_income", "Net income"),
    ("market_cap", "Market cap"),
    ("net_debt", "Net debt"),
]


def build_comps(spec: dict, out: str | Path, tamper=None) -> Path:
    for k in ("target", "currency", "scale", "period", "peers"):
        _need(spec, k, "the comps spec")
    # The target's row comes first; medians and means cover the peers below it only.
    peers = sorted(spec["peers"], key=lambda p: p.get("ticker") != spec["target"])
    n_target = sum(1 for p in peers if p.get("ticker") == spec["target"])
    if n_target > 1:
        raise SpecError("The target appears more than once in peers.")
    if not 2 <= len(peers) <= 30 or len(peers) - n_target < 1:
        raise SpecError("Comps need 2 to 30 companies, at least one of them a peer.")
    b = _Book(Workbook())
    b.wb.remove(b.wb.active)
    scale, period = spec["scale"], spec["period"]
    _cover(b, f"Trading comparables for {spec['target']} ({period})", spec,
           "Each company in its own reporting currency; multiples are currency-neutral.")
    s = "Comps"
    num = "#,##0;(#,##0)"
    b.text(s, "A1", f"Comparable companies ({period}, figures in {scale}, each in its reporting currency)", bold=True)
    head = ["Company", "Ticker", "Currency"] + [h for _, h in COMPS_COLS] + ["Enterprise value", "EV / Revenue", "EV / EBITDA", "P / E"]
    for i, h in enumerate(head, start=1):
        c = b.sheet(s).cell(3, i, h)
        c.font = BOLD
        c.fill = HEAD
        c.alignment = Alignment(wrap_text=True)
    first = 4
    for i, p in enumerate(peers):
        r = first + i
        name = _need(p, "name", f"peers[{i}]")
        b.text(s, f"A{r}", name, bold=p.get("ticker") == spec["target"])
        b.text(s, f"B{r}", _need(p, "ticker", f"peers[{i}]"))
        b.text(s, f"C{r}", p.get("currency", spec["currency"]))
        vals = {}
        for j, (k, h) in enumerate(COMPS_COLS):
            item = _need(p, k, f"peers[{i}] ({name})")
            if k == "market_cap" and isinstance(item, dict) and item.get("value") is None:
                vals[k] = None  # deskstack has no prices: a market cap nobody gave stays empty, never estimated
                continue
            v = _num(item["value"], f"{name} {k}")
            vals[k] = v
            b.inp(s, f"{L(4 + j)}{r}", v, f"{name} {h}", item.get("period", period), item.get("source"), num)
        if vals["market_cap"] is None:
            for c in "IJKL":
                b.text(s, f"{c}{r}", "n.a.")
            continue
        ev = vals["market_cap"] + vals["net_debt"]
        b.f(s, f"I{r}", f"=G{r}+H{r}", ev, num)
        evr = ev / vals["revenue"] if vals["revenue"] > 0 else "n.m."
        eve = ev / vals["ebitda"] if vals["ebitda"] > 0 else "n.m."
        pe = vals["market_cap"] / vals["net_income"] if vals["net_income"] > 0 else "n.m."
        b.f(s, f"J{r}", f'=IF(D{r}>0,I{r}/D{r},"n.m.")', evr, "0.0x")
        b.f(s, f"K{r}", f'=IF(E{r}>0,I{r}/E{r},"n.m.")', eve, "0.0x")
        b.f(s, f"L{r}", f'=IF(F{r}>0,G{r}/F{r},"n.m.")', pe, "0.0x")
    last = first + len(peers) - 1
    p1 = first + n_target  # first peer row
    rmed, rmean = last + 2, last + 3
    b.text(s, f"A{rmed}", "Peer median", bold=True)
    b.text(s, f"A{rmean}", "Peer mean", bold=True)
    for c in ("J", "K", "L"):
        # MEDIAN/AVERAGE skip the "n.m." text cells, so the cached values do too.
        vals = [x for x in _col_values(b, s, c, p1, last) if isinstance(x, float)]
        b.f(s, f"{c}{rmed}", f'=IFERROR(MEDIAN({c}{p1}:{c}{last}),"n.m.")', statistics.median(vals) if vals else "n.m.", "0.0x")
        b.f(s, f"{c}{rmean}", f'=IFERROR(AVERAGE({c}{p1}:{c}{last}),"n.m.")', statistics.fmean(vals) if vals else "n.m.", "0.0x")
    b.text(s, f"A{rmean + 2}", "n.m. = not meaningful (negative or zero denominator). Market cap is a typed input: price x shares, cited."
           + (" n.a. = not available: no market cap given." if any(isinstance(p.get("market_cap"), dict) and p["market_cap"].get("value") is None for p in peers) else ""))
    b.sheet(s).column_dimensions["A"].width = 30
    for j in range(2, 13):
        b.sheet(s).column_dimensions[L(j)].width = 13
    if tamper:
        tamper(b)
    return b.save(out)


def _col_values(b: _Book, s: str, col: str, r1: int, r2: int) -> list:
    return [b.cached.get((s, f"{col}{r}")) for r in range(r1, r2 + 1)]


def build(spec_path: str, out: str) -> Path:
    spec = json.loads(Path(spec_path).read_text())
    kind = spec.get("kind")
    if kind == "dcf":
        return build_dcf(spec, out)
    if kind == "comps":
        return build_comps(spec, out)
    raise SpecError("spec.kind must be 'dcf' or 'comps'.")
