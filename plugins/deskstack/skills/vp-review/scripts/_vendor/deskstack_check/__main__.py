"""CLI.

  python -m deskstack_check MODEL.xlsx [--json] [--audit FINDINGS.md]   model check (default)
  python -m deskstack_check check MODEL.xlsx [--json] [--audit FINDINGS.md]
  python -m deskstack_check extract MODEL.xlsx                           typed numbers + verify_value drafts (JSON)
  python -m deskstack_check tieout MODEL.xlsx RESULTS.json [--json]      tie-out report from verify_value results
  python -m deskstack_check build SPEC.json OUT.xlsx                     build a DCF or comps workbook

Exit code 1 when the model check finds a blocker or the tie-out finds a mismatch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import check, to_markdown


def _opt(args: list[str], name: str) -> str | None:
    if name in args:
        i = args.index(name)
        if i + 1 < len(args):
            return args[i + 1]
    return None


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    audit = _opt(argv, "--audit")
    args = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--audit")]
    if not args:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = args[0] if args[0] in ("check", "extract", "tieout", "build") else "check"
    rest = args[1:] if args[0] == cmd else args
    if cmd == "check":
        report = check(rest[0])
        merged = None
        if audit:
            from .companion import merge, parse_audit_table

            theirs = parse_audit_table(Path(audit).read_text())
            if not theirs["findings"]:
                why = "no findings table with the audit-xls header" if not theirs["table_found"] else f"{theirs['skipped']} row(s) with an unknown severity"
                print(f"Could not read any finding from {audit} ({why}). Pass the audit-xls report as written.", file=sys.stderr)
                return 2
            merged = merge(report, theirs)
            report["companion"] = {"summary": theirs["summary"], "merged": merged}
        print(json.dumps(report, indent=1) if as_json else to_markdown(report, merged))
        rows = merged if merged is not None else report["findings"]
        return 1 if any(f["severity"] == "blocker" for f in rows) else 0
    if cmd == "extract":
        from .tieout import extract

        print(json.dumps(extract(rest[0]), indent=1, default=str))
        return 0
    if cmd == "tieout":
        from .tieout import report as tie_report, to_markdown as tie_md

        from .tieout import ResultsError

        try:
            rep = tie_report(rest[0], json.loads(Path(rest[1]).read_text()))
        except ResultsError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(json.dumps(rep, indent=1, default=str) if as_json else tie_md(rep))
        return 1 if rep["counts"].get("mismatch") else 0
    if cmd == "build":
        from .build import SpecError, build

        try:
            out = build(rest[0], rest[1])
        except SpecError as e:
            print(f"Spec error: {e}", file=sys.stderr)
            return 2
        print(f"Wrote {out}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
