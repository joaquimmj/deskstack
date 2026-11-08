"""The golden set is current, and the differential comparison flags what it should (with fake oracles)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "evals" / "differential"))
from differential import compare, summarize  # noqa: E402

GOLDEN = json.loads((ROOT / "evals" / "golden.json").read_text())


def test_golden_json_is_current():
    r = subprocess.run([sys.executable, str(ROOT / "evals" / "build_golden.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_golden_set_covers_the_edge_cases_the_brief_asks_for():
    tags = {t for q in GOLDEN["questions"] for t in q["tags"]}
    assert GOLDEN["count"] >= 60
    assert {"us", "eu", "ifrs", "bank", "restated", "june-fye", "september-fye", "january-fye", "march-fye", "ifrs16", "stock-split"} <= tags
    sources = {q["source"]["type"] for q in GOLDEN["questions"]}
    assert {"sec-companyfacts", "esef", "treasury-par-yield", "ecb-exr", "behavior"} <= sources


class Fake:
    def __init__(self, values: dict, fail: set = frozenset(), latest: dict | None = None):
        self.values, self.fail, self._latest = values, fail, latest

    def value(self, key, concept, start, end):
        if (key, concept, end) in self.fail:
            raise LookupError("not in filing")
        return self.values[(key, concept, end)]


class FakeWithLatest(Fake):
    def latest(self, ticker, concept, start, end):
        return self._latest[(ticker, concept, end)]


def _q(qid, kind, key, expected, concept="us-gaap:Revenues", end="2025-12-31", unit="USD", ticker="AAA"):
    src = {"type": kind, "concept": concept, "start": "2025-01-01", "end": end, "ticker": ticker,
           ("accession" if kind == "sec-companyfacts" else "report"): key}
    return {"id": qid, "expected": expected, "unit": unit, "source": src}


def test_compare_is_exact_as_filed_and_flags_golden_and_live_differences():
    qs = [
        _q("agree", "sec-companyfacts", "A", 1000.0),
        _q("off-by-one", "sec-companyfacts", "B", 1001.0),
        _q("eps-cent", "sec-companyfacts", "E", 5.62, unit="USD/shares"),
        _q("live-off", "esef", "R", 500.0),
        _q("live-null", "esef", "N", 700.0),
        _q("unreadable", "sec-companyfacts", "C", 10.0),
        {"id": "rate", "expected": 0.04, "source": {"type": "treasury-par-yield"}},
    ]
    sec = Fake({("A", "us-gaap:Revenues", "2025-12-31"): 1000.0, ("B", "us-gaap:Revenues", "2025-12-31"): 1000.0,
                ("E", "us-gaap:Revenues", "2025-12-31"): 5.61}, fail={("C", "us-gaap:Revenues", "2025-12-31")})
    esef = Fake({("R", "us-gaap:Revenues", "2025-12-31"): 500.0, ("N", "us-gaap:Revenues", "2025-12-31"): 700.0})
    rows = compare(qs, {"live-off": 520.0, "live-null": None, "agree": 1000.0}, sec, esef)
    by = {r["id"]: r for r in rows}
    assert by["agree"]["status"] == "agree"
    assert by["off-by-one"]["status"] == "disagree"  # one unit off is a difference: exact as filed
    assert by["eps-cent"]["status"] == "disagree"  # a cent off on EPS
    assert by["live-off"]["status"] == "disagree" and "deskstack differs" in by["live-off"]["problems"][0]
    assert by["live-null"]["status"] == "disagree"  # deskstack returning null for a filed figure
    assert by["unreadable"]["status"] == "unchecked"
    assert "rate" not in by
    assert summarize(rows) == {"total": 6, "agree": 1, "disagree": 4, "unchecked": 1}


def test_compare_finds_a_later_filing_the_golden_builder_missed():
    q = _q("restated", "sec-companyfacts", "OLD", 1000.0)
    sec = FakeWithLatest({("OLD", "us-gaap:Revenues", "2025-12-31"): 1000.0}, latest={("AAA", "us-gaap:Revenues", "2025-12-31"): ("NEW", 990.0)})
    r = compare([q], {}, sec)[0]
    assert r["status"] == "disagree" and "later filing (NEW)" in r["problems"][0]
    sec_same = FakeWithLatest({("OLD", "us-gaap:Revenues", "2025-12-31"): 1000.0}, latest={("AAA", "us-gaap:Revenues", "2025-12-31"): ("NEW", 1000.0)})
    assert compare([q], {}, sec_same)[0]["status"] == "agree"  # a later filing with the same value is fine


def test_compare_skips_a_source_with_no_oracle():
    assert compare([_q("x", "sec-companyfacts", "A", 1.0)], {}, sec=None, esef=None) == []


def test_differential_fails_when_nothing_could_be_checked(tmp_path, monkeypatch):
    import differential

    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    assert differential.main(["--only", "sec", "--out", str(tmp_path / "d.json")]) == 1
    assert json.loads((tmp_path / "d.json").read_text())["skipped"]
