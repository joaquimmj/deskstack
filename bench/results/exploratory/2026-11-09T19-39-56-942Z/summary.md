# deskstack-bench results

Model claude-sonnet-5-5, effort high, prompts v2, set full (9 company-task pairs where every arm ran), run 2026-11-09T19:39:56.942Z.
Total API cost: $7.88.

| Arm | Models (valid) | Filed figures checked | Wrong vs filing | Why wrong | Other line of the filing | Other definition (EBITDA, net debt) | Not verifiable | Typed numbers unsourced | Checker blockers / model | Avg cost | Avg tokens | Avg time | Runs errored |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A: web search only | 2 (2) | 29 | 0.0% (0) | - | 0 | 2 | 15 | 0.0% (0/55) | 0.00 | $0.82 | 1,122,154 | 197 s | 1 |

How to read it:
- Wrong vs filing = reported lines (revenue, operating income, D&A, capex, net income, shares) that differ from the filing and from every other line of it, over all filed figures checked.
- Other line of the filing = the value equals another line of the same filing, or two lines added (e.g. revenue excluding excise taxes, capex including leased equipment): a different line, not counted as wrong.
- Other definition = EBITDA or net debt that differs from deskstack's definition. Definitions vary between analysts, so these are reported, not counted as wrong.
- Not verifiable = the filing doesn't report the line for that period, the period is ambiguous, or the company couldn't be resolved (e.g. a peer outside coverage). Reported, not counted as wrong.
- Scoring uses deskstack's verify_value as the oracle; arms B and C read the same data, so their tie-out is partly by construction. The comparison that matters is A against B and C. The nightly differential test (evals/differential) checks verify_value itself against the filings with independent parsers.
- Arm C sees the associate's tie-out before fixing, by design (it is B plus the review layer).
- EBITDA and net debt are compared with deskstack's definitions (operating income + D&A; total debt excluding leases - cash - short-term investments), which every arm is given in the prompt. Why wrong splits the remaining mismatches by the hint verify_value gave (scale, sign, currency, period, line item, typo, other).
- Pairs exclude company-tasks where any arm crashed or hit the budget; crashed runs are counted per arm.
