"""deskstack-check: check any spreadsheet model, built by an AI or a person.

  deskstack-check model.xlsx [more.xlsx ...]      offline model checks, readable report
  deskstack-check model.xlsx --verify             also tie every typed figure to the filings (deskstack connector)
  deskstack-check model.xlsx --markdown | --json  other formats

Options:
  --verify             call verify_value on the deskstack connector (sends the typed figures, nothing else)
  --company ID         ticker, CIK or LEI, when the workbook doesn't name its company as "Name (TICKER)"
  --connector URL      another deskstack server, e.g. your self-hosted copy (default: the public one)
  --ignore DS001,DS010 leave out rules a team accepts on purpose (the report says which)
  --fail-on LEVEL      blocker (default), major, minor or never: the exit code is 1 at or above it.
                       A figure that doesn't tie to the filing counts as a blocker.

Exit codes: 0 pass, 1 findings at or above --fail-on, 2 bad input or the connector failed.
The other tools (build, extract, tieout, sensitivity, compliance, signoff) run as: deskstack-check <tool> ...
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from . import __version__, check, to_markdown
from .rules import RULE_INFO, SEVERITY_ORDER

PUBLIC_CONNECTOR = "https://deskstack.deskstack-server.workers.dev/mcp"
LEVELS = ("blocker", "major", "minor", "never")
TIE_BAD = ("mismatch", "not_found", "ambiguous", "not_checked")


class ConnectorError(RuntimeError):
    pass


# ---- the connector: a minimal MCP client over HTTP (standard library only) ------------------

def _post(url: str, payload: dict, timeout: float = 60) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
                 "User-Agent": f"deskstack-check/{__version__}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "replace")
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        raise ConnectorError(f"{url} answered HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise ConnectorError(f"could not reach {url}: {getattr(e, 'reason', e)}") from None
    if "text/event-stream" in ctype:
        data = [line[5:].strip() for line in body.splitlines() if line.startswith("data:")]
        body = data[-1] if data else ""
    try:
        msg = json.loads(body)
    except ValueError:
        raise ConnectorError(f"{url} did not answer with MCP JSON") from None
    if "error" in msg:
        raise ConnectorError(f"{url}: {msg['error'].get('message', msg['error'])}")
    return msg.get("result", {})


def call_tool(url: str, name: str, arguments: dict) -> dict:
    """initialize, then tools/call. Returns the tool's JSON; a tool error (rate limit, daily cap) is raised as text."""
    _post(url, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                           "clientInfo": {"name": "deskstack-check", "version": __version__}}})
    res = _post(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    text = "\n".join(c.get("text", "") for c in res.get("content", []))
    if res.get("isError"):
        raise ConnectorError(text or f"{name} failed")
    try:
        return json.loads(text)
    except ValueError:
        raise ConnectorError(f"{name} returned no JSON: {text[:200]}") from None


def verify(path: str, url: str, company: str | None = None) -> dict:
    from .tieout import extract, report

    ex = extract(path)
    batches = ex["verify_batches"]
    if not batches:
        return {"report": "tieout", "file": path, "counts": {}, "rows": [], "note": "No typed figure that a filing reports was found."}
    for b in batches:
        if company:
            b["company"] = company
        if not b.get("company"):
            raise ConnectorError("the workbook doesn't name its company as 'Name (TICKER)': pass --company TICKER (or a CIK or LEI)")
    results = [call_tool(url, "verify_value", b) for b in batches]
    rep = report(path, results)
    rep["connector"] = url
    rep["companies"] = sorted({b["company"] for b in batches})
    return rep


# ---- output ---------------------------------------------------------------------------------

def _style(on: bool):
    def s(code: str, text: str) -> str:
        return f"\x1b[{code}m{text}\x1b[0m" if on else text
    return s


SEV_STYLE = {"blocker": "1;31", "major": "33", "minor": "36", "info": "2"}


def to_text(rep: dict, tie: dict | None, offline_hint: int, color: bool) -> str:
    s = _style(color)
    c = rep["counts"]
    out = [s("1", f"{rep['file']}") + s("2", f"  ({rep['checker']}, sha256 {rep['model_sha256'][:12]})")]
    out.append(f"Model checks: {c['blocker']} blocker, {c['major']} major, {c['minor']} minor, {c['info']} info")
    for f in rep["findings"]:
        _, fix = RULE_INFO.get(f["rule"], ("", ""))
        out.append(f"  {s(SEV_STYLE[f['severity']], f['severity'].upper().ljust(7))} {f['rule']}  {f['ref']}  {f['message']}")
        if fix and f["severity"] != "info":
            out.append(s("2", f"           Fix: {fix}"))
    if tie is not None:
        k = tie.get("counts", {})
        filed = sum(k.get(x, 0) for x in ("match",) + TIE_BAD)
        bad = sum(k.get(x, 0) for x in TIE_BAD)
        who = ", ".join(tie.get("companies", [])) or "-"
        line = f"Tie-out to the filings ({who}): {k.get('match', 0)} of {filed} match"
        out.append(line + (f", {s('1;31', f'{bad} do not')}" if bad else ""))
        for r in tie["rows"]:
            if r["status"] in TIE_BAD:
                filed_v = r.get("filed_value")
                fv = f"filed {filed_v:,.0f}" if isinstance(filed_v, (int, float)) else "no filed value"
                v = r.get("value")
                vv = f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)
                out.append(f"  {s('1;31', r['status'].upper().ljust(9))} {r['ref']}  {r.get('label', '')} {r.get('period', '')}  {vv}  {fv}")
                for h in r.get("hints", [])[:2]:
                    out.append(s("2", f"           {h}"))
        if tie.get("note"):
            out.append(f"  {tie['note']}")
    if rep.get("ignored"):
        out.append(s("2", f"Ignored: {', '.join(rep['ignored'])}"))
    if tie is None and offline_hint:
        out.append(s("2", f"Tie-out: {offline_hint} typed figure(s) could be checked against the filings. Add --verify."))
    return "\n".join(out)


