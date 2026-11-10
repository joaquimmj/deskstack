"""examples/: rebuilt from the recorded tool calls, the committed files must be current, and the planted-errors
example must have every error caught (stars brief lot 5)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "examples"


def _load():
    spec = importlib.util.spec_from_file_location("examples_build", EX / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_examples_are_current(capsys):
    """Regenerate: python3 examples/build.py (and examples/refresh.sh to re-record the tool calls)."""
    rc = _load().main(["--check"])
    assert rc == 0, capsys.readouterr().err


def test_every_example_ties_to_the_filings_except_the_planted_errors():
    for name in ("apple-dcf", "us-tech-comps", "heineken-dcf"):
        t = json.loads((EX / name / "associate.json").read_text())
        assert t["counts"].get("mismatch", 0) == 0 and t["counts"].get("match", 0) > 0, name
        assert json.loads((EX / name / "sign-off.json").read_text())["blocking"] == 0, name


def test_the_planted_errors_are_all_caught():
    d = EX / "errors-caught"
    spec = json.loads((d / "spec.json").read_text())
    tie = {r["ref"]: r for r in json.loads((d / "associate.json").read_text())["rows"]}
    mism = {ref for ref, r in tie.items() if r["status"] == "mismatch"}
    # stale-ltm (LTM revenue, operating income), shares-from-eps, placeholder-zero, offsetting-lines (both lines).
    assert mism == {"Inputs!D5", "Inputs!D6", "Inputs!B23", "Inputs!B7", "Inputs!C6", "Inputs!C7"}
    for ref in ("Inputs!D5", "Inputs!D6"):
        assert any(h.startswith(("Stale:", "Period: the value matches")) for h in tie[ref]["hints"]), tie[ref]
    review = json.loads((d / "vp-review.json").read_text())
    assert ("DS016", "Inputs!B7") in {(f["rule"], f["ref"]) for f in review["findings"]}
    so = json.loads((d / "sign-off.json").read_text())
    assert not so["ready"] and so["blocking"] >= 6
    # The placeholder keeps the label the model gave it.
    assert spec["history"]["lines"]["d_and_a"]["sources"][0] == "NOT FOUND - placeholder 0"
