# Data evals (brief §8.1)

Three layers check that deskstack returns the numbers that were actually filed.

| Layer | Runs | What it checks |
|---|---|---|
| Golden set, recorded | Every push (`server/test/golden.test.ts`, in `npm test`) | 101 questions with known answers, through the real MCP tools on recorded fixtures. Every question must pass; a known miss must be listed with its reason |
| Golden set, live | Nightly (`server/scripts/golden.ts`) | The same questions against the deployed connector, at ≥ 95% (live answers can drift when a company files). Writes `site/badges/golden.json` (a shields.io endpoint badge) |
| Differential | Nightly (`evals/differential/differential.py`) | Re-reads every golden answer from the filing itself with an independent parser (see below). Fails when a check couldn't run |

What the differential checks:

- **SEC:** edgartools reads each 10-K or 20-F's own XBRL instance, without the calculation linkbase, which would flip
  capex signs. It also lists the issuer's annual filings itself, so it catches a later filing that restated the
  period.
- **ESEF:** Arelle reads the inline XBRL in the published report package.
- **Comparisons are exact as filed** (EPS to the cent). They cover the golden answer and, when the live run produced
  one, deskstack's own answer.

## The golden set (`golden.json`)

`build_golden.py` writes the golden set; CI fails when it is stale.

**Where the answers come from:**

| Source | Data |
|---|---|
| SEC | Raw companyfacts as filed (`server/test/fixtures/sec`). Among annual filings, the latest that reports the period wins; `source.original` keeps the first-filed value when it differs |
| ESEF | What Arelle reads from each published report (`evals/fixtures/esef-arelle.json`, written by `esef_arelle.py`), not deskstack's own extractor |
| Rates | The Treasury and ECB files, by date |

**Scoring.** Each answer must match as filed: units to the unit, EPS to the cent, rates to 1e-6. It must also come
from the right period end, and cite the filing that reports it. A renamed field or a missing group is a miss, never
a silent `null`.

**Live runs.** A later annual filing that reports the same period, such as next year's 10-K, may be cited instead,
as long as the value is the same. Questions marked `fixture_only` (like "Apple has an LTM period", true only while a
10-Q follows the last 10-K) are skipped.

**How independent is it?** Not fully. The concepts are picked by hand from the face statements and usually match
deskstack's first choice. "Latest annual filing wins" is deskstack's policy too. The independence comes from the
differential, which doesn't share either.

**Coverage:**
- 10 SEC filers: US-GAAP 10-Ks, and IFRS 20-Fs in EUR and JPY;
- 2 ESEF issuers, one of them reporting in USD;
- Treasury yields and ECB rates;
- behavior checks: a bank flagged, `null` instead of 0, no LTM for 20-F filers, fiscal year ends.

**Edge cases, by tag:**

| Tag | Example |
|---|---|
| `restated` | SAP 2022 after the Qualtrics disposal; SAP 2024 cash flow |
| `stock-split` | Alphabet 2021 EPS: 112.20 as filed, 5.61 after the 20:1 split |
| `53-week year` | Apple FY2023 |
| `52-53-week year` / `september-fye` | Apple |
| `june-fye` | Microsoft |
| `march-fye` | Toyota |
| `january-fye` | Inditex |
| `comparative-only` | Inditex FY2023, seen only as the prior year in the FY2024 report |
| `bank` | JPMorgan |
| `ifrs16` | Inditex |
| `usd-reporter` | TotalEnergies |

The golden set already caught a real bug. A year seen only as a comparative was labeled from its end year, so
Inditex's FY2023 (ending January 2024) was also called "FY2024". It is now counted back from the nearest known year.

**Gap:** neither ESEF issuer restated anything between its two reports (checked fact by fact with Arelle), so ESEF
restatement handling isn't exercised yet. It needs an issuer that restated.

```bash
python3 evals/build_golden.py                 # regenerate golden.json
python3 evals/esef_arelle.py                  # re-read the ESEF answers with Arelle (network)
cd server && npx vitest run test/golden.test.ts
npx tsx scripts/golden.ts --url https://<worker>.workers.dev/mcp     # live; writes evals/results/ and the badge
SEC_USER_AGENT="deskstack-ci you@example.com" python3 evals/differential/differential.py --live evals/results/golden-live.json
```

## Status (2026-11-09)

| Check | Result |
|---|---|
| Recorded golden set (every push) | 100/100 |
| Live golden set, deployed connector (nightly) | 99/99 (1 fixture-only question skipped) |
| Differential, SEC: edgartools on each 10-K or 20-F XBRL instance, with its own search for later filings | 72/72 agree |
| Differential, ESEF: Arelle on the published report packages | 11/11 agree |

The nightly workflow (`.github/workflows/evals.yml`) runs all of this and publishes the badge.
