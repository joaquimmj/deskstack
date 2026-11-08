// deskstack-bench runner (brief §8.2).
//
//   npx tsx bench/run.ts --connector https://<worker>.workers.dev/mcp                     # dry run: plan + estimate
//   npx tsx bench/run.ts --connector URL --set pilot --budget 20 --i-approve-spend          # the approved $20 pilot
//
// Options: --set pilot|full  --tasks dcf,comps  --arms A,B,C  --only <company id>  --model claude-sonnet-5-5
//          --effort low|medium|high  --budget <usd>  --max-run-cost <usd>  --ledger <file>  --out <dir>
// --budget is a hard cap on everything spent through --ledger (default bench/results/ledger.json), across re-runs:
// the spend is written after every request, so a crash and a re-run continue from what was already spent.
// The API key comes from the environment (ANTHROPIC_API_KEY or `ant auth login`); it is never read from a file here
// or printed. Raw transcripts, submissions, scores and the summary go to bench/results/<run>/ (commit them).

import Anthropic from "@anthropic-ai/sdk";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { runOne, type Arm, type Task } from "./agent";
import { mcpConnector } from "./connector";
import { Budget, PRICES, WEB_SEARCH_PER_REQUEST } from "./pricing";
import { PROMPTS_VERSION } from "./prompts";
import { summarize, toMarkdown, type ScoredRun } from "./report";
import { scoreSubmission } from "./score";

const ROOT = join(import.meta.dirname, "..", "..");
const VALUE_OPTS = ["--connector", "--set", "--tasks", "--arms", "--only", "--model", "--effort", "--budget", "--max-run-cost", "--ledger", "--out"];

function parse(argv: string[]) {
  const opts: Record<string, string> = {};
  const flags = new Set<string>();
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]!;
    const [k, v] = a.includes("=") ? [a.slice(0, a.indexOf("=")), a.slice(a.indexOf("=") + 1)] : [a, undefined];
    if (VALUE_OPTS.includes(k)) {
      const val = v ?? argv[++i];
      if (val === undefined || val.startsWith("--")) throw new Error(`${k} needs a value`);
      opts[k] = val;
    } else if (k === "--i-approve-spend") flags.add(k);
    else throw new Error(`unknown option ${a}`);
  }
  return { opts, flags };
}

function oneOf<T extends string>(name: string, vals: string[], allowed: readonly T[]): T[] {
  for (const v of vals) if (!allowed.includes(v as T)) throw new Error(`${name}: ${v} is not one of ${allowed.join(", ")}`);
  return vals as T[];
}

function money(name: string, v: string): number {
  const n = Number(v);
  if (!Number.isFinite(n) || n <= 0) throw new Error(`${name} must be a positive dollar amount, got ${v}`);
  return n;
}

// Mid estimate per run from bench/COST_ESTIMATE.md (Sonnet 5.5), to size the plan before anything is spent.
const EST: Record<Arm, number> = { A: 0.6, B: 0.36, C: 0.89 };

