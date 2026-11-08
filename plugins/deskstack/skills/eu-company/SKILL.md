---
name: eu-company
description: Looks up a European listed company (by name or LEI) and returns its IFRS figures from ESEF annual reports via deskstack, with the coverage limits stated.
argument-hint: "<company name or LEI>"
---

# European company

1. **Find it:** `company_lookup` with the name or LEI.
   - European issuers resolve to an LEI.
   - If none is found, say that coverage is about 30 large issuers (France, Netherlands, Spain, Finland, Italy,
     Belgium). German issuers aren't in the public ESEF repository.
2. **Financials:** `financial_statements` with the LEI → annual IFRS figures, each line with its concept and report.
   - Some lines an issuer tags only with its own concepts come back `null`: say "not reported in the ESEF data",
     never estimate.
3. **Notes:**
   - The reporting currency can differ from the trading currency (e.g. a USD reporter listed in euros). Use `fx_rate`
     (ECB) to convert, at the period average for income statement figures and the period-end rate for balance sheet
     figures.
   - Annual figures only; no LTM.
   - Financial companies are flagged.
4. **Continue** with `company-snapshot`, `quick-dcf` or `comps` if the user wants.

Cite the ESEF report (filings.xbrl.org URL) for each figure. End with "Draft for human review. Not investment
advice."
