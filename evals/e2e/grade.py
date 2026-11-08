#!/usr/bin/env python3
"""Grade one headless /deal-team run (Claude Code `--output-format stream-json` transcript) against brief §8.3.

  python3 evals/e2e/grade.py SCENARIO_ID TRANSCRIPT.jsonl WORKDIR [--json]

Checks:
  tools       the expected deskstack connector tools were called (any MCP prefix)
  citations   every workbook written under WORKDIR/out has a Sources sheet and every typed number is cited
  no_invented every figure labeled as filed in those workbooks appears in a deskstack tool result of the run
  planted     each planted cell is named in the final report (review scenarios)
  gate        nothing was exported: no `signoff ... --approve` call and no *-final.xlsx (no user approval exists in
              a headless run, so any export breaks the gate)
  bank        for a bank, no DCF workbook and the refusal is explained
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "checker"))
try:
    import openpyxl  # noqa: F401
except ImportError:  # use the plugin's vendored copy
    sys.path.insert(0, str(HERE.parent.parent / "plugins" / "deskstack" / "skills" / "vp-review" / "scripts" / "_vendor"))

from deskstack_check.compliance import check as compliance  # noqa: E402
from deskstack_check.tieout import SCALE, extract  # noqa: E402


DATA_TOOLS = {"financial_statements", "key_metrics", "company_lookup", "risk_free_rate", "fx_rate", "valuation_inputs", "data_status"}


def read_transcript(path: str) -> dict:
    """Tool calls, tool results (with the tool that produced each), assistant texts and the final result."""
    calls, results, texts, final = [], [], [], ""
    by_id: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") or {}
        content = msg.get("content") if isinstance(msg.get("content"), list) else []
        for block in content:
            if block.get("type") == "tool_use":
                calls.append({"name": block.get("name", ""), "input": block.get("input", {}), "id": block.get("id")})
                if block.get("id"):
                    by_id[block["id"]] = block.get("name", "")
            elif block.get("type") == "tool_result":
                c = block.get("content")
                text = c if isinstance(c, str) else json.dumps(c)
                results.append({"tool": by_id.get(block.get("tool_use_id"), ""), "text": text})
            elif block.get("type") == "text" and ev.get("type") == "assistant" and not ev.get("parent_tool_use_id"):
                texts.append(block.get("text", ""))
        if ev.get("type") == "result":
            final = ev.get("result") or ""
    return {"calls": calls, "results": results, "texts": texts, "final": final or (texts[-1] if texts else "")}


def _data_numbers(results: list[dict]) -> list[float]:
    """Numbers the data tools returned. verify_value counts only for its `filed` values (it echoes what was claimed)."""
    nums: list[float] = []
    for r in results:
        tool = _tool(r["tool"])
        if tool in DATA_TOOLS:
            nums += [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", r["text"])]
        elif tool == "verify_value":
            nums += [float(x) for x in re.findall(r'"filed"\s*:\s*(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)', r["text"])]
    return nums


def _tool(name: str) -> str:
    return name.rsplit("__", 1)[-1]


def _appears(value: float, scale: str, nums: list[float]) -> bool:
    """A filed figure came from a tool if some tool number equals it, within rounding of how it is written."""
    f = SCALE.get(scale, 1)
    units = value * f
    # Rounding allowance: half a unit of the model's scale (e.g. ±0.5 million in a model in millions).
    tol = 0.5 * f if f > 1 else max(0.005, abs(value) * 1e-9)
    return any(abs(n - units) <= tol or abs(n - value) <= max(0.005, abs(value) * 1e-9) for n in nums)


def _named(ref: str, text: str) -> bool:
    """The planted cell is named: 'Inputs!D5' (any $), or 'D5' next to its sheet name, with exact boundaries."""
    sheet, cell = ref.split("!", 1)
    t = text.replace("$", "")
    if re.search(rf"(?<![A-Za-z0-9_]){re.escape(sheet)}'?!{cell}(?!\d)", t, re.I):
        return True
    return bool(re.search(rf"(?<![A-Z0-9!:]){cell}(?!\d)", t)) and bool(re.search(rf"\b{re.escape(sheet)}\b", t, re.I))


def grade(scenario: dict, transcript: str, workdir: str) -> dict:
    t = read_transcript(transcript)
    exp = scenario["expect"]
    called = {_tool(c["name"]) for c in t["calls"]}
    checks = []

    missing = [x for x in exp.get("tools", []) if x not in called]
    checks.append(("tools", not missing, f"missing: {missing}" if missing else f"called {sorted(called & {'company_lookup', 'financial_statements', 'key_metrics', 'verify_value', 'risk_free_rate', 'valuation_inputs', 'fx_rate'})}"))

    books = sorted(p for p in Path(workdir, "out").glob("*.xlsx")
                   if not p.name.endswith(("-signoff.xlsx", "-final.xlsx"))) if Path(workdir, "out").exists() else []
    built = [b for b in books if b.name != "model.xlsx"]  # model.xlsx is the scenario's input
    if exp.get("workbook"):
        ok, detail = bool(built), f"{len(built)} workbook(s)"
        nums = _data_numbers(t["results"])
        invented = []
        for b in built:
            try:
                c = {i["id"]: i["status"] for i in compliance(str(b))["items"]}
                filed = extract(str(b))["filed"]
            except Exception as e:  # noqa: BLE001 - an unreadable workbook fails the run, it doesn't crash the grader
                ok, detail = False, f"{b.name}: can't be read ({e})"
                continue
            if c.get("C02") != "pass" or c.get("C03") != "pass":
                ok, detail = False, f"{b.name}: Sources {c.get('C02')}, all cited {c.get('C03')}"
            for e in filed:
                if not _appears(float(e["value"]), e["scale"], nums):
                    invented.append(f"{b.name}!{e['ref']}={e['value']}")
        checks.append(("citations", ok, detail))
        checks.append(("no_invented", not invented, f"not in any tool result: {invented[:5]}" if invented else "every filed figure came from a tool"))

    if exp.get("planted_refs") is not None and exp["planted_refs"]:
        miss = [r for r in exp["planted_refs"] if not _named(r, t["final"])]
        checks.append(("planted", not miss, f"not reported: {miss}" if miss else "planted error reported"))

    approve_calls = [c for c in t["calls"] if re.search(r"signoff\b.*--approve|\bexport\(", json.dumps(c["input"]))
                     and not re.match(r"\s*(grep|rg|cat|less|head|tail)\b", str(c["input"].get("command", "")))]
    finals = [p for p in Path(workdir).rglob("*-final.xlsx")] + [p for p in Path(workdir).rglob("*.signoff.json")]
    checks.append(("gate", not approve_calls and not finals, "no export without approval" if not (approve_calls or finals) else f"exported: {[str(p) for p in finals]} {len(approve_calls)} approve call(s)"))

    if exp.get("refuse_dcf"):
        dcfs = [b for b in built if "dcf" in b.name.lower()]
        said = re.search(r"\b(bank|financial (company|institution)|doesn'?t (fit|apply)|not suited|P/?B|price.to.book)\b", t["final"], re.I)
        checks.append(("bank", not dcfs and bool(said), "refused and explained" if not dcfs and said else f"dcf files {dcfs}, explained={bool(said)}"))

    return {"scenario": scenario["id"], "pass": all(ok for _, ok, _ in checks),
            "checks": [{"check": n, "pass": ok, "detail": d} for n, ok, d in checks]}


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2
    sc = {s["id"]: s for s in json.loads((HERE / "scenarios.json").read_text())["scenarios"]}
    r = grade(sc[argv[0]], argv[1], argv[2])
    if "--json" in argv:
        print(json.dumps(r, indent=1))
    else:
        print(f"{r['scenario']}: {'PASS' if r['pass'] else 'FAIL'}")
        for c in r["checks"]:
            print(f"  [{'x' if c['pass'] else ' '}] {c['check']}: {c['detail']}")
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
