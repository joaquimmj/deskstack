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

A 5-company pilot ran first ([analysis](../bench/results/2026-11-08T23-43-41-903Z/ANALYSIS.md)). It led to the scorer's "other line" and "other
definition" categories and to five data fixes.
