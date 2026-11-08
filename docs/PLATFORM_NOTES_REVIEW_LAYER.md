# Platform notes: review layer (skills, plugins, subagents, MCP, Excel)

Research date 2026-11-08. Only current official docs and the public `anthropics/financial-services` repo were read, read-only. Every fact carries a source key `[Sn]`. All sources were read on 2026-11-08 (see "Sources" at the end). **UNVERIFIED** marks anything no official page confirmed.

Surfaces, as the docs name them [S9]: **Chat** is claude.ai web, the desktop app's chat, and mobile. **Cowork** is Cowork tasks. **Claude Code** is the CLI, the IDE extensions, and the desktop Code tab.

---

## 1. Agent Skills: scripts, code execution, packages, network, size

| | Chat | Cowork | Claude Code |
|---|---|---|---|
| Can a skill bundle scripts that Claude runs? | Yes. The skill's whole folder, scripts included, is copied into the code-execution sandbox [S2] | Yes. `${CLAUDE_SKILL_DIR}` is substituted when the skill loads [S2] | Yes. A script run is a Bash tool call and needs permission (or `allowed-tools`) [S2][S12] |
| Where code runs | Code-execution sandbox (VM) [S1] | "an isolated environment on Anthropic's servers" [S11]. Desktop can also read and write local files [S11] | The user's own machine [S1] |
| Plans | Skills: Free, Pro, Max, Ultra, Team, Enterprise [S3][S4]. Custom skills: platform overview lists only Pro and up [S1]. The help center includes Free [S4]. **Conflict, treat Free as UNVERIFIED** | Pro, Max, Ultra, Team, Enterprise. Paid plans only [S11] | Any Claude Code user [S1] |
| Code execution on by default? | Required for skills [S3]. On by default for Free, Pro, Max, Ultra and Team, and for new Enterprise orgs. Team and Enterprise Owners can turn it off [S5] | Built in [S11] | n/a (local shell) |
| Read uploaded .xlsx and write a downloadable .xlsx | Yes. Uploads and downloads of .xlsx; "working formulas"; 30 MB upload and download limit [S5] | Yes. "preview and download" outputs, and local files on desktop [S11] | Yes. Local filesystem |
| Python packages | No official preinstalled list for claude.ai (**UNVERIFIED** whether openpyxl is preinstalled). With egress on, Claude can install from PyPI and npm [S5][S4]. With egress off: "pre-installed packages only" [S5] | **UNVERIFIED** (no package list published) | Whatever is installed locally. Install packages locally, not globally [S1] |
| For contrast: API code-execution container | Python 3.11. openpyxl, xlsxwriter, xlrd and pandas are preinstalled. No internet, no runtime installs [S6] | | |
| Network inside code execution | Individual plans: egress on, "allowing Claude to install packages from approved sources". Default domains: pypi.org, files.pythonhosted.org, github.com, npm, crates, Ubuntu, Yarn, api.anthropic.com [S5]. Team default is "package managers only" (the page contradicts itself on Team). Enterprise default is off. Owners can add domains or allow all [S5]. **Not stated** that individual users can allowlist a custom domain, so a script calling our MCP URL is effectively blocked | "Cowork respects your current network egress permissions"; egress rules "don't apply to the web fetch or web search tools or MCPs" [S11] | Full network, same as any local program [S1] |
| Size limits | Skill ZIP limit not published ("exceeds size limits" is listed as a failure cause) [S3][S4]. As a plugin: 200 MB and 5,000 files per plugin [S9] | Plugin: 200 MB uncompressed, 5,000 files, 25 marketplaces, 500 plugins per marketplace [S10] | No account limits [S9] |

SKILL.md frontmatter:
- `name` and `description` are required. `name` is at most 64 characters: lowercase letters, digits and hyphens, no "anthropic" or "claude", and it must match the folder name [S1][S2].
- `description` limits conflict across sources:
  - At most 1,024 characters per the platform docs and claude.com [S1][S2].
  - "200-character maximum" on claude.ai uploads per the help center [S4].
  - The Claude Code listing truncates `description` plus `when_to_use` at 1,536 characters [S12].
