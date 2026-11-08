# End-to-end runs (brief §8.3)

Ten scripted `/deal-team` runs in Claude Code, headless (`scenarios.json`). Each runs in a fresh temporary folder
outside the repo, with only the deskstack plugin and connector, a pinned model and no session persistence.

- With `ANTHROPIC_API_KEY` set, runs use `--bare`: no user settings, hooks, CLAUDE.md or other plugins. This bills
  the API key.
- Without it, runs use the signed-in account with `--setting-sources local`. User-level CLAUDE.md or skills can still
  load, so the summary records the mode. `grade.py` checks that:

- the expected deskstack tools were called;
- every workbook written has a Sources sheet and every typed number is cited;
- every figure labeled as filed appears in a tool result of the run (no invented numbers);
- the planted error is named in the review scenarios;
- nothing was exported: a headless run has no user approval, so any export breaks the gate;
- for a bank, the DCF is refused and the refusal explained.

```bash
python3 evals/e2e/run.py --connector https://<worker>.workers.dev/mcp                     # dry run: prints the plan
python3 evals/e2e/run.py --connector URL --only build-aapl-dcf --i-approve-usage          # runs one scenario
python3 evals/e2e/grade.py build-aapl-dcf evals/e2e/runs/<ts>/build-aapl-dcf/transcript.jsonl evals/e2e/runs/<ts>/build-aapl-dcf
```

**Usage.** Running spends model usage on the account Claude Code is signed in with. `run.py` passes
`--max-budget-usd` (default $1 per run) and does nothing without `--i-approve-usage`, which needs the project owner's
OK.

**Requirements.** It needs the connector deployed. Raw transcripts land in `runs/` (not committed). The grader is
tested on synthetic transcripts in `checker/tests/test_e2e_grader.py`.
