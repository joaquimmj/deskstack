"""The plugin's scripts end to end: build -> check -> extract -> tie-out report, and companion mode."""

from __future__ import annotations

import json
import statistics
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from demo_models import DEMOS, FIXTURE, SPEC, build_demo, fixture  # noqa: E402

from deskstack_check import check, to_markdown  # noqa: E402
from deskstack_check.build import SpecError, build_comps, build_dcf  # noqa: E402
from deskstack_check.companion import merge, parse_audit_table  # noqa: E402
from deskstack_check.tieout import METRICS, extract, report, to_markdown as tie_md  # noqa: E402

HERE = Path(__file__).parent
COMPS = json.loads((HERE / "specs" / "peers_comps.json").read_text())
SERVER_VERIFY = HERE.parent.parent / "server" / "src" / "verify.ts"


def rules(r, sev=("blocker", "major", "minor")):
    return {f["rule"] for f in r["findings"] if f["severity"] in sev}


def test_built_dcf_and_comps_are_clean(tmp_path):
    for p in (build_dcf(SPEC, tmp_path / "dcf.xlsx"), build_comps(COMPS, tmp_path / "comps.xlsx")):
        r = check(str(p))
        assert r["findings"] == [], r["findings"]


def test_built_dcf_values_follow_the_spec(tmp_path):
    from openpyxl import load_workbook

    p = build_dcf(SPEC, tmp_path / "dcf.xlsx")
    ws = load_workbook(p, data_only=True)["DCF"]
    a = {k: v["value"] for k, v in SPEC["assumptions"].items() if isinstance(v, dict) and "value" in v}
    rev = 416161.0
    fcfs = []
    for g in SPEC["assumptions"]["revenue_growth"]["values"]:
        rev *= 1 + g
        fcfs.append(rev * a["ebit_margin"] * (1 - a["tax_rate"]) + rev * a["da_pct_revenue"] - rev * a["capex_pct_revenue"])
    w, tg = a["wacc"], a["terminal_growth"]
    ev = sum(f / (1 + w) ** (i + 1) for i, f in enumerate(fcfs)) + fcfs[-1] * (1 + tg) / (w - tg) / (1 + w) ** 5
    assert ws["B17"].value == pytest.approx(ev)
    assert ws["B21"].value == pytest.approx((ev - 43960) / 15004.697)


@pytest.mark.parametrize("name, rules_expected", [(d[0], d[3]) for d in DEMOS if d[3]])
def test_vp_review_catches_planted_model_errors(tmp_path, name, rules_expected):
    found = rules(check(str(build_demo(name, tmp_path))))
    assert set(rules_expected) <= found, f"{name}: expected {rules_expected}, got {sorted(found)}"


def test_clean_demo_raises_nothing(tmp_path):
    assert check(str(build_demo("clean", tmp_path)))["findings"] == []


def test_server_fixture_is_current(tmp_path):
    """server/test/demo.test.ts runs these batches through verify_value; regenerate if this fails."""
    assert json.loads(FIXTURE.read_text()) == fixture(tmp_path), "run: python checker/tests/demo_models.py"


def test_extract_splits_filed_figures_from_assumptions(tmp_path):
    ex = extract(str(build_dcf(SPEC, tmp_path / "dcf.xlsx")))
    assert ex["counts"] == {"filed": 14, "assumptions": 11, "other": 0, "unsourced": 0}
    by = {e["ref"]: e for e in ex["filed"]}
    want = {"metric": "revenue", "period": "FY2025", "scale": "millions", "company": "AAPL", "currency": "USD"}
    assert {k: by["Inputs!D5"][k] for k in want} == want
    assert by["Inputs!B23"]["metric"] == "diluted_shares" and by["Inputs!B23"]["scale"] == "millions"
    assert {e["label"].split(" FY")[0] for e in ex["assumptions"]} >= {"WACC", "Terminal growth", "Revenue growth"}
    assert sum(len(b["items"]) for b in ex["verify_batches"]) == 14


