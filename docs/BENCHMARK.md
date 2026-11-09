# Benchmark

deskstack-bench measures how many numbers in an AI-built financial model are wrong or unsourced, with and without
deskstack.

- **Design:** the method, the frozen company set, the arms and how to run it are in [bench/README.md](../bench/README.md).
- **Cost:** the cost model is in [bench/COST_ESTIMATE.md](../bench/COST_ESTIMATE.md).

**Main run, 2026-11-09:** 50 companies (35 US, 15 EU) × DCF × 3 arms, Claude Sonnet 5.5, 150 runs, $20.03.
Every transcript, submission and score is in [`bench/results/2026-11-09T09-25-07-305Z/`](../bench/results/2026-11-09T09-25-07-305Z/), with a hand-checked
[analysis](../bench/results/2026-11-09T09-25-07-305Z/ANALYSIS.md).

| Arm | Models finished | Wrong reported figures (read by hand) | Avg cost | Avg time |
|---|---|---|---|---|
| A: web search only | 50 of 50 | 20 of 573 (3.5%), in 12 of 50 models | $0.23 | 58 s |
| B: deskstack data | 49 of 50 | 0 of 593 | $0.07 | 18 s |
| C: deskstack + reviewers | 50 of 50 | 0 of 606 | $0.10 | 32 s |

Most of web search's 20 wrong figures are numbers it couldn't find and filled in anyway: derived or partial-year share
counts, estimated capex, aggregator or Wikipedia figures, non-GAAP revenue. Arms B and C score 0 partly by
construction, because they read the data the scorer checks against; that data is checked independently by the golden
set and the nightly differential. Net debt and EBITDA are reported apart as definitions, not scored as wrong. The run
also found four gaps in deskstack's data, listed in the analysis.

**Comps run, 2026-11-09:** the same 50 companies × comps (the company and 4 to 6 peers it picks) × 3 arms, 150 runs,
$47.09. Every transcript, submission and score is in
[`bench/results/2026-11-09T13-04-05-468Z/`](../bench/results/2026-11-09T13-04-05-468Z/), with a hand-checked
[analysis](../bench/results/2026-11-09T13-04-05-468Z/ANALYSIS.md).

| Arm | Models finished | Wrong reported figures (read by hand) | Placeholders left as 0 | Avg cost | Avg time |
|---|---|---|---|---|---|
| A: web search only | 45 of 50 | 16 of 445 (3.6%) | 7 | $0.56 | 171 s |
| B: deskstack data | 50 of 50 | 0 of 1,021 | 0 | $0.17 | 36 s |
| C: deskstack + reviewers | 50 of 50 | 0 of 1,010 | 0 | $0.22 | 51 s |

15 of web search's 16 are twelve-month figures a quarter late: an aggregator's "TTM" still showed the twelve months to
June when the September 10-Qs were out. The sixteenth is a fourth quarter written as the year. The run also found two
scorer bugs, in how peers are matched to companies by name; both fixed before the hand check.

A 5-company pilot ran first ([analysis](../bench/results/2026-11-08T23-43-41-903Z/ANALYSIS.md)). It led to the scorer's "other line" and "other
definition" categories and to five data fixes.
