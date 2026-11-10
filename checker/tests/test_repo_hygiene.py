"""Repo hygiene (stars brief lot 8): raw benchmark files live on a release, not in git; every result folder a visitor
opens has its analysis; the issue and PR templates exist."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "bench" / "results"


def _tracked(prefix: str) -> list[str]:
    p = subprocess.run(["git", "ls-files", prefix], cwd=ROOT, capture_output=True, text=True)
    return p.stdout.split()


def test_no_raw_benchmark_file_is_committed():
    raw = [f for f in _tracked("bench/results") if re.search(r"/(runs|work)/", f)]
    assert raw == [], raw[:5]


def test_each_result_folder_has_its_analysis():
    for d in sorted(p for p in RESULTS.iterdir() if p.is_dir() and p.name != "exploratory"):
        assert (d / "ANALYSIS.md").exists(), f"{d.name}: add an ANALYSIS.md or move it to exploratory/"
    assert (RESULTS / "exploratory" / "README.md").exists()


def test_the_fetch_script_pins_the_release_archive_and_its_checksum():
    s = (ROOT / "bench" / "fetch-raw.sh").read_text()
    assert re.search(r'SHA256="\$\{DS_RAW_SHA256:-[0-9a-f]{64}\}"', s)
    assert "github.com/joaquimmj/deskstack/releases/download/" in s
    local = ROOT / "bench" / "raw-archive" / "deskstack-bench-raw-2026-11-09.tar.gz"
    if local.exists():  # the maintainer's copy, before it is uploaded
        import hashlib

        assert hashlib.sha256(local.read_bytes()).hexdigest() in s


def test_issue_and_pr_templates():
    t = ROOT / ".github" / "ISSUE_TEMPLATE"
    for name in ("bug", "data-source", "rule", "benchmark-company"):
        text = (t / f"{name}.yml").read_text()
        assert re.search(r"^name: .+", text, re.M) and re.search(r"^description: .+", text, re.M) and "body:" in text, name
    pr = (ROOT / ".github" / "pull_request_template.md").read_text()
    for promise in ("Every number is cited", "free to run", "Reviewers report", "public, widely known practice"):
        assert promise in pr


def test_starter_issues_are_ten():
    s = (ROOT / "docs" / "STARTER_ISSUES.md").read_text()
    assert len(re.findall(r"^## \d+\. ", s, re.M)) == 10
