# deskstack-bench results

Model claude-sonnet-5-5, effort medium, prompts v2, set full (50 company-task pairs where every arm ran), run 2026-11-09T09:25:07.305Z.
Total API cost: $20.04.

| Arm | Models (valid) | Filed figures checked | Wrong vs filing | Why wrong | Other line of the filing | Other definition (EBITDA, net debt) | Not verifiable | Typed numbers unsourced | Checker blockers / model | Avg cost | Avg tokens | Avg time | Runs errored |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A: web search only | 50 (50) | 573 | 4.0% (23) | other 22, scale 1 | 78 | 27 | 87 | 7.1% (86/1210) | 0.00 | $0.23 | 152,097 | 58 s | 0 |
| B: deskstack data | 49 (49) | 593 | 0.2% (1) | scale 1 | 12 | 0 | 24 | 4.4% (51/1156) | 0.00 | $0.07 | 38,294 | 18 s | 0 |
| C: deskstack + associate + VP review + fix | 50 (50) | 606 | 0.2% (1) | scale 1 | 3 | 1 | 16 | 4.7% (55/1172) | 0.00 | $0.10 | 68,555 | 32 s | 0 |

How to read it:
- Wrong vs filing = reported lines (revenue, operating income, D&A, capex, net income, shares) that differ from the filing and from every other line of it, over all filed figures checked.
- Other line of the filing = the value equals another line of the same filing, or two lines added (e.g. revenue excluding excise taxes, capex including leased equipment): a different line, not counted as wrong.
- Other definition = EBITDA or net debt that differs from deskstack's definition. Definitions vary between analysts, so these are reported, not counted as wrong.
- Not verifiable = the filing doesn't report the line for that period, the period is ambiguous, or the company couldn't be resolved (e.g. a peer outside coverage). Reported, not counted as wrong.
- Scoring uses deskstack's verify_value as the oracle; arms B and C read the same data, so their tie-out is partly by construction. The comparison that matters is A against B and C. The nightly differential test (evals/differential) checks verify_value itself against the filings with independent parsers.
- Arm C sees the associate's tie-out before fixing, by design (it is B plus the review layer).
- EBITDA and net debt are compared with deskstack's definitions (operating income + D&A; total debt excluding leases - cash - short-term investments), which every arm is given in the prompt. Why wrong splits the remaining mismatches by the hint verify_value gave (scale, sign, currency, period, line item, other).
- Pairs exclude company-tasks where any arm crashed or hit the budget; crashed runs are counted per arm.
