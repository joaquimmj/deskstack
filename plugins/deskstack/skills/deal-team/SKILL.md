---
name: deal-team
description: Runs the whole deal team on a company: analyst builds, associate ties out, VP reviews, analyst fixes, MD red-teams, compliance checks, then you sign off. Use for "/deal-team <company> <task>".
argument-hint: "<company> <quick-dcf|comps>"
---

# Deal team: the full pipeline

Run the steps in order. Show progress after each one: `Step 3/7: VP review — 0 blockers, 2 majors`. Each step
follows its own skill. Reviewers report and never edit; the analyst applies fixes **only with the user's OK**.

| # | Step | Skill | Output |
|---|---|---|---|
| 1 | Build | `analyst` | Workbook in `out/` (agree the assumptions with the user first) |
| 2 | Tie-out | `associate` | Tie-out report + the path of `tieout.json` |
| 3 | Model review | `vp-review` | Review report + the path of `review.json` |
| 4 | Fixes | `analyst` | Show the findings; apply the ones the user accepts (edit the spec, rebuild); re-run steps 2–3 on the new file |
| 5 | Red team | `md-redteam` | Red-team memo + the path of `redteam.md` |
| 6 | Compliance | `compliance` | `compliance.json` |
| 7 | Sign-off | `sign-off` | Summary (with its approval token) from the report paths above, then **wait** for the user's approval before any export |

## Independence (who sees what)

- **Claude Code and Cowork:** run steps 2, 3 and 5 as the `deskstack:associate`, `deskstack:vp-review` and
  `deskstack:md-redteam` agents.
  - Pass each agent only the workbook path, the company and, for the red team, the user's share price.
  - Never pass your reasoning or the assumptions' rationale, and never use a fork.
  - Each agent returns its report and the path of its JSON or memo file; pass those paths to sign-off.
  - After a fix round, re-run every review: reports from the old file are stale.
- **Chat:** there are no separate agents.
  - Run the review steps here, re-deriving from the file and the tools only, and treat the build step's claims as
    unverified.
  - Tell the user that a fresh conversation per review is the more independent option.

## Rules

- **Stop at step 1** if the company is a bank or insurer and the task is a DCF: say why, and offer comps (P/E, P/B).
- **Missing data:** if a tool fails or data is missing, say so and ask. Never fill numbers from memory.
- **Fix loop:** at most two rounds (steps 2–4). Anything still open goes to sign-off as an open item.
- **Export:** only step 7 exports, and only after the user approves in their own words.

## Final message

1. Valuation summary.
2. A table of the seven steps with their status.
3. Open items.
4. Files written.
5. End with: "Draft for human review. Not investment advice."
