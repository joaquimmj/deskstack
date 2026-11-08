"""Tie-out support for /associate: list every typed number, then report verify_value results.

1. `extract(path)` reads the workbook and returns each typed number with its
   label, the period and scale it most likely has, and its Sources row.
   Numbers that look like filed figures (revenue, EBIT, capex...) come with a
   draft `verify_value` item; assumptions (growth, margins, WACC) are listed
   separately because no filing can confirm them, only their cited source.
2. Claude reviews the drafts, calls the connector's `verify_value` tool and
   saves its `results` to a JSON file.
3. `report(path, results)` joins both into the tie-out table.

No network access here: the tool call happens in the conversation.
"""

from __future__ import annotations

import datetime as _dt
import re

from .model import Workbook, file_sha256, label_of, load
from .rules import _looks_like_model_number, _sheet_unit

# Labels that name a filed line item -> verify_value metric. Keep in sync with server/src/verify.ts ALIASES
# (a test checks every metric here is one the server knows).
METRICS = {
    "revenue": "revenue", "revenues": "revenue", "sales": "revenue", "net sales": "revenue",
    "total revenue": "revenue", "turnover": "revenue", "chiffre d'affaires": "revenue",
    "gross profit": "gross_profit",
    "ebit": "operating_income", "operating income": "operating_income", "operating profit": "operating_income",
    "ebit (operating income)": "operating_income", "resultat operationnel": "operating_income",
    "pretax income": "pretax_income", "income before taxes": "pretax_income", "profit before tax": "pretax_income",
    "net income": "net_income", "net profit": "net_income", "resultat net": "net_income",
    "interest expense": "interest_expense",
    "d&a": "d_and_a", "depreciation and amortization": "d_and_a", "depreciation & amortization": "d_and_a",
    "operating cash flow": "operating_cash_flow", "cash from operations": "operating_cash_flow", "cfo": "operating_cash_flow",
    "capex": "capex", "capital expenditures": "capex", "capital expenditure": "capex",
    "diluted shares": "diluted_shares", "diluted shares outstanding": "diluted_shares",
    "diluted eps": "diluted_eps", "eps": "diluted_eps",
    "cash": "cash", "cash and cash equivalents": "cash",
    "total assets": "total_assets", "total equity": "total_equity",
    "ebitda": "ebitda", "free cash flow": "free_cash_flow", "fcf": "free_cash_flow",
    "total debt": "total_debt", "net debt": "net_debt",
}
ASSUMPTION = re.compile(
    r"%|\b(growth|margin|rate|wacc|beta|premium|multiple|discount|cost of|terminal|price|target|share of|convention|"
    r"ratio|yoy|cagr|assumption|forecast|projected)\b",
    re.I,
)
PERIOD = re.compile(r"\b(FY ?\d{2,4}[AE]?|\d{4}[AE]|LTM|TTM|NTM|latest|\d{4}-\d{2}-\d{2})\b", re.I)
YEAR = re.compile(r"^(19[9]\d|20\d\d)$")
# "Apple Inc. (AAPL)": a name, then a ticker in brackets. Codes that are not tickers are excluded.
NAME_TICKER = re.compile(r"[A-Za-z][\w&.,'\- ]*?\s\(([A-Z][A-Z0-9.\-]{0,9})\)")
NOT_TICKERS = {
    "LTM", "TTM", "NTM", "GAAP", "IFRS", "ESEF", "SEC", "XBRL", "EBIT", "EBITDA", "EPS", "FCF", "DCF", "WACC", "LBO",
    "USD", "EUR", "GBP", "CHF", "JPY", "SEK", "NOK", "DKK", "CAD", "AUD", "CNY", "HKD", "INR", "BRL", "PLN", "MM", "BN",
    "A", "E", "K", "M", "B", "NA", "NM",
}
CURRENCY = re.compile(r"\b(USD|EUR|GBP|CHF|JPY|SEK|NOK|DKK|CAD|AUD)\b|(US\$|\$)|(€)|(£)")
PER_SHARE = re.compile(r"per share|eps|shares", re.I)


def _clean(label: str) -> str:
    s = re.sub(r"\((?:in )?(?:thousands|millions|billions|units)\)", "", label, flags=re.I)
    s = PERIOD.sub("", s)
    return re.sub(r"\s+", " ", s).strip(" :-").lower()


def metric_for(label: str) -> str | None:
    """The verify_value metric a label names, or None. Ratio and assumption labels ("Capex (% of revenue)") never map."""
    if not label or ASSUMPTION.search(label):
        return None
    s = _clean(label)
    return METRICS.get(s) or METRICS.get(re.sub(r"\s*\(.*\)$", "", s))


