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
