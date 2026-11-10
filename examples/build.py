"""Builds the examples from recorded tool calls, with the plugin's own scripts.

    python3 examples/build.py            # rebuild every example in place
    python3 examples/build.py --check    # rebuild in a temp folder; exit 1 if a committed file differs

Each example folder holds:
- calls/      what the live connector returned (recorded by server/scripts/examples.ts, with the date);
- spec.json   the workbook spec, assembled from those responses by the rules below;
- model.xlsx  the workbook, built by deskstack_check (the analyst's builder);
- batches.json the tie-out batches /associate sends to verify_value;
- associate.md, vp-review.md, compliance.md, sign-off.md   the reports, with their JSON.

The assumptions (growth, margins, WACC) are an analyst's choices, not data. Here they follow fixed, stated rules so
the examples can be rebuilt; every source line says which rule. Nothing is estimated where data is missing: a
market cap needs a share price, which deskstack doesn't have, so it stays empty.
"""

from __future__ import annotations

import filecmp
import json
import re
import shutil
import statistics
import sys
import tempfile
import zipfile
from pathlib import Path

import os

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "checker"))
# Same bytes whether or not lxml is installed: openpyxl writes "/>" through lxml and " />" through the standard
# library, and every report carries the workbook's hash. Read when openpyxl is first imported.
os.environ["OPENPYXL_LXML"] = "False"

from deskstack_check import check, to_markdown  # noqa: E402
from deskstack_check.build import build_comps, build_dcf  # noqa: E402
from deskstack_check.compliance import check as comp_check, to_markdown as comp_md  # noqa: E402
from deskstack_check.signoff import summary, to_markdown as so_md  # noqa: E402
from deskstack_check.tieout import extract, report as tie_report, to_markdown as tie_md  # noqa: E402

M = 1e6  # every example is in millions
TERMINAL_GROWTH = {"USD": 0.025, "EUR": 0.02}
OUTPUTS = ["spec.json", "model.xlsx", "batches.json", "associate.md", "associate.json", "vp-review.md", "vp-review.json",
           "compliance.md", "compliance.json", "sign-off.md", "sign-off.json"]


class Stale(RuntimeError):
    pass


# ---- reading recorded calls ----------------------------------------------------------------

def calls(case: Path, cid: str) -> dict:
    return json.loads((case / "calls" / f"{cid}.json").read_text())


def period(fs: dict, label: str | None = None) -> dict:
    ps = fs["periods"]
    return ps[-1] if label is None else next(p for p in ps if p["label"] == label)


def cell(p: dict, metric: str) -> dict:
    for block in ("income_statement", "cash_flow", "balance_sheet", "derived"):
        c = (p.get(block) or {}).get(metric)
        if c is not None:
            return c
    raise KeyError(f"{metric} is null for {p['label']}: an example can't use it")


def source(fs: dict, p: dict, metric: str, recorded: str) -> str:
    c = cell(p, metric)
    if "formula" in c:
        acc = next((x.get("accession") for x in c.get("inputs", []) if isinstance(x, dict)), None) or _any_accession(p)
        return f"Computed by deskstack: {c['formula']}, {_filing(fs, acc)} (financial_statements, recorded {recorded})"
    return f"{_filing(fs, c['accession'])}, {c['concept']} (deskstack financial_statements, recorded {recorded})"


def _any_accession(p: dict) -> str | None:
    for block in ("income_statement", "cash_flow", "balance_sheet"):
        for c in (p.get(block) or {}).values():
            if c and c.get("accession"):
                return c["accession"]
    return None


def _filing(fs: dict, acc: str | None) -> str:
    s = next((s for s in fs["sources"] if s.get("accession_or_id") == acc), None)
    if s is None:
        return f"accession {acc}"
    return f"{s.get('form', 'filing')} for {s['period']}, {s['accession_or_id']}, {s['url']}"


def mil(p: dict, metric: str) -> float:
    return round(cell(p, metric)["value"] / M, 3)


# ---- assumptions: fixed rules, stated in each source ----------------------------------------

