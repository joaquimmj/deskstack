# Model specs for `deskstack.py build`

A spec is JSON. Every typed number is an object with `value` and `source`, or a `values` list with one `source`
(or a `sources` list, one per value).

- **Sources** say where the number comes from:
  - a filing: "SEC 10-K FY2025, accession …, us-gaap Revenues (deskstack financial_statements)";
  - an assumption: "Analyst assumption: <why>";
  - the user: "User-provided, 2026-11-08".
- **Units:** all money in the spec's `scale` (`units`, `thousands`, `millions`, `billions`). Rates are decimals
  (0.09 = 9%).

## DCF (`"kind": "dcf"`)

| Key | Content |
|---|---|
| `company`, `ticker`, `currency`, `scale` | e.g. "Apple Inc.", "AAPL", "USD", "millions" |
| `history.periods` | Filed years, oldest first: `["FY2023", "FY2024", "FY2025"]`. A bare year (2024) becomes `FY2024` |
| `history.lines.revenue`, `.operating_income`, `.d_and_a`, `.capex` | `{"values": [...], "source": "..."}`. Capex and D&A are positive. Use `null` for a value the filing doesn't report |
| `assumptions.projection_labels` | e.g. `["FY2026E", ..., "FY2030E"]` (3 to 10 years) |
| `assumptions.revenue_growth` | `{"values": [one per projected year], "source": "..."}` |
| `assumptions.ebit_margin`, `.tax_rate`, `.da_pct_revenue`, `.capex_pct_revenue`, `.wacc`, `.terminal_growth` | `{"value": 0.31, "source": "..."}`. Decimals: a WACC of 9 or a growth of 2.5 is refused |
| `assumptions.mid_year` | `true` (a JSON boolean, not a string) to discount each year at n − 0.5 |
| `bridge.net_debt` | `{"value": ..., "period": "FY2025", "source": "..."}`, in `scale` |
| `bridge.diluted_shares` | Same, **in the same scale as money** (millions of shares for a model in millions) |

Example: `examples/dcf.json` (Apple, FY2025 10-K).

### Layout the script produces

| Sheet | Contents |
|---|---|
| **Cover** | Title, disclaimer, currency and units |
| **Inputs** | Historicals (blue, by fiscal year), assumptions (blue), mid-year flag, net debt and diluted shares |
| **DCF** | Revenue → EBIT → taxes → NOPAT → D&A → capex → unlevered FCF → discount factor → PV, then terminal value (Gordon), PV of TV, sum of PV, EV, net debt, equity value, shares, value per share, TV share of EV, EV / last EBIT |
| **Sources** | Cell, item, period, value and source for each typed number |

## Comps (`"kind": "comps"`)

| Key | Content |
|---|---|
| `target` | Ticker of the company being valued. Its row comes first, in bold; the median and mean cover the peers only |
| `currency`, `scale`, `period` | Default currency, scale, and the period of the figures (e.g. "LTM" or "FY2025") |
| `peers[]` | `name`, `ticker`, optional `currency`, and `revenue`, `ebitda`, `net_income`, `market_cap`, `net_debt`, each `{"value", "source"}` with an optional `"period"`. `market_cap` may be `{"value": null, "source": "Not given"}` when the user gives no price: EV and the multiples then show "n.a." |

- **Per-figure periods:** when a figure's period differs from the spec's `period` (LTM for one peer, FY2025 for an
  EU peer that has no LTM), set it on that figure: `{"value": ..., "period": "FY2025", "source": "..."}`. The
  Sources sheet records it, and `/associate` ties it out against that period.

- **One currency per row.** Market cap must be in the same currency as that row's financials. Multiples are
  currency-neutral.
- **Market cap** = price × diluted shares. The price is user-provided, so cite it.

The Comps sheet computes EV = market cap + net debt, then EV/Revenue, EV/EBITDA and P/E. It shows "n.m." for a
negative or zero denominator, and adds the peer median and mean.

Example: `examples/comps.json`.
