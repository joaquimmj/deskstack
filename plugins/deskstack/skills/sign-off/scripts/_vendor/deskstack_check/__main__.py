"""CLI.

  python -m deskstack_check MODEL.xlsx [--json] [--audit FINDINGS.md]   model check (default)
  python -m deskstack_check check MODEL.xlsx [--json] [--audit FINDINGS.md]
  python -m deskstack_check extract MODEL.xlsx                           typed numbers + verify_value drafts (JSON)
  python -m deskstack_check tieout MODEL.xlsx RESULTS.json [--json]      tie-out report from verify_value results
  python -m deskstack_check build SPEC.json OUT.xlsx                     build a DCF or comps workbook
  python -m deskstack_check hash MODEL.xlsx                              the file's SHA-256 (reports carry it)
  python -m deskstack_check sensitivity MODEL.xlsx [--price P] [--json]  shocks, WACC x g grid, implied inputs
  python -m deskstack_check compliance MODEL.xlsx [--memo MEMO.md] [--json]
  python -m deskstack_check signoff MODEL.xlsx [--tieout T.json] [--review R.json] [--compliance C.json]
        [--redteam M.md] [--json]                                        summary; exit 3 = awaiting approval
  python -m deskstack_check signoff MODEL.xlsx ... --approve "USER'S WORDS" --by NAME --token TOKEN --out FINAL.xlsx
        [--accept-open "REASON"] [--accept-missing tieout,review]       signed copy (refused without approval)

Exit codes: 0 ok, 1 a blocker / mismatch / compliance failure, 2 bad input or refused, 3 awaiting approval.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import check, to_markdown

VALUE_OPTS = {"--audit", "--price", "--memo", "--tieout", "--review", "--compliance", "--redteam", "--approve", "--by", "--out",
              "--accept-open", "--accept-missing", "--token"}
FLAGS = {"--json"}


class UsageError(ValueError):
    pass
COMMANDS = ("check", "extract", "tieout", "build", "sensitivity", "compliance", "signoff", "hash")


def _parse(argv: list[str]) -> tuple[list[str], dict[str, str], set[str]]:
    pos, opts, flags = [], {}, set()
    i = 0
    while i < len(argv):
        a = argv[i]
        if a.startswith("--") and "=" in a and a.split("=", 1)[0] in VALUE_OPTS:
            k, v = a.split("=", 1)
            opts[k] = v
            i += 1
            continue
        if a in VALUE_OPTS:
            if i + 1 >= len(argv):
                raise UsageError(f"{a} needs a value")
            opts[a] = argv[i + 1]
            i += 2
            continue
        if a.startswith("--"):
            if a not in FLAGS:
                raise UsageError(f"Unknown option {a}")
            flags.add(a)
        else:
            pos.append(a)
        i += 1
    return pos, opts, flags


def main(argv: list[str]) -> int:
    try:
        return _main(argv)
    except (UsageError, FileNotFoundError, IsADirectoryError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2


def _main(argv: list[str]) -> int:
    pos, opts, flags = _parse(argv)
    as_json = "--json" in flags
    if not pos:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = pos[0] if pos[0] in COMMANDS else "check"
    rest = pos[1:] if pos[0] == cmd else pos
    if not rest:
        print(__doc__, file=sys.stderr)
        return 2
    out = lambda obj, md: print(json.dumps(obj, indent=1, default=str) if as_json else md(obj))  # noqa: E731

    if cmd == "check":
        report = check(rest[0])
        merged = None
        if "--audit" in opts:
            from .companion import merge, parse_audit_table

            theirs = parse_audit_table(Path(opts["--audit"]).read_text())
            if not theirs["findings"]:
                why = "no findings table with the audit-xls header" if not theirs["table_found"] else f"{theirs['skipped']} row(s) with an unknown severity"
                print(f"Could not read any finding from {opts['--audit']} ({why}). Pass the audit-xls report as written.", file=sys.stderr)
                return 2
            merged = merge(report, theirs)
            report["companion"] = {"summary": theirs["summary"], "merged": merged}
        print(json.dumps(report, indent=1) if as_json else to_markdown(report, merged))
        rows = merged if merged is not None else report["findings"]
        return 1 if any(f["severity"] == "blocker" for f in rows) else 0
    if cmd == "hash":
        from .model import file_sha256

        print(file_sha256(rest[0]))
        return 0
    if cmd == "extract":
        from .tieout import extract

        print(json.dumps(extract(rest[0]), indent=1, default=str))
        return 0
    if cmd == "tieout":
        from .tieout import ResultsError, report as tie_report, to_markdown as tie_md

        if len(rest) < 2:
            print("usage: tieout MODEL.xlsx RESULTS.json", file=sys.stderr)
            return 2
        try:
            rep = tie_report(rest[0], json.loads(Path(rest[1]).read_text()))
        except ResultsError as e:
            print(str(e), file=sys.stderr)
            return 2
        out(rep, tie_md)
        return 1 if rep["counts"].get("mismatch") else 0
    if cmd == "build":
        from .build import SpecError, build

        if len(rest) < 2:
            print("usage: build SPEC.json OUT.xlsx", file=sys.stderr)
            return 2
        try:
            path = build(rest[0], rest[1])
        except SpecError as e:
            print(f"Spec error: {e}", file=sys.stderr)
            return 2
        print(f"Wrote {path}")
        return 0
    if cmd == "sensitivity":
        from .sensitivity import NoLayout, sensitivity, to_markdown as sens_md

        try:
            price = None
            if "--price" in opts:
                try:
                    price = float(opts["--price"].replace(",", "").lstrip("$€£ "))
                except ValueError:
                    raise UsageError(f"--price must be a number, got {opts['--price']!r}") from None
            r = sensitivity(rest[0], price)
        except NoLayout as e:
            print(str(e), file=sys.stderr)
            return 2
        out(r, sens_md)
        return 0
    if cmd == "compliance":
        from .compliance import check as comp_check, to_markdown as comp_md

        r = comp_check(rest[0], opts.get("--memo"))
        out(r, comp_md)
        return 1 if r["result"] == "fail" else 0
    if cmd == "signoff":
        from .signoff import GateError, export, summary, to_markdown as so_md

        reports = {"tieout": opts.get("--tieout"), "review": opts.get("--review"), "compliance": opts.get("--compliance"),
                   "redteam": opts.get("--redteam")}
        if "--approve" not in opts:
            out(summary(rest[0], **reports), so_md)
            return 3
        missing_opts = [o for o in ("--out", "--by", "--token") if o not in opts]
        if missing_opts:
            print(f"Export needs {', '.join(missing_opts)} (the token is printed with the summary).", file=sys.stderr)
            return 2
        acc = [x.strip() for x in opts.get("--accept-missing", "").split(",") if x.strip()]
        try:
            rec = export(rest[0], opts["--out"], reports, opts["--by"], opts["--approve"], opts["--token"],
                         opts.get("--accept-open"), acc)
        except GateError as e:
            print(f"Refused: {e}", file=sys.stderr)
            return 2
        print(f"Signed copy: {rec['output']} (record: {rec['output']}.signoff.json)" + (f"\n{rec['note']}" if rec.get("note") else ""))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
