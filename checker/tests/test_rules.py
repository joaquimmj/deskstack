"""Each rule fires on its planted error and stays silent on the clean model (brief M4)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from builder import Model, clean_dcf  # noqa: E402

from deskstack_check import check  # noqa: E402


def run(m: Model, tmp_path: Path, cache: bool = True) -> dict:
    p = m.save(tmp_path / "model.xlsx", cache=cache)
    return check(str(p))


def rules(report: dict, severities=("blocker", "major", "minor")) -> set[str]:
    return {f["rule"] for f in report["findings"] if f["severity"] in severities}


def drop_source(m: Model, ref: str) -> None:
    for row in m.sheet("Sources").iter_rows():
        if row[0].value == ref:
            row[0].value = None


def test_clean_model_has_no_findings(tmp_path):
    r = run(clean_dcf(), tmp_path)
    assert r["findings"] == []


# (rule, mutation) pairs: each plants one classic error into the clean model.
def m_hardcode(m):
    m.f("DCF", "D3", "=C3*1.05", 1102.5)


def m_pattern_break(m):
    fcf = m.cached[("DCF", "F5")] + m.cached[("DCF", "F6")]
    m.f("DCF", "F8", "=F5+F6", fcf)  # forgot "-F7" (capex) in one year


def m_input_black(m):
    m.inp("Inputs", "B5", 0.2, blue=False)


def m_formula_blue(m):
    m.f("DCF", "C4", "=C3*Inputs!$B$5", m.cached[("DCF", "C4")], blue=True)


def m_unsourced(m):
    drop_source(m, "Inputs!B7")


def m_external_link(m):
    m.f("DCF", "B19", "='[peers.xlsx]Inputs'!B9", 0.09)


def m_ref_error(m):
    m.f("DCF", "B17", "=B16/#REF!", "#REF!")


def m_div0(m):
    m.f("DCF", "B17", "=B16/Inputs!B13", "#DIV/0!")


def m_circular(m):
    m.f("BS", "C3", "=C5-C4", 120.0)


def m_unbalanced(m):
    m.inp("BS", "C7", 390.0)
    m.f("BS", "C8", "=C6+C7", 990.0)  # what Excel caches after recalculating


def m_cash_not_tied(m):
    m.inp("BS", "C3", 110.0)
    m.f("BS", "C5", "=C3+C4", 990.0)


def m_tv_share(m):
    m.f("DCF", "B13", "=B12*G9", 9000.0)
    m.f("DCF", "B15", "=B13+B14", 9000.0 + m.cached[("DCF", "B14")])


def m_wacc_g(m):
    m.inp("Inputs", "B10", 0.08)
    m.f("DCF", "B20", "=Inputs!B10", 0.08)


def m_g_above_gdp(m):
    m.inp("Inputs", "B10", 0.05)
    m.f("DCF", "B20", "=Inputs!B10", 0.05)


def m_units(m):
    m.text("Inputs", "A1", "Inputs (USD in thousands)")


def m_capex_sign(m):
    m.f("DCF", "E7", "=-E3*Inputs!$B$8", -m.cached[("DCF", "E7")])


def m_mid_year(m):
    m.text("Inputs", "B14", "Yes")


@pytest.mark.parametrize(
    "rule, mutate",
    [
        ("DS001", m_hardcode),
        ("DS002", m_pattern_break),
        ("DS003", m_input_black),
        ("DS003", m_formula_blue),
        ("DS004", m_unsourced),
        ("DS005", m_external_link),
        ("DS006", m_ref_error),
        ("DS006", m_div0),
        ("DS007", m_circular),
        ("DS008", m_unbalanced),
        ("DS009", m_cash_not_tied),
        ("DS010", m_tv_share),
        ("DS011", m_wacc_g),
        ("DS012", m_g_above_gdp),
        ("DS013", m_units),
        ("DS014", m_capex_sign),
        ("DS015", m_mid_year),
    ],
)
def test_planted_error_is_caught(tmp_path, rule, mutate):
    m = clean_dcf()
    mutate(m)
    found = rules(run(m, tmp_path))
    assert rule in found, f"{rule} not raised; got {sorted(found)}"


def test_findings_point_at_the_planted_cell(tmp_path):
    m = clean_dcf()
    m_hardcode(m)
    f = [x for x in run(m, tmp_path)["findings"] if x["rule"] == "DS001"]
    assert [x["ref"] for x in f] == ["DCF!D3"]
    assert "1.05" in f[0]["message"]


def test_circularity_is_major_when_iteration_is_on(tmp_path):
    m = clean_dcf()
    m_circular(m)
    m.wb.calculation.iterate = True
    sev = {f["severity"] for f in run(m, tmp_path)["findings"] if f["rule"] == "DS007"}
    assert sev == {"major"}


def test_without_cached_values_value_checks_say_they_were_limited(tmp_path):
    m = clean_dcf()
    m_unbalanced(m)  # still visible: both totals are formulas, so without cache it can't be checked
    r = run(m, tmp_path, cache=False)
    assert "DS008" not in rules(r)
    assert any(f["rule"] == "DS000" and "cached" in f["message"] for f in r["findings"])


def test_a_broken_rule_does_not_hide_the_others(tmp_path, monkeypatch):
    import deskstack_check as dc
    from deskstack_check import rules as R

    def boom(wb):
        raise RuntimeError("bad sheet")

    monkeypatch.setattr(dc, "STRUCTURAL", [boom] + R.STRUCTURAL)
    m = clean_dcf()
    m_hardcode(m)
    r = run(m, tmp_path)
    assert "DS001" in rules(r)
    assert any(f["rule"] == "DS000" and "bad sheet" in f["message"] for f in r["findings"])


# ---- stars brief lot 2: the errors AI-built models make (Wall Street Prep 2026, deskstack's own benchmarks) ----
def set_source(m, ref, text):
    for row in m.sheet("Sources").iter_rows():
        if row[0].value == ref:
            row[1].value = text


def m_placeholder_zero(m):
    m.inp("Inputs", "B12", 0.0)  # shares outstanding left as 0
    set_source(m, "Inputs!B12", "NOT FOUND - placeholder 0")


def m_placeholder_label(m):
    set_source(m, "Inputs!B11", "TBD: estimate, to replace")


def m_rate_whole_number(m):
    m.sheet("Inputs")["B4"].value = 5.0  # revenue growth "5" among decimal rates (0.2, 0.25, 0.09...)


def m_rate_percent_format(m):
    c = m.sheet("Inputs")["B5"]
    c.value, c.number_format = 20.0, "0.0%"  # EBIT margin shows as 2000.0%


def m_synthetic_history(m):
    m.text("Hist", "A1", "History (USD in millions)")
    m.text("Hist", "A3", "Revenue")
    for col, v in zip("BCDE", [800.0, 840.0, 882.0, 926.1]):  # exactly 5% a year, to the decimal
        m.inp("Hist", f"{col}3", v)
        n = len([k for k in m.sheet("Sources").iter_rows() if any(x.value for x in k)]) + 1
        m.text("Sources", f"A{n}", f"Hist!{col}3")
        m.text("Sources", f"B{n}", "Company 10-K")


def m_plug(m):
    m.text("BS", "A9", "Balancing plug")
    m.inp("BS", "C9", 15.0)
    n = len([k for k in m.sheet("Sources").iter_rows() if any(x.value for x in k)]) + 1
    m.text("Sources", f"A{n}", "BS!C9")
    m.text("Sources", f"B{n}", "model")


def m_interest_typed(m):
    m.text("DCF", "A22", "Debt")
    m.text("DCF", "A23", "Interest expense")
    for col in "CDEFG":
        m.f("DCF", f"{col}22", "=Inputs!$B$11", 300.0)
        m.inp("DCF", f"{col}23", 15.0)  # typed every year, not debt x rate
        n = len([k for k in m.sheet("Sources").iter_rows() if any(x.value for x in k)]) + 1
        m.text("Sources", f"A{n}", f"DCF!{col}23")
        m.text("Sources", f"B{n}", "assumption")


def m_shares_flat_with_buybacks(m):
    m.text("DCF", "A24", "Share buybacks")
    m.text("DCF", "A25", "Diluted shares")
    for col in "CDEFG":
        m.f("DCF", f"{col}24", "=Inputs!$B$12*0", 50.0)
        m.f("DCF", f"{col}25", "=Inputs!$B$12", 100.0)


LOT2 = [
    ("DS021", m_rate_whole_number),
    ("DS021", m_rate_percent_format),
    ("DS016", m_placeholder_zero),
    ("DS016", m_placeholder_label),
    ("DS017", m_synthetic_history),
    ("DS018", m_plug),
    ("DS019", m_interest_typed),
    ("DS020", m_shares_flat_with_buybacks),
]


@pytest.mark.parametrize("rule, mutate", LOT2)
def test_lot2_planted_error_is_caught(tmp_path, rule, mutate):
    m = clean_dcf()
    mutate(m)
    found = rules(run(m, tmp_path), severities=("blocker", "major", "minor"))
    assert rule in found, f"{rule} not raised; got {sorted(found)}"


def test_lot2_rules_are_documented():
    from deskstack_check.rules import RULE_INFO

    readme = (Path(__file__).parent.parent / "README.md").read_text()
    for rule in ("DS016", "DS017", "DS018", "DS019", "DS020"):
        assert rule in RULE_INFO and f"| {rule} |" in readme, rule


def test_ds021_leaves_a_model_that_types_every_rate_as_a_whole_number_alone(tmp_path):
    """A consistent convention (9 for 9%, divided by 100 in the formulas) is not an error; DS011 reads it too."""
    m = clean_dcf()
    ws = m.sheet("Inputs")
    for r in range(3, 13):
        label, c = ws[f"A{r}"].value or "", ws[f"B{r}"]
        if any(k in label.lower() for k in ("growth", "margin", "tax rate", "%", "wacc")) and isinstance(c.value, float) and c.value < 1:
            c.value = round(c.value * 100, 4)
    assert "DS021" not in rules(run(m, tmp_path))


def test_ds021_says_what_the_cell_shows(tmp_path):
    m = clean_dcf()
    m_rate_percent_format(m)
    f = next(f for f in run(m, tmp_path)["findings"] if f["rule"] == "DS021")
    assert f["ref"] == "Inputs!B5" and f["severity"] == "major" and "2000%" in f["message"]


def test_ds021_no_false_positives_found_in_review(tmp_path):
    """Review 2026-11-10: a literal % in the format, growth above 100%, a beta or a spread on a rate row."""
    m = clean_dcf()
    ws = m.sheet("Inputs")
    ws["B4"].value, ws["B4"].number_format = 1.5, "0%"  # 150% revenue growth: unusual, not a units error
    m.text("Inputs", "A20", "Cost of equity")
    m.text("Inputs", "B20", "Beta")
    m.inp("Inputs", "C20", 1.2)
    m.text("Inputs", "A21", "Cost of debt")
    m.text("Inputs", "B21", "spread (bps)")
    m.inp("Inputs", "C21", 75.0)
    assert "DS021" not in rules(run(m, tmp_path))


def test_ds021_a_literal_percent_sign_is_not_a_percent_cell(tmp_path):
    m = clean_dcf()
    c = m.sheet("Inputs")["B5"]
    c.value, c.number_format = 20.0, '0.0"%"'  # shows "20.0%" without multiplying by 100
    f = next(f for f in run(m, tmp_path)["findings"] if f["rule"] == "DS021")
    assert "percent cell" not in f["message"] and "other" in f["message"]  # still out of line with the decimal rates