def test_extract_comps_uses_each_row_ticker_and_currency(tmp_path):
    spec = json.loads(json.dumps(COMPS))
    spec["peers"][1]["currency"] = "EUR"
    ex = extract(str(build_comps(spec, tmp_path / "comps.xlsx")))
    rows = {e["ref"]: e for e in ex["filed"]}
    assert rows["Comps!D5"]["company"] == "PONE" and rows["Comps!D5"]["currency"] == "EUR"
    assert rows["Comps!D4"]["currency"] == "USD"
    assert {b["company"] for b in ex["verify_batches"]} == {"AAPL", "PONE", "PTWO", "PTHR"}
    assert all(e["label"].endswith("Market cap") for e in ex["other"])  # a price input: cite it, can't tie it out


def test_tieout_report_puts_problems_first(tmp_path):
    p = build_demo("revenue-scale", tmp_path)
    results = {"results": [
        {"ref": "Inputs!D5", "status": "mismatch", "filed": 416161e6, "difference": 1, "hints": ["Scale: the value matches if it is in thousands"], "accessions": ["0000320193-25-000079"]},
        {"ref": "Inputs!C5", "status": "match", "filed": 391035e6, "hints": [], "accessions": ["0000320193-25-000079"]},
    ]}
    rep = report(str(p), results)
    assert rep["rows"][0]["ref"] == "Inputs!D5" and rep["rows"][0]["filed_value"] == pytest.approx(416161)
    assert rep["counts"]["mismatch"] == 1 and rep["counts"]["match"] == 1 and rep["counts"]["not_checked"] == 12
    md = tie_md(rep)
    assert "1 of 14 filed figure(s) match" in md and "Scale: the value matches" in md


def test_tieout_flags_unsourced(tmp_path):
    rep = report(str(build_demo("unsourced-input", tmp_path)), [])
    row = next(r for r in rep["rows"] if r["ref"] == "Inputs!D6")
    assert "unsourced" in row["flags"] and rep["counts"]["unsourced"] == 1


def test_spec_errors_are_explained(tmp_path):
    bad = json.loads(json.dumps(SPEC))
    bad["history"]["lines"]["revenue"]["source"] = ""
    with pytest.raises(SpecError, match="has no source"):
        build_dcf(bad, tmp_path / "x.xlsx")
    bad = json.loads(json.dumps(SPEC))
    bad["assumptions"]["terminal_growth"]["value"] = 0.095
    with pytest.raises(SpecError, match="WACC must be above terminal growth"):
        build_dcf(bad, tmp_path / "x.xlsx")
    for path, value, msg in [
        (("assumptions", "wacc"), 9, "Rates are decimals"),
        (("assumptions", "terminal_growth"), 2.5, "Rates are decimals"),
    ]:
        bad = json.loads(json.dumps(SPEC))
        bad[path[0]][path[1]]["value"] = value
        with pytest.raises(SpecError, match=msg):
            build_dcf(bad, tmp_path / "x.xlsx")
    bad = json.loads(json.dumps(SPEC))
    bad["assumptions"]["mid_year"] = "false"
    with pytest.raises(SpecError, match="true or false"):
        build_dcf(bad, tmp_path / "x.xlsx")
    bad = json.loads(json.dumps(SPEC))
    bad["assumptions"]["projection_labels"] = ["FY2026E"]
    with pytest.raises(SpecError, match="projection_labels needs 5"):
        build_dcf(bad, tmp_path / "x.xlsx")
    bad = json.loads(json.dumps(SPEC))
    bad["history"]["periods"] = ["2023", "last year", "FY2025"]
    with pytest.raises(SpecError, match="is not a period"):
        build_dcf(bad, tmp_path / "x.xlsx")


