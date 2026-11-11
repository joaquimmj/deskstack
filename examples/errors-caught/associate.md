## Tie-out report: model.xlsx
8 of 14 filed figure(s) match the filings; 6 mismatch, 0 not found, 0 ambiguous, 0 not checked. 11 assumption(s) and 0 other typed number(s) need a cited source; 0 have none.

| # | Cell | Item | Period | Model value | Status | Filed value (model scale) | Note | Source |
|---|---|---|---|---|---|---|---|---|
| 1 | `Inputs!B23` | Diluted shares (millions) | FY2026 | 7,946.02 | mismatch | 7,453 |  | Diluted shares / Derived: LTM net income / FY2026 diluted EPS (as a model wrote  |
| 2 | `Inputs!B7` | D&A | FY2025 | 0 | mismatch | 28,000 |  | D&A / NOT FOUND - placeholder 0 |
| 3 | `Inputs!C6` | EBIT (operating income) | FY2026 | 153,237 | mismatch | 155,237 |  | EBIT (operating income) / 10-K for 2026-06-30, 0001193125-26-323660, https://www |
| 4 | `Inputs!C7` | D&A | FY2026 | 41,000 | mismatch | 39,000 |  | D&A / Computed by deskstack: depreciation + amortization of intangible assets (t |
| 5 | `Inputs!D5` | Revenue | LTM | 331,839 | mismatch | 346,445 | Period: the value matches revenue for FY2026 (ended 2026-06-30), not LTM to 2026-09-30. | Revenue / TTM from an aggregator site (as a model wrote it) |
| 6 | `Inputs!D6` | EBIT (operating income) | LTM | 155,237 | mismatch | 163,191 | Period: the value matches operating_income for FY2026 (ended 2026-06-30), not LTM to 2026-09-30. | EBIT (operating income) / TTM from an aggregator site (as a model wrote it) |
| 7 | `Inputs!B12` | Revenue growth FY2027E | FY2027 | 0.1292 | assumption |  |  | Revenue growth / Analyst assumption (example rule): FY2026 growth of 17.8%, capp |
| 8 | `Inputs!B13` | EBIT margin FY2027E | FY2027 | 0.4568 | assumption |  |  | EBIT margin / Analyst assumption (example rule): average operating margin FY2024 |
| 9 | `Inputs!B14` | Tax rate FY2027E | FY2027 | 0.194 | assumption |  |  | Tax rate / Analyst assumption (example rule): 1 - net income / pretax income, FY |
| 10 | `Inputs!B15` | D&A % revenue FY2027E | FY2027 | 0.1175 | assumption |  |  | D&A % revenue / Analyst assumption (example rule): FY2026 D&A / revenue |
| 11 | `Inputs!B16` | Capex % revenue FY2027E | FY2027 | 0.3494 | assumption |  |  | Capex % revenue / Analyst assumption (example rule): FY2026 capex / revenue |
| 12 | `Inputs!B17` | WACC FY2027E | FY2027 | 0.1022 | assumption |  |  | WACC / Analyst assumption (example rule): Damodaran Software (System & Applicati |
| 13 | `Inputs!B18` | Terminal growth FY2027E | FY2027 | 0.025 | assumption |  |  | Terminal growth / Analyst assumption (example rule): below long-run nominal GDP |
| 14 | `Inputs!C12` | Revenue growth FY2028E | FY2028 | 0.1083 | assumption |  |  | Revenue growth / Analyst assumption (example rule): FY2026 growth of 17.8%, capp |
| 15 | `Inputs!D12` | Revenue growth FY2029E | FY2029 | 0.0875 | assumption |  |  | Revenue growth / Analyst assumption (example rule): FY2026 growth of 17.8%, capp |
| 16 | `Inputs!E12` | Revenue growth FY2030E | FY2030 | 0.0667 | assumption |  |  | Revenue growth / Analyst assumption (example rule): FY2026 growth of 17.8%, capp |
| 17 | `Inputs!F12` | Revenue growth FY2031E | FY2031 | 0.0458 | assumption |  |  | Revenue growth / Analyst assumption (example rule): FY2026 growth of 17.8%, capp |
| 18 | `Inputs!B22` | Net debt | FY2026 | -36,549 | match | -36,549 | Computed value: total_debt - cash - short_term_investments. | Net debt / Computed by deskstack: total_debt - cash - short_term_investments, 10 |
| 19 | `Inputs!B5` | Revenue | FY2025 | 281,724 | match | 281,724 |  | Revenue / 10-K for 2026-06-30, 0001193125-26-323660, https://www.sec.gov/Archive |
| 20 | `Inputs!B6` | EBIT (operating income) | FY2025 | 128,528 | match | 128,528 |  | EBIT (operating income) / 10-K for 2026-06-30, 0001193125-26-323660, https://www |
| 21 | `Inputs!B8` | Capex | FY2025 | 64,551 | match | 64,551 |  | Capex / 10-K for 2026-06-30, 0001193125-26-323660, https://www.sec.gov/Archives/ |
| 22 | `Inputs!C5` | Revenue | FY2026 | 331,839 | match | 331,839 |  | Revenue / 10-K for 2026-06-30, 0001193125-26-323660, https://www.sec.gov/Archive |
| 23 | `Inputs!C8` | Capex | FY2026 | 115,948 | match | 115,948 |  | Capex / 10-K for 2026-06-30, 0001193125-26-323660, https://www.sec.gov/Archives/ |
| 24 | `Inputs!D7` | D&A | LTM | 42,500 | match | 42,500 |  | D&A / Computed by deskstack: depreciation + amortization of intangible assets (t |
| 25 | `Inputs!D8` | Capex | LTM | 135,921 | match | 135,921 |  | Capex / Computed by deskstack: FY + YTD - prior YTD, 10-Q for 2026-09-30, 000119 |