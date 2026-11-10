"""Writes demo.cast, the asciinema recording behind site/media/demo.gif.

    python3 site/media/demo/make_cast.py          # writes demo.cast
    python3 site/media/demo/render_gif.py         # demo.cast -> ../demo.gif (Pillow), or: agg demo.cast demo.gif

It replays /deal-team on Apple, step by step, with the real outputs of the plugin's scripts and of the live tools,
read from examples/apple-dcf-typo (FY2025 revenue keyed with two digits swapped, planted for the demo) and
examples/apple-dcf (the same model once fixed). Nothing in it is typed by hand except the prompts. A test checks that
demo.cast is current.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EX = ROOT / "examples"
sys.path.insert(0, str(ROOT / "checker"))

COLS, ROWS = 78, 26
PACE = 1.15  # stretches every pause: about 25 seconds in all
TITLE = "deskstack: replay of /deal-team on Apple (one planted typo)"

# ANSI styles the renderer understands (and any terminal player).
B, DIM, RED, GREEN, BLUE, RESET = "\x1b[1m", "\x1b[2m", "\x1b[31m", "\x1b[32m", "\x1b[34m", "\x1b[0m"


def _j(case: str, f: str):
    return json.loads((EX / case / f).read_text())


def script() -> list[tuple[float, str]]:
    """(pause before, text) pairs. Text ends lines with \\r\\n like a terminal."""
    from deskstack_check.sensitivity import sensitivity

    st = _j("apple-dcf-typo", "calls/statements.json")["response"]
    rf = _j("apple-dcf-typo", "calls/risk-free.json")["response"]
    vi = _j("apple-dcf-typo", "calls/valuation-inputs.json")["response"]
    spec = _j("apple-dcf-typo", "spec.json")
    tie = _j("apple-dcf-typo", "associate.json")
    review = _j("apple-dcf-typo", "vp-review.json")
    tie2 = _j("apple-dcf", "associate.json")
    comp = _j("apple-dcf", "compliance.json")
    so = _j("apple-dcf", "sign-off.json")
    sens = sensitivity(str(EX / "apple-dcf" / "model.xlsx"))

    periods = spec["history"]["periods"]
    last = st["periods"][-1]
    acc = last["income_statement"]["revenue"]["accession"]
    k, k2 = tie["counts"], tie2["counts"]
    filed = k["match"] + k.get("mismatch", 0)
    bad = next(r for r in tie["rows"] if r["status"] == "mismatch")
    hint = bad["hints"][0].split(" (")[0]
    sev = {s: sum(1 for f in review["findings"] if f["severity"] == s) for s in ("blocker", "major", "minor")}
    top = sens["tornado"][0]
    cur = sens["currency"]
    ind, country = vi["industry"][0], vi["country"][0]

    def step(n, name, role):
        return f"{B}Step {n}/7  {name}{RESET} {DIM}/{role}{RESET}\r\n"

    out: list[tuple[float, str]] = [(0.6, f"{BLUE}›{RESET} ")]
    out += [(0.07, ch) for ch in "/deal-team Apple quick-dcf"]
    out += [
        (0.5, "\r\n\r\n"),
        (0.6, step(1, "Build", "analyst")),
        (0.5, f"  financial_statements AAPL: {periods[0]}-{periods[-1]}, 10-K {acc}\r\n"),
        (0.4, f"  risk_free_rate US 10Y: {rf['rate_pct']:.2f}% (U.S. Treasury, {rf['date']})\r\n"),
        (0.4, f"  valuation_inputs: beta {ind['beta']:.2f}, ERP {country['equity_risk_premium']:.2%} (Damodaran)\r\n"),
        (0.4, f"  model.xlsx: {filed} filed figures, each cited  {DIM}(demo: FY2025 revenue mistyped){RESET}\r\n"),
        (0.9, step(2, "Tie-out", "associate")),
        (0.5, f"  verify_value: {filed} figures against Apple's filings\r\n"),
        (0.8, f"  {RED}{B}{k['match']} of {filed} match; {k['mismatch']} mismatch{RESET}\r\n"),
        (0.3, f"  {bad['ref']}  {bad['label']} {bad['period']}  {bad['value']:,.0f}   filed {bad['filed_value']:,.0f}\r\n"),
        (0.3, f"  {RED}{hint}{RESET}\r\n"),
        (1.6, step(3, "Model review", "vp-review")),
        (0.5, f"  20 rules: {sev['blocker']} blocker, {sev['major']} major, {sev['minor']} minor\r\n"),
        (0.9, step(4, "Fixes", "analyst")),
        (0.5, f"  Fix {bad['ref']} to {bad['filed_value']:,.0f}? "),
        (0.9, f"{BLUE}yes{RESET}\r\n"),
        (0.6, f"  Rebuilt. Tie-out again: {GREEN}{k2['match']} of {k2['match'] + k2.get('mismatch', 0)} match{RESET}\r\n"),
        (0.9, step(5, "Red team", "md-redteam")),
        (0.5, f"  Value per share {sens['base']['value_per_share']:,.2f} {cur}; terminal value {sens['base']['tv_share']:.0%} of EV\r\n"),
        (0.4, f"  Biggest swing: {top['label']} ±{top['shock'] * 100:g} pt -> {top['per_share_up']:,.2f} to {top['per_share_down']:,.2f}\r\n"),
        (0.9, step(6, "Compliance", "compliance")),
        (0.4, f"  {comp['counts']['pass']} pass, {comp['counts']['fail']} fail\r\n"),
        (0.9, step(7, "Sign-off", "sign-off")),
        (0.5, f"  {GREEN}{so['blocking']} blocking items{RESET}. Nothing is exported until you approve\r\n"),
        (0.2, "  in your own words.\r\n"),
        (4.0, ""),
    ]
    return out


def cast() -> str:
    t = 0.0
    lines = [json.dumps({"version": 2, "width": COLS, "height": ROWS, "title": TITLE,
                         "env": {"TERM": "xterm-256color"}})]
    for pause, text in script():
        t = round(t + pause * PACE, 3)
        lines.append(json.dumps([t, "o", text], ensure_ascii=False))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    (HERE / "demo.cast").write_text(cast())
    print(f"Wrote {HERE / 'demo.cast'}")
