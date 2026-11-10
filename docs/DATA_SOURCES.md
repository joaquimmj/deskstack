# Data sources — terms, limits, attribution

Status: M0 audit, 2026-11-08. The per-source audit below is the source of truth for terms; re-check before each integration.

## Decisions after cross-checking with PLATFORM_NOTES.md

| Need | v1 hosted decision | Why |
|---|---|---|
| US financials | SEC EDGAR, **precomputed**: nightly GitHub Action builds trimmed per-company JSON from bulk `companyfacts.zip`, shipped as Worker static assets. Live fallback only to small endpoints (`companyconcept`, `submissions`). Global limiter ≤ 5 req/s, declared UA with contact email, back off on 403. | Apple companyfacts = 3.9 MB / ~17 ms parse vs 10 ms free CPU limit; SEC cap is 10 req/s across all machines. |
| EU financials | **Live in v0.4.** filings.xbrl.org xBRL-JSON, precomputed for the issuers in `server/data/eu-issuers.json` (LEIs resolved with GLEIF, CC0). Extractions cached per filing; the API is paced at one request per 2 s (it rate-limits bursts with HTTP 429). Coverage: no German issuers (not in the repository); half-year ESEF reports are rare, so annual only. | Large ESEF reports (TotalEnergies 21.6 MB) also exceed CPU. No formal licence/SLA → cache our extracts, cite each filing. |
| Risk-free rates | **Live in v0.2.** US Treasury par yield curve (the official CSV download on home.treasury.gov, one file per year) + ECB YC par yields `PY_<tenor>` (AAA `G_N_A` by default, all issuers `G_N_C`). Cached 6 h (latest) or 30 days (historical). | Free, no key. ECB requires "Source: ECB statistics." and no modification of figures. |
| FX | **Live in v0.3.** ECB EXR daily reference rates (`D.<CUR>.EUR.SP00.A`), crossed through EUR; latest, on a date, or period average. | Same terms as above. |
| Macro | ECB + Eurostat (CC BY 4.0) + Treasury. **No FRED in the hosted service.** Point users to the official FRED connector; self-hosters may use their own key. | FRED terms: every end user needs their own key; a shared server key is a BLOCKER. |
| Valuation inputs | **Live in v0.3.** Damodaran `betas*.xls`, `wacc*.xls` (US/Europe/Global) and `ctryprem.xlsx`, parsed at build time into figures with dataset date, attribution and link (his files are not republished). | No licence, "no strings attached", vendor-derived — attribution terms to confirm with the author. |
| Prices / market cap | **No price provider in the hosted app path.** `market_data` returns SEC shares outstanding / public float and asks for a price; skills tell Claude to use the user's own web search or an input from the user, cited. BYOK Tiingo via `x-api-key` header for Claude Code and self-hosters; never cached across users. | No provider allows a shared free key. Per-user headers in the Claude app are beta for a limited set of orgs and treated as org credentials; keys in URLs are prohibited. |
| Yahoo Finance | Excluded. | Terms forbid it. |

---

## Summary

| # | Source | Key needed | Rate limit | Caching / redistribution via hosted public service | Attribution | Risk |
|---|---|---|---|---|---|---|
| 1 | SEC EDGAR (data.sec.gov, Archives, efts) | No (declared User-Agent with contact email required) | 10 req/s total "across all machines"; IP block possible | Allowed: SEC site content "may be copied or further distributed" | Cite the SEC as source; no seal/logos; no "EDGAR"/"SEC" in our name | **CAUTION**: shared Worker egress plus a strict 10 req/s cap |
| 2 | filings.xbrl.org | No (UA with contact email requested) | None stated; "reserve the right" to add or withdraw | "no restrictions on the ways that the data can be used" | None required | **CAUTION**: no formal licence or SLA; API may change |
| 3 | GLEIF API | No | 60 req/min per user | CC0 | None required; don't imply GLEIF endorsement | **OK** |
| 4 | US Treasury par yield curve | No | None stated | US-gov data; FiscalData says "free, without restriction" | Cite Treasury (good practice) | **OK** |
| 5 | ECB Data Portal (YC, EXR) | No | None stated | Free reuse incl. commercial, if unmodified and source quoted | "Source: ECB statistics." | **OK** |
| 6 | FRED API | Yes, and **each end user needs their own** | 120 req/min | No caching clause; third-party series need owner permission | Mandatory FRED notice text + link to ToU | **BLOCKER** for a shared server key |
| 7 | Eurostat API | No | None stated | CC BY 4.0; commercial reuse allowed (exceptions below) | Acknowledge source + flag changes | **OK** |
| 8 | Damodaran datasets | No (static xls/xlsx) | n/a | No licence; "no strings attached" | Acknowledgement appreciated | **CAUTION**: informal terms; vendor-derived |
| 9 | Price/market-cap APIs (FMP, AV, Tiingo, Finnhub, Twelve Data, Massive, EODHD, Marketstack, Stooq) | Yes (all) | Free tiers 25/day to 1,000/day | **None** allows hosted redistribution on a free key; BYOK varies | Varies | **BLOCKER** for a shared key; BYOK is CAUTION/OK (see §9) |
| 10 | Companies House (UK private companies: accounts bulk data, API) | API: free key. Bulk accounts: none | API: 600 requests per 5 minutes per key | **No licence stated** for the data or the API (see §10). "We impose no rules or requirements on how the information on the public register is used" | OGL default line if OGL applies (UNVERIFIED) | **STOPPED**: licence to confirm with Companies House before any code |
| 11 | EDINET (Japan, FSA): API v2 | Yes, free (account with phone verification) | No number published; bursts banned ("短時間における大量のアクセス") | Public Data License 1.0, compatible with CC BY 4.0: "商用利用も可能です". Numeric data isn't copyrighted. The EDINET taxonomy is excluded | "出典：EDINET閲覧（提出）サイト（URL）、PDL1.0（URL）", plus a note when edited | **OK** (key needed) |
| 12 | OpenDART (Korea, FSS) | Yes, free; one key per member, never usable by a third party | 20,000 calls a day for an individual key (all 83 APIs together); over 1,000 a minute may be blocked | Public data under the Public Data Act: use "not restricted" if it doesn't infringe the public interest or others' rights; redistribution at the user's own responsibility | None found | **OK** (key needed; a batch job holds the key) |
| 13 | CVM open data (Brazil): DFP and ITR | No | None numeric; the portal "may limit simultaneous accesses" | ODbL 1.0: attribution, share-alike for a derived database, keep open. CVM terms: free for anyone, cite the portal | Cite "Portal de Dados Abertos da CVM, https://dados.cvm.gov.br/" plus the ODbL notice | **OK**, with ODbL obligations on our snapshot |