def test_wrong_shapes_are_spec_errors_not_crashes(tmp_path):
    # Main run 2026-11-09: a bridge sent as text crashed the build with a TypeError traceback.
    for mutate, msg in [
        (lambda b: b.__setitem__("bridge", "net debt 20,000"), "bridge must be an object"),
        (lambda b: b["bridge"].__setitem__("net_debt", 20000), "bridge.net_debt must be an object like"),
        (lambda b: b["assumptions"].__setitem__("wacc", 0.09), "assumptions.wacc must be an object like"),
    ]:
        bad = json.loads(json.dumps(SPEC))
        mutate(bad)
        with pytest.raises(SpecError, match=msg):
            build_dcf(bad, tmp_path / "x.xlsx")


def test_numeric_year_periods_are_labeled_fy(tmp_path):
    spec = json.loads(json.dumps(SPEC))
    spec["history"]["periods"] = [2023, 2024, 2025]
    ex = extract(str(build_dcf(spec, tmp_path / "dcf.xlsx")))
    assert {d["period"] for b in ex["verify_batches"] for d in b["items"]} <= {"FY2023", "FY2024", "FY2025"}


def test_comps_with_no_meaningful_peer_multiple_has_no_error_cells(tmp_path):
    spec = json.loads(json.dumps(COMPS))
    for p in spec["peers"][1:]:
        p["net_income"]["value"] = -1
    r = check(str(build_comps(spec, tmp_path / "c.xlsx")))
    assert "DS006" not in rules(r)


def test_every_metric_name_is_known_to_the_server():
    src = SERVER_VERIFY.read_text()
    known = set(re.findall(r'"([a-z_]+)"', src[src.index("const KNOWN"):]))
    assert set(METRICS.values()) <= known


AUDIT_XLS = """Model type: DCF — Overall: Major Issues — 1 critical, 1 warnings, 1 info

| # | Sheet | Cell/Range | Severity | Category | Issue | Suggested Fix |
|---|---|---|---|---|---|---|
| 1 | DCF | E4 | Critical | Hardcode | Growth typed into formula | Link to Inputs |
| 2 | Inputs | B18 | Warning | Assumption | Terminal growth looks high | Justify |
| 3 | Cover | A1 | Info | Formatting | Title missing date | Add date |
"""


def test_companion_parses_audit_xls_and_merges(tmp_path):
    theirs = parse_audit_table(AUDIT_XLS)
    assert theirs["summary"].startswith("Model type: DCF")
    assert [f["severity"] for f in theirs["findings"]] == ["blocker", "major", "minor"]
    ours = check(str(build_demo("hardcode-in-formula", tmp_path)))
    merged = merge(ours, theirs)
    by = {m["ref"]: m["found_by"] for m in merged}
    assert by["DCF!E4"] == "both"
    assert by["Inputs!B18"] == "audit-xls" and by["Cover!A1"] == "audit-xls"
    md = to_markdown(ours, merged)
    assert "| # | Sheet | Cell/Range | Severity | Category | Issue | Suggested Fix | Rule | Found by |" in md


def test_markdown_header_is_audit_xls_compatible(tmp_path):
    md = to_markdown(check(str(build_demo("hardcode-in-formula", tmp_path))))
    header = next(line for line in md.splitlines() if line.startswith("| #"))
    assert header.startswith("| # | Sheet | Cell/Range | Severity | Category | Issue | Suggested Fix |")
    assert "Overall: Minor Issues" in md or "Overall: Major Issues" in md


def test_comps_put_the_target_first_and_exclude_it_from_peer_medians(tmp_path):
    from openpyxl import load_workbook

    spec = json.loads(json.dumps(COMPS))
    spec["peers"] = spec["peers"][1:] + spec["peers"][:1]  # target listed last
    ws = load_workbook(build_comps(spec, tmp_path / "c.xlsx"), data_only=True)["Comps"]
    assert ws["B4"].value == "AAPL"
    assert ws["K9"].value == pytest.approx(statistics.median([1180000 / 60000, 160000 / 20000, 2005000 / 90000]))
    assert ws["L9"].value == pytest.approx(statistics.median([1200000 / 40000, 2000000 / 55000]))  # PTWO's n.m. skipped


