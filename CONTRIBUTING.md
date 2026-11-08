# Contributing

Thanks for helping. Every change keeps four promises:

- every number is cited;
- the service stays free to run;
- reviewers report rather than edit;
- checks use only public, widely known practice.

## Ground rules

- **Data:** official or openly licensed sources only. Record their terms in `docs/DATA_SOURCES.md` before
  integrating. No scraping of sites whose terms forbid it.
- **Missing values stay `null`.** Never fill a gap with an estimate.
- **Code reuse:** MIT, Apache or BSD, with a notice in `THIRD_PARTY_NOTICES.md` and a header in the adapted file.
  No GPL or AGPL code.
- **Tests first:** a bug gets a failing test before the fix.
- **No secrets in the repo,** and no personal data in fixtures.

## Setup

```bash
cd server && npm ci && npm test                  # data server: TypeScript, Cloudflare Worker, Vitest
python3 -m venv checker/.venv && checker/.venv/bin/pip install openpyxl==3.1.5 pytest
checker/.venv/bin/python -m pytest -q checker/tests
```

## Common contributions

### Add a data source

1. **Terms.** Write the source's terms, limits and attribution in `docs/DATA_SOURCES.md`.
2. **Code.** Add the fetcher and parser under `server/src/`, with recorded fixtures in `server/test/fixtures/`.
3. **Tool.** Expose it through a tool in `server/src/tools.ts`. Give it a precise description: the description is
   the user experience.
4. **Golden questions.** Add them for the new data (below).

### Add a checker rule

1. **Rule.** Add it to `checker/deskstack_check/rules.py`, with an id (`DS016`), a severity, and an entry in
   `RULE_INFO`: category and suggested fix.
2. **Tests.** Plant the error in the synthetic model (`checker/tests/test_rules.py`) and check it fires. Check that
   the clean model stays clean.
3. **Vendored copies.** Run `python3 plugins/sync_vendor.py`; the plugin ships a copy of the checker.

### Add a role

1. **Skill.** Write `plugins/deskstack/skills/<name>/SKILL.md`: one job, a checklist, a fixed output. Keep the
   description under 200 characters.
2. **Agent.** A reviewer also gets a read-only agent in `plugins/deskstack/agents/`.
3. **Validate.** Run `claude plugin validate --strict plugins/deskstack`.

### Add golden questions

1. **Questions.** Add them to `evals/build_golden.py`: the company, the period, and the concept as it appears on the
   face of the statements.
2. **Regenerate.** Run `python3 evals/build_golden.py`.
3. **Check.** `cd server && npx vitest run test/golden.test.ts` must stay at 100%.

### Add benchmark companies

`bench/companies.json` is frozen once a run uses it. Add a new set file rather than editing it, and say why in the
pull request.

## Pull requests

- **Scope:** one change per pull request, with tests.
- **Description:** say what a user sees differently.
- **Format:** commit messages say what changed and why.
