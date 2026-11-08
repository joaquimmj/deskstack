---
name: company-snapshot
description: One-page snapshot of a public company (US or EU): profile, 5-year financials, margins, growth, leverage, all cited to the filings via deskstack. No spreadsheet.
argument-hint: "<company>"
---

# Company snapshot

1. **Profile:** `company_lookup` → name, ticker or LEI, region, reporting standard, currency, fiscal year end.
2. **Financials:** `financial_statements` (annual, up to 5 years, plus LTM for SEC filers) → revenue, EBIT, net
   income, operating cash flow, capex, free cash flow, net debt.
3. **Metrics:** `key_metrics` → growth and CAGR, margins, FCF conversion, ROIC, net debt / EBITDA, interest coverage.
   Each value shows its formula.
4. **Write one page:**
   - a header line (company, ticker, currency, units, fiscal year end);
   - a financials table (years as columns);
   - a metrics table;
   - three factual observations drawn from the numbers (no forecasts, no recommendation);
   - a Sources list (filing, accession, URL).
5. **Flags:**
   - Bank or insurer: say which metrics don't apply.
   - Any `null`: "not reported", never filled from memory.

End with "Draft for human review. Not investment advice."
