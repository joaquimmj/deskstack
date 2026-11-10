# Examples

Five deliverables built with deskstack's real tools, with every review report. Download a folder and open
`model.xlsx` next to its reports.

| Folder | What it is | Result |
|---|---|---|
| [apple-dcf](apple-dcf/) | Apple quick DCF, FY2024-FY2026 history | 14 of 14 filed figures tie to the 10-K. No model finding. Ready for sign-off |
| [us-tech-comps](us-tech-comps/) | Apple against Microsoft, Alphabet, Amazon, Meta and Nvidia, latest twelve months | 24 of 24 figures tie to the filings. Market caps are empty: see below |
| [heineken-dcf](heineken-dcf/) | Heineken N.V. quick DCF, from its ESEF annual reports, in euros | 14 of 14 figures tie to the reports. `/vp-review` flags the terminal value at 82% of EV |
| [apple-dcf-typo](apple-dcf-typo/) | The Apple DCF with FY2025 revenue keyed with two digits swapped: the demo GIF's model | `/associate` flags it: "two adjacent digits look swapped" |
| [errors-caught](errors-caught/) | A Microsoft DCF with four errors from the benchmark typed in on purpose | All four caught: 6 mismatches in the tie-out, a placeholder rule in the review, a failed citation check |

Each folder holds:

| File | Made by | What it is |
|---|---|---|
| `model.xlsx` | `/analyst`'s builder | The workbook: blue inputs, a Sources sheet citing every typed number, a Cover with the disclaimer |
| `associate.md` | `/associate` | Every typed number tied to the filing with `verify_value` |
| `vp-review.md` | `/vp-review` | The checker's 21 rules on the workbook |
| `compliance.md` | `/compliance` | Disclaimer, citations, hygiene |
| `sign-off.md` | `/sign-off` | The one-page summary you approve, or not |
| `spec.json`, `batches.json`, `*.json` | | The build spec, the tie-out batches and each report as JSON |
| `calls/` | the live connector | What the tools returned, with the date |

The reports are the deterministic part of each role. In Claude, `/vp-review` also compares the assumptions with filed
history, and `/md-redteam` writes a memo; those need a conversation, so they aren't here.

## The planted errors

[errors-caught](errors-caught/) is Microsoft's real data with four errors that Claude made in the
[benchmark](../bench/README.md), typed in on purpose. Its Cover sheet says so.

| Error | In the benchmark | In this model | Caught by |
|---|---|---|---|
| Last twelve months a quarter late | 15 comps figures: an aggregator's "TTM" after a new 10-Q | LTM revenue and operating income typed as the year to June 2026 | `/associate`: mismatch; the hint says the value matches FY2026, not the LTM to 2026-09-30 |
| Share count derived from EPS | Boeing, Pfizer, GE | Diluted shares = LTM net income / FY2026 EPS: 7,946 million against 7,453 filed | `/associate`: mismatch |
| Placeholder left at 0 | Cigna, CVS, Humana | FY2025 D&A = 0, labelled "NOT FOUND - placeholder 0" | `/associate`: mismatch; `/vp-review`: DS016; `/compliance`: C04 |
| Two lines that cancel out | (a known spreadsheet error) | FY2026 operating income 2,000 too low, D&A 2,000 too high, so EBITDA still ties | `/associate`: both lines mismatch |

The sign-off page lists 7 blocking items, and nothing can be exported until they are fixed.

## How they are made

1. `server/scripts/examples.ts data` calls the live connector with the requests in [plan.json](plan.json) and saves
   each response in `calls/`, with the date. The current set was recorded on 2026-11-10.
2. [build.py](build.py) turns the responses into a spec, builds the workbook with the plugin's builder, and extracts
   the tie-out batches.
3. `server/scripts/examples.ts verify` sends those batches to the live `verify_value` and saves the answers.
4. `build.py` writes every report with the plugin's own scripts.

[refresh.sh](refresh.sh) runs all four steps. A test rebuilds every example from `calls/` and fails if a committed
file differs.

**Assumptions.** Growth, margins, tax rate and WACC are an analyst's choices, not data. Here they follow fixed rules so
the examples can be rebuilt, and each source line says which rule. For example, growth starts at the last year's
growth, capped at 15%, and fades in a straight line to terminal growth. WACC uses the Treasury or ECB 10-year rate,
Damodaran's industry beta and weights, and his equity risk premium. They are not recommendations.

**Market caps.** deskstack has no share prices, so the comps leave market cap empty and show EV and the multiples as
"n.a.". In Claude, `/comps` asks you for prices. A price is never estimated.

**Live behaviour.** The tie-out answers are what the live connector returned on 2026-11-10. A newer `verify_value`
says *Stale* for a twelve-month figure a quarter late. It isn't deployed yet, so these reports show the *Period* hint
instead. Re-run `refresh.sh` after the next deploy.

Draft deliverables for illustration. Not investment advice.