async function main() {
  const { opts, flags } = parse(process.argv.slice(2));
  const url = opts["--connector"];
  const set = oneOf("--set", [opts["--set"] ?? "pilot"], ["pilot", "full"] as const)[0]!;
  const tasks = oneOf("--tasks", (opts["--tasks"] ?? "dcf,comps").split(","), ["dcf", "comps"] as const) as Task[];
  const arms = oneOf("--arms", (opts["--arms"] ?? "A,B,C").split(","), ["A", "B", "C"] as const) as Arm[];
  const effort = oneOf("--effort", [opts["--effort"] ?? "medium"], ["low", "medium", "high"] as const)[0]!;
  const model = opts["--model"] ?? "claude-sonnet-5-5";
  const cap = money("--budget", opts["--budget"] ?? "20");
  const maxRunCost = money("--max-run-cost", opts["--max-run-cost"] ?? "1.5");
  const ledgerPath = opts["--ledger"] ?? join(ROOT, "bench", "results", "ledger.json");
  if (!url) throw new Error("--connector URL is required (the deployed deskstack MCP endpoint, or a local wrangler dev)");
  if (!PRICES[model]) throw new Error(`no price for ${model} in bench/pricing.ts`);
  const all = JSON.parse(readFileSync(join(ROOT, "bench", "companies.json"), "utf8")).companies as Array<{ id: string; name: string; pilot?: boolean }>;
  const only = opts["--only"];
  const companies = all.filter((c) => (only ? c.id === only : set === "full" || c.pilot));
  if (!companies.length) throw new Error(`no company matches${only ? ` --only ${only}` : ""}`);
  const plan = companies.flatMap((c) => tasks.flatMap((t) => arms.map((a) => ({ company: c, task: t, arm: a }))));
  const ledger = {
    read: () => (existsSync(ledgerPath) ? Number(JSON.parse(readFileSync(ledgerPath, "utf8")).spent_usd) || 0 : 0),
    write: (total: number) => {
      mkdirSync(dirname(ledgerPath), { recursive: true });
      writeFileSync(ledgerPath, JSON.stringify({ spent_usd: Number(total.toFixed(6)), updated: new Date().toISOString() }) + "\n");
    },
  };
  const already = ledger.read();
  const p = PRICES[model]!;
  console.log(`deskstack-bench: ${plan.length} runs (${companies.length} companies × ${tasks.join("+")} × arms ${arms.join("")}), model ${model}, effort ${effort}`);
  console.log(`prices used ($/MTok): input ${p.input}, output ${p.output}, cache write ${p.cacheWrite5m}, cache read ${p.cacheRead}; web search $${WEB_SEARCH_PER_REQUEST}/search. Check them against the live pricing page.`);
  console.log(`mid estimate $${plan.reduce((s, x) => s + EST[x.arm], 0).toFixed(2)}; hard cap $${cap.toFixed(2)} on the ledger (${ledgerPath}, $${already.toFixed(2)} already spent); per-run cap $${maxRunCost.toFixed(2)}`);
  if (!flags.has("--i-approve-spend")) {
    console.log("Dry run: nothing was sent. Add --i-approve-spend to run (spends API credits, only with the owner's OK).");
    return;
  }
  const started = new Date().toISOString();
  const out = opts["--out"] ?? join(ROOT, "bench", "results", started.replace(/[:.]/g, "-"));
  mkdirSync(join(out, "runs"), { recursive: true });
  const meta = { started, model, effort, set, tasks, arms, budget: cap, spent_before: already, prompts_version: PROMPTS_VERSION, connector: url, prices: p, companies: companies.map((c) => c.id) };
  writeFileSync(join(out, "plan.json"), JSON.stringify(meta, null, 1) + "\n");

  // maxRetries 0: the loop retries only 429/529 itself (not billed) and counts a timed-out request as billed.
  const client = new Anthropic({ maxRetries: 0, timeout: 600_000 });
  const connector = await mcpConnector(url);
  const budget = new Budget(cap, ledger);
  const scored: ScoredRun[] = [];
  try {
    for (const { company, task, arm } of plan) {
      const name = `${company.id}-${task}-${arm}`;
      const workdir = join(out, "work", name);
      const r = await runOne({ client, connector, budget, model, effort, company, task, arm, workdir, maxRunCost });
      const file = join(out, "runs", `${name}.json`);
      writeFileSync(file, JSON.stringify({ company: company.id, task, arm, run: r }, null, 1) + "\n"); // the cost is on disk before scoring
      let score;
      try {
        score = await scoreSubmission(connector, r.submission, company, join(workdir, "final"));
      } catch (e) {
        score = { valid: false, error: `scoring failed: ${String((e as Error).message ?? e)}`, filed: 0, match: 0, mismatch: 0, not_found: 0, ambiguous: 0, unverifiable: 0, causes: {}, typed: 0, unsourced: 0, items: [], unsourced_refs: [], errors: [] };
      }
      writeFileSync(file, JSON.stringify({ company: company.id, task, arm, run: r, score }, null, 1) + "\n");
      const { transcript: _t, ...run } = r;
      scored.push({ company: company.id, task, arm, run, score });
      const s = summarize(scored, arms);
      writeFileSync(join(out, "summary.json"), JSON.stringify({ meta, ...s, spent_total: budget.spent }, null, 1) + "\n");
      writeFileSync(join(out, "summary.md"), toMarkdown(s, meta) + "\n");
      console.log(`${name}: ${r.status}${r.error ? ` (${r.error})` : ""}, $${r.cost.toFixed(3)} (ledger $${budget.spent.toFixed(2)}), ${score.mismatch}/${score.match + score.mismatch} wrong, ${score.unsourced}/${score.typed} unsourced`);
      if (r.status === "budget") {
        console.log(`budget: stopped at $${budget.spent.toFixed(2)} of $${cap.toFixed(2)}`);
        break;
      }
    }
  } finally {
    await connector.close();
  }
  console.log(`done: ledger at $${budget.spent.toFixed(2)}. Summary: ${join(out, "summary.md")}`);
}

main().catch((e) => {
  console.error(String(e?.message ?? e));
  process.exit(2);
});
