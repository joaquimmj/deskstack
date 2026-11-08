# Roles

The deskstack plugin adds a deal team to Claude. Each role is a skill with one job, a checklist and a fixed output.
Roles never fix each other's work silently:

- reviewers report;
- the analyst applies fixes only when you agree;
- nothing is exported before you sign off.

| Command | Role | Output |
|---|---|---|
| `/analyst <company> <quick-dcf\|comps>` | Builds the deliverable from deskstack data. It agrees the assumptions with you first, cites every typed number, and asks rather than invents | An Excel workbook: blue inputs, black formulas, green links, a Sources sheet, a Cover with the disclaimer |
| `/associate` | Extracts every typed number and ties it to the filing with `verify_value` | A tie-out report: each number, its status, the filed value, the note and the source; problems first |
| `/vp-review` | Runs the checker's 15 rules, then compares the assumptions with filed history | A review report, ranked blocker / major / minor, with cell references, in the `audit-xls` table format |
| `/md-redteam` | Argues against the valuation | A memo: the top five objections with their value-per-share impact, the bear case, what the market price implies, the questions for the analyst |
| `/compliance` | Runs hygiene checks | A pass/fail list: disclaimer, citations, dated user inputs, no sign of non-public information, no buy/sell or promise language, no external links, no hidden sheets |
| `/sign-off` | The human gate | One page of every check and every open item, with an approval token. A signed copy is written only after you approve in your own words (see below) |
| `/deal-team <company> <task>` | Runs the whole sequence: analyst → associate → VP → fixes → MD → compliance → sign-off | Every report above, with progress at each step |

**Sign-off.** The gate keeps you in control of the export:

- Every open blocker needs your stated reason.
- A refusal, a question or a condition ("not yet", "approve once fixed") is never taken as approval.
- If the file changed after the reviews, the export is refused.

**One-shot skills:** `/quick-dcf`, `/comps`, `/company-snapshot`, `/wacc`, `/eu-company`, `/guide`. A `conventions`
skill holds the house rules every role follows.

## Independence

Reviewers must not inherit the builder's reasoning.

- **Claude Code and Cowork:** `/associate`, `/vp-review` and `/md-redteam` run as separate, read-only agents
  (`deskstack:associate`, `deskstack:vp-review`, `deskstack:md-redteam`). Each gets only the workbook path and the
  company.
- **Chat:** there are no separate agents. The reviewer skills re-derive everything from the file and the tools, and
  treat the builder's claims as unverified. For a clean review, open a new conversation, upload the workbook and run
  `/associate`.

## Scripts

- **Where they run:** the deterministic parts (checker, tie-out extraction, sensitivities, compliance, sign-off) are
  Python scripts inside each skill's folder. They need no installs: openpyxl is bundled.
- **Network:** none. Every tool call happens in the conversation.

## Companion mode

`/associate`, `/vp-review`, `/md-redteam` and `/sign-off` work on any workbook, including one built by Anthropic's
`financial-analysis` plugin. `/vp-review` merges an `audit-xls` findings table with its own: findings both tools
raised are marked `both`.
