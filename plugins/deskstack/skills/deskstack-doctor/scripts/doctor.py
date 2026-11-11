#!/usr/bin/env python3
"""deskstack doctor: checks what the plugin's scripts need, on this machine.

  python3 doctor.py [--json]

- Python 3.8 or later (what the plugin README states);
- the plugin version;
- for each role, that its bundled scripts and openpyxl load.

No network: the connector is checked in the conversation, with the data_status tool. Exit code 0 when everything
passes, 1 otherwise.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PLUGIN_VERSION = "0.2.0"  # kept equal to .claude-plugin/plugin.json by a test
ROLES = ["analyst", "associate", "vp-review", "md-redteam", "compliance", "sign-off"]
HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent  # .../skills
REINSTALL = "Reinstall the plugin: Customize > Plugins (or /plugin in Claude Code), remove deskstack, add it again."

PROBE = (
    "import sys; sys.path.insert(0, sys.argv[1]); "
    "import openpyxl, deskstack_check; "
    "from deskstack_check.build import build_dcf; "
    "print(openpyxl.__version__, deskstack_check.__version__)"
)


def checks() -> list[dict]:
    out = []
    v = sys.version_info
    ok = v >= (3, 8)
    out.append({"check": "Python", "status": "pass" if ok else "fail", "detail": f"{v.major}.{v.minor}.{v.micro} at {sys.executable}",
                "fix": "" if ok else "Install Python 3.8 or later (python.org), then run the command again."})
    found = 0
    for role in ROLES:
        vendor = SKILLS / role / "scripts" / "_vendor"
        name = f"/{role} scripts"
        if not (SKILLS / role).exists():
            # In claude.ai chat each skill is uploaded on its own: siblings aren't visible from here.
            out.append({"check": name, "status": "skip", "detail": "not visible from this skill's folder", "fix": ""})
            continue
        found += 1
        if not vendor.exists():
            out.append({"check": name, "status": "fail", "detail": "the bundled scripts are missing", "fix": REINSTALL})
            continue
        p = subprocess.run([sys.executable, "-I", "-S", "-c", PROBE, str(vendor)], capture_output=True, text=True)
        if p.returncode == 0:
            ox, dc = p.stdout.split()
            out.append({"check": name, "status": "pass", "detail": f"openpyxl {ox}, deskstack_check {dc}", "fix": ""})
        else:
            last = (p.stderr.strip().splitlines() or ["unknown error"])[-1]
            out.append({"check": name, "status": "fail", "detail": last, "fix": REINSTALL})
    return out


def plugin_version() -> tuple[str, str | None]:
    manifest = SKILLS.parent / ".claude-plugin" / "plugin.json"
    try:
        return PLUGIN_VERSION, json.loads(manifest.read_text())["version"]
    except (OSError, ValueError, KeyError):
        return PLUGIN_VERSION, None


def main(argv: list[str]) -> int:
    cs = checks()
    mine, manifest = plugin_version()
    if manifest is not None and manifest != mine:
        cs.append({"check": "Plugin version", "status": "fail", "detail": f"doctor {mine}, manifest {manifest}",
                   "fix": "The plugin is half updated. " + REINSTALL})
    else:
        cs.append({"check": "Plugin version", "status": "pass", "detail": mine, "fix": ""})
    failed = [c for c in cs if c["status"] == "fail"]
    report = {"plugin_version": mine, "ok": not failed, "checks": cs}
    if "--json" in argv:
        print(json.dumps(report, indent=1))
    else:
        print(f"## deskstack doctor (plugin {mine})\n")
        print("| Check | Status | Detail | Fix |\n|---|---|---|---|")
        for c in cs:
            print(f"| {c['check']} | {c['status']} | {c['detail']} | {c['fix']} |")
        print("\nAll local checks pass." if not failed else f"\n{len(failed)} check(s) failed: see Fix.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
