# Tools

The deskstack connector is a remote MCP server, with no sign-in. Every tool is read-only.

**Every number carries its source:**
- For a filing: the XBRL concept and accession, or the ESEF report.
- For a rate: the series and its date.
- `sources` lists each document with its URL.

**`null` means not reported.** It is never zero and never an estimate.

**Units:**
- Money is in absolute units of the company's reporting currency.
- Ratios and rates are decimals (0.25 = 25%). `risk_free_rate` also gives `rate_pct`.

| Tool | Inputs | Returns |
|---|---|---|
| `company_lookup` | `query` (ticker, name, CIK or LEI), `limit` | The canonical record: name, ticker or LEI, region (US or EU), reporting standard (US-GAAP or IFRS), currency, fiscal year end. Covers SEC registrants (including 20-F filers) and the EU issuers with ESEF reports |
| `financial_statements` | `ticker` (ticker, CIK or LEI), `years` (default 5, max 15), `include_ltm` | Standardized income statement, cash flow and balance sheet: annual fiscal years plus LTM for SEC filers, built as FY + YTD − prior YTD. Also computed EBITDA, free cash flow, total debt and net debt, each with its formula, and SEC cover-page shares outstanding |
| `key_metrics` | `ticker`, `years`, `include_ltm` | Growth, CAGR, margins, capex to revenue, FCF conversion, ROE, ROA, ROIC, net debt / EBITDA, interest coverage, each with its formula. Banks and insurers get no EBITDA-based ratios |
| `verify_value` | `company`, `items` (up to 50: `metric`, `period`, `value`, `scale`, `currency`, `ref`) | Each item comes back match / mismatch / not_found / ambiguous, with the filed value, the difference, the source, and hints: wrong scale, flipped sign, wrong currency, another period, another line item. The default tolerance is the rounding of the value as written |
| `risk_free_rate` | `region` (US or EUR), `tenor` (default 10Y), `date`, `eur_curve` (aaa or all) | U.S. Treasury par yield or ECB euro area par yield, latest or the last business day on or before a date |
| `fx_rate` | `from`, `to`, and `on`, or `average_from` + `average_to` | ECB reference rates crossed through EUR: the latest rate, a period-end rate (for balance-sheet items) or a period average (for income-statement items) |
| `valuation_inputs` | `country`, `industry`, `region` (US, Europe or Global) | Damodaran: ERP, country risk premium, rating and default spread by country; beta, unlevered beta, D/E, tax rate, and costs of equity, debt and capital by industry |
| `data_status` | none | Coverage, data freshness, limits, self-hosting link and disclaimer |

## Periods

- **Fiscal years are labeled as the company labels them.**
  - Apple's FY2025 ends 2025-09-27.
  - Inditex's FY2025 ends 2026-01-31.
  - A year seen only as the comparative in the next report is counted back from its neighbour, never named after
    its end year.
- **Restatements:** when a period was restated, the latest annual filing that reports it wins.

## Computed lines

Each computed line carries its formula, so a different definition is visible.

- **D&A:** when a company tags depreciation and intangible amortization separately (no combined line), the D&A line
  is the two added, and its formula says so (Merck, Microsoft, Keurig Dr Pepper). A company that tags a narrower
  figure as combined D&A keeps it (Cisco's covers property and equipment only).
- **EBITDA** is operating income + D&A.
- **Operating income** is the tagged line, except for a short list of filers that tag something else as operating
  income: Disney tags its segment total, so its operating income is revenue − costs and expenses, with a note.
- **Diluted shares** off by a thousand or a million in a filer's XBRL (McDonald's tags 716.4) are rescaled only when
  net income ÷ diluted EPS confirms the corrected figure within 3%, with a note giving the filed value.
- **Total debt** excludes leases. If no current-debt line is tagged, the 12-month maturity of long-term debt stands
  in for the current portion, and the formula names it.
- **Net debt** is total debt − cash − short-term investments. Short-term investments are marketable securities and
  other short-term investments (US GAAP), or short-term deposits (IFRS). Wider IFRS lines such as other current
  financial assets are left out: they mix derivatives and receivables.
- **A new holding company** with no 10-K yet (ExxonMobil since July 2026) gets its predecessor's filings, with a
  `predecessor_note` that names both registrants.
- **Dual filers:** a European issuer that also files a 20-F on another basis (ASML: US GAAP) gets a `basis_note`
  pointing to it. Both sets of figures are right; say which one a number comes from.

## Limits

- **Shared service:** the free hosted service has a daily cap and a per-IP rate limit. When either is reached, the
  error message says how to self-host.
- **Response size:** responses are capped in size; ask for fewer years if needed.
