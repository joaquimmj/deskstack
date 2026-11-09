# deskstack plugin

A deal team for financial models inside Claude. Each role has one job:

- **`/analyst`** builds a cited Excel model (quick DCF or comps) from free SEC and EU ESEF filings data.
- **`/associate`** ties every hardcoded number back to the filings.
- **`/vp-review`** checks the model.
- **`/md-redteam`** argues against it.
- **`/compliance`** checks hygiene.
- **`/sign-off`** waits for your approval before anything is exported.
- **`/deal-team`** runs them all in order.

Reviewers report; nothing changes without your OK.

## Install

1. **Connector (data).** In Claude, open **Settings → Connectors → Add custom connector**. Paste
   `https://deskstack.deskstack-server.workers.dev/mcp`, with no sign-in. In Claude Code the plugin declares the connector itself (`.mcp.json`).
2. **Plugin.** Open **Customize → Plugins → Add marketplace**, paste this repository's GitHub URL, then install
   **deskstack**.

In Claude Code, the same in one line:

```
/plugin install deskstack --marketplace joaquimmj/deskstack
```

This needs Claude Code 2.1.275 or later. On older versions run `/plugin marketplace add joaquimmj/deskstack`, then
`/plugin install deskstack@deskstack`.

## Skills

| Skill | Role | What it does |
|---|---|---|
| `analyst` | Builder | Pulls cited data, agrees the assumptions with you, builds the workbook (blue inputs, Sources sheet, disclaimer), self-checks, hands off for review |
| `associate` | Tie-out | Extracts every typed number, runs `verify_value` in batches, reports match / mismatch / not found with scale, sign, period and line-item hints |
| `vp-review` | Model review | Checker rules DS001–DS020 (audit-xls table format), then assumptions vs filed history |
| `md-redteam` | Challenge | Sensitivities, the WACC × growth grid, the assumptions the price implies, top 5 objections, IC questions |
| `compliance` | Hygiene | Disclaimer, every number cited, dated user inputs, no sign of non-public information, no buy/sell language |
| `sign-off` | Human gate | One page of every check. A signed copy is exported only after you approve in your own words; open blockers need your stated reason |
| `deal-team` | Orchestrator | analyst → associate → VP → fixes → MD → compliance → sign-off, with progress at each step |
| `conventions` | House rules | Formatting, sourcing, units, disclaimer |
| `guide` | Help | Plain-language explanations (EN/FR) and setup |
| `quick-dcf`, `comps`, `company-snapshot`, `wacc`, `eu-company` | One-shots | Common tasks; follow with `/associate` and `/vp-review` |

**Agents** (Claude Code and Cowork): `deskstack:associate`, `deskstack:vp-review` and `deskstack:md-redteam` run the
reviews in a separate context, so they don't see the builder's reasoning. In chat, open a new conversation for the review.

**Scripts** run inside the skill folder with Python 3.8+ and no installs. openpyxl and the checker are vendored
under `scripts/_vendor/` (MIT; see `_vendor/NOTICE.md`). They never call the network: tool calls happen in the
conversation.

**Companion mode:** `/associate` and `/vp-review` also review workbooks built by other plugins, such as Anthropic's
`financial-analysis`, and merge an `audit-xls` findings table with their own.

Privacy: [PRIVACY.md](../../PRIVACY.md). Independent open-source project. Not affiliated with or endorsed by Anthropic. Outputs are drafts for human review,
not investment advice. License: MIT.