def dcf_assumptions(fs: dict, hist: list[dict], rf: dict, vi: dict, currency: str) -> dict:
    tg = TERMINAL_GROWTH[currency]
    last, prev = hist[-1], hist[-2]
    g_raw = cell(last, "revenue")["value"] / cell(prev, "revenue")["value"] - 1
    g0 = max(-0.05, min(0.15, g_raw))
    g_note = f"{g_raw:.1%}" + (f", capped at {g0:.0%}," if g0 != g_raw else "")
    growth = [round(g0 + (tg - g0) * (i + 1) / 6, 4) for i in range(5)]
    margins = [cell(p, "operating_income")["value"] / cell(p, "revenue")["value"] for p in hist]
    margin = round(statistics.fmean(margins), 4)
    t_raw = 1 - cell(last, "net_income")["value"] / cell(last, "pretax_income")["value"]
    tax = round(max(0.0, min(0.35, t_raw)), 4)
    t_note = "" if tax == round(t_raw, 4) else f" ({t_raw:.1%}, capped at 35%)"
    da = round(cell(last, "d_and_a")["value"] / cell(last, "revenue")["value"], 4)
    capex = round(cell(last, "capex")["value"] / cell(last, "revenue")["value"], 4)
    country, ind = vi["country"][0], vi["industry"][0]
    ke = rf["rate_decimal"] + ind["beta"] * country["equity_risk_premium"]
    wacc = round(ind["equity_weight"] * ke + ind["debt_weight"] * ind["after_tax_cost_of_debt"], 4)
    lab = last["label"]
    end = int(hist[-1]["end"][:4])
    return {
        "projection_labels": [f"FY{end + i}E" for i in range(1, 6)],
        "revenue_growth": {"values": growth, "source": f"Analyst assumption (example rule): {lab} growth of {g_note} fading in a straight line toward terminal growth of {tg:.1%}"},
        "ebit_margin": {"value": margin, "source": f"Analyst assumption (example rule): average operating margin {hist[0]['label']}-{lab}"},
        "tax_rate": {"value": tax, "source": f"Analyst assumption (example rule): 1 - net income / pretax income, {lab}{t_note}"},
        "da_pct_revenue": {"value": da, "source": f"Analyst assumption (example rule): {lab} D&A / revenue"},
        "capex_pct_revenue": {"value": capex, "source": f"Analyst assumption (example rule): {lab} capex / revenue"},
        "wacc": {"value": wacc, "source": (
            f"Analyst assumption (example rule): Damodaran {ind['industry']} ({ind['region']}) weights, "
            f"{ind['equity_weight']:.1%} x cost of equity [risk-free {rf['rate_decimal']:.2%} ({rf['source']['name']}, {rf['date']}) "
            f"+ beta {ind['beta']:.2f} x ERP {country['equity_risk_premium']:.2%} ({country['country']})] "
            f"+ {ind['debt_weight']:.1%} x after-tax cost of debt {ind['after_tax_cost_of_debt']:.2%} (deskstack valuation_inputs)")},
        "terminal_growth": {"value": tg, "source": "Analyst assumption (example rule): below long-run nominal GDP"},
        "mid_year": False,
    }


def dcf_spec(case: Path, labels: list[str] | None = None) -> dict:
    st, rf, vi = calls(case, "statements"), calls(case, "risk-free")["response"], calls(case, "valuation-inputs")["response"]
    fs, rec = st["response"], st["recorded_at"]
    annual = [p for p in fs["periods"] if p["type"] == "annual"]
    hist = [period(fs, x) for x in labels] if labels else annual[-3:]
    co = fs["company"]
    lines = {}
    for key, metric in (("revenue", "revenue"), ("operating_income", "operating_income"), ("d_and_a", "d_and_a"), ("capex", "capex")):
        lines[key] = {"values": [mil(p, metric) for p in hist], "sources": [source(fs, p, metric, rec) for p in hist]}
    base = annual[-1]
    return {
        "kind": "dcf",
        "company": co["name"],
        "ticker": co.get("ticker") or co.get("lei"),
        "currency": co["currency"],
        "scale": "millions",
        "history": {"periods": [p["label"] if p["type"] == "annual" else "LTM" for p in hist], "lines": lines},
        "assumptions": dcf_assumptions(fs, annual[-3:], rf, vi, co["currency"]),
        "bridge": {
            "net_debt": {"value": mil(base, "net_debt"), "period": base["label"], "source": source(fs, base, "net_debt", rec)},
            "diluted_shares": {"value": mil(base, "diluted_shares"), "period": base["label"], "source": source(fs, base, "diluted_shares", rec)},
        },
    }


# ---- the cases ---------------------------------------------------------------------------

def apple_dcf(case: Path) -> dict:
    return dcf_spec(case)


def heineken_dcf(case: Path) -> dict:
    return dcf_spec(case)


