"""M6 scripts: red-team sensitivities, compliance checks and the sign-off gate."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from openpyxl import load_workbook

sys.path.insert(0, str(Path(__file__).parent))
from demo_models import SPEC, build_demo  # noqa: E402

from deskstack_check import check  # noqa: E402
from deskstack_check.build import build_comps, build_dcf, dcf_math  # noqa: E402
from deskstack_check.compliance import check as compliance  # noqa: E402
from deskstack_check.sensitivity import NoLayout, sensitivity  # noqa: E402
from deskstack_check.signoff import GateError, export, summary  # noqa: E402
from deskstack_check.tieout import report  # noqa: E402

HERE = Path(__file__).parent
COMPS = json.loads((HERE / "specs" / "peers_comps.json").read_text())


def cli(*args, cwd):
    return subprocess.run([sys.executable, "-m", "deskstack_check", *map(str, args)], capture_output=True, text=True,
                          cwd=HERE.parent, env={"PYTHONPATH": str(HERE.parent)})


# ---- sensitivity -------------------------------------------------------------------------

def test_sensitivity_base_matches_the_workbook(tmp_path):
    p = build_dcf(SPEC, tmp_path / "m.xlsx")
    r = sensitivity(str(p))
    cached = load_workbook(p, data_only=True)["DCF"]["B21"].value
    assert r["base"]["value_per_share"] == pytest.approx(cached) and r["warnings"] == []
    g = r["grid"]
    assert g["value_per_share"][2][2] == pytest.approx(cached)  # centre of the grid = base case
    wacc = next(t for t in r["tornado"] if t["input"] == "wacc")
    assert wacc["per_share_down"] > cached > wacc["per_share_up"]


def test_sensitivity_reads_inputs_edited_in_the_file(tmp_path):
    p = build_dcf(SPEC, tmp_path / "m.xlsx")
    wb = load_workbook(p)
    wb["Inputs"]["B17"] = 0.10  # WACC edited by hand; formulas not recalculated
    wb.save(p)
    r = sensitivity(str(p))
    a = {k: SPEC["assumptions"][k]["value"] for k in ("ebit_margin", "tax_rate", "da_pct_revenue", "capex_pct_revenue", "terminal_growth")}
    want = dcf_math(416161, SPEC["assumptions"]["revenue_growth"]["values"], {**a, "wacc": 0.10}, False, 43960, 15004.697)
    assert r["base"]["value_per_share"] == pytest.approx(want["per_share"])


def test_sensitivity_implied_inputs_reprice_to_the_market(tmp_path):
    p = build_dcf(SPEC, tmp_path / "m.xlsx")
    r = sensitivity(str(p), price=200)
    w = r["implied"]["wacc"]
    a = {k: SPEC["assumptions"][k]["value"] for k in ("ebit_margin", "tax_rate", "da_pct_revenue", "capex_pct_revenue", "terminal_growth")}
    assert dcf_math(416161, SPEC["assumptions"]["revenue_growth"]["values"], {**a, "wacc": w}, False, 43960, 15004.697)["per_share"] == pytest.approx(200, rel=1e-4)
    assert r["implied"]["ebit_margin"] > SPEC["assumptions"]["ebit_margin"]["value"]


def test_sensitivity_refuses_workbooks_it_did_not_build(tmp_path):
    with pytest.raises(NoLayout, match="wasn't built by deskstack"):
        sensitivity(str(build_comps(COMPS, tmp_path / "c.xlsx")))


# ---- compliance --------------------------------------------------------------------------

def _status(r, cid):
    return next(i["status"] for i in r["items"] if i["id"] == cid)


def test_compliance_passes_a_clean_build(tmp_path):
    r = compliance(str(build_dcf(SPEC, tmp_path / "m.xlsx")))
    assert r["result"] == "pass" and r["counts"]["fail"] == 0


def test_compliance_catches_each_problem(tmp_path):
    spec = json.loads(json.dumps(SPEC))
    spec["assumptions"]["wacc"]["source"] = "From memory, approx."
    spec["bridge"]["net_debt"]["source"] = "User-provided"
    spec["assumptions"]["ebit_margin"]["source"] = "Management's internal only budget, board pack"

    def tamper(b):
        b.sheet("Cover")["A2"] = "Strong buy recommendation"  # disclaimer removed, advice language added
        b.sources = [x for x in b.sources if x[0] != "Inputs!D5"]
        ws = b.sheet("Scratch")
        ws["A1"] = "hidden notes"
        ws.sheet_state = "hidden"

    p = build_dcf(spec, tmp_path / "m.xlsx", tamper=tamper)
    memo = tmp_path / "memo.md"
    memo.write_text("Apple is worth 123 per share. We recommend buying now.\n")
    r = compliance(str(p), str(memo))
    for cid in ("C01", "C01m", "C03", "C04", "C05", "C06", "C07"):
        assert _status(r, cid) == "fail", cid
    assert _status(r, "C09") == "warn" and _status(r, "C10") == "warn"
    assert r["result"] == "fail"


# ---- sign-off ----------------------------------------------------------------------------

def _reports(tmp_path, model, results=None, memo=True):
    from deskstack_check.model import file_sha256

    t = tmp_path / "tieout.json"
    t.write_text(json.dumps(report(str(model), results or [])))
    rv = tmp_path / "review.json"
    rv.write_text(json.dumps(check(str(model))))
    c = tmp_path / "compliance.json"
    c.write_text(json.dumps(compliance(str(model))))
    m = tmp_path / "redteam.md"
    m.write_text(f"Model SHA-256: {file_sha256(str(model))}\n1. Growth is above history.\n2. TV is 74% of EV.\n")
    return dict(tieout=str(t), review=str(rv), compliance=str(c), redteam=str(m) if memo else None)


def _all_match(model):
    from deskstack_check.tieout import extract

    return [{"ref": e["ref"], "status": "match", "filed": 1, "hints": []} for e in extract(str(model))["filed"]]


def _signed(tmp_path, model, reps, words="I approve the export", **kw):
    s = summary(str(model), **reps)
    return export(str(model), str(tmp_path / kw.pop("name", "f.xlsx")), reps, kw.pop("by", "Joaquim"), words, kw.pop("token", s["token"]), **kw)


@pytest.mark.parametrize("words", ["I approve", "Approved.", "Yes, I approve the export", "j'approuve l'export", "Je valide", "go ahead"])
def test_affirmative_words_are_approval(words):
    from deskstack_check.signoff import is_approval

    assert is_approval(words)


@pytest.mark.parametrize("words", ["I don't approve", "not approved", "Do not sign off yet", "I need approval from my MD first",
                                   "No. Go ahead and fix the blockers first", "pas ok pour moi", "je ne valide pas", "approve?",
                                   "Approve once the scale is fixed", "looks good to me", "ok", "", "approval"])
def test_refusals_questions_and_conditions_are_not_approval(words):
    from deskstack_check.signoff import is_approval

    assert not is_approval(words)


def test_signoff_exports_only_after_explicit_approval(tmp_path):
    model = build_demo("clean", tmp_path)
    reps = _reports(tmp_path, model, _all_match(model))
    s = summary(str(model), **reps)
    assert s["blocking"] == 0 and s["ready"] and s["missing"] == []
    with pytest.raises(GateError, match="Not an approval"):
        _signed(tmp_path, model, reps, "I don't approve")
    with pytest.raises(GateError, match="never guess"):
        _signed(tmp_path, model, reps, by=" ")
    with pytest.raises(GateError, match="token"):
        _signed(tmp_path, model, reps, token="000000000000")
    rec = _signed(tmp_path, model, reps, "J'approuve l'export")
    out = load_workbook(rec["output"], data_only=True)
    assert out["DCF"]["B21"].value == pytest.approx(load_workbook(model, data_only=True)["DCF"]["B21"].value)
    vals = {r[0]: r[1] for r in out["Sign-off"].iter_rows(values_only=True) if r[0]}
    assert vals["Approved by"] == "Joaquim" and vals["Approval, in the approver's words"] == "J'approuve l'export"
    assert json.loads(Path(rec["output"] + ".signoff.json").read_text())["output_sha256"] == rec["output_sha256"]
    assert check(rec["output"])["findings"] == []  # the signed copy is still a clean model
    with pytest.raises(GateError, match="already exists"):
        _signed(tmp_path, model, reps)


def test_signoff_blocks_open_items_until_accepted_with_a_real_reason(tmp_path):
    model = build_demo("revenue-scale", tmp_path)
    results = _all_match(model)
    results[2] = {"ref": "Inputs!D5", "status": "mismatch", "filed": 416161e6, "hints": ["Scale: ..."]}
    reps = _reports(tmp_path, model, results)
    s = summary(str(model), **reps)
    assert s["blocking"] >= 1 and any(o["ref"] == "Inputs!D5" for o in s["open_items"])
    with pytest.raises(GateError, match="blocking item"):
        _signed(tmp_path, model, reps)
    with pytest.raises(GateError, match="real sentence"):
        _signed(tmp_path, model, reps, accept_open="n/a")
    rec = _signed(tmp_path, model, reps, accept_open="Illustrative draft; scale fixed next round")
    assert rec["accepted_open_items"].startswith("Illustrative")


def test_signoff_treats_untied_figures_and_missing_reviews_as_open(tmp_path):
    model = build_demo("clean", tmp_path)
    r = _reports(tmp_path, model)  # no verify_value results: 14 figures not tied out
    assert summary(str(model), **r)["blocking"] == 14
    reps = {"tieout": r["tieout"], "review": None, "compliance": None}
    s2 = summary(str(model), **reps)
    assert set(s2["missing"]) == {"review", "compliance"}
    with pytest.raises(GateError, match="Missing review"):
        _signed(tmp_path, model, reps, accept_open="We only want the tie-out recorded today")
    rec = _signed(tmp_path, model, reps, accept_open="We only want the tie-out recorded today", accept_missing=["review", "compliance"])
    assert rec["accepted_missing_reviews"] == ["compliance", "review"]


def test_reports_of_the_wrong_kind_or_shape_count_as_missing(tmp_path):
    model = build_demo("clean", tmp_path)
    r = _reports(tmp_path, model, _all_match(model))
    empty = tmp_path / "empty.json"
    empty.write_text("{}")
    fake = tmp_path / "fake.json"
    fake.write_text(json.dumps({"counts": {"pass": 1, "fail": 0, "warn": 0}, "items": []}))
    s = summary(str(model), tieout=str(empty), review=r["tieout"], compliance=str(fake))
    assert set(s["missing"]) == {"tieout", "review", "compliance"} and not s["ready"]


def test_signoff_cli_refuses_a_file_changed_after_the_reviews(tmp_path):
    model = build_demo("clean", tmp_path)
    r = _reports(tmp_path, model, _all_match(model))
    token = summary(str(model), **r)["token"]
    wb = load_workbook(model)
    wb["Inputs"]["B17"] = 0.20
    wb.save(model)
    p = cli("signoff", model, "--tieout", r["tieout"], "--review", r["review"], "--compliance", r["compliance"],
            "--approve", "I approve", "--by", "Joaquim", "--token", token, "--out", tmp_path / "final.xlsx", cwd=tmp_path)
    assert p.returncode == 2 and "token" in p.stderr and not (tmp_path / "final.xlsx").exists()
    s = summary(str(model), **r)  # the reports are now stale, and say so
    assert {c["status"] for c in s["checks"] if c["key"] != "redteam"} == {"stale"} and s["blocking"] == 3


def test_signoff_cli_waits_for_approval_then_exports(tmp_path):
    model = build_demo("clean", tmp_path)
    r = _reports(tmp_path, model, _all_match(model))
    args = ["signoff", model, "--tieout", r["tieout"], "--review", r["review"], "--compliance", r["compliance"], "--redteam", r["redteam"]]
    p = cli(*args, cwd=tmp_path)
    assert p.returncode == 3 and "Nothing is exported until you approve" in p.stdout
    token = re.search(r"Approval token: `([0-9a-f]{12})`", p.stdout).group(1)
    p = cli(*args, "--approve=I approve =1+1", "--by", "Joaquim\x07", f"--token={token}", "--out", tmp_path / "final.xlsx", cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    ws = load_workbook(tmp_path / "final.xlsx")["Sign-off"]
    vals = {r[0]: r[1] for r in ws.iter_rows(values_only=True) if r[0]}
    assert vals["Approval, in the approver's words"] == "I approve =1+1" and vals["Approved by"] == "Joaquim"


def test_signoff_keeps_cached_dates_and_leaves_nothing_on_failure(tmp_path):
    from openpyxl import Workbook

    from deskstack_check.xlsxio import inject_values

    p = tmp_path / "dated.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "Model"
    ws["A1"], ws["B1"] = "Valuation date", "=DATE(2026,11,8)"
    ws["A2"] = "Draft for human review. Not investment advice."
    wb.create_sheet("Sources")["A1"] = "Cell"
    wb.save(p)
    import datetime as dt

    inject_values(p, {("Model", "B1"): dt.datetime(2026, 11, 8)}, ["Model", "Sources"])
    from deskstack_check.compliance import check as comp

    tie = tmp_path / "t.json"
    tie.write_text(json.dumps({"report": "tieout", "model_sha256": __import__("deskstack_check.model", fromlist=["x"]).file_sha256(str(p)),
                               "counts": {"match": 1}, "rows": [{"ref": "Model!B9", "status": "match"}]}))
    rv = tmp_path / "r.json"
    rv.write_text(json.dumps(check(str(p))))
    cp = tmp_path / "c.json"
    cp.write_text(json.dumps(comp(str(p))))
    reps = {"tieout": str(tie), "review": str(rv), "compliance": str(cp)}
    rec = _signed(tmp_path, p, reps, accept_open="Compliance items reviewed by hand today")
    from openpyxl.utils.datetime import to_excel

    assert load_workbook(rec["output"], data_only=True)["Model"]["B1"].value == to_excel(dt.datetime(2026, 11, 8))  # a date serial
    assert not list(tmp_path.glob("tmp*.xlsx"))


def test_tornado_puts_unbounded_shocks_first(tmp_path):
    spec = json.loads(json.dumps(SPEC))
    spec["assumptions"]["wacc"]["value"] = 0.05
    spec["assumptions"]["terminal_growth"]["value"] = 0.042
    r = sensitivity(str(build_dcf(spec, tmp_path / "m.xlsx")))
    assert r["tornado"][0]["unbounded"] and r["tornado"][0]["input"] in ("wacc", "terminal_growth")
    assert any("no upper bound" in w for w in r["warnings"])
    from deskstack_check.sensitivity import to_markdown

    assert "unbounded" in to_markdown(r) and "nan" not in to_markdown(r)


def test_sensitivity_detects_moved_rows(tmp_path):
    p = build_dcf(SPEC, tmp_path / "m.xlsx")
    wb = load_workbook(p)
    wb["Inputs"].delete_rows(14)
    wb.save(p)
    with pytest.raises(NoLayout, match="rows were moved|not a number"):
        sensitivity(str(p))


@pytest.mark.parametrize("text", ["Damodaran Online, Jan 2026 (accession n/a)", "Citi NA credit agreement", "Source: Business Insider",
                                  "Insider ownership 0.1% (DEF 14A)", "Exhibit 10.2 (confidential treatment requested)",
                                  "User-provided price, 8 November 2026", "fourni par l'utilisateur le 8 novembre 2026",
                                  "Data provided by SEC EDGAR", "buy-side consensus not used"])
def test_compliance_has_no_false_positive_on_ordinary_sources(tmp_path, text):
    spec = json.loads(json.dumps(SPEC))
    spec["assumptions"]["wacc"]["source"] = text
    r = compliance(str(build_dcf(spec, tmp_path / "m.xlsx")))
    assert r["result"] == "pass", [i for i in r["items"] if i["status"] == "fail"]


@pytest.mark.parametrize("text, cid", [("Per the CIM in the data room", "C06"), ("Shared under our NDA", "C06"),
                                       ("Not yet announced guidance", "C06"), ("Rating: BUY", "C07"), ("User-provided", "C05"),
                                       ("TBD", "C04")])
def test_compliance_catches_the_real_problems(tmp_path, text, cid):
    spec = json.loads(json.dumps(SPEC))
    spec["assumptions"]["wacc"]["source"] = text
    r = compliance(str(build_dcf(spec, tmp_path / "m.xlsx")))
    assert _status(r, cid) == "fail"


def test_the_comps_example_passes_compliance(tmp_path):
    assert compliance(str(build_comps(COMPS, tmp_path / "c.xlsx")))["result"] == "pass"


def test_cli_rejects_unknown_options_and_bad_values(tmp_path):
    model = build_demo("clean", tmp_path)
    assert cli("check", model, "--jsn", cwd=tmp_path).returncode == 2
    p = cli("sensitivity", model, "--price=$230", cwd=tmp_path)
    assert p.returncode == 0 and "At the price of 230.00" in p.stdout
    p = cli("sensitivity", model, "--price", "abc", cwd=tmp_path)
    assert p.returncode == 2 and "--price must be a number" in p.stderr
    p = cli("check", tmp_path / "missing.xlsx", cwd=tmp_path)
    assert p.returncode == 2 and "Error" in p.stderr and "Traceback" not in p.stderr
    from deskstack_check.model import file_sha256

    assert cli("hash", model, cwd=tmp_path).stdout.strip() == file_sha256(str(model))
