# deskstack-bench: statistical analysis

Python analysis of the benchmark's committed results, and the source of every number in the paper
([`bench/paper/deskstack-bench.pdf`](../paper/deskstack-bench.pdf)).

```bash
python3 bench/analysis/analyze.py      # needs numpy, scipy, pandas, matplotlib
```

**Inputs**
- `bench/results/*/rescored/summary.json`: the scorer's denominators, cost, tokens and time per arm.
- `hand_read.json`: the counts read by hand against the filings, transcribed from each run's `ANALYSIS.md` and from
  `bench/ROBUSTNESS.md`. Each block names its source file.

**Outputs** (in `output/`)
- `stats.json`: every estimate, interval and test.
- `tables.md`: the same, as tables.
- `fig_error_rates`, `fig_error_causes`, `fig_cost_accuracy` (`.pdf` and `.png`).

**Methods**
- Proportions: Wilson 95% intervals; zero counts: exact Clopper-Pearson.
- Differences between arms: Newcombe's hybrid score interval; Fisher's exact test.
- Both tasks pooled: Cochran-Mantel-Haenszel test, tasks as strata.
- DCF, company level: exact McNemar test, paired by company; percentile bootstrap over companies (20,000 resamples,
  fixed seed) for arm A's error rate, with the design effect.
- Robustness check: Fisher's exact test between 12 searches/medium effort and 30 searches/high effort.

**Limits**
- The committed summaries are per arm, not per company. The company-level bootstrap spreads checked figures evenly
  across companies; a sensitivity check with random per-company counts moves the bounds by under half a point.
- Comps peers are shared across tables, so the comps figure-level intervals are narrower than they should be.
- B finished 49 of 50 DCFs. The A-vs-B McNemar test is computed as if the missing company were one of A's 12.
