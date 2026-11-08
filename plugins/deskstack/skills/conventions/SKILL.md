---
name: conventions
description: deskstack house rules for financial work: banking formatting, a cited source for every number, units and periods stated, ask instead of invent. Use with any deskstack role.
---

# deskstack conventions

Every deskstack role (analyst, associate, VP review, one-shot commands) follows these rules. They are public,
widely used modeling practices.

## Numbers come from tools or from the user, never from memory

- Filed figures come from the **deskstack connector**:
  - `financial_statements` and `key_metrics` for company figures (SEC for the US, ESEF for the EU);
  - `risk_free_rate` and `fx_rate` for rates;
  - `valuation_inputs` for Damodaran ERP, betas and cost of capital.
- Each tool result carries `sources` (URL, accession or ID, period). Keep them.
- **If a tool returns `null`, the figure is not reported.** Say so, and never fill the gap with a number from memory.
- Anything the tools don't cover (share price, target multiples, management guidance, a scenario) is **asked of the
  user** and cited as "User-provided, <date>".
- If the connector isn't connected, stop and say how to add it (see the `guide` skill). Don't fall back to web
  numbers without saying so, and cite the page for each one if the user accepts.

## Workbook formatting (banking convention)

| Element | Format |
|---|---|
| Typed input | **Blue** font (`0000FF`) |
| Formula | Black font |
| Link to another sheet | Green font |
| Calculations | Formulas only. No number typed inside a formula (`=B5*1.05` hides an assumption) |
| Units | In the sheet title: "Inputs (USD in millions)". One unit per sheet. Convert explicitly when linking |
| Periods | Unambiguous labels: `FY2025` (fiscal year, with its end date when not December), `LTM`, `FY2026E` |
| Signs | Capex and D&A positive, subtracted in the formula. One convention throughout |

## A Sources sheet row for every typed number

| Column | Content |
|---|---|
| Cell | e.g. `Inputs!D5` |
| Item | e.g. "Revenue" |
| Period | e.g. `FY2025` |
| Value | The number as typed |
| Source | e.g. "SEC 10-K FY2025, accession 0000320193-25-000079, us-gaap Revenues (deskstack financial_statements)". For assumptions: "Analyst assumption: <rationale>". For user inputs: "User-provided, <date>" |

## Every deliverable

- Starts with what it is, the company, the currency and the units.
- Lists assumptions explicitly, each with its rationale.
- Ends with: **"Draft for human review. Not investment advice."**
- **Banks and insurers:** when `company_lookup` or `financial_statements` flags a financial company, say that EBITDA,
  EV and an unlevered DCF don't apply. Offer P/E, P/B or a dividend model instead.
- Reply in the user's language (French or English); keep tool and cell names as they are.

## Reviews

- Reviewers (associate, VP) **report**; they never edit the deliverable.
- The analyst applies fixes only after the user agrees.
- Each review lists cell references and severity: blocker, major, minor.
- Nothing is final until the user signs off.
