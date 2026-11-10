---
name: deskstack-doctor
description: Checks that deskstack works here (data connector, plugin version, Python, each role's bundled openpyxl) and says how to fix what doesn't. Use for "/deskstack-doctor" or when a tool fails.
---

# deskstack doctor

Run three checks, then show one table: check, status, detail, fix. You report; you change nothing.

## 1. The data connector

Call the `data_status` tool.

- **It answers:** pass. Report the server `version`, the snapshot's `built_at` and how old it is, and the number of
  European issuers.
  - A snapshot older than 3 days is a warning: the nightly update may have failed. The data still works.
- **The tool doesn't exist here:** fail. The connector isn't added. Fix: Customize → Connectors → Add custom connector,
  paste `https://deskstack.deskstack-server.workers.dev/mcp`, no sign-in. In Claude Code:
  `claude mcp add --transport http deskstack https://deskstack.deskstack-server.workers.dev/mcp`.
- **It returns the daily-capacity or rate-limit message:** warning. Quote the message: it says when service comes
  back and links the self-hosting guide.
- **Any other error:** fail. Quote it.

## 2. Python, the plugin version and each role's scripts

The script lives in this skill's folder: `${CLAUDE_SKILL_DIR}/scripts/doctor.py` in Claude Code, or
`scripts/doctor.py` next to this SKILL.md in chat and Cowork.

```bash
python3 scripts/doctor.py
```

It checks Python 3.8 or later, the plugin version, and that each role's bundled scripts and openpyxl load. It needs no
network and installs nothing.

- **`python3` isn't found:** fail. In chat and Cowork, code execution must be on (Settings → Capabilities). On your
  own machine, install Python 3.8 or later.
- **In chat, the roles show `skip`:** each skill is uploaded on its own there, so this folder can't see the others.
  That is expected. Run `/deskstack-doctor` from Claude Code or Cowork for the full check.

## 3. Report

One table, failures first, then: "Everything deskstack needs works here." or the fixes in order. End with the
plugin version.
