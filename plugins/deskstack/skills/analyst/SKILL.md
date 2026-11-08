---
name: analyst
description: Builds a cited Excel model (quick DCF or comps) for a public company from deskstack filings data, then hands it to independent review. Use for "/analyst <company> <task>".
argument-hint: "<company> <quick-dcf|comps>"
---

# Analyst: build the model

You build the deliverable. Reviewers (`associate`, `vp-review`) check it afterwards, independently. Follow the
`conventions` skill: every number comes from a deskstack tool or the user, and is cited.

## 1. Identify the company

- Call the deskstack connector's `company_lookup` with the name, ticker or LEI.
- Note the region (US/EU), reporting standard, currency and fiscal year end.
- **Bank or insurer?** Say that an unlevered DCF and EV multiples don't fit, and offer P/E, P/B or a dividend model
  instead. Stop unless the user insists.

## 2. Pull the data

| Need | Tool |
|---|---|
| Last 3 fiscal years: revenue, operating income (EBIT), D&A, capex | `financial_statements` (annual) |
| Margins and growth to anchor assumptions | `key_metrics` |
| Net debt and diluted shares at the last fiscal year end | `financial_statements` (computed net debt is labeled with its formula) |
| Risk-free rate, tenor-matched (10y) | `risk_free_rate` |
| Equity risk premium, country risk, industry beta | `valuation_inputs` |
| Currency conversion | `fx_rate` |

- Keep each value's citation from the tool result: filing type, fiscal year, accession, concept.
- **Missing line (`null`):** tell the user and ask. Never use a number from memory.
- **Share price** (for market cap, comps, WACC weights): ask the user, and cite it as "User-provided, <date>".

## 3. Set the assumptions

Derive each assumption from history and state why:

- revenue growth per projected year, fading toward long-run growth;
- EBIT margin, tax rate, D&A and capex as % of revenue;
- WACC (rf + beta × ERP, then weighted with the cost of debt), and terminal growth at or below long-run nominal GDP
  and well below WACC.

Show the assumptions to the user in a short table **before building**, and change any they disagree with.

## 4. Write the spec and build

- Write a JSON spec following `references/specs.md`. Worked examples are in `references/examples/`.
- Every typed number needs a `source` string.
- Run the build script, saving to `out/<ticker>-dcf.xlsx` or `out/<ticker>-comps.xlsx`. The script lives in this
  skill's folder: in Claude Code use `${CLAUDE_SKILL_DIR}/scripts/deskstack.py`; in chat or Cowork use
  `scripts/deskstack.py` relative to this SKILL.md.

```bash
python3 scripts/deskstack.py build spec.json out/AAPL-dcf.xlsx
```

- The script refuses specs with missing sources or WACC ≤ terminal growth, and says what to fix.
- It writes blue inputs, black formulas, green links, a Sources sheet, a Cover with the disclaimer, and cached
  values so the file shows numbers anywhere.
- **If the script can't run:** build the workbook with the spreadsheet tools available, with the same layout and
  rules (`references/specs.md` → "Layout"). Say that you did.

## 5. Self-check, then hand off

- Run the checker on your file: `python3 scripts/deskstack.py check out/AAPL-dcf.xlsx`.
  - Fix any blocker or major in the spec and rebuild.
  - Explain any finding you keep.
- **Hand off for independent review. Don't review your own work as final.**
  - **Claude Code / Cowork:** delegate to the `deskstack:associate` agent, then the `deskstack:vp-review` agent. Pass
    only the workbook path and the company. Don't pass your reasoning or assumptions. Never use a fork.
  - **Chat:** offer the file for download. Suggest the user opens a **new chat**, uploads it and runs `/associate`
    then `/vp-review`, so reviewers don't see this conversation.

## 6. Applying review findings

- Apply a reviewer's finding only after the user agrees: edit the spec, rebuild, re-run the checker.
- Never change a number to make a tie-out pass without a cited reason.

## Output

1. One-paragraph summary: value per share and EV, with the three assumptions that matter most.
2. The assumptions table.
3. The file.
4. Next steps (review).
5. End with: **"Draft for human review. Not investment advice."**
