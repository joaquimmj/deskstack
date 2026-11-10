# deskstack-check

Checks any spreadsheet financial model (`.xlsx`), whether an AI or a person built it.

- **Offline:** 21 deterministic model checks, built on [openpyxl](https://openpyxl.readthedocs.io) (MIT). Only
  public, widely known modelling practices are checked. It reports findings and never grades a person.
- **With `--verify`:** every typed figure is tied to the SEC or ESEF filing through the free
  [deskstack](https://github.com/joaquimmj/deskstack) connector. Only those figures are sent.

```bash
pipx run deskstack-check model.xlsx              # readable report
pipx run deskstack-check model.xlsx --verify     # also tie figures to the filings
pipx run deskstack-check model.xlsx --markdown   # or --json
```

Options:

- `--company ID`: a ticker, CIK or LEI, when the workbook doesn't name its company as "Name (TICKER)".
- `--connector URL`: a self-hosted deskstack server.
- `--ignore DS010,DS017`: leave out rules a team accepts on purpose; the report says which were ignored.
- `--fail-on LEVEL`: `blocker` (default), `major`, `minor` or `never`. A figure that doesn't tie to the filing counts
  as a blocker.

The exit code is 0 for a pass, 1 for a fail, and 2 when a file can't be read or the connector fails. A GitHub Action
runs the same checks in a repository ([action.yml](https://github.com/joaquimmj/deskstack/blob/main/action.yml)).

The deskstack plugin's roles use the same package:

```bash
deskstack-check model.xlsx                               # model check (also: python -m deskstack_check model.xlsx)
deskstack-check check model.xlsx --audit a.md            # merge an audit-xls findings table (companion mode)
deskstack-check extract model.xlsx                       # typed numbers + draft verify_value batches (JSON)
deskstack-check tieout model.xlsx results.json           # tie-out report from verify_value results
deskstack-check build spec.json out.xlsx                 # build a cited DCF or comps workbook
deskstack-check sensitivity model.xlsx --price 230       # tornado, WACC x g grid, implied inputs (/md-redteam)
deskstack-check compliance model.xlsx --memo memo.md     # pass/fail hygiene list (/compliance)
deskstack-check signoff model.xlsx --tieout t.json --review r.json --compliance c.json   # summary, exit 3
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
| DS016 | major / minor | A typed number whose label or source says it wasn't found: a placeholder 0, "NOT FOUND", "TBD" (minor for "estimate" with no filing cited) |
| DS017 | minor | Four or more typed figures on a row that grow at one exact rate, or are all round thousands |
| DS018 | major | A non-zero line labeled as a plug or balancing item |
| DS019 | major / minor | Interest typed or not computed from debt and cash (major); debt flat with no repayment schedule (minor) |
| DS020 | minor | A share count flat across periods while the model has buybacks |
| DS021 | major | A rate typed as a whole number (5 for 5%): shown as 500% in a percent cell, or out of line with the model's other rates, which are decimals |

Value-based rules (DS008–DS015) read the results Excel cached when it last saved the file. A file
written by a script and never opened in Excel has none, and the report says so (DS000, info).

Tests: `python -m pytest tests`.
- Each rule fires on a planted error in a synthetic model, and the clean model raises nothing.
- 11 Apple demo DCFs (`tests/demo_models.py`) each plant one error.
  - Model errors must be caught by the checker.
  - Data errors must be caught by the tie-out: `server/test/demo.test.ts` runs their extracted batches through
    `verify_value`.
