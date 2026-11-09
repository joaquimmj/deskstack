# deskstack

**Your AI deal team inside Claude. One agent builds the model, others check every number against the filings, and
nothing ships without your sign-off. Free data, US and Europe.**

[![golden set](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/joaquimmj/deskstack/main/site/badges/golden.json)](evals/README.md)
· [Website](https://joaquimmj.github.io/deskstack/) · [Tutorial](docs/TUTORIAL.md) · [Tutoriel (FR)](docs/TUTORIEL.md)

> **Public beta.** The hosted connector is online at `https://deskstack.deskstack-server.workers.dev/mcp`. Feedback and issues are welcome.

## Benchmark

How many numbers in an AI-built model are wrong or unsourced, with and without deskstack. The test covers 50
companies (a DCF and a comps table each) and three setups: web search only, deskstack
data, and deskstack plus its reviewers. Scoring is automatic, against the filings. The runner, the frozen company set and the method are in
[bench/](bench/README.md).

**First results (50 companies, DCF, Claude Sonnet 5.5):** with web search only, 20 of 573 reported figures were wrong (3.5%, in 12 of 50 models), read by hand against the filings. With deskstack's data: 0, at a third of the cost ($0.07-0.10 vs $0.23 per model) and 2-3× faster. The 0 is partly by construction, since the scorer checks against the same data; the [analysis](bench/results/2026-11-09T09-25-07-305Z/ANALYSIS.md) says how that data is checked independently, and what the run found wrong in deskstack itself.

**Comps (same 50 companies):** with web search only, 16 of 445 reported figures were wrong (3.6%), 15 of them twelve-month figures a quarter out of date, taken from an aggregator after the September 10-Qs were filed; 7 more were left as 0 placeholders. With deskstack's data: 0 of 1,021, at a third of the cost ($0.17-0.22 vs $0.56 per table) and 3-5× faster ([analysis](bench/results/2026-11-09T13-04-05-468Z/ANALYSIS.md)).

## Install in 30 seconds

1. **Data:** in Claude, open **Settings → Connectors → Add custom connector** and paste
   `https://deskstack.deskstack-server.workers.dev/mcp`, with no sign-in. You can also run your own copy ([self-hosting](docs/SELF_HOSTING.md)).
2. **Roles:** open **Customize → Plugins → Add marketplace**, paste `https://github.com/joaquimmj/deskstack`, then
   install **deskstack**. In Claude Code: `/plugin install deskstack --marketplace joaquimmj/deskstack` (2.1.275+).
3. **Try it:** `/deal-team Apple quick-dcf`.

The tutorial walks through a first reviewed DCF in about 10 minutes: [English](docs/TUTORIAL.md) ·
[français](docs/TUTORIEL.md).

## The roles

| Command | Role | What it does |
|---|---|---|
| `/analyst` | Builder | Pulls cited data, agrees the assumptions with you, builds the workbook (blue inputs, a Sources sheet, a disclaimer) |
| `/associate` | Tie-out | Checks every typed number against the filing with `verify_value`, and flags wrong scale, sign, period, line item or currency |
| `/vp-review` | Model review | Runs 15 deterministic checks (hardcodes, broken rows, balance sheet, terminal value…), then compares the assumptions with filed history |
| `/md-redteam` | Challenge | Sensitivities, the assumptions the market price implies, the top five objections |
| `/compliance` | Hygiene | Disclaimer, citations, dated user inputs, no sign of non-public information, no buy/sell language |
| `/sign-off` | Human gate | One page of every check. A signed copy is exported only after you approve in your own words |
| `/deal-team` | Orchestrator | Runs the whole sequence |

Reviewers report; they never edit. In Claude Code and Cowork, they run as separate agents that don't see the
builder's reasoning. Details: [docs/ROLES.md](docs/ROLES.md).

**Companion mode.** The reviewers also work on models built by Anthropic's `financial-analysis` plugin, and merge its
`audit-xls` findings.

## Data sources and coverage

| Data | Source | Coverage |
|---|---|---|
| Financial statements (US) | SEC EDGAR XBRL (10-K, 10-Q, 20-F) | US-listed companies, including IFRS foreign filers; annual years plus LTM |
| Financial statements (EU) | ESEF annual reports via [filings.xbrl.org](https://filings.xbrl.org) | About 30 large issuers in France, the Netherlands, Spain, Finland, Italy and Belgium; annual |
| Risk-free rates | U.S. Treasury par yield curve; ECB euro area par yields | Daily, 1 month to 30 years |
| Exchange rates | ECB reference rates | 30+ currencies, latest, on a date or as a period average |
| Valuation inputs | Aswath Damodaran's public datasets (NYU Stern) | ERP and country risk by country; betas and cost of capital by industry |

Every value carries its source: filing, accession or report, period. The 8 tools are documented in
[docs/TOOLS.md](docs/TOOLS.md). Terms and attribution for each source are in [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md).

## Accuracy

- **The golden set:** 100 questions with known answers from the filings. It covers:
  - US and EU issuers, and IFRS 20-F filers;
  - a bank;
  - restatements and a stock split;
  - 52/53-week years, and fiscal years ending in January, March, June and September.
- **Every push:** every question must pass through the real tools on recorded data. Today: 100%.
- **Nightly:** an independent re-read of each answer from the filing itself, with edgartools for SEC and Arelle for
  ESEF. Details: [evals/README.md](evals/README.md).

## Limitations

- No share prices: a market cap needs a price you give.
- No consensus estimates.
- European coverage is partial and annual only. There are no German issuers, because their reports aren't in the
  public ESEF repository.
- IFRS 20-F filers have no LTM.
- Banks and insurers are flagged; EBITDA and EV metrics don't apply to them.
- **Reviewers reduce errors but don't replace a human reviewer.** Everything is a draft until you sign it off.

## How it stays free

- **Free hosting:** the server runs on Cloudflare Workers' Free plan, with a daily cap and a per-IP limit.
- **Static snapshot:** SEC data comes from a nightly snapshot served as static files.
- **Self-hosting:** your own copy takes a few minutes and costs nothing ([docs/SELF_HOSTING.md](docs/SELF_HOSTING.md)).
- **Privacy:** the server stores no user data and logs no prompts ([PRIVACY.md](PRIVACY.md)).

## Contributing

You can add a data source, a checker rule, a role, golden questions or benchmark companies. See
[CONTRIBUTING.md](CONTRIBUTING.md).

```bash
cd server && npm ci && npm test           # data server (TypeScript, Cloudflare Worker)
python3 -m pytest checker/tests           # checker and plugin scripts (Python, openpyxl)
```

## Credits

- **SEC XBRL standardization:** first solved by [open-finance-mcp](https://github.com/nathanaelhub/open-finance-mcp)
  by Nathanael Johnson (MIT). deskstack ports it to TypeScript with parity tests.
- **Bundled code:** openpyxl and et_xmlfile (MIT), vendored in the plugin.
- **Third-party data:** SEC EDGAR, XBRL International's filings.xbrl.org, U.S. Treasury, ECB statistics, and Aswath
  Damodaran (NYU Stern).

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

Independent open-source project. Not affiliated with or endorsed by Anthropic. Data may be incomplete or delayed;
verify against the cited filing. Not investment advice. MIT license.
