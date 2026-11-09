# Pilot, 2026-11-08: what the numbers mean

5 companies (Apple, Coca-Cola, Caterpillar, TotalEnergies, Inditex) × 2 tasks (DCF, comps) × 3 arms, Claude Sonnet 5.5,
effort medium. 30 runs, $6.68 of API credits. Raw transcripts, submissions and scores are in `runs/` and `work/`;
the automatic table is in `summary.md`.

**Short version: this pilot does not support a headline accuracy number.** `summary.md` shows arm A (web search only) at
19.4% of filed figures "wrong vs filing" and arms B and C at 0%. We read every one of arm A's 13 mismatches by hand.
Only one is a plain error by the model. Four come from gaps in deskstack's own data, and most of the rest are
definition differences that the scorer counts as errors. We fixed what was ours to fix, and we will fix the scoring
before any full run.

## The 13 arm-A mismatches, one by one

| Company | Figure | Arm A | deskstack (scorer) | What it is |
|---|---|---|---|---|
| Coca-Cola | net debt FY2025 | 31,620 | 35,166 | **deskstack bug, fixed.** KO tags its short-term investments as `OtherShortTermInvestments` ($3.6B), which deskstack didn't read. Fixed: 31,564. Arm A was right. |
| Caterpillar | net debt FY2025 | 33,344 | 26,230 | **deskstack bug, fixed.** CAT tags "long-term debt due within one year" ($7.1B) with a company extension, absent from the SEC's companyfacts data. deskstack now uses the 12-month maturity figure when no current line is tagged: 33,350. Arm A was right. |
| Inditex | net debt FY2025 | -10,958 | -5,274 | **deskstack gap.** deskstack reads no short-term investments for IFRS filers (no standard IFRS concept), so Inditex's current financial investments are missing. Arm A is probably right. Open. |
| TotalEnergies | net debt FY2025 | 20,215 | 34,831 | **Same gap, plus a definition difference.** TotalEnergies' current financial assets are missing in deskstack; arm A followed the company's own net debt. Not settled. |
| Apple | net debt FY2025 | -33,763 | 43,960 | **Definition not followed.** Arm A also subtracted non-current marketable securities ($77.7B). That's a common view of Apple, but not the definition given in the prompt (cash + short-term investments). |
| TotalEnergies | revenue FY2023-25 (3) | 218,945 … | 237,128 … | **Definition.** Arm A used "revenues from sales" (excluding excise taxes, about $18-19B a year); deskstack's IFRS `Revenue` is "sales" including them. Arm A's line is defensible. |
| Caterpillar | capex FY2023-25 (3) | 3,092 … | 1,597 … | **Definition.** Arm A added "expenditures for equipment leased to others" to PP&E capex. Defensible either way. |
| Keurig Dr Pepper | EBITDA FY2025 | 4,328 | 4,030 | **deskstack gap.** KDP tags depreciation and amortization separately; deskstack's D&A took depreciation only (455), and arm A also counted amortization. Arm A is closer to a standard EBITDA. Open. |
| Monster | EBITDA FY2025 | 2,447.8 | 2,533.8 | **Model error.** Arm A took D&A of 28.4 from a segment note instead of the cash-flow figure (114.4). |

Arms B and C read the same deskstack data the scorer uses, so their 0% is partly by construction (see the notes in
`summary.md`). The pilot shows that this design hides deskstack's own data errors: when deskstack is wrong, B and C
are scored as right.

## What the pilot does show

- **Reliability.** Arm A finished 6 of 10 models: all four of its unfinished runs are comps tables stopped by the
  per-run cost cap ($1.50) after 2-3 requests, because the worst case of one more web-search request (its whole context
  plus the maximum output) would have crossed it. Arm B finished 8 of 10 (two runs ended without a submission). Arm C finished 10 of 10.
- **Cost and time.** Average per model: A $0.38 and 99 s; B $0.13 and 32 s; C $0.16 and 47 s. Arm A uses about 3×
  more tokens because it searches and reads pages.
- **Sourcing.** Arm A's citations are web pages and filings it found itself, sometimes with admissions such as
  "rounded; exact figure not retrieved" or "value recalled". B and C cite accession numbers. B and C have more typed
  numbers without a source (12-14% vs 7%), mostly market capitalizations: deskstack provides no prices.

## What changed after the pilot

Data (deskstack connector):
- `OtherShortTermInvestments` counts as short-term investments (Coca-Cola: net debt 35.2B -> 31.6B).
- With no current-debt line tagged, the 12-month maturity of long-term debt
  (`LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths`) stands in for the current portion, next to a
  non-current line only, and the formula says so (Caterpillar: 26.2B -> 33.4B).
- IFRS short-term deposits (`ShorttermDepositsNotClassifiedAsCashEquivalents`) count as short-term investments
  (Inditex: -5.3B -> -11.0B, arm A's figure). TotalEnergies only tags `OtherCurrentFinancialAssets`, which mixes
  derivatives and receivables, so it stays out.
- EBITDA adds intangible amortization when D&A is depreciation alone (Keurig Dr Pepper: 4,030 -> 4,168).
- ExxonMobil: XOM moved to ExxonMobil Holdings Corp (new CIK, no 10-K yet) in July 2026. The connector now falls back
  to the predecessor's filings for this known reorganization and says so in a `predecessor_note`.

Scoring (`server/bench/score.ts`, `filing-facts.ts`):
- EBITDA and net debt mismatches are reported as **other definition**, not wrong: definitions vary between analysts.
  The cost: a computed figure that is plainly wrong (Monster's EBITDA, above) is no longer counted as wrong either.
- A reported line that equals another line of the same filing, or two lines added, to the precision written, is
  **other line of the filing**. Facts come from the filing itself (SEC companyfacts, or the ESEF report with its
  extension concepts), not from deskstack.

## Re-scored with the new scorer

`rescored/` holds the same 30 submissions scored again (no API calls). Arm A: **0 wrong** of 67 filed figures;
6 other lines (TotalEnergies revenue matched `tot:RevenueFromContractsWithCustomersExcludingExciseTax`; Caterpillar
capex matched `us-gaap:SegmentExpenditureAdditionToLongLivedAssets`, capex including leased equipment) and 7 other
definitions (net debt and EBITDA). Arms B and C: 0 wrong, as before. (Re-scored after the data fixes, B and C show
other definitions too: their submissions used deskstack's net debt from before the fixes.)

On this pilot, Claude with web search alone got every reported line it submitted right. Where it fell short was
finishing (6 of 10 models), cost (2-3x) and time (2-3x), not accuracy.

## Before a full run

- The per-run cost cap: pass `--max-run-cost 3` so arm A's comps can finish (the overall budget stays the hard limit).
- Scope: the measured cost per company-task is about $0.89 ($0.49 DCF, $1.29 comps), so by the rule fixed before the
  pilot (`bench/COST_ESTIMATE.md`) the main run is 50 companies x DCF x 3 arms, about $25.
