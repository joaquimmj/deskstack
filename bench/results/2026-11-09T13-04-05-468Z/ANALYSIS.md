# Comps run, 2026-11-09: 50 companies, trading comparables

50 companies (35 US, 15 EU) × comps × 3 arms, Claude Sonnet 5.5, effort medium, prompts v2. 150 runs, $47.09 of API
credits. Each model is a comps table: the company and 4 to 6 listed peers it picks, with revenue, EBITDA, net income,
net debt and market cap, each with its source and period. Raw transcripts, submissions and scores are in `runs/` and
`work/`. `summary.md` is the scorer's table at run time; `rescored/` is the same submissions scored again after the
scorer fixes below. Every figure the rescored table still calls wrong was then read by hand.

## Result

| Arm | Models finished | Filed figures | Wrong for the period asked, read by hand | Placeholders left as 0 | Avg cost | Avg time |
|---|---|---|---|---|---|---|
| A: web search only | 45 of 50 | 445 | **16 (3.6%)** | 7 | $0.56 | 171 s |
| B: deskstack data | 50 of 50 | 1,021 | **0** | 0 | $0.17 | 36 s |
| C: deskstack + associate + VP review + fix | 50 of 50 | 1,010 | **0** | 0 | $0.22 | 51 s |

Filed figures are revenue and net income of the company and of every peer the scorer could tie to a filing; EBITDA
and net debt are reported apart (they depend on a definition), and market caps aren't scored. Figures are counted over
the 49 companies where every arm finished a run (one arm A run timed out).

With web search only, 15 of the 16 wrong figures have one cause: **the last twelve months a quarter late.** The
model took "TTM" figures from an aggregator (stockanalysis.com, for all 15) that still showed the twelve months to
June 2026, when the September 10-Qs were already filed. Each was rebuilt from the filings: Motorola Solutions'
12,240 is the twelve months to June (12,236), Fortinet's 7,530 likewise (7,527), and so on for Elevance, XPO,
C.H. Robinson, Expeditors, J.B. Hunt and FedEx (its fiscal year to May). The sixteenth is Boeing's fourth-quarter
net income (8,220) written as its full-year figure (2,235). A comps table is "as of now", so these are wrong for the
period asked, though each was right for an earlier one.

The **7 placeholders** are numbers the model didn't find and left as 0 with a label ("NOT FOUND - placeholder 0"):
Cigna, CVS and Humana in UnitedHealth's table, after the model used up its web searches (arm A has 12 per request),
and ConocoPhillips' net income in Exxon's. They are counted apart: a reader sees the label, but the zeros are in the
table, and a ratio computed from them is wrong.

Four more arm A runs never produced a table: the builder rejected a missing market cap ("market_cap must be a
number"; market caps aren't scored, but the table needs one), and the model stopped instead of fixing it.

With deskstack's data, none of the filed figures was wrong. As in the DCF run, that is partly by construction: B and
C read the data the scorer checks against. The independent checks of that data are the golden set (99/99 live) and the
nightly differential against two other XBRL parsers.

## How the figures were read

`summary.md` (run time) counted A at 38 wrong, B at 10 and C at 8. All of B's and C's, and 12 of A's, were the
scorer's mistakes, not the models'. Peers are matched to companies by name, and the matching was too loose:

**Scorer fix 1: the target by name.** A peer counted as the company itself when the two names shared one word:
Coca-Cola Europacific Partners was scored as Coca-Cola, BJ's Wholesale Club as Costco, Howmet Aerospace as GE
Aerospace, Canadian Pacific Kansas City as Union Pacific, Charter Communications as Verizon. Now every word the model
wrote must be in the official name ("LVMH" still matches LVMH Moët Hennessy Louis Vuitton; asides like "(target)" are
dropped).

**Scorer fix 2: peers by lookup.** A peer took the first company_lookup hit whose name matched: "Coca-Cola Co" (KO)
became Coca-Cola Consolidated, the bottler, in two tables; General Motors became GM Financial; Hermès, which deskstack
doesn't cover, matched an unrelated US filer on "International". Now the hit with the ticker the model wrote wins, then
one with exactly the same name, then a single longer name; anything else is not verifiable.

Re-scored, A has 28 mismatches, B and C none. All 28 were read against the filings:

| What it is | Count | Wrong? |
|---|---|---|
| Twelve months a quarter late (aggregator TTM, or FedEx's fiscal year to May as LTM) | 15 | yes |
| A quarter written as the year (Boeing net income) | 1 | yes |
| Placeholder 0, labelled as not found (Cigna, CVS, Humana; ConocoPhillips net income) | 7 | counted apart |
| Another line of the company's own statements: Exxon "sales and other operating revenue", Elevance "operating revenue", Carrefour "net sales", Ambev profit including minorities | 4 | no |
| Iberdrola revenue from its results report (45,017) where its annual report tags 44,076 | 1 | no |

Not read by hand: the 87 "other definition" figures in A (EBITDA and net debt) and the 255 "not verifiable" ones
(mostly peers deskstack doesn't cover, or a period the filing doesn't have).

## What it found in deskstack

Nothing in the data: no figure B or C wrote differs from the filing. What it found was in the benchmark itself: the
two scorer bugs above. (Five European gaps from the DCF run, where deskstack returned null because an issuer tags a
line only with its own concept, were fixed in the meantime, in PR #14; they don't affect this run, which reads revenue
and net income.)

## Cost

$47.09 for 150 runs: A $27.81 (web search is billed per search, and the pages it reads are input tokens), B $8.44,
C $10.84. Per table, deskstack costs about a third of web search alone and is 3-5× faster.
