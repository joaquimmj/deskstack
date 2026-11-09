# Benchmark

deskstack-bench measures how many numbers in an AI-built financial model are wrong or unsourced, with and without
deskstack.

- **Design:** the method, the frozen company set, the arms and how to run it are in [bench/README.md](../bench/README.md).
- **Cost:** the cost model is in [bench/COST_ESTIMATE.md](../bench/COST_ESTIMATE.md).

**Status:** a pilot ran on 2026-11-08 (5 companies, 30 models, $6.68). Every transcript, submission and score is in
[`bench/results/2026-11-08T23-43-41-903Z/`](../bench/results/2026-11-08T23-43-41-903Z/), with a hand-checked [analysis](../bench/results/2026-11-08T23-43-41-903Z/ANALYSIS.md).

It gives no headline accuracy number. The scorer counted 13 of web-search Claude's 67 filed figures as wrong, but only
one of the 13 is a plain model error: four come from gaps in deskstack's own data (two fixed), and most of the rest
are definition differences. Arms B and C score 0% partly by construction, because they read the data the scorer uses.
What the pilot does show: with deskstack, models cost 2-3× less ($0.13-0.16 vs $0.38) and finish 2-3× faster; web
search alone finished 6 of 10 models (1 of its 5 comps tables), deskstack data 8 of 10,
deskstack with reviewers 10 of 10. The full run waits for a scorer that tells a wrong number from a different definition.