def _column_header(wb: Workbook, c) -> str | None:
    """The nearest text cell above in the same column (the line-item header in a table)."""
    for r in range(c.row - 1, 0, -1):
        h = wb.get(c.sheet, f"{c.coord.rstrip('0123456789')}{r}")
        if h is not None and isinstance(h.constant, str) and h.constant.strip():
            return h.constant.strip()
    return None


def _period_of(v) -> str | None:
    """A period label from a header cell: 'FY2024', '2024A', 2024 (a number), a date, 'LTM'."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)) and float(v).is_integer() and YEAR.match(str(int(v))):
        return str(int(v))
    if isinstance(v, (_dt.date, _dt.datetime)):
        return v.date().isoformat() if isinstance(v, _dt.datetime) else v.isoformat()
    if isinstance(v, str):
        t = v.strip()
        if YEAR.match(t):
            return t
        m = PERIOD.search(t)
        if m:
            return m.group(1)
    return None


def _period_header(wb: Workbook, c) -> str | None:
    """The nearest period-like cell above in the same column, skipping other text ('n.a.', notes)."""
    col = c.coord.rstrip("0123456789")
    for r in range(c.row - 1, 0, -1):
        h = wb.get(c.sheet, f"{col}{r}")
        if h is None:
            continue
        v = h.constant if h.formula is None else wb.value(h)
        p = _period_of(v)
        if p and isinstance(v, (int, float)):
            # A typed number such as 2024 is a year header only on a header row (no label, or a year-like one).
            lab = label_of(wb, h)
            if lab and not re.search(r"\b(year|fy|period|fiscal)\b", lab, re.I):
                continue
        if p:
            return p
    return None


def _sources(wb: Workbook) -> dict[str, dict]:
    """Sources sheet rows by cited cell: period (if a column says so) and source text."""
    src = next((s for s in wb.sheet_order if s.lower().startswith("source")), None)
    out: dict[str, dict] = {}
    if src is None:
        return out
    cells = wb.cells[src]
    header = {c.col: str(c.constant).strip().lower() for c in cells.values() if c.row == 1 and isinstance(c.constant, str)}
    rows: dict[int, dict[int, object]] = {}
    for c in cells.values():
        rows.setdefault(c.row, {})[c.col] = c.constant
    for r, vals in rows.items():
        refs = []
        for v in vals.values():
            if isinstance(v, str):
                refs += [_ref(m) for m in re.findall(r"(?:'[^']+'|[A-Za-z_][A-Za-z0-9_.]*)!\$?[A-Z]{1,3}\$?\d+", v)]
        if not refs:
            continue
        period = next((str(vals[k]) for k, h in header.items() if h == "period" and k in vals), None)
        text = " | ".join(str(v) for k, v in sorted(vals.items()) if isinstance(v, str) and header.get(k) not in ("cell", "period"))
        for ref in refs:
            out[ref] = {"period": period, "source": text}
    return out


def _ref(r: str) -> str:
    """Normalise a cell reference for joining: no $, no quotes around the sheet name."""
    return str(r).replace("$", "").replace("'", "").strip()


def _model_ticker(wb: Workbook) -> str | None:
    """A ticker written as 'Name (TICKER)' near the top of the first sheets, or None (then Claude must look it up)."""
    for s in wb.sheet_order[:3]:
        for c in list(wb.cells[s].values())[:40]:
            if isinstance(c.constant, str):
                for m in NAME_TICKER.finditer(c.constant):
                    t = m.group(1)
                    if t not in NOT_TICKERS and not re.fullmatch(r"(FY)?\d{2,4}[AE]?", t):
                        return t
    return None


def _row_field(wb: Workbook, c, header: str) -> str | None:
    """In a table (e.g. comps), the text in this row under the column headed `header`."""
    for h in wb.cells[c.sheet].values():
        if isinstance(h.constant, str) and h.constant.strip().lower() == header and h.row < c.row:
            t = wb.get(c.sheet, f"{h.coord.rstrip('0123456789')}{c.row}")
            if t is not None and isinstance(t.constant, str):
                return t.constant.strip()
    return None


def _sheet_currency(wb: Workbook, sheet: str) -> str | None:
    for c in list(wb.cells[sheet].values())[:20]:
        if isinstance(c.constant, str):
            m = CURRENCY.search(c.constant)
            if m:
                return m.group(1) or ("USD" if m.group(2) else "EUR" if m.group(3) else "GBP")
    return None


def extract(path: str) -> dict:
    wb = load(path)
    srcs = _sources(wb)
    model_ticker = _model_ticker(wb)
    filed, assumptions, other = [], [], []
    for c in wb.all():
        if not c.is_number_constant or not _looks_like_model_number(wb, c):
            continue
        row_label = label_of(wb, c)
        col_head = _column_header(wb, c) or ""
        src = srcs.get(_ref(c.ref))
        row_metric = metric_for(row_label)
        # A row label that is an assumption ("Capex (% of revenue)") wins over the column header.
        metric = row_metric or (None if ASSUMPTION.search(row_label) else metric_for(col_head))
        # Period: the Sources row, then a period header above, then the label. Never guessed.
        raw = None
        for cand in ((src or {}).get("period"), _period_header(wb, c), row_label):
            raw = _period_of(cand) if cand is not None else None
            if raw:
                break
        period, estimate = _norm_period(raw) if raw else (None, False)
        unit = _sheet_unit(wb, c.sheet)
        scale = "units" if (metric == "diluted_eps" or (PER_SHARE.search(row_label) and "shares" not in row_label.lower())) else (unit or "units")
        if metric == "diluted_shares":
            m = re.search(r"\((thousands|millions|billions)\)", row_label, re.I)
            scale = m.group(1).lower() if m else (unit or "units")
        entry = {
            "ref": _ref(c.ref),
            "label": row_label if row_metric or not col_head else f"{row_label} {col_head}".strip(),
            "value": c.constant,
            "company": _row_field(wb, c, "ticker") or model_ticker,
            "period": period,
            "scale": scale,
            "currency": _row_field(wb, c, "currency") or _sheet_currency(wb, c.sheet),
            "source": (src or {}).get("source"),
        }
        if metric and not estimate:
            entry["metric"] = metric
            filed.append(entry)
        elif metric and estimate:
            entry["note"] = f"{metric} for an estimate period ({raw}): a forecast, not a filed figure"
            assumptions.append(entry)
        elif ASSUMPTION.search(row_label or "") or (isinstance(c.constant, float) and abs(c.constant) < 1 and c.constant != 0):
            assumptions.append(entry)
        else:
            other.append(entry)
    drafts = []
    for e in filed:
        item = {"metric": e["metric"], "period": e["period"], "value": e["value"], "scale": e["scale"], "ref": e["ref"]}
        if e["currency"]:
            item["currency"] = e["currency"]
        drafts.append({"company": e["company"], "item": item})
    needs = [e["ref"] for e in filed if not e["period"]] + [e["ref"] for e in filed if not e["company"]]
    return {
        "file": path,
        "counts": {"filed": len(filed), "assumptions": len(assumptions), "other": len(other),
                   "unsourced": sum(1 for e in filed + assumptions + other if not e["source"])},
        "filed": filed,
        "assumptions": assumptions,
        "other": other,
        "verify_batches": _batches(drafts),
        # Drafts with period or company null must be completed (from the sheet, Sources or the user) before the call.
        "needs_review": sorted(set(needs)),
    }


def _norm_period(p: str) -> tuple[str, bool]:
    """(verify_value period, is_estimate). 'FY24A' -> FY2024; '2026E', 'FY26E', 'NTM' are estimates."""
    q = p.upper().replace(" ", "")
    if q == "TTM":
        return "LTM", False
    if q == "NTM":
        return "NTM", True
    if q == "LATEST":
        return "latest", False
    m = re.fullmatch(r"FY(\d{2}|\d{4})([AE]?)", q) or re.fullmatch(r"(\d{4})([AE]?)", q)
    if m:
        y = m.group(1)
        return f"FY{'20' + y if len(y) == 2 else y}", m.group(2) == "E"
    return p, False


def _batches(drafts: list[dict], size: int = 50) -> list[dict]:
    by: dict[str, list] = {}
    for d in drafts:
        by.setdefault(d["company"] or "?", []).append(d["item"])
    out = []
    for company, items in by.items():
        for i in range(0, len(items), size):
            out.append({"company": None if company == "?" else company, "items": items[i : i + size]})
    return out


def _flatten(results) -> list[dict]:
    """verify_value result items from one response, a list of responses, nested lists, or bare items."""
    out: list[dict] = []
    stack = [results]
    while stack:
        r = stack.pop()
        if isinstance(r, list):
            stack.extend(reversed(r))
        elif isinstance(r, dict) and isinstance(r.get("results"), list):
            stack.extend(reversed(r["results"]))
        elif isinstance(r, dict) and "status" in r:
            out.append(r)
    return out


class ResultsError(ValueError):
    pass


def report(path: str, results) -> dict:
    """Join extraction with verify_value results. Results whose ref matches no extracted cell still get a row."""
    ex = extract(path)
    items = _flatten(results)
    by_ref = {_ref(i["ref"]): i for i in items if i.get("ref")}
    entries = [(e, "filed") for e in ex["filed"]] + [(e, "assumption") for e in ex["assumptions"]] + [(e, "other") for e in ex["other"]]
    known = {e["ref"] for e, _ in entries}
    if items and not (set(by_ref) & known):
        raise ResultsError(
            f"None of the {len(items)} verify_value result(s) matches a cell in the workbook: send each item with "
            "`ref` set to its cell (e.g. 'Inputs!D5'), as in the extract drafts."
        )
    rows = []
    for e, kind in entries:
        v = by_ref.get(e["ref"])
        if v is None and kind != "filed":
            rows.append({**e, "status": kind, "hints": [e["note"]] if e.get("note") else []})
            continue
        rows.append(_row(e, v))
    for ref, v in by_ref.items():
        if ref not in known:
            rows.append(_row({"ref": ref, "label": v.get("metric", ""), "value": v.get("claimed"), "period": v.get("period"),
                              "scale": "units", "company": None, "currency": None, "source": "(not a typed number in the workbook)"}, v))
    for row in rows:
        row["flags"] = []
        if not row.get("source"):
            row["flags"].append("unsourced")
    order = {"mismatch": 0, "ambiguous": 1, "not_found": 2, "not_checked": 3, "assumption": 4, "other": 4, "match": 5}
    rows.sort(key=lambda r: (order.get(r["status"], 9), not r["flags"], r["ref"]))
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    counts["unsourced"] = sum(1 for r in rows if "unsourced" in r["flags"])
    return {"report": "tieout", "file": path, "model_sha256": file_sha256(path), "counts": counts, "rows": rows}


def _row(e: dict, v: dict | None) -> dict:
    # verify_value states `claimed_units` and `filed` in units: compare in the model's scale when we can.
    scale = e["scale"]
    if v and v.get("claimed_units") and e.get("value"):
        scale = next((k for k, f in SCALE.items() if abs(v["claimed_units"] / f - float(e["value"])) < 1e-9 * max(1, abs(float(e["value"])))), scale)
    return {
        **e,
        "status": v["status"] if v else "not_checked",
        "filed_value": _in_scale((v or {}).get("filed", (v or {}).get("filed_value")), scale),
        "difference": (v or {}).get("difference"),
        "hints": (v or {}).get("hints", []),
        "accessions": (v or {}).get("accessions", []),
    }


SCALE = {"units": 1, "thousands": 1e3, "millions": 1e6, "billions": 1e9}


def _in_scale(filed, scale: str):
    """verify_value returns filed figures in units; show them in the model's scale."""
    return filed / SCALE.get(scale, 1) if isinstance(filed, (int, float)) else None


