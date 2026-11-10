## Sign-off summary: model.xlsx
File SHA-256: `6f783b4a45a8b552fa96e9e0842a52bd60e36ed16017dc04f8252feb8265a1ae`

| Check | Status | Detail |
|---|---|---|
| Tie-out to filings (/associate) | fail | 8 match, 6 mismatch, 0 not found, 0 ambiguous, 0 not checked, 0 unsourced |
| Model review (/vp-review) | warn | 0 blocker, 1 major, 0 minor |
| Compliance (/compliance) | fail | 9 pass, 1 fail, 0 warn |
| Red team (/md-redteam) | missing | No red-team memo (optional). |

**Open items: 8** (7 blocking). Missing reviews: none.
1. [blocker] `Inputs!B23` (tie-out): Diluted shares (millions): mismatch.
2. [blocker] `Inputs!B7` (tie-out): D&A: mismatch.
3. [blocker] `Inputs!C6` (tie-out): EBIT (operating income): mismatch.
4. [blocker] `Inputs!C7` (tie-out): D&A: mismatch.
5. [blocker] `Inputs!D5` (tie-out): Revenue: mismatch. Period: the value matches revenue for FY2026 (ended 2026-06-30), not LTM to 2026-09-30.
6. [blocker] `Inputs!D6` (tie-out): EBIT (operating income): mismatch. Period: the value matches operating_income for FY2026 (ended 2026-06-30), not LTM to 2026-09-30.
7. [major] `Inputs!B7` (model review): DS016: Looks like a placeholder 0: its label or source says 'NOT FOUND'.
8. [blocker] `Sources!A8` (compliance): C04 No placeholder or memory citations: Citations that say TBD, approx., from memory, unknown or end with '?'.

Approval token: `5626b8e3cdd6` (it changes if the file, a report or an open item changes).

Nothing is exported until you approve in your own words. Blocking items must be fixed, or accepted with a reason that is recorded on the sign-off sheet.

Draft for human review. Not investment advice.