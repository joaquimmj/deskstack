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


def test_the_demo_recording_is_current():
    """site/media/demo/demo.cast replays the real outputs in examples/. Regenerate: python3 site/media/demo/make_cast.py,
    then render the GIF: python3 site/media/demo/render_gif.py."""
    spec = importlib.util.spec_from_file_location("make_cast", ROOT / "site" / "media" / "demo" / "make_cast.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (ROOT / "site" / "media" / "demo" / "demo.cast").read_text() == mod.cast()


def test_check_says_what_differs(tmp_path):
    """--check names the part of the file that changed, so a CI-only difference can be read from the log."""
    import zipfile

    def xlsx(p, cell):
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("xl/worksheets/sheet1.xml", f"<sheetData><c r='A1'><v>{cell}</v></c></sheetData>")
        return p

    why = _load()._why(xlsx(tmp_path / "new.xlsx", "0.1"), xlsx(tmp_path / "old.xlsx", "0.10000000000000001"))
    assert "xl/worksheets/sheet1.xml" in why and "0.1" in why and "[Content_Types].xml" not in why
    (tmp_path / "a.json").write_text('{\n "x": 1,\n "y": 2\n}\n')
    (tmp_path / "b.json").write_text('{\n "x": 1,\n "y": 3\n}\n')
    assert '"y": 2' in _load()._why(tmp_path / "a.json", tmp_path / "b.json")
