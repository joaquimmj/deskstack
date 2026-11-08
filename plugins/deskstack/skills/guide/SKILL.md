---
name: guide
description: Explains deskstack outputs in plain words (WACC, terminal value, multiples, tie-out statuses, checker findings) and how to set up the connector and plugin. FR + EN.
---

# deskstack guide

Use this skill when the user asks what something means, how to read a report, or how to install deskstack. Answer in
the user's language, briefly, with one concrete example from their own model when there is one. Definitions are in
`references/glossary.md` (EN and FR).

## Setup (no terminal needed)

1. **Connector (data).** In Claude: **Settings → Connectors → Add custom connector**. Paste the deskstack connector URL
   given in the project README, with no sign-in. Free accounts can add one custom connector.
2. **Plugin (roles).** **Customize → Plugins → Add marketplace**, then paste the GitHub repository URL. Install
   **deskstack**.
3. **Try it:** "/analyst Apple quick DCF", then "/associate" and "/vp-review" on the file it produces.

**For an independent review in chat,** start a new conversation, upload the workbook and run `/associate`. A fresh
conversation doesn't see the builder's reasoning. Claude Code and Cowork run reviewers as separate agents
automatically.

## Reading the reports

**Tie-out report (`/associate`):**

| Status | Meaning |
|---|---|
| `match` | The number agrees with the filing, within rounding of how it is written |
| `mismatch` | It doesn't. The note says why when it can tell: wrong scale (thousands vs millions), flipped sign, another year, another line item, another currency |
| `not_found` | The filing doesn't report that line for that period. The model needs another source, or the line is wrong |
| `ambiguous` | The period could mean two fiscal years. State the year explicitly |
| `assumption` | Not a filed figure (growth, margin, WACC). It needs a cited rationale, not a tie-out |

**Review report (`/vp-review`):**

| Severity | Meaning |
|---|---|
| blocker | The model is broken or wrong (`#REF!`, unbalanced balance sheet, link to another file) |
| major | Likely wrong or unreviewable (hardcoded number in a formula, formula breaking its row, terminal value > 75% of EV) |
| minor | Convention (input not in blue) |

Each finding has a rule ID (DS001…) and a suggested fix.

## Limits to state honestly

- No share prices and no consensus estimates.
- European coverage is about 30 large issuers, annual figures only.
- A `match` checks the data, not the judgement. Reviews reduce errors but don't replace a human reviewer.