- The help center also lists an optional `dependencies` field, for example `python>=3.8, pandas>=1.5.0` [S4].
- Claude Code-only fields include `when_to_use`, `argument-hint`, `disable-model-invocation`, `user-invocable`, `allowed-tools`, `disallowed-tools`, `model`, `effort`, `context: fork`, `agent`, `background`, `hooks`, `paths` and `shell`. Claude Code ignores unknown fields [S12]. How claude.ai treats them is **UNVERIFIED**.

## 2. Plugins: component support and manifests

Component support by surface, verbatim from the official matrix [S9]:

| Component | Chat | Cowork | Claude Code |
|---|---|---|---|
| Skills `skills/<name>/SKILL.md` | Loads | Loads | Loads |
| Commands `commands/*.md` | "Loads as a skill; Claude applies it when it fits" | Loads; run as `/plugin-name:command` | Loads |
| Agents `agents/*.md` | **Ignored** | Loads | Loads |
| Hooks `hooks/hooks.json` | **Ignored** | Loads | Loads |
| Remote MCP (`http`/`sse`, fixed URL) | Listed on the plugin's Connectors tab; works once added or connected | Loads; connect from the Connectors tab | Loads |
| Local MCP (command or `.mcpb`) | Ignored | Only when the Cowork session runs on your computer | Loads |
| MCP that uses `${user_config.*}` | Ignored if in the URL | Ignored if an option has no default | Loads; prompts for values |
| Top-level `bin/` | **Can't be installed** | **Can't be installed** | Loads |
| LSP, output styles, themes, `settings` | Ignored | Ignored | Loads |

So our previous finding is **re-verified**: in chat, commands load as skills and agents and hooks are ignored [S9][S8]. Also new: a top-level `bin/` makes claude.ai and Cowork refuse the whole plugin. Put executables in `scripts/` [S7][S13].

Installs and sync:
- Chat and Cowork share the account install via Customize > Plugins. Account installs also reach Claude Code as "synced" plugins [S9][S8].
- Cowork does not read the CLI's `~/.claude` [S14].
- A self-added marketplace can be a GitHub or GHE repo, or a public GitLab or Bitbucket repo, given as `owner/repo` or a URL [S8][S10].
- Org sync requires private or internal repos and accepts relative `./` sources, `github`, `url` and `git-subdir` [S13].

**plugin.json** sits at `.claude-plugin/plugin.json` [S7].
- `name` is the only required key: kebab-case, no spaces, `@`, `:` or path separators. Names starting with `claude-` or `anthropic-` are errors [S7].
- The manifest itself is optional in Claude Code [S7]. The directory needs a README of at least 40 words and a license [S15].
- Fields every app reads: `name`, `displayName`, `version`, `description`, `author{name,...}`, `license` [S15].

**marketplace.json** sits at `.claude-plugin/marketplace.json`.
- Requires `name`, `owner` and `plugins[]`. Each entry needs `name` and `source` [S16].
- Keep the entry name equal to the manifest name [S16].
- Relative sources start at the marketplace root, with no `..` [S16].
- Official names such as `claude-plugins-official` are reserved [S16].

**Layout** [S7][S15]:

```
deskstack/.claude-plugin/plugin.json
deskstack/skills/<name>/SKILL.md (+ scripts/, references/, assets/)
deskstack/commands/*.md
deskstack/agents/*.md
deskstack/hooks/hooks.json
deskstack/.mcp.json
```

- `.mcp.json` remote entry: `{"mcpServers":{"x":{"type":"http","url":"https://…/mcp"}}}`. No secrets in it [S15].
- `"streamable-http"` is accepted as an alias of `"http"` in Claude Code [S17].

## 3. Subagents and separate context (reviewers must not see builder reasoning)