def us_tech_comps(case: Path) -> dict:
    peers = []
    for t in ("AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA"):
        r = calls(case, t)
        fs, rec = r["response"], r["recorded_at"]
        p = period(fs)  # the latest twelve months: the LTM column, or the annual year if a 10-K is the latest filing
        when = "LTM" if p["type"] == "ltm" else p["label"]
        item = lambda m: {"value": mil(p, m), "period": when, "source": source(fs, p, m, rec)}  # noqa: E731
        peers.append({
            "name": fs["company"]["name"], "ticker": t, "currency": fs["company"]["currency"],
            "revenue": item("revenue"), "ebitda": item("ebitda"), "net_income": item("net_income"),
            "market_cap": {"value": None, "source": "Not given: deskstack has no share prices. Type price x diluted shares, with its date, to fill it."},
            "net_debt": item("net_debt"),
        })
    return {"kind": "comps", "target": "AAPL", "currency": "USD", "scale": "millions",
            "period": "latest twelve months", "peers": peers}


def apple_dcf_typo(case: Path) -> dict:
    """The demo GIF's model: Apple's DCF with FY2025 revenue keyed with two adjacent digits swapped."""
    spec = dcf_spec(case)
    rev = spec["history"]["lines"]["revenue"]
    digits = str(int(rev["values"][1]))
    rev["values"][1] = float(digits[:-2] + digits[-1] + digits[-2])
    return spec


# The real errors from the benchmark (bench/results/*/ANALYSIS.md), planted in a Microsoft DCF built from real data.
PLANTED = {
    "stale-ltm": "LTM revenue and operating income typed from the twelve months to June (FY2026), after the September 10-Q",
    "shares-from-eps": "Diluted shares derived as LTM net income / FY2026 diluted EPS",
    "placeholder-zero": "FY2025 D&A left as a 0 placeholder, labelled not found",
    "offsetting-lines": "FY2026 operating income 2,000 too low and D&A 2,000 too high: EBITDA still ties",
}


def errors_caught(case: Path) -> dict:
    fs = calls(case, "statements")["response"]
    ltm = next(p for p in fs["periods"] if p["type"] == "ltm")
    fy = [p for p in fs["periods"] if p["type"] == "annual"]
    fy25, fy26 = fy[-2], fy[-1]
    spec = dcf_spec(case, [fy25["label"], fy26["label"], ltm["label"]])
    L = spec["history"]["lines"]
    # stale-ltm: an aggregator's "TTM" a quarter late, i.e. the fiscal year to June.
    for key in ("revenue", "operating_income"):
        L[key]["values"][2] = mil(fy26, key)
        L[key]["sources"][2] = "TTM from an aggregator site (as a model wrote it)"
    # shares-from-eps
    derived = round(cell(ltm, "net_income")["value"] / cell(fy26, "diluted_eps")["value"] / M, 3)
    spec["bridge"]["diluted_shares"] = {"value": derived, "period": fy26["label"],
                                        "source": "Derived: LTM net income / FY2026 diluted EPS (as a model wrote it)"}
    # placeholder-zero
    L["d_and_a"]["values"][0] = 0
    L["d_and_a"]["sources"][0] = "NOT FOUND - placeholder 0"
    # offsetting-lines: the sources still cite the filing, as in the model this mimics.
    L["operating_income"]["values"][1] = round(L["operating_income"]["values"][1] - 2000, 3)
    L["d_and_a"]["values"][1] = round(L["d_and_a"]["values"][1] + 2000, 3)
    return spec


CASES = {"apple-dcf": apple_dcf, "apple-dcf-typo": apple_dcf_typo, "us-tech-comps": us_tech_comps, "heineken-dcf": heineken_dcf, "errors-caught": errors_caught}


# ---- build -------------------------------------------------------------------------------

def _stamp(recorded: str, planted: bool = False):
    def t(b):
        b.sheet("Cover")["A5"].value = f"Built from deskstack data recorded {recorded}. Review with /associate and /vp-review before use."
        if planted:
            b.sheet("Cover")["A7"].value = ("EXAMPLE WITH PLANTED ERRORS. Four errors from the deskstack benchmark were typed in on purpose: "
                                            + "; ".join(PLANTED.values()) + ".")
    return t


def _deterministic(xlsx: Path, recorded: str) -> None:
    """Same input, same bytes: fixed zip dates and document times (openpyxl stamps the save time)."""
    tmp = xlsx.with_suffix(".tmp")
    # Stored, not deflated: compressed bytes depend on the zlib build, and every report carries the file's hash.
    with zipfile.ZipFile(xlsx) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as zout:
        for info in sorted(zin.infolist(), key=lambda i: i.filename):
            data = zin.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:(created|modified)[^>]*>)[^<]*", rb"\g<1>" + f"{recorded}T00:00:00Z".encode(), data)
            zi = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_STORED
            zout.writestr(zi, data)
    tmp.replace(xlsx)


