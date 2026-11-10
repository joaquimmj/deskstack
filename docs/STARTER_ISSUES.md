# Starter issues

Ten small issues for a first contribution, ready to open with the `good first issue` label. Each says where to work
and when it's done. CONTRIBUTING.md has the setup and the four promises every change keeps.

## 1. Glossary entries for the newer checker rules

**Labels:** `good first issue`, `docs`

The `/guide` skill explains terms in English and French from `plugins/deskstack/skills/guide/references/glossary.md`.
It has no entry for the five rules added most recently: DS016 (placeholder 0), DS017 (a synthetic series), DS018 (a
plug), DS019 (interest and debt) and DS020 (a flat share count).

**Where:** the glossary. The rule texts are in `checker/deskstack_check/rules.py` (`RULE_INFO`) and
`checker/README.md`.

**Done when:** each rule has a short EN and FR entry in the glossary's format, saying what the rule catches and why it
matters.

## 2. `deskstack-check --ignore DS010`

**Labels:** `good first issue`, `checker`

Teams sometimes accept a finding on purpose, such as a terminal value above 75% of EV. Today they can only lower
`--fail-on`.

**Where:** `checker/deskstack_check/cli.py`, tests in `checker/tests/test_cli.py`, and the `action.yml` inputs.

**Done when:** `--ignore DS010,DS017` drops those rules from the report and from the exit code; the report says
which rules were ignored; tests cover both.

## 3. `deskstack-check rules`

**Labels:** `good first issue`, `checker`

There is no way to list the checks from the command line.

**Where:** `checker/deskstack_check/cli.py`, which reads `RULE_INFO` in `rules.py`.

**Done when:** `deskstack-check rules` prints each rule's id, severity, category and suggested fix, and a test checks
that every rule appears.

## 4. A rule for a percentage typed as a whole number

**Labels:** `good first issue`, `checker`, `rule`

An assumption cell holding `5` where the model means 5% (0.05) makes growth 500%. It's a widely known modelling
error.

**Where:** a new DS021 in `checker/deskstack_check/rules.py`, with its `RULE_INFO` entry and a row in
`checker/README.md`. Tests in `checker/tests/test_rules.py`.

**Done when:** a typed value above 1 in a row labelled as a rate (growth, margin, tax rate, WACC) is flagged; the
clean demo models stay clean; `python3 plugins/sync_vendor.py` has refreshed the plugin's copies.

## 5. `data_status` shows how old the snapshot is

**Labels:** `good first issue`, `server`

`data_status` returns the snapshot's `built_at`. Users then work out its age themselves, and `/deskstack-doctor` asks
Claude to.

**Where:** `server/src/tools.ts` (`data_status`), test in `server/test/server.test.ts`.

**Done when:** the response adds `snapshot.age_hours`, computed from `built_at` at call time, with a test.

## 6. Annotations from the GitHub Action

**Labels:** `good first issue`, `github action`

The Action writes its report to the job summary. Annotations (`::warning file=…::message`) would also show each
finding on the workflow run.

**Where:** `action.yml`, using `deskstack-check --json`.

**Done when:** an `annotate` input (default on) prints one annotation per blocker or major finding, naming the
workbook, the cell and the rule; the CI job in `.github/workflows/ci.yml` still passes.

## 7. Macro-enabled workbooks

**Labels:** `good first issue`, `checker`

Many models are saved as `.xlsm`. It isn't tested whether `deskstack-check` reads them, and the Action only looks for
`.xlsx`.

**Where:** `checker/deskstack_check/model.py`, `action.yml`, tests in `checker/tests/test_cli.py`.

**Done when:** a test checks an `.xlsm` file (macros are never run); the Action's default pattern includes `.xlsm`.

## 8. How to record an ESEF fixture

**Labels:** `good first issue`, `docs`

CONTRIBUTING.md says to add recorded fixtures for a new source, but not how to record a European report:
`server/scripts/build-esef.ts --only <LEI> --cache …` writes the extractions that `server/test/fixtures/esef/` holds.

**Where:** CONTRIBUTING.md, from `server/scripts/build-esef.ts` and `server/test/golden.test.ts`.

**Done when:** a short section walks through recording one issuer's reports and adding its golden questions, and
someone else has followed it once.

## 9. More issuers from Sweden, Norway and Belgium

**Labels:** `good first issue`, `data`

These countries have 3 issuers each in `server/data/eu-issuers.json`, against 34 for France.

**Where:** `server/data/eu-issuers.json`, then `npx tsx server/scripts/build-esef.ts --only <LEI,LEI>`. Golden
questions go in `evals/build_golden.py`.

**Done when:** five large listed issuers from these countries are added; each one's build is clean (nothing in
`coverage.json`'s rejected list); each country keeps at least 10 golden questions, with Arelle's answers.

## 10. Golden questions for a fiscal year ending in May

**Labels:** `good first issue`, `evals`

The golden set covers fiscal years ending in January, February, March, June and September. FedEx's ends in May, and
the benchmark found a model using FedEx's fiscal year as its last twelve months.

**Where:** a trimmed SEC fixture in `server/test/fixtures/sec/` (see its README), questions in
`evals/build_golden.py`.

**Done when:** at least 5 questions for FedEx (revenue, operating income, net income for two years, plus the LTM)
pass in `server/test/golden.test.ts`, and their answers come from the filings.
