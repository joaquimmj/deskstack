# Exploratory runs

These three runs only have arm A (web search only), on 10 companies. They tested whether web search does better on
the comps task with more searches and more effort: 12 searches at effort medium, then 30 searches at effort high. They are not a comparison of the three setups, so their `summary.md` tables have
no B or C rows.

Their analysis, read by hand like the main runs, is in [bench/ROBUSTNESS.md](../../ROBUSTNESS.md).

- `2026-11-09T19-12-17-173Z`: A12, 12 searches per request, effort medium.
- `2026-11-09T19-39-56-942Z`: A30, 30 searches, effort high. The 2 runs that finished; 7 stopped on the runner's $3
  per-run cap.
- `2026-11-09T20-18-34-250Z`: A30, the 7 runs re-run with a $6 per-run cap, as the amendment in ROBUSTNESS.md says.