---

## 1. SEC EDGAR — CAUTION
- **Terms / policy:** https://www.sec.gov/os/accessing-edgar-data and https://www.sec.gov/privacy (both read 2026-11-08).
- **Key:** None. The data.sec.gov APIs "do not require any authentication or API keys" (https://www.sec.gov/search-filings/edgar-application-programming-interfaces, read 2026-11-08).
- **Rate limit:** "no more than 10 requests per second" in total, across all machines a user operates. "We reserve the right to block IP addresses that submit excessive requests." Access resumes once the request rate stays under the threshold for 10 minutes (sec.gov/privacy, read 2026-11-08). Also "Current max request rate: 10 requests/second" (accessing-edgar-data, read 2026-11-08).
- **User-Agent:** Scripts must declare themselves with a company/app name plus an admin contact email, e.g. `Sample Company Name AdminContact@<domain>.com`. "Unclassified" bots are "managed" (accessing-edgar-data, read 2026-11-08).
- **Redistribution:** sec.gov information "is considered public information and may be copied or further distributed by users of the web site without the SEC's permission". The SEC asks to be cited as source. Do not use the SEC seal or logos. "SEC" and "EDGAR" may not appear in a trade name or domain (sec.gov/privacy, read 2026-11-08). → Indefinite caching is fine.
- **Update frequency:** submissions JSON is updated "in real time" as filings disseminate. XBRL APIs typically lag under a minute. `submissions.zip` and `companyfacts.zip` are rebuilt nightly at about 03:00 ET. data.sec.gov **does not support CORS** (edgar-application-programming-interfaces, read 2026-11-08).
- **Endpoints:** `data.sec.gov/submissions/CIK##########.json`, `/api/xbrl/companyfacts/CIK##########.json`, `/api/xbrl/companyconcept/CIK##########/us-gaap/{tag}.json`, `/api/xbrl/frames/us-gaap/{tag}/{unit}/CY####[Q#][I].json`, plus `www.sec.gov/Archives/edgar/data/{cik}/{accession}/` and `www.sec.gov/files/company_tickers.json` (ticker map; UNVERIFIED, not re-read today).
- **Full-text search (efts):** The official FAQ says FTS covers filings "since 2001" and refers API, automation and rate questions to textsearch@sec.gov (https://www.sec.gov/edgar/search/efts-faq.html, read 2026-11-08). `efts.sec.gov/LATEST/search-index` is **undocumented**. Only third-party blogs describe it (UNVERIFIED) → treat as best-effort.
- **Cloudflare Workers egress:** We searched for reports of the SEC blocking Workers egress and **found none** (UNVERIFIED either way). We did find many reports of `403 "Undeclared Automated Tool"` when the UA has no contact email (e.g. https://github.com/sec-edgar/sec-edgar/discussions/194, https://dev.to/odeeb/sec-edgar-rate-limit-and-user-agent-fair-access-rules-nki, both read 2026-11-08). A Cloudflare community thread suggests Workers may share egress IPs within a region (https://community.cloudflare.com/t/cloudflare-blocking-cloudflare-workers-from-making-requests/528590, read 2026-11-08; UNVERIFIED). Because the SEC applies 10 req/s per user or IP, other tenants' traffic could trip a block on a shared IP. Cloudflare adds a `CF-Worker: <zone>` header to every Worker subrequest (https://developers.cloudflare.com/fundamentals/reference/http-request-headers/, read 2026-11-08 via search snippet), so the SEC can identify our zone.
- **Mitigations:** (a) Send a declared UA with a project name and monitored email on every request. (b) Use a global token bucket in one Durable Object at ≤5 req/s. (c) Cache filings and accession-level files indefinitely in R2; give submissions/companyfacts a short TTL. (d) Run a nightly Cron Trigger that pulls `companyfacts.zip`/`submissions.zip` into R2 so hot paths never hit SEC. (e) Never retry a 403 immediately; back off for 10+ min. (f) Keep a fallback egress path, e.g. a small fixed-IP proxy. Whether Cloudflare offers dedicated egress IPs for Workers is UNVERIFIED.

## 2. filings.xbrl.org (XBRL International) — CAUTION
- **Terms:** https://filings.xbrl.org/about.html (read 2026-11-08): "At present, there are no restrictions on the ways that the data can be used." No named licence. The docs footer reads "© 2021-23 XBRL All Rights Reserved" (https://filings.xbrl.org/docs/api, read 2026-11-08).
- **Key:** None. "Access to the API is provided free of charge". Routine users should "set a user agent that includes a contact email address" and join the mailing list (docs/api, read 2026-11-08).
- **Rate limit:** None stated. Operators "reserve the right to alter the API at any time, including applying rate limits or withdrawing it completely" (docs/api, read 2026-11-08). Live check: no rate-limit headers; server is Apache.
- **Coverage:** ESEF, UKSEF and Ukraine's Financial Reporting System. "there are a number of countries where ESEF filings are not made available", e.g. Germany and Ireland. Filings whose LEI or date can't be determined are excluded (about.html, read 2026-11-08). Live check: `meta.count` = 27,626 filings.
- **xBRL-JSON:** Provided per filing. Errors in some filings prevent the viewer/JSON output (about.html). Live check: each filing has `json_url`, `report_url`, `viewer_url`, `package_url`, `sha256`, `fxo_id`, `published`, `processed` and error/warning counts.
- **Update frequency:** "try to keep our index as up-to-date as possible", but there may be "significant lag" after the filing is lodged with the OAM (about.html).
- **Endpoints:** `/api/filings` (JSON:API; `filter[country]=GB`, complex `filter=[{name,op,val}]`, `include=entity`, `sort=-processed`, `page[size]` ≤1000), `/api/entities`, `/api/validation_messages`, and bulk `/indexes/filings-{YEAR}.json`, which supports `If-Modified-Since`/304 (docs/api, read 2026-11-08).
- **Risk reasoning:** Usage is permissive, but there is no licence and no SLA. Cache by `sha256`. Prefer the yearly index files for discovery.
- **Re-read 2026-11-10 (stars brief lot 2 bis, Europe and UK listed):** about.html still says "At present, there are no restrictions on the ways that the data can be used". No licence is named, no attribution is required, and no paid access is needed. The API docs still ask for a user agent with a contact email and still reserve the right to add rate limits. Nothing forbids redistribution or use in a free hosted service, so the brief's stop conditions do not apply. Live counts: GB 2,970 filings, FR 1,185, DE 0, IE 0.
- **UKSEF:** UK listed companies file UKSEF reports, in the same repository and the same xBRL-JSON format, so they go through the same extractor. Irish issuers that list in London (Kerry) appear under GB. UNVERIFIED: whether every UK listed company files there; we serve only those we found and checked.
- **What we check before serving a country:** recorded fixtures, at least 10 golden questions whose answers Arelle reads from the published report (`evals/esef_arelle.py`), and a coverage line in the README and in `data_status`. `server/scripts/build-esef.ts` writes `v1/eu/coverage.json`: issuers served and rejected, with the reason.

## 3. GLEIF API — OK
- **Terms:** https://www.gleif.org/en/meta/lei-data-terms-of-use (read 2026-11-08). LEI data is "provided under the CC0 licence". Don't claim IP in LEI data. Don't imply GLEIF endorsement. The logo needs permission. Liquidated damages of CHF 100,000 per breach apply to those clauses. Data is provided "AS IS".
- **Key:** None. Live check: anonymous `GET api.gleif.org/api/v1/lei-records` returned 200.
- **Rate limit:** "Rate limiting is currently set at 60 requests, per minute, per user, for all users." (GLEIF API Postman docs, https://documenter.getpostman.com/view/7679680/SVYrrxuU, read 2026-11-08). No rate-limit headers were returned (live check).
- **Attribution:** None required.
- **Caching/redistribution:** CC0, so unrestricted.
- **Update frequency:** Golden Copy publishes 3×/day (02:00/10:00/18:00 UTC per https://www.gleif.org/en/lei-data/gleif-golden-copy, read 2026-11-08 via search snippet; UNVERIFIED exact times).
- **Endpoints:** `/api/v1/lei-records?filter[lei]=…`, `filter[isin]=…`, `filter[bic]=…`, `filter[entity.legalName]=…`, `/api/v1/fuzzycompletions`, `/api/v1/autocompletions`, `/lei-records/{lei}/isins`, and the parent-relationship endpoints (Postman docs, read 2026-11-08).

## 4. US Treasury daily par yield curve — OK
- **Terms:** Treasury site policies (https://home.treasury.gov/subfooter/site-policies-and-notices) and the privacy policy (https://home.treasury.gov/subfooter/privacy-policy), both read 2026-11-08. **Neither has an explicit copyright/reuse statement** (UNVERIFIED: public-domain status as US-gov work is assumed, not stated). FiscalData API docs: "The data is offered free, without restriction" for commercial or non-commercial use, and "does not require a user account" (https://fiscaldata.treasury.gov/api-documentation/, read 2026-11-08). Par yield curve is not confirmed as a FiscalData dataset (UNVERIFIED).
- **Key / rate limit:** None. No rate limit stated (https://home.treasury.gov/treasury-daily-interest-rate-xml-feed, read 2026-11-08).
- **Format/endpoints:** XML (OData-Atom) at `home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml?data=daily_treasury_yield_curve&field_tdr_date_value=YYYY` (or `field_tdr_date_value_month=YYYYMM`; `all&page=N`, 300 rows/page, zero-based) (xml-feed page, read 2026-11-08). Live check: a CSV endpoint `…/daily-treasury-rates.csv/{YYYY}/all?type=daily_treasury_yield_curve&field_tdr_date_value=YYYY&_format=csv` returns tenors 1Mo, 1.5Mo, 2Mo, 3Mo, 4Mo, 6Mo, 1Y, 2Y, 3Y, 5Y, 7Y, 10Y, 20Y, 30Y. This endpoint is not documented on the feed page.
- **Update frequency:** "usually available … by 6:00 PM Eastern Time each trading day". Inputs are indicative bid quotes collected by the NY Fed near 15:30. Monotone convex method since 6 Dec 2021 (https://home.treasury.gov/policy-issues/financing-the-government/interest-rate-statistics/treasury-yield-curve-methodology, read 2026-11-08).
- **Attribution:** None required. Cite "U.S. Department of the Treasury" as good practice.

## 5. ECB Data Portal API — OK
- **Reuse policy:** https://www.ecb.europa.eu/stats/ecb_statistics/governance_and_quality_framework/html/usage_policy.en.html (read 2026-11-08). Statistics may be reused free of charge "irrespective of any subsequent commercial or non-commercial use", "on the condition that the source is quoted (e.g. "Source: ECB statistics.")" and the statistics, including metadata, are not modified. Free reuse "does not apply to third-party data without a prior permission from the originator".
- **Disclaimer:** https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html (read 2026-11-08). Modifications such as growth rates "must be stated explicitly". If the data goes into sold documents, buyers must be told it is free on the ECB site. No liability for FX reference rates.
- **FX rates:** "published for information purposes only", and "Using the rates for transaction purposes is strongly discouraged". Updated "around 16:00 CET every working day, except on TARGET closing days" (https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html, read 2026-11-08).
- **Yield curves:** "updated every TARGET business day at noon (12:00 CET)". AAA-only and all-bonds curves are available, with data since 6 Sep 2004 (https://www.ecb.europa.eu/stats/financial_markets_and_interest_rates/euro_area_yield_curves/html/index.en.html, read 2026-11-08). Live check: series `YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y` has the title "…Svensson model - continuous compounding…".
- **Key / rate limit:** No key or registration is mentioned. No rate limit is stated. Status codes include 304 for `If-Modified-Since` but no 429 (https://data.ecb.europa.eu/help/api/status-codes and /help/api/data, read 2026-11-08).
- **Endpoints:** `https://data-api.ecb.europa.eu/service/data/{flow}/{key}?format=csvdata|jsondata&startPeriod=&endPeriod=&lastNObservations=&updatedAfter=`. For example `EXR/D.USD.EUR.SP00.A` and `EXR/D..EUR.SP00.A` (all currencies), or `YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_{1Y..30Y}` (G_N_C = all bonds; PY_/IF_ prefixes for par/forward are UNVERIFIED). Live check: responses carry `cache-control: max-age=30` and `last-modified`.

## 6. FRED API (St. Louis Fed) — BLOCKER for a shared server key
- **Terms:** https://fred.stlouisfed.org/docs/api/terms_of_use.html (read 2026-11-08, full text reviewed).
- **One key for many users? No.** "Developers should request a distinct API key for each application they build. **All users of an application shall use their own API key.**" (https://fred.stlouisfed.org/docs/api/api_key.html, read 2026-11-08). The ToU also says the key is "uniquely associated with you".
- **Apps for other users:** Must "display to the users of your application the link to these Terms of Use" and state in our ToU that users are bound by the FRED ToU. Must place "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis." prominently. "FRED" may not appear in our hostname. Apps may not "replicate[] or attempt[] to replace the essential user experience" of FRED (ToU, read 2026-11-08).
- **Caching:** No caching clause. On termination, all copies of "the FRED® API" must be destroyed (ToU). Long-lived caching is legally ambiguous (UNVERIFIED).
- **Third-party series:** "Before using data series owned by third parties for anything other than your own personal use … you must contact the data owner to obtain permission"; copyrighted series carry "Copyright" in their notes (ToU). Examples include S&P 500 and ICE BofA.
- **Rate limit:** "Up to 120 requests per minute are allowed before being served a 429" (https://fred.stlouisfed.org/docs/api/fred/errors.html, read 2026-11-08).
- **Alternative:** The St. Louis Fed runs an **official FRED MCP Connector** at `https://mcp.stlouisfed.org`. It needs no FRED API key but each user needs their own connector account, and it is listed in Claude's directory (https://fred.stlouisfed.org/help/data/connecting-fred-to-ai-services/FRED-MCP-Connector, read 2026-11-08).
- **Recommendation:** Don't proxy FRED with a server key. Either take BYOK via a header (never cached across users) or point users to the official connector. Source Treasury and ECB rates from the primary publishers instead.

## 7. Eurostat API — OK
- **Terms:** https://ec.europa.eu/eurostat/help/copyright-notice (read 2026-11-08). Content is CC BY 4.0. Reuse is "authorised for commercial or non-commercial purposes" with acknowledgement of source and an indication of changes, and "There is no special procedure or requirement for a written licence."
- **Exceptions (non-commercial only):** third-party/non-Eurostat-source data; data for countries outside EU/EFTA/candidates (e.g. USA, Japan, China); Swiss/Liechtenstein trade data; Austrian 8-digit CN trade data. Logos are excluded.
- **Key / rate limit:** No key mentioned. No rate limit stated. Large requests may go async (https://ec.europa.eu/eurostat/web/user-guides/data-browser/api-data-access/api-introduction, read 2026-11-08).
- **Update frequency:** "twice a day, at 11:00 and at 23:00 CET" when new data exists. No vintages kept (same page).
- **Endpoints:** `https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}?…` (JSON-stat 2.0) and the SDMX 2.1/3.0 equivalents under `/api/dissemination/sdmx/` (same page; path suffix pattern UNVERIFIED beyond WADL links).
- **Attribution:** "Source: Eurostat", plus a note of any modification.

## 8. Damodaran datasets (NYU Stern) — CAUTION
- **Terms:** No licence or copyright notice. "Usage rules" (https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datahistory.html, read 2026-11-08) say "there are no strings attached" and "If you do use my data and wish to acknowledge … I thank you". He says the data is best for real-time corporate finance and valuation, "never meant for public policy debates", and asks to be left out of legal disputes. He tries "not to reproduce data on individual companies" from his data services. His aggregates are derived from licensed vendors, so republishing whole files is a grey area. Serve figures with attribution and a link rather than mirroring files (judgement, not a stated rule).
- **Key / rate limit:** None; these are static files.
- **Format/URLs:** Base `https://pages.stern.nyu.edu/~adamodar/pc/datasets/` (https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html, read 2026-11-08):
  - ERP/CRP by country: `ctryprem.xlsx` (Jan 2026), plus `ctrypremApr26.xlsx` and `ctrypremJuly26.xlsx`
  - Betas: `betas.xls` (US), `betaEurope.xls`, `betaGlobal.xls`
  - Cost of capital: `wacc.xls`, `waccEurope.xls`, `waccGlobal.xls`
  - Multiples: `pedata.xls`/`peEurope.xls`/`peGlobal.xls`, `vebitda.xls`/`vebitdaEurope.xls`/`vebitdaGlobal.xls`, `pbvdata.xls`/`pbvEurope.xls`/`pbvGlobal.xls`, `psdata.xls`/`psEurope.xls`/`psGlobal.xls`
  - Legacy `.xls` (BIFF) means the Worker needs an xls parser, or a cron job that pre-converts to JSON in R2.
- **Update cadence:** Annual full update, dated "January 9, 2026" on the page. Country risk premiums also update mid-year (Apr/Jul 2026 files). Live check of `Last-Modified`: ctryprem.xlsx 2026-02-16, ctrypremJuly26.xlsx 2026-07-10, betas.xls 2026-04-12, betaEurope/betaGlobal/pedata/vebitda 2026-01-08, wacc.xls 2026-01-12. Files can change silently, so poll with `If-Modified-Since` and record file hash plus date in each citation.

## 9. Share prices / market cap — open decision

Yahoo Finance: **excluded**. Its API terms bar selling, sharing or sublicensing the APIs and using them in competing services (https://legal.yahoo.com/us/en/yahoo/terms/product-atos/apiforydn/index.html, read 2026-11-08). yfinance itself says the API "is intended for personal use only" (https://github.com/ranaroussi/yfinance, read 2026-11-08).

| Provider | Free tier (read 2026-11-08) | Free-tier licence | User's own key via our hosted connector (BYOK) | Hosted single-key redistribution | Risk |
|---|---|---|---|---|---|
| **Tiingo** | 50 req/h, 1,000 req/day, 500 unique symbols/mo, 1 GB/mo (https://www.tiingo.com/about/pricing) | "Internal use … only for your own personal use"; commercial internal use costs $50/mo (pricing) | **Explicitly supported:** Developer Program covers software "where their software requires users to supply their own Tiingo API Token"; "Each user must have their own API token"; "Tiingo must be clearly attributed"; register by email; never ask for passwords; not for "digesting Tiingo data and then redistributing" (https://www.tiingo.com/documentation/appendix/developers) | Needs a redistribution licence ("without requiring your users to make their own Tiingo account") | **OK** (BYOK, no cross-user cache) |
| **Massive** (ex-Polygon; renamed Oct 2025 per search snippet, UNVERIFIED) | Stocks Basic: 5 req/min per asset class, EOD, 2 yrs history (https://massive.com/knowledge-base/article/what-is-the-request-limit-for-massives-restful-apis; plan details via search snippet of massive.com/pricing, UNVERIFIED) | Individual: "personal, non-commercial, and non-business purposes" (https://massive.com/legal/individuals-terms-of-service, last updated 2026-11-03) | **Explicitly allowed:** §3.3 lets you use Credentials "in Third-Party Services you enable under Section 7". §7 Third-Party Services "include AI tools, agents, hosting providers". Such a service "may process the Information only on your behalf", and you "may not let them … make it available to anyone else" (same page) | Business plans only (pricing not public) | **OK/CAUTION** (BYOK; low rate cap, US-only) |
| **Alpha Vantage** | 25 req/day; `TIME_SERIES_DAILY` compact only; `DAILY_ADJUSTED` premium; "unlimited API requests for verified open-source or educational projects" (https://www.alphavantage.co/support/, https://www.alphavantage.co/documentation/) | Personal non-commercial. Commercial includes use "on behalf of a corporation" or letting others access info "directly or indirectly" (ToU PDF, https://www.alphavantage.co/terms_of_service/) | Not addressed. A user's own key is OK for their own private research; PE-firm users fall under "commercial" (ToU §2) | Possibly via the open-source/educational program, which needs written confirmation (UNVERIFIED) | **CAUTION** |
| **Financial Modeling Prep** | Basic: 250 req/day, US only (search snippet, UNVERIFIED; pages return 403 to automated reads) | Personal, non-business only; "may not use this licence on behalf of a company…" (ToS §2.2.1 via search snippet, UNVERIFIED) | FMP guidance: holding a key or calling server-side "does not automatically include public-display or redistribution rights" (https://site.financialmodelingprep.com/insights/platform/can-you-use-fmp-data-in-a-public-app-website-or-client-dashboard, snippet only, UNVERIFIED) | Needs a "Data Display and Licensing Agreement" (Enterprise) | **CAUTION/BLOCKER** |
| **Finnhub** | ~60 calls/min. Candles (history) reportedly paid (third-party snippets, UNVERIFIED) | "strictly for personal use"; "can't be used by any business even internally" without approval (https://finnhub.io/terms-of-service) | "agree to not redistribute **or share access** to data or derived results" without written approval (ToS) | Written approval only | **CAUTION** (no free history) |
| **Twelve Data** | 8 credits/min, 800/day; US equities/ETFs, FX, crypto; "Internal non-display usage" (https://twelvedata.com/pricing) | §2.3(l) bars "Use Free Tier data for commercial purposes" (https://twelvedata.com/terms, updated 2026-01-01) | §2.3(m) bars "Share Credentials". "Non-display" means showing prices to the user would itself breach the free plan. Display starts at Grow ($79/mo) | Redistribution add-on; caching limited "beyond permitted timeframes" §2.3(g) | **BLOCKER** (free) |
| **EODHD** | 20 calls/day, 1 yr EOD history (https://eodhd.com/pricing) | Non-professional: "private, non-commercial purposes" (https://eodhd.com/financial-apis/terms-conditions) | Bars "displaying, or granting access" and using info "on behalf of any other individual" | B2B/custom only | **CAUTION/BLOCKER** |
| **Marketstack** (APILayer) | 100 req/**month**, EOD, 1 yr history, "Non-Commercial Use" (https://marketstack.com/pricing) | Non-commercial | Terms redirect to Idera/APILayer legal index; clause text not retrieved (UNVERIFIED) | "Commercial Use" from the paid Basic plan; redistribution not stated (UNVERIFIED) | **CAUTION** (limit too low) |
| **Stooq** | No API docs. As of 2026, CSV downloads reportedly need a CAPTCHA-issued `apikey` (https://github.com/pydata/pandas-datareader/issues/1012, snippet; UNVERIFIED). Live check: stooq.com serves a JS proof-of-work bot check | No published terms found (UNVERIFIED) | Key is captcha-gated per user; automating around that is not acceptable | No | **BLOCKER** |

**Official/free EOD with redistribution rights:** We found none that covers individual equities broadly. The ECB and Eurostat publish no single-stock prices. FRED equity indices such as SP500 are third-party copyrighted (§6). SIX Swiss Exchange reportedly gives free EOD closing prices without an MDLA after a letter of confirmation (search snippet of six-exfeed-mdla-pricelist.pdf; PDF 404 today, UNVERIFIED). IEX HIST is free T+1 pcap of IEX-only trades, so it is not a consolidated close and is impractical (https://iextrading.com/trading/market-data, snippet, UNVERIFIED). An exchange-licensing article questions whether closing prices are copyrightable at all, but that is contested (hedgeweek/EDI, snippet). **Partial fallback:** SEC XBRL `dei:EntityCommonStockSharesOutstanding` / `EntityPublicFloat` (from companyfacts) give share count and public float without a price vendor. Market cap = user-supplied or BYOK price × SEC shares, cited to both.

## Recommendation for the price provider decision
- **Recommended: BYOK with Tiingo.** Users send their own token in a request header, e.g. `X-Tiingo-Token`. The Worker forwards it to `api.tiingo.com/tiingo/daily/{ticker}/prices`. Responses are shown only to that caller, and price data is **never written to the shared cache**; at most use a per-request memo keyed by a hash of the token. This is the only provider with a written developer program for software where users supply their own token. Its free limits are the most generous: 1,000 req/day with raw and adjusted EOD. Obligations: register by email, display "Price data: Tiingo", never log tokens or ask for passwords, and say that commercial users (e.g. PE firms) need their own Tiingo commercial plan ($50/mo).
- **Runner-up: BYOK with Massive.** Its individual ToS §7 is the clearest text permitting "AI tools, agents, hosting providers" to process data on the user's behalf. But the free tier is 5 req/min, US-only, EOD with 2-year history, and non-business use only.
- **Rejected:** a single server key on any free or cheap plan. Every provider reviewed requires a paid redistribution, display or B2B licence for that. Twelve Data's free tier forbids display. Stooq is captcha-gated. FMP and EODHD forbid display or use on behalf of others. The one lead worth an email is Alpha Vantage's "verified open-source or educational projects" program; get written scope before relying on it.

## 10. Companies House (UK private companies) — STOPPED until the licence is confirmed

Read 2026-11-10. Not served, and no code written. Stars brief rule: stop and ask when the terms aren't published.

**What it is.** The Free Accounts Data Product is a free daily ZIP of the accounts filed electronically the day before
(https://download.companieshouse.gov.uk/en_accountsdata.html).
- Files: one instance document per filing, iXBRL (`.html`), XBRL (`.xml`) or a ZIP of iXBRL, named
  `Prod223_<n>_<company number>_<balance sheet date>`.
- Schedule: a new file Tuesday to Saturday. Daily files stay 60 days, then only monthly files.
- Size: about 60 to 160 MiB a day, up to 598 MiB (2026-10-01).
- Coverage: "about 75% of the 2.2 million accounts we expect to be filed each year". The GOV.UK data-products page
  says 60%; the two pages disagree.
- No payment: "Each data file is provided free of charge and is not supported."

**Rate limit (API).** "You can make up to 600 requests within a five-minute period." Over it, `429 Too Many Requests`
until the window resets. "We reserve the right to ban without notice applications that regularly exceed or attempt
to bypass the rate limits."
(https://developer-specs.company-information.service.gov.uk/guides/rateLimiting)

**Licence: not stated.**
- The accounts download page states no licence, copyright or re-use terms.
- The API pages (developer.company-information.service.gov.uk and its guidelines) state none either. They end with
  "© Crown copyright".
- The old terms page (resources.companieshouse.gov.uk/legal/termsAndConditions.shtml) now redirects to a "Service
  information" page with no terms.
- The service's "Policies" link leads to https://www.gov.uk/guidance/search-the-companies-house-register. It says the
  data is free and "not intended to be a source for bulk downloads" (that is about the search service).
- The closest statement, from https://www.gov.uk/guidance/companies-house-data-products: "We impose no rules or
  requirements on how the information on the public register is used, and we're not responsible for your use of the
  company data. You are responsible for complying with any applicable data protection, copyright and other
  legislation and regulations." This is permissive, but it isn't a licence.
- GOV.UK pages end with "All content is available under the Open Government Licence v3.0, except where otherwise
  stated". That covers the pages' content. Whether it covers the register data is UNVERIFIED.

**If the OGL applies.** It allows "copy, publish, distribute and transmit", including commercially. It requires the
attribution "Contains public sector information licensed under the Open Government Licence v3.0." unless the
provider gives its own. It does not cover personal data
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

**Personal data.** Companies House says re-users "become controllers of your personal data" under UK GDPR
(personal information charter). deskstack would serve only company accounts: no officers, no persons with
significant control, no addresses. The ECCTA 2023 suppression rules for bulk and API data are UNVERIFIED (not on the
pages read).

**Next step.** Ask Companies House whether the OGL v3.0 covers the Free Accounts Data Product and the API, for a free
hosted service that extracts accounts figures and cites each filing. A draft email is ready for the owner to send.

**UNVERIFIED:** an explicit licence for the bulk accounts data and for the API; a Companies House attribution
statement; ECCTA rules for re-users; the file count per daily ZIP; the share of filings with a profit and loss
account.

## 11. EDINET (Japan) — OK, needs a free API key

Read 2026-11-10.

**Terms.** https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WZEK0030.html ("EDINET 利用規約", revised
2025-04-25, linked from the API specification).
- Content on EDINET can be used by anyone under the Public Data License 1.0 ("公共データ利用規約（第1.0版）", PDL1.0).
- PDL1.0 (https://www.digital.go.jp/resources/open_data/public_data_license_v1.0) allows copying, public
  transmission and adaptation, "商用利用も可能です" (commercial use is allowed). It is declared compatible with CC BY 4.0.
- It also says "数値データ、簡単な表・グラフ等は著作権による保護の対象ではありません" (numeric data and simple tables
  aren't protected by copyright) and are freely usable.
- Third-party rights (PDL1.0 §1.2): content whose copyright belongs to someone other than the state needs that
  owner's permission. Filed reports are written by the companies; the figures we would extract are numeric data
  (above). We would not republish report text.
- Not covered by the PDL: logos, and the **EDINET taxonomy**. The FSA forbids modifying or translating the taxonomy
  without permission (https://www.fsa.go.jp/search/EDINET_Taxonomy_Legal_Statement.html). We would cite element names,
  never redistribute or translate the taxonomy.

**Attribution.** "出典：EDINET閲覧（提出）サイト（当該ページのURL）、PDL1.0（規約原文ページのURL）". When content is
edited or extracted, also say so and who did it, e.g. "EDINET閲覧（提出）サイト（URL）より抜粋して作成", and never
present edited figures as the government's own.

**Access and limits.** The API needs a free key: an account with SMS verification
(EDINET API仕様書 Version 2, ESE140206.pdf, updated 2026-06-03). No numeric limit is published. Banned: "短時間に
おける大量のアクセス" (heavy access in a short time). Scraping the website is banned; the API is the allowed route.

**UNVERIFIED:** a numeric rate limit; whether any filing contains figures under third-party rights beyond numeric data.

## 12. OpenDART (Korea) — OK, needs a free API key held by a batch job

Read 2026-11-10.

**Terms.** https://opendart.fss.or.kr/intro/terms.do, in force since 2020-01-21.
- Art. 11 ①: the service is free in principle ("원칙적으로 무료"); any paid service would be announced in advance.
- Art. 16: copyright in the API service and programs belongs to the FSS. Other matters follow the Copyright Act and
  the Public Data Act.
- Art. 19 ②: "회원은 ID 및 비밀번호, 인증키를 제3자에게 이용하게 해서는 안 됩니다" (a member must not let a third
  party use their ID, password or key). Art. 19 ⑤: one key per member.

**Commercial use and redistribution.** OpenDART FAQ "공시정보를 상업적으로 사용해도 되나요?" (2020-01-18): the data
is public data under the Public Data Act, so "공익이나 타인의 권리를 침해하지 않는 선에서 데이터의 공개 및 활용은
제한되지 않습니다" (its disclosure and use are not restricted as long as they don't infringe the public interest or
others' rights). The FSS doesn't review services built on it, and "재배포 및 재가공과 관련한 모든 책임은 이용자 부담"
(all responsibility for redistribution and reprocessing rests with the user).

**Limits.** FAQ "오픈API 이용한도는 어떻게 되나요?": individuals 20,000 calls a day across all 83 APIs; corporate members
(business registration and IP) have no limit on two of them. "과도한 네트워크 접속(분당 1,000회 이상)" (over 1,000 a
minute) may be restricted.

**What it means for us.** The key stays in the batch job that builds the static snapshot, as for the SEC; end users
never use it, which keeps Art. 19 ②. The Worker calls nothing live.

**Attribution.** None required on the pages read. We would still cite "Financial Supervisory Service, OpenDART" and
each filing's receipt number.

**UNVERIFIED:** the Public Data Act's own text (not read); an attribution requirement in it.

## 13. CVM open data (Brazil) — OK, with ODbL obligations; served since 2026-11-10

Read 2026-11-10.

**Licence.** The DFP (annual) and ITR (quarterly) dataset pages give "Licença Aberta para Bases de Dados (ODbL) do
Open Data Commons", linked to ODbL 1.0 (https://dados.cvm.gov.br/dataset/cia_aberta-doc-dfp,
https://dados.cvm.gov.br/dataset/cia_aberta-doc-itr).

**CVM's terms of use** (https://dados.cvm.gov.br/about, published 05/08/2024).
- The data is "serviço público gratuito a qualquer pessoa física ou jurídica" (a free public service to any person
  or company), "tal como está" (as is).
- Any secondary use must cite the source, "declarando que eles foram acessados pelo Portal de Dados Abertos da CVM,
  disponível em https://dados.cvm.gov.br/".
- The data must not be presented "de forma incorreta ou enganosa" (incorrectly or misleadingly).
- The portal "pode empregar mecanismos para limitar a quantidade de acessos simultâneos" (may limit simultaneous
  access, e.g. robots). No numeric limit.

**The data.** One ZIP per year (dfp_cia_aberta_2025.zip, 12.9 MB; itr 2026, 22 MB), updated weekly with
resubmissions; DFP since 2010, ITR since 2011.
- Each ZIP holds semicolon-separated CSVs in Latin-1: BPA and BPP (balance sheet), DRE (income statement), DFC
  (cash flow, direct and indirect), DMPL, DRA, DVA, each consolidated (`_con`) and individual (`_ind`).
- Columns include `CNPJ_CIA`, `CD_CVM`, `DENOM_CIA`, `MOEDA`, `ESCALA_MOEDA` (e.g. MIL), `ORDEM_EXERC` (ÚLTIMO or
  PENÚLTIMO), `DT_INI_EXERC`, `DT_FIM_EXERC`, `CD_CONTA` (a fixed chart of accounts, e.g. 3.01 revenue), `DS_CONTA`,
  `VL_CONTA`, `ST_CONTA_FIXA`.

**What the ODbL means for the snapshot** (ODbL 1.0 text, https://opendatacommons.org/licenses/odbl/1-0/):
- Extracting a substantial part of the data into our snapshot makes it a **Derivative Database** (§4.4(b)).
- Serving it publicly is public use. So that snapshot must be offered **under the ODbL** (§4.4(a)), with the licence
  or its URI (§4.2), and a **machine-readable copy of the whole derived database must be free to download** (§4.6).
- Figures in a tool answer are a **Produced Work**. Each needs a notice that the content comes from the database and
  is under the ODbL (§4.3), e.g. "Contains information from the CVM Open Data Portal (dados.cvm.gov.br), made
  available under the Open Database License (ODbL)."
- The ODbL covers the Brazilian data only. The rest of deskstack's code stays MIT and its other data keeps its own
  terms. The Brazilian snapshot files would carry their own ODbL notice and a download link.

**How deskstack meets them** (2026-11-10, `server/scripts/build-cvm.ts`):
- 20 large non-financial companies (`server/data/br-issuers.json`), consolidated DFP statements, by fixed account code.
- Every Brazilian answer carries the notice above in `attribution`, and each source's `license_note` names the ODbL.
- Each file under `v1/br/` states the licence. `v1/br/dataset.json` is the whole derived database, a static file
  anyone can download (§4.6). B3 tickers come from CVM's FCA forms, also ODbL.

**UNVERIFIED:** whether the ODbL version is 1.0 (inferred from the Open Definition link); any rights in the statement
contents under Brazilian law beyond the database licence; the terms of the file repository (dados.cvm.gov.br/dados).

## Open questions / unverified
1. Whether the SEC has ever blocked Cloudflare Workers egress ranges. No report found. Test from a deployed Worker with a declared UA, and check whether Cloudflare offers fixed egress IPs for Workers.
2. efts.sec.gov is undocumented. Ask textsearch@sec.gov whether programmatic use within 10 req/s is acceptable.
3. FMP terms and pricing could not be read directly (HTTP 403 to automated fetch). Its numbers come from search snippets.
4. Marketstack/APILayer clause text (redistribution, key sharing) was not retrieved.
5. Tiingo: does its developer program cover a hosted web service, not just distributed software? It isn't addressed, so email Tiingo when registering. Full Tiingo ToS text was not found (/about/terms returns 404).
6. Massive free-tier specifics and the Polygon rename come from search snippets; the pricing page didn't render them.
7. Treasury: no explicit public-domain or reuse statement on home.treasury.gov; the CSV endpoint is undocumented.
8. FRED: does caching for one user count as "making available to others"? Moot if we take BYOK with no shared cache, or point users to mcp.stlouisfed.org.
9. GLEIF Golden Copy exact publish times (02/10/18 UTC vs 00/08/16 UTC).
10. Damodaran: confirm by email that serving derived figures with attribution is acceptable for a hosted tool. Note that his files embed vendor-derived aggregates.
11. SIX free EOD closing-price terms (PDF 404) and IEX HIST terms, if an official price source is pursued.
