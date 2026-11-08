# deskstack_check

Deterministic checks for financial models in `.xlsx`, used by the `/vp-review` skill. Built on
[openpyxl](https://openpyxl.readthedocs.io) (MIT). Only public, widely known modeling practices are
checked. It reports findings and never grades a person.

```bash
python -m deskstack_check model.xlsx                     # model check, markdown (audit-xls table + Rule, Found by)
python -m deskstack_check model.xlsx --json              # machine-readable
python -m deskstack_check check model.xlsx --audit a.md  # merge an audit-xls findings table (companion mode)
python -m deskstack_check extract model.xlsx             # typed numbers + draft verify_value batches (JSON)
python -m deskstack_check tieout model.xlsx results.json # tie-out report from verify_value results
python -m deskstack_check build spec.json out.xlsx       # build a cited DCF or comps workbook
```

The plugin's skills run vendored copies of this package (`python3 plugins/sync_vendor.py` refreshes them; a test
fails when they are stale).

| Rule | Severity | Check |
|---|---|---|
| DS001 | major | Hardcoded number inside a formula (`=B5*1.05`) |
| DS002 | major | Formula breaks its row's pattern |
| DS003 | minor | Inputs not blue, or formulas formatted as inputs |
| DS004 | major | Typed number with no row in the Sources sheet |
| DS005 | blocker | Link to another workbook |
| DS006 | blocker | `#REF!`, `#DIV/0!`, `#N/A`… |
| DS007 | blocker / major | Circular reference (major if iterative calculation is on) |
| DS008 | blocker | Balance sheet doesn't balance |
| DS009 | major | Ending cash doesn't tie to balance-sheet cash |
| DS010 | major | Terminal value > 75% of enterprise value |
| DS011 | major | WACC − terminal growth < 2 points |
| DS012 | major | Terminal growth above a ~4% long-run nominal GDP proxy |
| DS013 | major | A sheet reads another declared in different units without converting |
| DS014 | major | Capex or D&A changes sign across periods |
| DS015 | major / minor | Discount factors don't match the stated mid-year / end-of-year convention |

Value-based rules (DS008–DS015) read the results Excel cached when it last saved the file. A file
written by a script and never opened in Excel has none, and the report says so (DS000, info).

Tests: `python -m pytest tests`.
- Each rule fires on a planted error in a synthetic model, and the clean model raises nothing.
- 11 Apple demo DCFs (`tests/demo_models.py`) each plant one error.
  - Model errors must be caught by the checker.
  - Data errors must be caught by the tie-out: `server/test/demo.test.ts` runs their extracted batches through
    `verify_value`.
