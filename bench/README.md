# deskstack-bench

How many numbers in an AI-built financial model are wrong or unsourced, with and without deskstack (brief §8.2).

## Design

| | |
|---|---|
| **Set** | `companies.json`: 50 companies (35 US, 15 EU), mixed sectors, no banks or insurers. Frozen on 2026-11-08 before any run. The pilot is the 5 flagged `pilot` (Apple, Coca-Cola, Caterpillar, TotalEnergies, Inditex) |
| **Tasks** | A quick DCF and a comps table, from scratch |
| **Arm A** | Claude with web search only |
| **Arm B** | Claude with the deskstack data tools |
| **Arm C** | B, then one review round, then a fix. The review is the associate's tie-out (`verify_value` on every filed figure) and the VP's deterministic checker findings |
| **Model** | `claude-sonnet-5-5`, effort `medium`, the same frozen prompts for every arm (`server/bench/prompts.ts`, v2). They give every arm the same conventions: positive capex and D&A, and the EBITDA and net-debt definitions. Only the tools differ, and B and C also get the deskstack server's MCP instructions, as real MCP clients do |
| **Output** | Every arm submits the same structured model (deskstack's builder spec) through `submit_model`. The builder validates it: missing sources, rates typed as percents, WACC ≤ g. Its errors go back to the model to fix |

## Scoring (automatic, against the filings; no human grading)

| Metric | Definition |
|---|---|
| Wrong vs filing | Reported lines that `verify_value` finds different from the filing and that match no other line of it, over all filed figures checked. Filed figures are history lines, net debt and diluted shares for a DCF; revenue, EBITDA, net income and net debt for comps. Each mismatch carries its likely cause from the hint: scale, sign, currency, period, line item or other |
| Other line of the filing | The value equals another line of the same filing, or two lines added, to the precision written (revenue excluding excise taxes, capex including leased equipment). Facts come from the filing itself: SEC companyfacts or the ESEF report. Reported, not counted as wrong |
| Other definition | EBITDA or net debt different from deskstack's definition. Definitions vary, so reported, not counted as wrong (a computed figure that is plainly wrong lands here too) |
| Not verifiable | The line isn't reported for that period, the period is ambiguous, or a peer can't be resolved by name with `company_lookup`. Colliding tickers (MC is LVMH in Paris and Moelis in New York) are never scored against the wrong company. Reported separately, never counted as wrong |
| Unsourced | Typed numbers whose source is missing, a placeholder, or "not found" |
| Checker | Blockers and majors per model, from the deterministic checker on the built workbook |
| Cost, tokens, time | Per run, from the API's usage |

**Caveats**, stated in every results page:
- The oracle is deskstack's own `verify_value`, and B and C read the same data, so their tie-out is partly true by
  construction. The comparison that matters is A against B and C.
- `verify_value` itself is checked against the filings by independent parsers (`evals/differential`).
- Arm C sees the tie-out before fixing, by design.

## Running it

```bash
cd server
npx tsx bench/run.ts --connector https://<worker>.workers.dev/mcp                          # dry run: plan + estimate, sends nothing
ANTHROPIC_API_KEY=... npx tsx bench/run.ts --connector URL --set pilot --budget 20 --i-approve-spend
SEC_USER_AGENT="name email" npx tsx bench/run.ts --rescore ../bench/results/<run> --connector URL  # score again, no API calls
```

- **Second reading.** Set `SEC_USER_AGENT` (SEC asks for a contact) so the scorer can look for other lines in SEC
  filings; ESEF reports need nothing. Without it, SEC mismatches on reported lines stay counted as wrong.

- **Budget.** `--budget` is a hard cap on the spend recorded in `bench/results/ledger.json`.
  - The ledger is written after every request, so a crash and a re-run continue from what was already spent.
  - Before each request, the runner computes the most it could cost: all input billed as a cache write, the full
    `max_tokens` of output, and every allowed search. It refuses the request if that could cross the cap.
  - A timed-out request is counted at that worst case.
  - The SDK's own retries are off. Only 429/529 are retried, because those aren't billed.
  - `--max-run-cost` (default $1.50) stops a runaway run the same way. Arm A's comps needs about 3: with web pages
    in context, the worst case of one more request is near $1.
- **Order.** Runs go company by company, arms A, B, C, so a stop leaves paired sets. The summary only compares
  company-tasks where every arm ran.
- **Prices.** The prices used are printed at start (`server/bench/pricing.ts`). Check them against the live
  pricing page before a paid run.
- **Before deploy.** The pilot can run against a local `wrangler dev` with the fixture snapshot. Its 5 companies are
  all in the fixtures.
- **Output.** Results land in `bench/results/<timestamp>/` and are meant to be committed:
  - `plan.json`;
  - one `runs/<company>-<task>-<arm>.json` per run, with the full transcript, the submission and the score;
  - `summary.json` and `summary.md`.

**Status:** the runner and scorer are built and tested offline with a scripted model (`server/test/bench.test.ts`).
No paid run yet. The $20 pilot is approved (see `COST_ESTIMATE.md`) and waits for the API key.
