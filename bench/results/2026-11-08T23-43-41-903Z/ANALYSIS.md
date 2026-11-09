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

- **Reliability.** Arm A finished 6 of 10 models: all four of its unfinished runs are comps tables that hit the per-run request
  cap before submitting. Arm B finished 8 of 10 (two runs ended without a submission). Arm C finished 10 of 10.
- **Cost and time.** Average per model: A $0.38 and 99 s; B $0.13 and 32 s; C $0.16 and 47 s. Arm A uses about 3×
  more tokens because it searches and reads pages.
- **Sourcing.** Arm A's citations are web pages and filings it found itself, sometimes with admissions such as
  "rounded; exact figure not retrieved" or "value recalled". B and C cite accession numbers. B and C have more typed
  numbers without a source (12-14% vs 7%), mostly market capitalizations: deskstack provides no prices.

## Fixed in this change

- `OtherShortTermInvestments` now counts as short-term investments (Coca-Cola and other filers).
- With no current-debt line tagged, the 12-month maturity of long-term debt
  (`LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths`) stands in for the current portion, next to a
  non-current line only. The formula says so.

## Before a full run

1. The scorer has to tell a wrong number apart from a different definition: an arm-A line that matches a
   different line of the same filing should be "other definition", not "wrong".
2. IFRS short-term investments (Inditex, TotalEnergies) and separately tagged D&A (KDP): fix or mark as not verifiable.
3. ExxonMobil (in the 50-company list) moved to a new holding registrant; its history sits under the old CIK (34088).
   Pin it, or the B and C runs will fail.
4. Raise arm A's request cap for comps, or report its unfinished runs as a result in their own right (they are one).
