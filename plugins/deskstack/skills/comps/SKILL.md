---
name: comps
description: Builds a trading comparables table (EV/Revenue, EV/EBITDA, P/E) from deskstack filings data, with user-provided prices cited. Then suggests /associate.
argument-hint: "<company> [peer tickers]"
---

# Comps

1. **Target:** `company_lookup` for the target.
2. **Peers:**
   - Use the user's peers if given.
   - Otherwise propose 4–6 listed companies in the same industry and of similar size, and **ask the user to confirm
     the list** (no peer tool yet).
3. **Financials:** for each company, `financial_statements` for the chosen period (LTM where available, else the
   last fiscal year): revenue, EBITDA (computed: operating income + D&A), net income, net debt.
   - EU issuers have annual figures only.
   - Record each figure's own period in the spec (`"period": "FY2025"`), so the tie-out checks the right year.
4. **Prices:** ask the user for each share price and its date, or the market caps. Market cap = price × diluted
   shares. Cite the price as "User-provided, <date>" and the shares to the filing. If the user gives no price, write
   `"market_cap": {"value": null, "source": "Not given"}`: the row keeps its financials, and EV and the multiples show
   "n.a.". Never estimate a price.
5. **Build:** follow the `analyst` skill's comps spec (`references/specs.md`) and run its build script. Keep each
   company in its own reporting currency; multiples are currency-neutral.
6. **Hand off:** run the self-check, then offer `/associate` (ties out every peer's figures) and `/vp-review`.

End with "Draft for human review. Not investment advice."