def _first_diff(new: bytes, old: bytes, width: int = 160) -> str:
    """The first place two texts part, with a little context: enough to read a CI-only difference from its log."""
    i = next((k for k, (x, y) in enumerate(zip(new, old)) if x != y), min(len(new), len(old)))
    lo = max(0, i - width // 2)
    show = lambda b: b[lo:i + width // 2].decode("utf-8", "replace")
    return f"at byte {i}: new {show(new)!r} / committed {show(old)!r}"


def _why(new: Path, old: Path) -> str:
    """What differs between a rebuilt output and the committed one: the workbook parts that changed, or a text's
    first differing place."""
    if new.suffix == ".xlsx":
        with zipfile.ZipFile(new) as a, zipfile.ZipFile(old) as b:
            na, nb = set(a.namelist()), set(b.namelist())
            out = [f"part {m} only in {'new' if m in na else 'committed'}" for m in sorted(na ^ nb)]
            out += [f"part {m} {_first_diff(a.read(m), b.read(m))}" for m in sorted(na & nb) if a.read(m) != b.read(m)]
            if not out:
                out = ["same parts, different zip bytes (headers)"]
            return "; ".join(out[:3])
    return _first_diff(new.read_bytes(), old.read_bytes())


def _write(path: Path, obj) -> None:
    path.write_text(obj if isinstance(obj, str) else json.dumps(obj, indent=1, ensure_ascii=False) + "\n")


def build_case(name: str, src: Path, out: Path) -> None:
    """Builds one example from src/calls into out (src == out for an in-place rebuild)."""
    import openpyxl.xml

    if openpyxl.xml.LXML:
        raise RuntimeError("openpyxl was imported with lxml on, so the workbook bytes would differ from CI's. "
                           "Run with OPENPYXL_LXML=False set before openpyxl is imported.")
    out.mkdir(parents=True, exist_ok=True)
    spec = CASES[name](src)
    recorded = max(json.loads(f.read_text())["recorded_at"] for f in (src / "calls").glob("*.json") if f.name != "verify.json")
    _write(out / "spec.json", spec)
    xlsx = out / "model.xlsx"
    (build_dcf if spec["kind"] == "dcf" else build_comps)(spec, xlsx, tamper=_stamp(recorded, planted=name == "errors-caught"))
    _deterministic(xlsx, recorded)
    batches = extract(str(xlsx))["verify_batches"]
    _write(out / "batches.json", batches)

    verify = src / "calls" / "verify.json"
    if not verify.exists() or [b["request"] for b in json.loads(verify.read_text())["batches"]] != batches:
        raise Stale(f"{name}: the recorded verify_value calls don't match batches.json. Run: cd server && npx tsx scripts/examples.ts verify")
    results = [b["response"] for b in json.loads(verify.read_text())["batches"]]

    # The reports name the file relatively, so they read the same wherever the repo is.
    import os
    cwd = os.getcwd()
    os.chdir(out)
    try:
        tie = tie_report("model.xlsx", results)
        review = check("model.xlsx")
        comp = comp_check("model.xlsx")
        _write(out / "associate.json", tie)
        _write(out / "associate.md", tie_md(tie))
        _write(out / "vp-review.json", review)
        _write(out / "vp-review.md", to_markdown(review))
        _write(out / "compliance.json", comp)
        _write(out / "compliance.md", comp_md(comp))
        so = summary("model.xlsx", tieout="associate.json", review="vp-review.json", compliance="compliance.json")
        _write(out / "sign-off.json", so)
        _write(out / "sign-off.md", so_md(so))
    finally:
        os.chdir(cwd)


def main(argv: list[str]) -> int:
    only = [a for a in argv if not a.startswith("--")]
    names = only or list(CASES)
    if "--check" not in argv:
        stale = []
        for n in names:
            try:
                build_case(n, HERE / n, HERE / n)
                print(f"built examples/{n}")
            except Stale as e:
                stale.append(str(e))
        for s in stale:
            print(s, file=sys.stderr)
        return 1 if stale else 0
    bad = []
    with tempfile.TemporaryDirectory() as d:
        for n in names:
            tmp = Path(d) / n
            shutil.copytree(HERE / n / "calls", tmp / "calls")
            try:
                build_case(n, tmp, tmp)
            except Stale as e:
                bad.append(str(e))
                continue
            for f in OUTPUTS:
                if not (HERE / n / f).exists():
                    bad.append(f"examples/{n}/{f} is missing. Run: python3 examples/build.py")
                elif not filecmp.cmp(tmp / f, HERE / n / f, shallow=False):
                    bad.append(f"examples/{n}/{f} is out of date ({_why(tmp / f, HERE / n / f)}). Run: python3 examples/build.py")
    for b in bad:
        print(b, file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
