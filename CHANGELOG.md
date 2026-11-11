# Changelog

## v0.1.0 (unreleased): first public release

The first release of the repository as a whole. The parts keep their own version numbers: data server 0.5.0,
plugin 0.2.0, `deskstack-check` 0.2.0.

**Data connector**
- Eight tools: `company_lookup`, `financial_statements`, `key_metrics`, `verify_value`, `risk_free_rate`, `fx_rate`,
  `valuation_inputs`, `data_status`. Every figure carries its filing, concept and period; a missing one is `null`.
- US companies from SEC EDGAR XBRL (annual years plus last twelve months), 232 European and UK issuers from ESEF and
  UKSEF reports, and 20 Brazilian companies from CVM open data (ODbL).
- Fallbacks say what they are: a note on the figure (D&A that is depreciation only, debt with finance leases,
  equity with minorities, net debt without leases…), repeated in the ratios built on it.
- `verify_value` names the usual cause of a mismatch: scale, sign, period, line item, currency, swapped digits, a
  stale twelve months, or another common definition.
- Lease liabilities and non-controlling interests on the balance sheet, for the bridge to equity value.

**Review layer**
- Roles: `/analyst`, `/associate`, `/vp-review`, `/md-redteam`, `/compliance`, `/sign-off`, `/deal-team`, plus
  `/deskstack-doctor`.
- `deskstack-check` command and GitHub Action: 21 model checks, and a tie-out to the filings with `--verify`.

**Evidence**
- Golden set: 377 questions with known answers, every one passing on recorded filings, re-read nightly by
  independent parsers.
- Benchmark on 50 companies: 0 of 3,230 reported figures wrong with deskstack, 36 of 1,018 (3.5%) with web search
  only, with the caveat that the 0 is partly by construction ([bench/README.md](bench/README.md)).
