"""deskstack-check, the command for any workbook (stars brief lot 3): offline checks, formats, exit codes, and
--verify against a local MCP server that replays real recorded verify_value answers (no network)."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "checker"))
sys.path.insert(0, str(Path(__file__).parent))

from deskstack_check.cli import main  # noqa: E402
from demo_models import build_demo  # noqa: E402

TYPO = ROOT / "examples" / "apple-dcf-typo"
RECORDED = json.loads((TYPO / "calls" / "verify.json").read_text())["batches"]


class FakeMcp(BaseHTTPRequestHandler):
    refuse: str | None = None
    calls: list = []

    def do_POST(self):  # noqa: N802
        msg = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeMcp.calls.append(msg)
        if msg["method"] == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {"tools": {}}, "serverInfo": {"name": "fake", "version": "0"}}
        elif FakeMcp.refuse:
            result = {"content": [{"type": "text", "text": FakeMcp.refuse}], "isError": True}
        else:
            args = msg["params"]["arguments"]
            hit = next((b["response"] for b in RECORDED if b["request"] == args), None)
            result = ({"content": [{"type": "text", "text": json.dumps(hit)}]} if hit is not None
                      else {"content": [{"type": "text", "text": "unknown batch"}], "isError": True})
        body = f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': msg['id'], 'result': result})}\n\n".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture
def server():
    FakeMcp.refuse, FakeMcp.calls = None, []
    httpd = HTTPServer(("127.0.0.1", 0), FakeMcp)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{httpd.server_port}/mcp"
    httpd.shutdown()


def test_offline_report_names_each_finding_and_exits_by_level(tmp_path, capsys):
    model = str(build_demo("hardcode-in-formula", tmp_path))  # DS001, a major
    assert main([model]) == 0
    out = capsys.readouterr().out
    assert "MAJOR" in out and "DS001" in out and "DCF!E4" in out and "Fix:" in out
    assert "Add --verify" in out and out.rstrip().endswith("PASS (fails on blocker)")
    assert main([model, "--fail-on", "major"]) == 1
    assert main([model, "--fail-on", "never"]) == 0


def test_json_and_markdown(tmp_path, capsys):
    model = str(build_demo("terminal-growth-too-high", tmp_path))
    assert main([model, "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert {f["rule"] for f in r["model_check"]["findings"]} >= {"DS011", "DS012"} and r["tieout"] is None and r["passed"]
    main([model, "--markdown"])
    assert "| # | Sheet | Cell/Range | Severity |" in capsys.readouterr().out


def test_verify_ties_figures_to_the_filings_through_the_connector(server, capsys):
    rc = main([str(TYPO / "model.xlsx"), "--verify", "--connector", server])
    out = capsys.readouterr().out
    assert rc == 1  # a figure that doesn't tie is a blocker
    assert "13 of 14 match" in out and "MISMATCH" in out and "Inputs!C5" in out and "two adjacent digits look swapped" in out
    assert [c["method"] for c in FakeMcp.calls] == ["initialize", "tools/call"]
    assert FakeMcp.calls[1]["params"]["arguments"]["company"] == "AAPL"


def test_a_connector_refusal_is_reported_not_hidden(server, capsys):
    FakeMcp.refuse = "deskstack's free daily capacity is used up: ... It resets at 00:00 UTC, in 3 h 5 min."
    rc = main([str(TYPO / "model.xlsx"), "--verify", "--connector", server])
    assert rc == 2
    assert "resets at 00:00 UTC" in capsys.readouterr().err


def test_an_unreachable_connector_exits_2(capsys):
    assert main([str(TYPO / "model.xlsx"), "--verify", "--connector", "http://127.0.0.1:9/mcp"]) == 2
    assert "could not reach" in capsys.readouterr().err


def test_a_workbook_that_names_no_company_asks_for_one(tmp_path, server, capsys):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws["A1"], ws["A2"], ws["B3"], ws["A4"], ws["B4"] = "Revenue model", "($ in millions)", "FY2025", "Revenue", 416116
    p = tmp_path / "other-tool.xlsx"
    wb.save(p)
    assert main([str(p), "--verify", "--connector", server]) == 2
    assert "--company" in capsys.readouterr().err


def test_other_tools_and_bad_input(tmp_path, capsys):
    assert main(["extract", str(TYPO / "model.xlsx")]) == 0
    assert json.loads(capsys.readouterr().out)["counts"]["filed"] == 14
    audit = tmp_path / "a.md"
    audit.write_text("| # | Sheet | Cell/Range | Severity | Category | Issue | Suggested Fix |\n|---|---|---|---|---|---|---|\n"
                     "| 1 | DCF | E4 | Warning | Hardcode | Typed growth | Link it |\n")
    assert main(["check", str(TYPO / "model.xlsx"), "--audit", str(audit)]) == 0
    assert "Found by" in capsys.readouterr().out
    assert main([str(tmp_path / "missing.xlsx")]) == 2
    assert main(["model.xlsx", "--fail-on", "sometimes"]) == 2
    assert main(["model.xlsx", "--frobnicate"]) == 2


def test_ignore_drops_rules_from_the_report_and_the_exit_code(tmp_path, capsys):
    """A team accepts a finding on purpose: --ignore DS001,DS010 (starter issue 2)."""
    model = str(build_demo("hardcode-in-formula", tmp_path))  # DS001 and DS002, both major, on DCF!E4
    assert main([model, "--fail-on", "major"]) == 1
    assert main([model, "--fail-on", "major", "--ignore", "DS001"]) == 1  # DS002 still counts
    capsys.readouterr()
    assert main([model, "--fail-on", "major", "--ignore", "DS001,DS002"]) == 0
    out = capsys.readouterr().out
    assert "DS001" not in out.split("Ignored")[0] and "Ignored: DS001, DS002" in out
    assert main([model, "--json", "--ignore", "ds001"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["ignored"] == ["DS001"] and {f["rule"] for f in r["model_check"]["findings"]} == {"DS002"}
    assert main([model, "--ignore", "nope"]) == 2


def test_company_fills_only_the_batches_that_name_none(server, capsys, monkeypatch):
    """--company is for workbooks that don't name their company; a comps row naming MSFT stays MSFT (review 2026-11-10)."""
    import deskstack_check.cli as cli

    sent = []
    monkeypatch.setattr(cli, "call_tool", lambda url, name, args: sent.append(args["company"]) or {"results": []})
    monkeypatch.setattr("deskstack_check.tieout.extract", lambda p: {"verify_batches": [{"company": "MSFT", "items": [{"ref": "A!B1"}]},
                                                                               {"company": None, "items": [{"ref": "A!B2"}]}]})
    monkeypatch.setattr("deskstack_check.tieout.report", lambda p, r: {"counts": {}, "rows": []})
    cli.verify("x.xlsx", server, company="AAPL")
    assert sent == ["MSFT", "AAPL"]


def test_a_broken_workbook_exits_2_with_a_message_not_a_traceback(tmp_path, capsys):
    import zipfile

    bad = tmp_path / "broken.xlsx"
    with zipfile.ZipFile(bad, "w") as z:
        z.writestr("hello.txt", "not a workbook")
    assert main([str(bad)]) == 2
    err = capsys.readouterr().err
    assert "Error:" in err and "Traceback" not in err


def test_a_connector_error_that_is_not_an_object_is_still_reported(capsys, monkeypatch):
    import deskstack_check.cli as cli

    class R:
        headers = {"Content-Type": "application/json"}

        def read(self):
            return b'{"jsonrpc":"2.0","id":1,"error":"boom"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda req, timeout=60: R())
    with pytest.raises(cli.ConnectorError, match="boom"):
        cli._post("http://x/mcp", {})
