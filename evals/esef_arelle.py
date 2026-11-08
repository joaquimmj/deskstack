#!/usr/bin/env python3
"""Record the ESEF golden answers as Arelle reads them from the published reports (evals/fixtures/esef-arelle.json).

The golden set's ESEF answers must not come from deskstack's own extractor (server/src/esef/extract.ts). This
script loads each report package from filings.xbrl.org with Arelle (Apache-2.0) and records the facts the golden
questions ask for. build_golden.py reads them from here.

  pip install -r evals/differential/requirements.txt
  python3 evals/esef_arelle.py            # network: filings.xbrl.org
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "differential"))
sys.path.insert(0, str(HERE))

from build_golden import ESEF, INSTANT  # noqa: E402
from differential import ArelleOracle  # noqa: E402

OUT = HERE / "fixtures" / "esef-arelle.json"


def main() -> int:
    import arelle

    o = ArelleOracle()
    facts = []
    for _lei, _name, _label, report, start, end, items, _tags in ESEF:
        for metric, concept in items:
            s = None if metric in INSTANT else start
            facts.append({"report": report, "concept": f"ifrs-full:{concept}", "start": s, "end": end,
                          "value": o.value(report, f"ifrs-full:{concept}", s, end)})
    version = getattr(getattr(arelle, "Version", None), "__version__", None) or "unknown"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"_note": "Written by evals/esef_arelle.py: values Arelle reads from each report's inline XBRL "
                               "(filings.xbrl.org report packages). Do not edit by hand.", "parser": f"Arelle {version}",
                               "facts": facts}, indent=1) + "\n")
    print(f"Wrote {OUT} ({len(facts)} facts)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