def _foreign_model(path, rows, title="Apple Inc. (AAPL)", unit="($ in millions)", header=("FY2023", "FY2024", "FY2025"), between=None):
    """A workbook laid out like another tool's: no Sources sheet, title row, unit row, period header row."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Model"
    ws["A1"], ws["A2"] = title, unit
    for j, h in enumerate(header):
        ws.cell(4, 2 + j, h)
    r = 5
    if between:
        ws.cell(r, 1, "Note")
        ws.cell(r, 2, between)
        r += 1
    for label, vals in rows:
        ws.cell(r, 1, label)
        for j, v in enumerate(vals):
            if v is not None:
                ws.cell(r, 2 + j, v)
        r += 1
    wb.save(path)
    return str(path)


def test_extract_on_another_tools_layout(tmp_path):
    p = _foreign_model(tmp_path / "m.xlsx", [
        ("Revenue", [383285, 391035, 416161]),
        ("Capex (% of revenue)", [0.029, 0.024, 0.031]),
        ("D&A (% of sales)", [0.03, 0.029, 0.028]),
        ("Revenue (YoY %)", [-0.028, 0.02, 0.064]),
    ], header=(2023, 2024, 2025), between="n.a.")
    ex = extract(p)
    filed = {e["ref"]: e for e in ex["filed"]}
    assert set(filed) == {"Model!B6", "Model!C6", "Model!D6"}  # only the revenue row is a filed figure
    assert [filed[r]["period"] for r in ("Model!B6", "Model!C6", "Model!D6")] == ["FY2023", "FY2024", "FY2025"]
    assert all(e["scale"] == "millions" and e["company"] == "AAPL" and e["currency"] == "USD" for e in filed.values())
    assert ex["counts"]["assumptions"] == 9 and ex["counts"]["unsourced"] == 12


def test_extract_treats_estimates_as_assumptions(tmp_path):
    p = _foreign_model(tmp_path / "m.xlsx", [("Revenue", [416161, 440000, 465000])], header=("FY25A", "FY26E", "2027E"))
    ex = extract(p)
    assert [e["ref"] for e in ex["filed"]] == ["Model!B5"] and ex["filed"][0]["period"] == "FY2025"
    assert {e["ref"] for e in ex["assumptions"]} == {"Model!C5", "Model!D5"}
    assert all("estimate" in e["note"] for e in ex["assumptions"])


def test_extract_never_guesses_the_period_or_the_company(tmp_path):
    p = _foreign_model(tmp_path / "m.xlsx", [("Revenue", [416161])], title="Income statement (GAAP)", header=("Actual",))
    ex = extract(p)
    item = ex["verify_batches"][0]["items"][0]
    assert item["period"] is None and ex["verify_batches"][0]["company"] is None
    assert ex["needs_review"] == ["Model!B5"]


@pytest.mark.parametrize("unit, scale", [("$mm", "millions"), ("US$m", "millions"), ("(000s)", "thousands"), ("EUR bn", "billions")])
def test_extract_reads_shorthand_units(tmp_path, unit, scale):
    ex = extract(_foreign_model(tmp_path / "m.xlsx", [("Revenue", [1, 2, 3])], unit=unit))
    assert {e["scale"] for e in ex["filed"]} == {scale}


def test_tieout_accepts_nested_lists_quoted_refs_and_keeps_unmatched_results(tmp_path):
    p = build_demo("clean", tmp_path)
    results = [
        [{"ref": "'Inputs'!$D$5", "status": "match", "filed": 416161e6, "claimed_units": 416161e6, "hints": []}],
        [{"results": [{"ref": "Inputs!B12", "metric": "revenue growth", "status": "not_found", "claimed": 0.06, "hints": ["Unknown line item"]}]}],
        {"ref": "Other!Z99", "metric": "revenue", "status": "mismatch", "claimed": 1, "hints": []},
    ]
    rep = report(str(p), results)
    by = {r["ref"]: r for r in rep["rows"]}
    assert by["Inputs!D5"]["status"] == "match"
    assert by["Inputs!B12"]["status"] == "not_found"  # an assumption Claude chose to check keeps its result
    assert by["Other!Z99"]["status"] == "mismatch"  # never dropped
    assert rep["counts"]["mismatch"] == 1


def test_tieout_refuses_results_that_match_no_cell(tmp_path):
    from deskstack_check.tieout import ResultsError

    with pytest.raises(ResultsError, match="matches a cell"):
        report(str(build_demo("clean", tmp_path)), [{"status": "match", "ref": None}, {"status": "match", "ref": "X!A1"}])


def test_companion_reads_decorated_tables_and_keeps_both_findings_on_a_cell(tmp_path):
    t = """| **#** | **Sheet** | **Cell/Range** | **Severity** | **Category** | **Issue** | **Suggested Fix** |
