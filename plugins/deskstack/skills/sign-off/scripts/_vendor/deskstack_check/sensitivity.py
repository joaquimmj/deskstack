"""Sensitivities for /md-redteam: how much the answer moves when each assumption moves.

Works on DCFs built by deskstack (they carry a hidden layout sheet that says
where each input lives). It reads the inputs as they are now in the file, so
edits made in Excel count, and re-runs the same DCF math the workbook's
formulas use. For other workbooks it says so: the red team then works from
the model's own sensitivity tables or by hand.
"""

from __future__ import annotations

import json
import math

from .build import LAYOUT_SHEET, dcf_math
from .model import file_sha256, label_of, load

SINGLE = ["ebit_margin", "tax_rate", "da_pct_revenue", "capex_pct_revenue", "wacc", "terminal_growth"]
# One-at-a-time shocks (absolute, decimals). Growth shifts every projected year.
SHOCKS = [
    ("revenue_growth", 0.02, "Revenue growth, every year"),
    ("ebit_margin", 0.02, "EBIT margin"),
    ("capex_pct_revenue", 0.01, "Capex % revenue"),
    ("tax_rate", 0.03, "Tax rate"),
    ("wacc", 0.01, "WACC"),
    ("terminal_growth", 0.005, "Terminal growth"),
]


class NoLayout(ValueError):
    pass


def _cell(wb, ref: str, label: str | None):
    sheet, coord = ref.split("!", 1)
    c = wb.get(sheet, coord)
    if c is None:
        raise NoLayout(f"Layout points to {ref}, which is empty: rows or columns were moved. Rebuild the model, or "
                       "compute sensitivities by hand.")
    if label and label_of(wb, c) != label:
        raise NoLayout(f"{ref} should be '{label}' but its row says '{label_of(wb, c)}': rows were moved. Rebuild the "
                       "model, or compute sensitivities by hand.")
    return c


def _num(wb, ref: str, label: str | None) -> float:
    v = wb.value(_cell(wb, ref, label))
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise NoLayout(f"{ref} ({label}) holds {v!r}, not a number.")
    return float(v)


def read_inputs(path: str) -> tuple[dict, dict]:
    wb = load(path, include_layout=True)
    cell = wb.get(LAYOUT_SHEET, "A2")
    if cell is None or not isinstance(cell.constant, str):
        raise NoLayout("This workbook wasn't built by deskstack (no layout sheet). Use its own sensitivity tables, or "
                       "compute the shocks by hand from its inputs.")
    try:
        layout = json.loads(cell.constant)
        i, lab = layout["inputs"], layout.get("labels", {})
        vals = {
            "revenue0": _num(wb, i["revenue0"], lab.get("revenue0")),
            "revenue_growth": [_num(wb, r, lab.get("revenue_growth")) for r in i["revenue_growth"]],
            **{k: _num(wb, i[k], lab.get(k)) for k in SINGLE},
            "mid_year": str(wb.value(_cell(wb, i["mid_year"], lab.get("mid_year")))).strip().lower() in ("yes", "true", "1", "oui"),
            "net_debt": _num(wb, i["net_debt"], lab.get("net_debt")),
            "diluted_shares": _num(wb, i["diluted_shares"], lab.get("diluted_shares")),
        }
        cached = wb.value(_cell(wb, layout["outputs"]["value_per_share"], None))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        if isinstance(e, NoLayout):
            raise
        raise NoLayout(f"The layout sheet is damaged ({e}). Rebuild the model, or compute sensitivities by hand.") from None
    if vals["diluted_shares"] <= 0:
        raise NoLayout("Diluted shares must be positive.")
    return layout, {**vals, "_cached_per_share": cached if isinstance(cached, (int, float)) else None}


def _run(v: dict) -> dict | None:
    if v["wacc"] <= v["terminal_growth"]:
        return None
    a = {k: v[k] for k in SINGLE}
    return dcf_math(v["revenue0"], v["revenue_growth"], a, v["mid_year"], v["net_debt"], v["diluted_shares"])


def _shock(v: dict, key: str, delta: float) -> dict:
    w = dict(v)
    w["revenue_growth"] = list(v["revenue_growth"])
    if key == "revenue_growth":
        w[key] = [g + delta for g in v["revenue_growth"]]
    else:
        w[key] = v[key] + delta
    return w


