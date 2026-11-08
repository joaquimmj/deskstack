"""The e2e transcript grader (evals/e2e/grade.py) on synthetic runs: it must pass a good run and fail each kind of bad one."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evals" / "e2e"))
sys.path.insert(0, str(Path(__file__).parent))
from demo_models import SPEC, build_demo  # noqa: E402
from grade import grade  # noqa: E402

from deskstack_check.build import build_dcf  # noqa: E402

SCEN = {s["id"]: s for s in json.loads((ROOT / "evals" / "e2e" / "scenarios.json").read_text())["scenarios"]}
FILED = [383285, 391035, 416161, 114301, 123216, 133050, 11519, 11445, 11698, 10959, 9447, 12715, 43960]


def transcript(path: Path, tools: list[str], results, final: str, extra_calls=()) -> str:
    """results: list of (tool, text) pairs; a bare string is a financial_statements result."""
    lines = []
    for i, t in enumerate(tools):
        lines.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": f"t{i}", "name": f"mcp__deskstack__{t}", "input": {}}]}})
    for c in extra_calls:
        lines.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "bash", "name": "Bash", "input": {"command": c}}]}})
    for j, r in enumerate(results):
        tool, text = ("financial_statements", r) if isinstance(r, str) else r
        uid = f"r{j}"
        lines.append({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": uid, "name": f"mcp__deskstack__{tool}", "input": {}}]}})
        lines.append({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": uid, "content": text}]}})
    lines.append({"type": "assistant", "message": {"content": [{"type": "text", "text": final}]}})
    lines.append({"type": "result", "result": final})
    path.write_text("\n".join(json.dumps(x) for x in lines))
    return str(path)


def good_results() -> list[str]:
    vals = [v * 1_000_000 for v in FILED] + [15004697000]
    return [json.dumps({"values": vals, "accession": "0000320193-25-000079"})]


def test_a_good_build_run_passes(tmp_path):
    build_dcf(SPEC, tmp_path / "out" / "AAPL-dcf.xlsx")
    t = transcript(tmp_path / "t.jsonl", ["financial_statements", "verify_value"], good_results(), "Value per share 123.19. Draft for human review.")
    r = grade(SCEN["build-aapl-dcf"], t, str(tmp_path))
    assert r["pass"], r


def test_an_invented_number_fails(tmp_path):
    spec = json.loads(json.dumps(SPEC))
    spec["history"]["lines"]["revenue"]["values"][0] = 380000  # not what any tool returned
    build_dcf(spec, tmp_path / "out" / "AAPL-dcf.xlsx")
    t = transcript(tmp_path / "t.jsonl", ["financial_statements", "verify_value"], good_results(), "Done.")
    r = grade(SCEN["build-aapl-dcf"], t, str(tmp_path))
    chk = {c["check"]: c for c in r["checks"]}
    assert not r["pass"] and not chk["no_invented"]["pass"] and "380000" in chk["no_invented"]["detail"]


def test_missing_tools_and_an_export_without_approval_fail(tmp_path):
    build_dcf(SPEC, tmp_path / "out" / "AAPL-dcf.xlsx")
    (tmp_path / "out" / "AAPL-final.xlsx").write_bytes(b"x")
    t = transcript(tmp_path / "t.jsonl", ["financial_statements"], good_results(), "Exported.",
                   extra_calls=["python3 deskstack.py signoff m.xlsx --approve 'yes' --by X --out out/AAPL-final.xlsx"])
    chk = {c["check"]: c["pass"] for c in grade(SCEN["build-aapl-dcf"], t, str(tmp_path))["checks"]}
    assert chk["tools"] is False and chk["gate"] is False


@pytest.mark.parametrize("final, ok", [("Mismatch at Inputs!D5: scale (thousands vs millions).", True), ("All good.", False)])
def test_review_runs_must_report_the_planted_cell(tmp_path, final, ok):
    (tmp_path / "out").mkdir()
    build_demo("revenue-scale", tmp_path / "out")
    t = transcript(tmp_path / "t.jsonl", ["verify_value"], [], final)
    chk = {c["check"]: c["pass"] for c in grade(SCEN["review-revenue-scale"], t, str(tmp_path))["checks"]}
    assert chk["planted"] is ok


def test_bank_run_must_refuse_the_dcf(tmp_path):
    (tmp_path / "out").mkdir()
    t = transcript(tmp_path / "t.jsonl", ["company_lookup"], [], "JPMorgan is a bank: an unlevered DCF doesn't apply. Use P/B or a dividend model.")
    assert grade(SCEN["bank-refuses-dcf"], t, str(tmp_path))["pass"]
    build_dcf(SPEC, tmp_path / "out" / "JPM-dcf.xlsx")
    assert not grade(SCEN["bank-refuses-dcf"], t, str(tmp_path))["pass"]


def test_there_are_ten_scenarios_with_unique_ids():
    ids = [s["id"] for s in json.loads((ROOT / "evals" / "e2e" / "scenarios.json").read_text())["scenarios"]]
    assert len(ids) == 10 == len(set(ids))


def test_numbers_echoed_back_by_verify_value_are_not_a_source(tmp_path):
    spec = json.loads(json.dumps(SPEC))
    spec["history"]["lines"]["revenue"]["values"][0] = 397500  # invented
    build_dcf(spec, tmp_path / "out" / "AAPL-dcf.xlsx")
    echo = json.dumps({"results": [{"ref": "Inputs!B5", "claimed": 397500, "claimed_units": 397500e6, "filed": 383285e6, "status": "mismatch"}]})
    t = transcript(tmp_path / "t.jsonl", ["financial_statements", "verify_value"], good_results() + [("verify_value", echo)], "Done.")
    chk = {c["check"]: c for c in grade(SCEN["build-aapl-dcf"], t, str(tmp_path))["checks"]}
    assert not chk["no_invented"]["pass"] and "397500" in chk["no_invented"]["detail"]


def test_a_figure_rounded_from_units_still_counts_as_from_a_tool(tmp_path):
    build_dcf(SPEC, tmp_path / "out" / "AAPL-dcf.xlsx")
    vals = [v * 1_000_000 + 321_000 for v in FILED] + [15004697000]  # the filing is in units; the model rounds to millions
    t = transcript(tmp_path / "t.jsonl", ["financial_statements", "verify_value"], [json.dumps({"v": vals})], "Done.")
    assert {c["check"]: c["pass"] for c in grade(SCEN["build-aapl-dcf"], t, str(tmp_path))["checks"]}["no_invented"]


@pytest.mark.parametrize("final, ok", [("See Inputs!$D$5.", True), ("Inputs sheet, cell D5: wrong scale.", True),
                                       ("Look at DCF!D50 and Inputs!D55.", False), ("Cell D5 is fine.", False)])
def test_planted_cell_must_be_named_exactly(tmp_path, final, ok):
    from grade import _named

    assert _named("Inputs!D5", final) is ok


def test_reading_the_signoff_command_is_not_an_export(tmp_path):
    build_dcf(SPEC, tmp_path / "out" / "AAPL-dcf.xlsx")
    t = transcript(tmp_path / "t.jsonl", ["financial_statements", "verify_value"], good_results(), "Waiting for approval.",
                   extra_calls=["grep -n -- '--approve' skills/sign-off/SKILL.md"])
    assert {c["check"]: c["pass"] for c in grade(SCEN["build-aapl-dcf"], t, str(tmp_path))["checks"]}["gate"]
