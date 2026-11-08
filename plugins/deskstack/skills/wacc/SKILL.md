---
name: wacc
description: Computes a cited WACC step by step: risk-free rate, ERP, country risk, beta, cost of debt, market-value weights, from deskstack tools plus the user's price. Shows each source.
argument-hint: "<company>"
---

# WACC

Build it in a table where every input has a source, then show the formula with the numbers.

| Input | Where it comes from |
|---|---|
| Risk-free rate | `risk_free_rate`: 10-year in the company's currency (US Treasury for USD, ECB AAA par yields for EUR), with its date. Use `rate_decimal` |
| Equity risk premium (+ country risk premium) | `valuation_inputs` by the country of operations; say which dataset year |
| Beta | `valuation_inputs` industry beta: levered, or unlevered then relevered at the company's D/E. Say which |
| Cost of equity | rf + beta × (ERP + CRP if used) |
| Pre-tax cost of debt | Interest expense / average total debt from `financial_statements`, or the industry pre-tax cost of debt from `valuation_inputs` (state which), checked for sense |
| Tax rate | Effective rate from history, or the statutory rate (state which) |
| Weights | Market cap (price from the user × diluted shares from the filing) and debt (book value from the filing as a proxy for market value; say so) |

**WACC** = E/(D+E) × Ke + D/(D+E) × Kd × (1 − t).

Then give a ±1 point sensitivity in words: what it does to a DCF. End with "Draft for human review. Not investment
advice."