|---|---|---|---|---|---|---|
| 1 | DCF | `C4:G4` | 🔴 **Critical** | Formula | Growth typed in =IF(A1\\|B1) | Link it |
2 | Inputs | B18 | ⚠️ Warning | Assumption | g high | Justify
"""
    theirs = parse_audit_table(t)
    assert [f["severity"] for f in theirs["findings"]] == ["blocker", "major"]
    assert theirs["findings"][0]["issue"] == "Growth typed in =IF(A1|B1)"
    ours = check(str(build_demo("hardcode-in-formula", tmp_path)))  # DS001 at DCF!E4, inside their C4:G4
    merged = merge(ours, theirs)
    on_e4 = [m for m in merged if m["ref"] in ("DCF!E4", "DCF!C4:G4")]
    assert {m["found_by"] for m in on_e4} == {"both"} and {m["rule"] for m in on_e4} >= {"DS001", "audit-xls"}
    assert merged[0]["severity"] == "blocker"  # their Critical is kept, so the report isn't "Minor"


def test_cli_fails_loudly_on_an_unreadable_audit_file(tmp_path):
    import subprocess

    a = tmp_path / "audit.md"
    a.write_text("The model looks fine overall.")
    m = build_demo("clean", tmp_path)
    r = subprocess.run([sys.executable, "-m", "deskstack_check", "check", str(m), "--audit", str(a)],
                       capture_output=True, text=True, cwd=HERE.parent)
    assert r.returncode == 2 and "Could not read any finding" in r.stderr


def test_comps_without_a_price_leave_market_cap_empty_and_multiples_not_available(tmp_path):
    """deskstack has no share prices. A market cap nobody gave stays null: no EV, no EV or P/E multiple (stars brief lot 5)."""
    from openpyxl import load_workbook

    spec = json.loads(json.dumps(COMPS))
    spec["peers"][1]["market_cap"] = {"value": None, "source": "No price given"}
    p = build_comps(spec, tmp_path / "c.xlsx")
    ws = load_workbook(p, data_only=True)["Comps"]
    row = next(r for r in range(4, 12) if ws[f"B{r}"].value == "PONE")
    assert ws[f"G{row}"].value is None
    assert [ws[f"{c}{row}"].value for c in "IJKL"] == ["n.a."] * 4
    # EV / EBITDA of the rated peers still gets its median, without PONE.
    assert ws["K9"].value == pytest.approx(statistics.median([160000 / 20000, 2005000 / 90000]))
    r = check(str(p))
    assert r["findings"] == [], r["findings"]
    ex = extract(str(p))
    assert not any(i.get("ref") == f"Comps!G{row}" for b in ex["verify_batches"] for i in b["items"])


def test_extract_names_a_european_issuer_by_its_lei(tmp_path):
    """EU issuers have no ticker: the DCF is titled 'Heineken N.V. (724500K5PTPSST86UQ23)'. The batch must carry the LEI,
    or verify_value can't be called (found building the examples; stars brief lot 5)."""
    spec = json.loads(json.dumps(SPEC))
    spec["company"], spec["ticker"], spec["currency"] = "Heineken N.V.", "724500K5PTPSST86UQ23", "EUR"
    ex = extract(str(build_dcf(spec, tmp_path / "h.xlsx")))
    assert {b["company"] for b in ex["verify_batches"]} == {"724500K5PTPSST86UQ23"}