| | Chat | Cowork | Claude Code |
|---|---|---|---|
| Plugin `agents/*.md` | Ignored [S9] | Loads; "Specialists Claude can delegate part of a task to" [S8]. "Cowork also runs the plugin's agents" [S8] | Loads [S9] |
| Built-in parallel sub-tasks | None documented | "Sub-agent coordination … parallel workstreams" [S14][S11] | Subagents, forks, background agents [S18] |
| Context isolation documented? | n/a | **UNVERIFIED.** The help center doesn't say whether sub-agents get a separate context [S11]. Cowork "uses the same agentic architecture that powers Claude Code" [S14] | Yes: "Each subagent starts with a fresh, isolated context window. It doesn't see your conversation history" [S18] |

Claude Code details [S18]:
- **Agent file.** Markdown with YAML frontmatter. The body is the system prompt. `name` and `description` are required.
- **Optional fields:** `tools` (allowlist; omitting it inherits all tools), `disallowedTools`, `model`, `skills` (preloaded), `maxTurns`, `effort`, `omitClaudeMd`, and others.
- **Plugin agents ignore** `hooks`, `mcpServers`, `permissionMode` and `initialPrompt`.
- **Naming and calling.** Plugin agents are namespaced `deskstack:associate`, and subfolders become part of the name. Claude delegates automatically from `description`, by name ("Use the … subagent"), or by `@agent-<name>` mention.
- **What the subagent sees:** its own prompt, the delegation message, CLAUDE.md, a git status snapshot, and its preloaded skills. Only its final report returns.
- **Forks break isolation.** A fork "inherits the entire conversation", and fork mode is **on by default** (v2.1.302+).
- **Skills with `context: fork` + `agent:`** run the skill body as the task in a subagent that "doesn't see your conversation history" [S12]. The documented `agent:` targets are built-ins or `.claude/agents/`. Naming a *plugin* agent there is **UNVERIFIED** [S12].
- **Nesting.** Subagents can spawn subagents up to 3 levels down. Remove `Agent` from `tools` to stop it.
- **MCP tools in `tools`.** A plugin MCP tool's full name is `mcp__plugin_<plugin>_<server>__<tool>`. Use it in `tools`, `allowed-tools` and hook matchers [S17].

## 4. Skills calling connector (MCP) tools

| | Chat | Cowork | Claude Code |
|---|---|---|---|
| Skill instructs Claude to call a connector tool | Yes. Official example: "Call the expenses connector's `create_report` tool" [S15]. "A skill can tell Claude how to use a connector, but it can't reach the service itself" [S2] | Yes, same model [S15][S8] | Yes [S15][S17] |
| Connector must be | Added and connected. The plugin's Connectors tab shows Connected, Not connected or Not added. Skills load regardless, but can't reach the service until it's Connected [S8] | Same [S8] | Loaded from `.mcp.json` directly [S15] |
| Custom remote connector | All plans; "Free users are limited to one custom connector"; "No sign in" (authless) option; must be reachable from Anthropic IPs; Team and Enterprise Owners add it, members connect [S19] | Same [S19] | `claude mcp add --transport http` or plugin `.mcp.json` [S17] |

Naming:
- No naming convention is documented for chat or Cowork. Docs refer to the tool by connector name plus tool name in prose [S15].
- In Claude Code a plugin server's tools are `mcp__plugin_deskstack_<server>__financial_statements` [S17].
- claude.ai connectors appear as `claude.ai <Name>` servers [S17]. Their callable prefix is **UNVERIFIED**. In this desktop session, connector tools surfaced under opaque `mcp__<uuid>__…` names (observed, not documented).
- If our server is also in the directory, use the same URL in `.mcp.json` "so that someone who has both … sees one set of tools" [S15].

## 5. Built-in Excel capabilities

- **Chat file creation** (Settings > Capabilities > "Code execution and file creation"):
  - Creates .xlsx "with working formulas and calculations" and "proper formulas, formatting, and even charts" [S5].
  - Uses the prebuilt `xlsx` Agent Skill: "Create spreadsheets, analyze data, generate reports with charts". It is available on claude.ai and the API, **not** in Claude Code [S1].