def fails(rep: dict, tie: dict | None, level: str) -> bool:
    if level == "never":
        return False
    worst = SEVERITY_ORDER[level]
    if any(SEVERITY_ORDER[f["severity"]] <= worst for f in rep["findings"]):
        return True
    return bool(tie) and any(tie.get("counts", {}).get(x, 0) for x in TIE_BAD)


# ---- entry point ----------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    from .__main__ import COMMANDS, main as tools_main

    if argv and argv[0] in COMMANDS and argv[0] != "check":
        return tools_main(argv)
    if "--audit" in argv:  # companion mode: merge an audit-xls table, as the /vp-review skill does
        return tools_main(argv if argv[0] == "check" else ["check", *argv])
    if argv and argv[0] == "check":
        argv = argv[1:]
    if not argv or "-h" in argv or "--help" in argv:
        print(__doc__.strip())
        return 0 if argv else 2
    if "--version" in argv:
        print(f"deskstack-check {__version__}")
        return 0
    files, opts, flags = [], {}, set()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--company", "--connector", "--fail-on", "--ignore"):
            if i + 1 >= len(argv):
                print(f"Error: {a} needs a value.", file=sys.stderr)
                return 2
            opts[a] = argv[i + 1]
            i += 2
            continue
        if a.startswith("--"):
            if a not in ("--verify", "--json", "--markdown", "--no-color"):
                print(f"Error: unknown option {a} (see --help).", file=sys.stderr)
                return 2
            flags.add(a)
        else:
            files.append(a)
        i += 1
    ignored = sorted({x.strip().upper() for x in opts.get("--ignore", "").split(",") if x.strip()})
    unknown = [x for x in ignored if x not in RULE_INFO or x == "DS000"]
    if unknown:
        print(f"Error: --ignore: no rule {', '.join(unknown)} (the rules are listed in checker/README.md).", file=sys.stderr)
        return 2
    level = opts.get("--fail-on", "blocker")
    if level not in LEVELS:
        print(f"Error: --fail-on must be one of {', '.join(LEVELS)}.", file=sys.stderr)
        return 2
    if not files:
        print("Error: give at least one .xlsx file.", file=sys.stderr)
        return 2
    url = opts.get("--connector", PUBLIC_CONNECTOR)
    color = sys.stdout.isatty() and "NO_COLOR" not in os.environ and "--no-color" not in flags
    worst = 0
    results = []
    for n, path in enumerate(files):
        try:
            rep = check(path)
            if ignored:
                rep["findings"] = [f for f in rep["findings"] if f["rule"] not in ignored]
                rep["counts"] = {sv: sum(1 for f in rep["findings"] if f["severity"] == sv) for sv in SEVERITY_ORDER}
                rep["ignored"] = ignored
            tie, hint = None, 0
            if "--verify" in flags:
                tie = verify(path, url, opts.get("--company"))
            else:
                from .tieout import extract

                try:
                    hint = len(extract(path)["filed"])
                except Exception:  # noqa: BLE001 - the hint is optional
                    hint = 0
        except ConnectorError as e:
            print(f"Error: {path}: the connector failed: {e}", file=sys.stderr)
            worst = max(worst, 2)
            continue
        except (FileNotFoundError, IsADirectoryError, ValueError, OSError) as e:
            print(f"Error: {path}: {e}", file=sys.stderr)
            worst = max(worst, 2)
            continue
        bad = fails(rep, tie, level)
        worst = max(worst, 1 if bad else 0)
        if "--json" in flags:
            results.append({"model_check": rep, "tieout": tie, "fail_on": level, "ignored": ignored, "passed": not bad})
            continue
        if n:
            print()
        if "--markdown" in flags:
            from .tieout import to_markdown as tie_md

            print(to_markdown(rep))
            if ignored:
                print(f"\nIgnored: {', '.join(ignored)}.")
            if tie is not None:
                print()
                print(tie_md(tie))
        else:
            print(to_text(rep, tie, hint, color))
        print(("FAIL" if bad else "PASS") + f" (fails on {level})")
    if "--json" in flags:
        print(json.dumps(results[0] if len(results) == 1 and len(files) == 1 else results, indent=1, default=str))
    return worst


if __name__ == "__main__":
    sys.exit(main())