def _solve(v: dict, key: str, target: float, lo: float, hi: float) -> float | None:
    """The value of one input at which value per share equals `target` (bisection), or None if out of range."""
    def f(x):
        r = _run({**v, key: x})
        return None if r is None else r["per_share"] - target

    flo, fhi = f(lo), f(hi)
    if flo is None or fhi is None or flo * fhi > 0:
        return None
    for _ in range(80):
        mid = (lo + hi) / 2
        fm = f(mid)
        if fm is None:
            return None
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def sensitivity(path: str, price: float | None = None) -> dict:
    layout, v = read_inputs(path)
    base = _run(v)
    if base is None:
        raise NoLayout("WACC is not above terminal growth in the file: the DCF has no finite value.")
    warn = []
    cp = v.pop("_cached_per_share")
    if cp is not None and not math.isclose(cp, base["per_share"], rel_tol=1e-6, abs_tol=1e-6):
        warn.append(f"The file's value per share ({cp:,.2f}) differs from deskstack's DCF math on its inputs "
                    f"({base['per_share']:,.2f}): a formula was changed, or the file wasn't recalculated. Treat the "
                    "sensitivities as deskstack's DCF, not the file's.")
    tornado = []
    for key, d, label in SHOCKS:
        lo, hi = _run(_shock(v, key, -d)), _run(_shock(v, key, d))
        unbounded = lo is None or hi is None  # the shock pushes WACC to or below terminal growth
        tornado.append({
            "input": key, "label": label, "shock": d,
            "base": v[key] if key != "revenue_growth" else v[key][0],
            "per_share_down": lo["per_share"] if lo else None,
            "per_share_up": hi["per_share"] if hi else None,
            "swing": None if unbounded else abs(hi["per_share"] - lo["per_share"]),
            "unbounded": unbounded,
        })
    tornado.sort(key=lambda t: (not t["unbounded"], -(t["swing"] or 0)))
    spread = v["wacc"] - v["terminal_growth"]
    if any(t["unbounded"] for t in tornado):
        warn.append("A ±1 pt WACC or ±0.5 pt growth shock makes WACC ≤ terminal growth: the value has no upper bound. "
                    "This is the most important objection.")
    elif spread < 0.015:
        warn.append(f"WACC − terminal growth is only {spread:.1%}: small changes move the value a lot.")
    waccs = [round(v["wacc"] + k * 0.005, 6) for k in range(-2, 3)]
    gs = [round(v["terminal_growth"] + k * 0.0025, 6) for k in range(-2, 3)]
    grid = [[(r["per_share"] if (r := _run({**v, "wacc": w, "terminal_growth": g})) else None) for g in gs] for w in waccs]
    grid_vals = [x for row in grid for x in row if x is not None]
    if any(x is None for row in grid for x in row) or (grid_vals and max(abs(x) for x in grid_vals) > 3 * abs(base["per_share"])):
        warn.append("Parts of the WACC × growth grid are unbounded or more than 3× the base value: the terminal value dominates.")
    out = {
        "file": path,
        "model_sha256": file_sha256(path), "company": layout.get("company"), "ticker": layout.get("ticker"), "currency": layout.get("currency"),
        "base": {"value_per_share": base["per_share"], "enterprise_value": base["ev"], "tv_share": base["tv_share"]},
        "tornado": tornado,
        "grid": {"wacc": waccs, "terminal_growth": gs, "value_per_share": grid},
        "warnings": warn,
    }
    if price is not None:
        out["implied"] = {
            "price": price,
            "wacc": _solve(v, "wacc", price, v["terminal_growth"] + 0.0005, 0.5),
            "terminal_growth": _solve(v, "terminal_growth", price, -0.05, v["wacc"] - 0.0005),
            "ebit_margin": _solve(v, "ebit_margin", price, -0.5, 0.95),
        }
    return out


def to_markdown(r: dict) -> str:
    cur = r.get("currency") or ""
    b = r["base"]
    lines = [f"## Sensitivities: {r.get('company')} ({r.get('ticker')})",
             f"Model SHA-256: `{r['model_sha256']}`",
             f"Base value per share {b['value_per_share']:,.2f} {cur}; terminal value is {b['tv_share']:.0%} of EV.", ""]
    for w in r["warnings"]:
        lines.append(f"> {w}")
    lines += ["", "| Input (base) | Shock | Value per share if lower | if higher | Swing |", "|---|---|---|---|---|"]
    for t in r["tornado"]:
        f = lambda x: f"{x:,.2f}" if isinstance(x, (int, float)) else "unbounded"  # noqa: E731
        lines.append(f"| {t['label']} ({t['base']:.1%}) | ±{t['shock'] * 100:g} pt | {f(t['per_share_down'])} | {f(t['per_share_up'])} | {f(t['swing'])} |")
    g = r["grid"]
    lines += ["", "Value per share by WACC (rows) and terminal growth (columns):", "",
              "| WACC \\ g | " + " | ".join(f"{x:.2%}" for x in g["terminal_growth"]) + " |",
              "|---|" + "---|" * len(g["terminal_growth"])]
    for w, row in zip(g["wacc"], g["value_per_share"]):
        lines.append(f"| {w:.2%} | " + " | ".join(f"{x:,.2f}" if x is not None else "unbounded" for x in row) + " |")
    if "implied" in r:
        im = r["implied"]
        p = lambda x, pct=True: (f"{x:.2%}" if pct else f"{x:,.2f}") if x is not None else "out of range"  # noqa: E731
        lines += ["", f"At the price of {im['price']:,.2f} {cur}, the market implies (one input at a time): WACC "
                  f"{p(im['wacc'])}, terminal growth {p(im['terminal_growth'])}, EBIT margin {p(im['ebit_margin'])}."]
    return "\n".join(lines)
