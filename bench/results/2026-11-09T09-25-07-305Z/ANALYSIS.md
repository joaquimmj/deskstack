# Main run, 2026-11-09: 50 companies, DCF

50 companies (35 US, 15 EU) × DCF × 3 arms, Claude Sonnet 5.5, effort medium, prompts v2. 150 runs, $20.03 of API
credits. Raw transcripts, submissions and scores are in `runs/` and `work/`. `summary.md` is the scorer's table at run
time; `rescored/` is the same submissions scored again after one scorer fix (below). Every figure the scorer still
called wrong was then read by hand.

## Result

| Arm | Models finished | Filed figures | Wrong, read by hand | Avg cost | Avg time |
|---|---|---|---|---|---|
| A: web search only | 50 of 50 | 573 | **20 (3.5%)** | $0.23 | 58 s |
| B: deskstack data | 49 of 50 | 593 | **0** | $0.07 | 18 s |
| C: deskstack + associate + VP review + fix | 50 of 50 | 606 | **0** | $0.10 | 32 s |

With web search only, Claude put a wrong reported figure in its DCF for 12 of the 50 companies. Most of the 20 are
numbers it couldn't find and filled in anyway: a share count derived from net income / EPS, a six-month or a Q1 share
count used for the full year, capex estimated from "operating cash flow minus free cash flow", figures taken from
aggregator sites or Wikipedia, non-GAAP "adjusted revenue", a segment's D&A for the group's. It flagged about half of
them in its own source notes ("reviewer should replace"), but the numbers went into the model.

With deskstack's data, none of the reported figures was wrong. That comparison is partly by construction: B and C read
the data the scorer checks against. The independent checks of that data are the golden set (99/99 live) and the
nightly differential against two other XBRL parsers.

## How the figures were read

`summary.md` (run time) counted A at 23 wrong and B and C at 1 each. Reading them, plus the scorer fix, gives:

**Scorer fix.** The "other line of the filing" rule accepted any two lines of a filing that added up to the submitted
value. With hundreds of lines per filing, pairs matched by chance ("deferred tax assets + changes in ownership
interests" passing for capex). Lines now have to belong to the metric's family (revenue/sales, operating
income/EBIT, depreciation/amortization, capital expenditure; shares as single lines only). Re-scored, A went from 23
to 50 mismatches, and all 50 were read:

| What it is | Count | Wrong? |
|---|---|---|
| Model error: number not in the filing (estimates, proxies, aggregators, non-GAAP, segment instead of group) | 20 | yes |
| Other accounting basis: ASML's US GAAP figures (its 20-F) against its IFRS report (ESEF) | 6 | no |
| deskstack's D&A is depreciation only, the model's includes amortization (Cisco, Merck, Microsoft) | 9 | no, deskstack's line is narrow |
| Disney tags segment operating income as operating income; the model derived GAAP revenue minus costs | 3 | no, the model is right |
| Another line of the company's own statements: Exxon "sales and other operating revenue", KONE capex including leases, Sanofi capex excluding intangibles, Eni reported capex | 10 | no |
| Rounding: Iberdrola 8,973.1 against 8,973 | 1 | no |
| McDonald's diluted shares: all three arms wrote 716.4 million; McDonald's tagged 716.4 shares in its XBRL | 1 (A) + 1 (B) + 1 (C) | no, the filing's tag is off by a factor of a million |

The 20 model errors: GE revenue ×2 (adjusted, non-GAAP), Iberdrola capex (a "gross investment" figure, as the model
noted), Cisco operating income ×3 and Verizon ×1 (aggregator sites), UPS revenue (approximated from 9 months plus a
rounded Q4), Stellantis D&A ×3 (industrial activities, not the group), Boeing, Pfizer and GE diluted shares (derived,
six months, Q1), Netflix capex (estimated), Schneider operating income (Wikipedia, rounded), and four near misses on
share counts or operating income under 1% (Chevron, Cisco, UPS, Thermo Fisher).

Not read by hand: the 27 "other definition" figures (net debt and EBITDA, which depend on a definition) and the
"not verifiable" ones (87 in A, mostly lines the filing doesn't tag for that year).

## What it found in deskstack

- **D&A is depreciation only** for filers that tag the two separately (Cisco, Merck, Microsoft). EBITDA already adds
  intangible amortization in that case; the D&A line itself doesn't yet. B and C added amortization themselves.
- **Disney's operating income** is its tagged segment figure, not a GAAP line (Disney reports none).
- **Implausible share counts** (McDonald's 716.4) pass through as filed. A plausibility warning would catch them.
- **Dual filers** (ASML: US GAAP 20-F and IFRS annual report) give two right answers; deskstack serves the IFRS one.
- **Checker:** a bridge sent as text crashed the workbook build with a traceback instead of a clear error. Fixed with
  this run; the model recovered on its own.

## Cost

$20.03 for 150 runs, against an estimate of $24.50. Total spent on the benchmark: $26.71 (pilot $6.68, main run
$20.03).
