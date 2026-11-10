"""scripts/self-host.sh (stars brief lot 7): one command, the same builds as the nightly deploy, the SEC contact never
printed or written to the repo. Tested in --dry-run: no network, no Cloudflare account."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "self-host.sh"


def _dry(*args: str, contact: str = "testdesk jane@example.com") -> str:
    env = {**os.environ, "SEC_USER_AGENT": contact}
    p = subprocess.run(["bash", str(SCRIPT), "--dry-run", *args], capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 0, p.stderr
    return p.stdout


def test_dry_run_mirrors_the_nightly_deploy_in_order():
    before = (ROOT / "server" / "wrangler.jsonc").read_text()
    out = _dry()
    steps = ["npm ci", "wrangler d1 create", "d1 execute deskstack-usage --remote", "build-snapshot.ts --tickers",
             "build-damodaran.ts", "build-esef.ts", "build-cvm.ts", "wrangler deploy", "wrangler secret put SEC_USER_AGENT"]
    pos = [out.index(s) for s in steps]
    assert pos == sorted(pos), out
    assert "/mcp" in out
    assert (ROOT / "server" / "wrangler.jsonc").read_text() == before


def test_options_and_the_contact_stays_out_of_the_output():
    out = _dry("--bulk", "--no-eu", contact="secretdesk private@example.org")
    assert "build-snapshot.ts --bulk" in out and "build-esef.ts" not in out
    assert "private@example.org" not in out


def test_a_contact_without_an_email_is_refused():
    env = {**os.environ, "SEC_USER_AGENT": "no contact"}
    p = subprocess.run(["bash", str(SCRIPT), "--dry-run"], capture_output=True, text=True, env=env, timeout=60)
    assert p.returncode == 1 and "contact email" in p.stderr
