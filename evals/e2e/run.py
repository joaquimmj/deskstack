#!/usr/bin/env python3
"""Run the 10 /deal-team scenarios headless in Claude Code, then grade them.

  python3 evals/e2e/run.py --connector https://<worker>.workers.dev/mcp            # dry run: prints the plan
  python3 evals/e2e/run.py --connector URL --only build-aapl-dcf --i-approve-usage  # actually runs

Isolation: each scenario runs in a fresh temporary folder outside the repo, with only the deskstack plugin
(--plugin-dir) and connector (--strict-mcp-config), no session persistence, and a pinned model.
- With ANTHROPIC_API_KEY set, runs use --bare: no user settings, hooks, CLAUDE.md or other plugins. This bills the
  API key (the benchmark budget).
- Without it, runs use the signed-in Claude Code account with --setting-sources local. User-level CLAUDE.md and
  skills may still load, so results are less clean; the summary says which mode ran.

It spends model usage, so it does nothing without --i-approve-usage (the project owner's explicit OK).
Transcripts and outputs are copied to evals/e2e/runs/<timestamp>/<scenario>/ (not committed).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "checker"))
sys.path.insert(0, str(ROOT / "checker" / "tests"))

from grade import grade  # noqa: E402

# What the skills and agents need: the scripts (python3), working files written from Bash, reading, delegation, the connector.
ALLOWED = ["Bash(python3:*)", "Bash(cat:*)", "Bash(mkdir:*)", "Bash(mktemp:*)", "Bash(ls:*)", "Bash(cp:*)",
           "Read", "Write", "Glob", "Grep", "Skill", "Agent", "Task", "mcp__deskstack__*"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--connector", required=True, help="deskstack MCP URL")
    ap.add_argument("--only", action="append", help="scenario id (repeatable)")
    ap.add_argument("--claude", default="claude", help="Claude Code executable")
    ap.add_argument("--model", default="claude-sonnet-5-5")
    ap.add_argument("--max-budget-usd", type=float, default=1.0, help="per-run spending cap passed to Claude Code")
    ap.add_argument("--timeout", type=int, default=1800, help="seconds per run")
    ap.add_argument("--i-approve-usage", action="store_true")
    a = ap.parse_args()
    scen = [s for s in json.loads((HERE / "scenarios.json").read_text())["scenarios"] if not a.only or s["id"] in a.only]
    bare = bool(os.environ.get("ANTHROPIC_API_KEY"))
    mode = "bare (API key)" if bare else "account (--setting-sources local)"
    base = HERE / "runs" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    print(f"{len(scen)} scenario(s) on {a.model}, mode {mode}, at most ${a.max_budget_usd:.2f} each "
          f"(${a.max_budget_usd * len(scen):.2f} in all). Results under {base}")
    if not a.i_approve_usage:
        for s in scen:
            print(f"  would run {s['id']}: {s['prompt'][:90]}")
        print("Dry run. Add --i-approve-usage to run (spends model usage).")
        return 0
    from demo_models import build_demo

    results = []
    for s in scen:
        wd = Path(tempfile.mkdtemp(prefix=f"deskstack-e2e-{s['id']}-"))
        (wd / "out").mkdir()
        if s.get("model"):
            built = build_demo(s["model"], wd / "out")
            built.rename(wd / "out" / "model.xlsx")
        (wd / "mcp.json").write_text(json.dumps({"mcpServers": {"deskstack": {"type": "http", "url": a.connector}}}))
        cmd = [a.claude, "-p", s["prompt"], "--output-format", "stream-json", "--verbose", "--model", a.model,
               "--max-budget-usd", str(a.max_budget_usd), "--plugin-dir", str(ROOT / "plugins" / "deskstack"),
               "--mcp-config", str(wd / "mcp.json"), "--strict-mcp-config", "--no-session-persistence",
               "--permission-mode", "acceptEdits", "--permission-prompts", "none", "--allowedTools", *ALLOWED]
        cmd += ["--bare"] if bare else ["--setting-sources", "local"]
        status = "ran"
        with open(wd / "transcript.jsonl", "w") as f:
            try:
                subprocess.run(cmd, cwd=wd, stdout=f, stderr=subprocess.STDOUT, timeout=a.timeout)
            except subprocess.TimeoutExpired:
                status = "timeout"
        r = grade(s, str(wd / "transcript.jsonl"), str(wd))
        r["run"] = {"status": status, "mode": mode, "model": a.model}
        if status == "timeout":
            r["pass"] = False
        results.append(r)
        dest = base / s["id"]
        shutil.copytree(wd, dest)
        shutil.rmtree(wd, ignore_errors=True)
        print(f"{s['id']}: {'PASS' if r['pass'] else 'FAIL'} ({status})")
    base.mkdir(parents=True, exist_ok=True)
    (base / "summary.json").write_text(json.dumps(results, indent=1))
    passed = sum(r["pass"] for r in results)
    print(f"{passed}/{len(results)} passed. Summary: {base / 'summary.json'}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
