# Your first reviewed DCF in Claude, in 10 minutes

You'll build a quick DCF of Apple from its filings, have every number checked against the 10-K, get the model
reviewed and challenged, and sign it off. No terminal needed.

**You need:**
- A Claude account. Plugins need a paid plan. A free account can add one custom connector and use the data tools
  without the roles.
- Code execution turned on, in **Settings → Capabilities**. The roles run small scripts in Claude's sandbox.

## 1. Add the data connector (1 minute)

1. **Open the dialog:** in Claude, go to **Settings → Connectors → Add custom connector**.
2. **Fill it in:** name it `deskstack` and paste `https://deskstack.deskstack-server.workers.dev/mcp`. No sign-in is needed. You can also run your own copy
   ([self-hosting](SELF_HOSTING.md)).
3. **Check it works:** ask *"Using deskstack, what was Apple's revenue in FY2025? Cite the filing."* The answer
   should name the 10-K and its accession number.

## 2. Add the deal team (1 minute)

1. Go to **Customize → Plugins → Add marketplace**.
2. Paste `https://github.com/joaquimmj/deskstack`.
3. Install **deskstack**. The commands `/analyst`, `/associate`, `/vp-review`, `/md-redteam`, `/compliance`,
   `/sign-off` and `/deal-team` appear.

## 3. Build the model (3 minutes)

Type `/analyst Apple quick-dcf`. The analyst:

1. **Pulls the data.** It gets the last three fiscal years from the 10-K: revenue, operating income, D&A, capex. It
   also pulls a 10-year Treasury yield and Damodaran's equity risk premium.
2. **Shows a table of assumptions** (growth, margins, WACC, terminal growth), each with its reason. **Read it and
   change anything you disagree with**: this is your model.
3. **Builds the workbook:**
   - blue cells are inputs, black cells are formulas;
   - a **Sources** sheet cites every typed number;
   - the Cover says *Draft for human review. Not investment advice.*
4. **Runs the checker** on its own file and fixes what it can.

Download the workbook.

## 4. Have every number checked (2 minutes)

**Open a new conversation,** so the reviewer doesn't see how the model was built. Upload the workbook and type
`/associate`.

The associate ties every typed number to the filing. A typical report looks like this:

| # | Cell | Item | Period | Model value | Status | Filed value | Note |
|---|---|---|---|---|---|---|---|
| 1 | `Inputs!D5` | Revenue | FY2025 | 416,161,000 | mismatch | 416,161 | Scale: the value matches if it is in thousands, not millions |
| 2 | `Inputs!C5` | Revenue | FY2024 | 391,035 | match | 391,035 | |

A **mismatch** says why when it can tell:
- wrong scale;
- a flipped sign;
- last year's figure;
- a different line item;
- another currency.

**Not found** means the filing doesn't report that line for that period.

## 5. Review and challenge (2 minutes)

In the same review conversation:

- **`/vp-review`** runs 20 deterministic checks:
  - numbers typed inside formulas, and rows whose formula breaks the pattern;
  - an unbalanced balance sheet;
  - terminal value above 75% of EV, WACC too close to terminal growth.

  It then compares your assumptions with Apple's filed history.
- **`/md-redteam`** argues against the valuation. Give it today's share price and it tells you what the market
  implies: for example, *"at $230 the market implies a WACC of 6.0%"*. It also lists the five strongest objections,
  with their impact on value per share.
- **`/compliance`** checks the hygiene: disclaimer, citations, dated inputs, no sign of non-public information.

## 6. Fix, then sign off (1 minute)

1. **Fix.** Back in the first conversation, tell the analyst which findings to fix, and it rebuilds the workbook.
   Reviewers never change your file themselves.
2. **Sign off.** Run `/sign-off`. It shows one page: every check, every open item, and an approval token. Nothing is
   exported until you answer in your own words, for example *"I approve the export"*. Then:
   - you get a copy with a **Sign-off** sheet recording who approved, when, and what was still open;
   - a reply like *"not yet"* or *"approve once fixed"* is never taken as approval.

## The shortcut

`/deal-team Apple quick-dcf` runs all the steps above in order and stops at sign-off for your approval. In Claude
Code and Cowork, the reviewers run as separate agents automatically, so you don't need a new conversation.

## If something goes wrong

| Symptom | What to do |
|---|---|
| "connector not connected" | Check **Settings → Connectors**: deskstack must show *Connected* |
| The scripts don't run | Turn on code execution in **Settings → Capabilities** |
| A European company isn't found | Coverage is about 100 large issuers in 13 countries. Try its LEI, or ask `/eu-company` |
| A bank or insurer | A standard DCF doesn't fit them. The analyst offers P/E or P/B instead |
| "Free daily capacity is used up" | The shared service resets at 00:00 UTC; you can also [self-host](SELF_HOSTING.md) |

Everything deskstack produces is a draft for human review, not investment advice.