def to_markdown(rep: dict) -> str:
    c = rep["counts"]
    filed = sum(c.get(k, 0) for k in ("match", "mismatch", "not_found", "ambiguous", "not_checked"))
    lines = [
        f"## Tie-out report: {rep['file']}",
        f"{c.get('match', 0)} of {filed} filed figure(s) match the filings; {c.get('mismatch', 0)} mismatch, "
        f"{c.get('not_found', 0)} not found, {c.get('ambiguous', 0)} ambiguous, {c.get('not_checked', 0)} not checked. "
        f"{c.get('assumption', 0)} assumption(s) and {c.get('other', 0)} other typed number(s) need a cited source; "
        f"{c.get('unsourced', 0)} have none.",
        "",
        "| # | Cell | Item | Period | Model value | Status | Filed value (model scale) | Note | Source |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(rep["rows"], start=1):
        note = "; ".join(r.get("hints") or [])
        if "unsourced" in r["flags"]:
            note = ("no Sources row; " + note).strip("; ")
        fv = r.get("filed_value")
        fv_s = f"{fv:,.6g}" if isinstance(fv, (int, float)) else ""
        src = (r.get("source") or "").replace("|", "/")[:80]
        val = f"{r['value']:,.6g}" if isinstance(r.get("value"), (int, float)) else ""
        lines.append(f"| {i} | `{r['ref']}` | {r['label']} | {r.get('period') or ''} | {val} | {r['status']} | {fv_s} | {note} | {src} |")
    return "\n".join(lines)