- **Cowork:** "Creates polished deliverables including Excel spreadsheets with functional formulas" [S14].
- **Claude for Excel add-in.**
  - Plans: Pro, Max, Team, Enterprise [S20].
  - Runs in Excel web, Windows M365 build ≥16.0.13127.20296, and Mac ≥16.46 [S20].
  - Edits live workbooks: cell-level citations, assumption changes that keep formula relationships intact, error tracing (#REF!, #DIV/0!), building and populating models, sort/filter/pivot/conditional formatting/validation [S20].
  - Unsupported: data tables, macros and VBA [S20]. "Not recommended for … Audit-critical calculations without verification" [S20].
  - Uses enabled Skills and connectors from Claude settings; invoke a skill by typing `/` in the sidebar [S21].
  - Whether it runs skill *scripts* is **UNVERIFIED**.
  - Plugins (as opposed to skills) in the add-in: **UNVERIFIED**.

## 6. anthropics/financial-services (companion mode targets)

Read via `gh api` (repo pushed 2026-10-28) [S22]. Marketplace name `claude-for-financial-services`.

Plugins:
- **Vertical:** financial-analysis (core), investment-banking, equity-research, private-equity, fund-admin, operations.
- **Agent plugins:** pitch-agent, market-researcher, earnings-reviewer, meeting-prep-agent, model-builder, gl-reconciler, kyc-screener, valuation-reviewer, month-end-closer, statement-auditor.
- **Partner:** lseg, sp-global. Plus claude-for-msft-365-install.
- The official install guide lists the financial-analysis core plus IB, ER and PE add-ons; the core bundles data connectors (Daloopa, Morningstar, S&P, FactSet, Moody's, LSEG, PitchBook and others) [S23].

Review and QC skills in the repo (data, not docs) [S22]:
- **`audit-xls`** (identical copy, sha a2cae1d, in financial-analysis and six agent plugins). Scope: selection, sheet or model.
  - Formula checks: errors, hardcodes in formulas, inconsistent or off-by-one ranges, pasted-over values, circular references, broken links, unit mismatches, hidden rows.
  - Model checks: BS balance, RE rollforward, cash tie-out, CF sums, D&A/CapEx/WC, tax and share count, TV dominance, plus DCF, LBO, merger and 3-statement bugs.
  - **Output:** a markdown table `| # | Sheet | Cell/Range | Severity | Category | Issue | Suggested Fix |`. Severity is Critical, Warning or Info. Model scope prepends `Model type: [...] — Overall: [Clean / Minor Issues / Major Issues] — [N] critical, [N] warnings, [N] info`. "Don't change anything without asking".
- **`xlsx-author`.** Headless writer: openpyxl, output to `./out/<name>.xlsx`. Conventions: blue, black and green colouring; no hardcodes in calc cells; named ranges; a Checks tab with TRUE/FALSE ties. It defers to `mcp__office__excel_*` tools "If … available (Cowork plugin mode)". That office MCP is **UNVERIFIED** in official docs.
- **Other QC skills:** `clean-data-xls` (data hygiene; Office JS when in Excel) and `ib-check-deck` (deck number consistency and narrative).
- **Command `/debug-model [path to .xlsx]`** loads `audit-xls` with scope model.
- **Agents:**
  - `statement-auditor`: `tools: Read, Grep, Glob, mcp__nav__*`; tie-out table, exception list, sign-off sheet.
  - `model-builder`: `tools: Read, Write, Edit, mcp__capiq__*, mcp__daloopa__*`.
  - The managed-agent cookbook `model-builder/subagents/auditor.yaml` is a read-only `model-auditor` with only read and grep tools, `mcp_servers: []`, and skill `audit-xls`. It re-checks `./out/model.xlsx` and returns a pass/fail report. This is their own pattern for an independent reviewer.

---

## Design implications for deskstack

1. **The checker is a Python script inside each reviewer skill, not an executable.**
   - Ship it under `skills/<reviewer>/scripts/` (or a shared skill folder that every reviewer references by relative path).
   - Never use a top-level `bin/`, which blocks claude.ai and Cowork install [S9].
   - Reference it as `python3 ${CLAUDE_SKILL_DIR}/scripts/check.py` **and** keep it working from a path relative to `SKILL.md`, because chat copies the folder but doesn't substitute the variable [S2].
2. **Vendor pure-Python dependencies.** Package lists and egress vary: Team and Enterprise can be off or package-managers-only, and claude.ai doesn't publish its package list [S5].
   - Try `import openpyxl`. On ImportError, fall back to `pip install --user openpyxl`, then to a vendored copy in `scripts/_vendor/`. openpyxl and its dependency et_xmlfile are pure Python and MIT-licensed, which fits `THIRD_PARTY_NOTICES.md`.
   - In Claude Code, install into `${CLAUDE_PLUGIN_DATA}` rather than globally [S1][S7].
3. **Scripts never call the network or the MCP server.** Chat egress usually allows only package registries [S5]. Have Claude call connector tools (e.g. `financial_statements`), write the returned JSON to a file, and pass that file to the checker as input. MCP calls bypass the egress setting [S5][S11].
4. **Independence per surface:**
   - **Claude Code:** ship `agents/associate.md`, `agents/vp-review.md` and `agents/md-redteam.md`.
     - Use `tools: Read, Grep, Glob, Bash` (no Write/Edit), list the reviewer skill in `skills:`, and set `omitClaudeMd` if CLAUDE.md could leak builder notes.
     - The analyst skill ends with "Delegate review to the `deskstack:associate` subagent; pass only the workbook path and the spec" [S18].
     - Forbid forks for review: the instruction must name a subagent, because forks inherit the conversation and fork mode is on by default [S18].
     - Optionally make the reviewer skills `context: fork` with `agent: general-purpose` for isolation. Pointing `agent:` at a plugin agent is UNVERIFIED [S12].
   - **Cowork:** the same agents load [S9]. Isolation is UNVERIFIED, so treat it as best effort and keep the deterministic script as the authority.
   - **Chat:** no agents [S9], so true isolation is impossible in one conversation. Fallbacks:
     - The reviewer skill runs the checker script first and reports its findings verbatim, as deterministic and reasoning-free.
     - It instructs the reviewer persona to ignore the prior analysis and judge only the file plus the checker output.
     - Recommended: tell the user to start a **new chat**, upload the .xlsx, and run `/associate`. A fresh conversation is the only documented clean context. State this limitation in the README.
5. **Commands double as skills in chat** [S9]. Keep `commands/*.md` thin wrappers whose `description` doesn't hijack unrelated requests, or prefer skills only. Write descriptions to ≤200 characters for claude.ai upload safety [S4].
6. **Companion mode.** Parse findings tables shaped like `audit-xls`, `| # | Sheet | Cell/Range | Severity | Category | Issue | Suggested Fix |`, and its `Model type … Overall …` header line [S22].
   - Emit our own findings in a superset of that schema so outputs can be diffed.
   - Recognise `xlsx-author` conventions (Checks tab, blue/black/green colouring, `./out/*.xlsx`).
7. **Analyst skill and Excel.** Rely on the built-in file creation (xlsx skill) in chat and Cowork [S1][S5][S14]. In Claude Code the prebuilt xlsx skill is absent [S1], so the analyst must write openpyxl code itself (vendored).
   - openpyxl writes formulas but doesn't calculate them, so the checker must evaluate structure and formula text, not cached values, unless the workbook was saved by Excel. This is standard openpyxl behaviour, not from an Anthropic doc.
8. **Connector.** Declare `{"type":"http","url":…}` in `.mcp.json`. Users must still add and connect it in chat and Cowork; Free accounts get one custom connector [S8][S19]. Skills should name tools in prose ("the deskstack connector's `financial_statements` tool"), not with hard-coded `mcp__…` prefixes [S15][S17].
9. **Manifests.** Use a kebab-case `name` without "claude" or "anthropic" [S7]. Add a README of 40+ words and a license [S15]. Keep `marketplace.json` `name`, `owner` and `plugins[{name, source:"./plugins/deskstack"}]` with entry name equal to manifest name [S16].

## Verified locally (2026-11-08, M5)

- `claude plugin validate --strict .` (marketplace) and `claude plugin validate --strict plugins/deskstack` pass on
  Claude Code 2.1.317.
- The only plugin-directory warning is a missing icon. That matters only when submitting to the directory, and the
  logo is a launch item.
- Each script-running skill runs its vendored copy with `python -I -S`: no user site and no site-packages, so no
  installed openpyxl. That is the worst case for a claude.ai sandbox with egress off. Tests in
  `checker/tests/test_plugin_structure.py`.
- **Not yet tested on a live surface.** The connector isn't deployed yet, and running Claude Code headless would
  spend the owner's usage. This includes:
  - an install via "Add marketplace" in chat or Cowork;
  - the plugin agents' isolation;
  - skill script execution in claude.ai.

## Open questions / unverified

- Whether openpyxl is preinstalled in the claude.ai and Cowork sandboxes. Python version there.
- Whether individual (non-Team) users can allowlist a custom egress domain.
- Free plan custom-skill upload: the platform docs say Pro and up [S1], the help center says Free [S3][S4].
- Description limit: 200 [S4] versus 1,024 characters [S1][S2].
- Skill ZIP size limit in chat; only the plugin limits are published [S9][S10].
- Cowork sub-agent context isolation, and whether Cowork honours the `tools`, `model` and `skills` fields of plugin agents.
- Whether `context: fork` + `agent:` can target a plugin agent (`deskstack:associate`).
- The callable tool-name prefix for claude.ai connectors in Claude Code and Cowork.
- Whether the Excel add-in executes skill scripts. The `mcp__office__excel_*` tools referenced by `xlsx-author` [S22].
- How claude.ai treats Claude Code-only SKILL.md frontmatter fields.

## Sources (all read 2026-11-08)

- S1 https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- S2 https://claude.com/docs/skills/how-to
- S3 https://support.claude.com/en/articles/12512180-using-skills-in-claude
- S4 https://support.claude.com/en/articles/12512198-creating-custom-skills
- S5 https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude
- S6 https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool
- S7 https://code.claude.com/docs/en/plugins-reference
- S8 https://claude.com/docs/plugins/overview
- S9 https://claude.com/docs/plugins/platform-support
- S10 https://claude.com/docs/cowork/guide/plugins
- S11 https://support.claude.com/en/articles/13345190-get-started-with-cowork
- S12 https://code.claude.com/docs/en/skills
- S13 https://claude.com/docs/plugins/org-sync
- S14 https://claude.com/docs/cowork/overview
- S15 https://claude.com/docs/plugins/build
- S16 https://code.claude.com/docs/en/plugin-marketplaces
- S17 https://code.claude.com/docs/en/mcp
- S18 https://code.claude.com/docs/en/sub-agents
- S19 https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp
- S20 https://claude.com/docs/office-agents/excel
- S21 https://claude.com/docs/office-agents/connectors-and-skills
- S22 https://github.com/anthropics/financial-services (via `gh api`: `.claude-plugin/marketplace.json`, `plugins/vertical-plugins/financial-analysis/{.claude-plugin/plugin.json,.mcp.json,skills/audit-xls,skills/xlsx-author,commands/debug-model.md}`, `plugins/agent-plugins/{statement-auditor,model-builder}/agents/*.md`, `managed-agent-cookbooks/model-builder/subagents/auditor.yaml`)
- S23 https://claude.com/docs/office-agents/fsi-plugins
