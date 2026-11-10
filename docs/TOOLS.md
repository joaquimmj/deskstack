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
| `company_lookup` | `query` (ticker, name, CIK, LEI, CVM id or B3 ticker), `limit` | The canonical record: name, ticker or LEI (or CVM id and B3 tickers), region (US, EU or BR), reporting standard, currency, fiscal year end. Covers SEC registrants (including 20-F filers), the EU issuers with ESEF reports, and the Brazilian companies from CVM's open data |
| `financial_statements` | `ticker` (ticker, CIK, LEI, CVM id or B3 ticker), `years` (default 5, max 15), `include_ltm` | Standardized income statement, cash flow and balance sheet: annual fiscal years plus LTM for SEC filers, built as FY + YTD − prior YTD. Also computed EBITDA, free cash flow, total debt and net debt, each with its formula, and SEC cover-page shares outstanding. The balance sheet also has non-controlling interests and lease liabilities (IFRS 16 in Europe; operating plus finance leases for US filers, finance leases left out when debt already includes them), for the bridge from enterprise value to equity value |
| `key_metrics` | `ticker`, `years`, `include_ltm` | Growth, CAGR, margins, capex to revenue, FCF conversion, ROE, ROA, ROIC, net debt / EBITDA, interest coverage, each with its formula. A ratio repeats its inputs' notes (`inputs: d_and_a: …`). Banks and insurers get no EBITDA-based ratios |
| `verify_value` | `company`, `items` (up to 50: `metric`, `period`, `value`, `scale`, `currency`, `ref`) | Each item comes back match / mismatch / not_found / ambiguous, with the filed value, the difference, the source, and hints: wrong scale, flipped sign, wrong currency, another period, another line item, another common definition (net debt with lease liabilities, equity without minorities: "Definition"), swapped digits, and a last-twelve-months figure a quarter late ("Stale", with the latest value). A diluted share count more than 10% from the latest cover page gets a "Cover page" hint. When the filed figure has a caveat (a segment total, impairment included, basic EPS), the item carries it as `note`. The default tolerance is the rounding of the value as written |
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
  is the two added, and its formula says so (Merck, Microsoft, Keurig Dr Pepper). So is D&A for a short list of
  filers whose combined D&A tag covers property and equipment only (Cisco), with a note.
- **EBITDA** is operating income + D&A.
- **Lines from an issuer's own concepts:** a European issuer that tags a line only with its own concept gets that
  figure for a short list of lines, matched on the whole concept name; the cell shows the real concept and a note, and
  a standard IFRS concept always wins:
  - capex: purchases of PP&E and intangible assets (TotalEnergies, Airbus, VINCI, AB InBev, Stellantis, L'Oréal);
  - operating income: profit before financial result and income taxes (Airbus's EBIT);
  - D&A: "amortissements et dépréciations" (Sanofi), which includes impairment (see below); or PP&E depreciation and
    intangible amortization as two concepts, added, with the formula (Schneider Electric).
- **D&A with impairment:** a European issuer that tags D&A only together with impairment (TotalEnergies, AB InBev,
  Ahold, Iberdrola, Sanofi) gets that figure, with a note; its EBITDA then includes impairment too.
- **EPS and shares:** with no diluted EPS tagged (Inditex), diluted EPS is the basic figure, with a note; with only
  EPS from continuing operations tagged (Iberdrola), that figure, with a note. With no share count tagged, diluted
  shares are net income to ordinary holders (else to owners) ÷ EPS, with the formula and how far EPS rounding can
  move it; the owners' figure carries a note that coupons on hybrid or AT1 instruments overstate it. Never from EPS
  from continuing operations, or from a loss.
- **Operating income** is the tagged line, except for a short list of filers that tag something else as operating
  income: Disney tags its segment total, so its operating income is revenue − costs and expenses, with a note.
- **Diluted shares** off by a thousand or a million in a filer's XBRL (McDonald's tags 716.4) are rescaled only when
  net income ÷ diluted EPS confirms the corrected figure within 3%, with a note giving the filed value.
- **Net debt** is total debt − cash − short-term investments. A European issuer that tags its current financial assets
  only mixed with derivatives and receivables (TotalEnergies) gets net debt without them, and a note giving the amount.
- **Total debt** excludes leases, except for a US filer that tags its long-term debt only together with finance
  leases: total debt then includes them, and a note says so. Net debt carries a note with the lease liabilities it
  leaves out. If no current-debt line is tagged, the 12-month maturity of long-term debt stands
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
