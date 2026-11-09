# Robustness check: does web search do better with more searches and more effort?

Pre-registered 2026-11-09, before any run. The comps run (`results/2026-11-09T13-04-05-468Z/`) gave arm A (web search
only) 12 searches per request at effort medium. The obvious objection: with more room, web search would get it right.

**Question.** With 30 searches per request and effort high, does arm A still write figures that differ from the filing
for the period asked?

**Design.** Arm A only, comps task, prompts v2, Claude Sonnet 5.5, two settings on the same 10 companies:

| Setting | Searches per request | Effort |
|---|---|---|
| A12 (as in the comps run) | 12 | medium |
| A30 | 30 | high |

Companies, fixed before running:
- the 5 where arm A wrote wrong figures or placeholders in the comps run: CSCO, UNH, UPS, XOM, Airbus
  (MINO79WLOO247M1IL051);
- 5 controls, by rule: the first 5 companies in `companies.json` whose arm A comps table was valid and had no
  mismatch after the rescore: AAPL, KO, TotalEnergies (529900S21EQ1BO4ESM68), Inditex (549300TTCXZOGZM2EY83), MSFT.

A12 is re-run too, so A30 is compared with a fresh run of the same setting (the model is not deterministic), not only
with the earlier result.

**Scoring and reading.** The same scorer as the comps rescore. Every mismatch is read by hand against the filings and
classified as in the comps analysis (wrong for the period asked, placeholder, other line, other basis).

**What would change the claim.** If A30 has no wrong figures and no placeholders on these 10 companies, the site and
README say that web search's errors in the main runs depend on its search allowance. Otherwise they say they persist
with 30 searches and high effort. Either result is published, with this file.

**Budget.** Hard cap $98 on the ledger ($73.80 spent before this check), per-run cap $3. Expected about $15-20.

## Amendment, 2026-11-09, after the A30 pass and before any re-run

In A30, 7 of 10 runs (AAPL, KO, TotalEnergies, Inditex, UNH, XOM, UPS) stopped on the runner's per-run cap ($3)
without a table: the first submission was rejected (a missing market cap), and the worst-case bound for the request
that would fix it (30 searches' worth of conversation, priced as if none of it were cached) crossed the cap after
about $0.80 spent. That cap is a property of our runner, not of web search, so those 7 runs are re-run at A30 with a
per-run cap of $6 (same companies, prompts, model, searches and effort), into a separate results folder. The ledger's
hard cap stays $98. The A12 pass and the two A30 runs that finished are kept as they are. The reading rule above is
unchanged.
