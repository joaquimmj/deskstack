import json
import sys

from . import check, to_markdown

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("usage: python -m deskstack_check model.xlsx [--json]", file=sys.stderr)
        sys.exit(2)
    report = check(args[0])
    print(json.dumps(report, indent=1) if "--json" in sys.argv else to_markdown(report))
    sys.exit(1 if report["counts"]["blocker"] else 0)
