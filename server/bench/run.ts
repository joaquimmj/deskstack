// deskstack-bench runner (brief §8.2).
//
//   npx tsx bench/run.ts --connector https://<worker>.workers.dev/mcp                     # dry run: plan + estimate
//   npx tsx bench/run.ts --connector URL --set pilot --budget 20 --i-approve-spend          # the approved $20 pilot
//
// Options: --set pilot|full  --tasks dcf,comps  --arms A,B,C  --only <company id>  --model claude-sonnet-5-5
//          --rescore <run dir>   (score an earlier run again: no API calls, nothing spent; set SEC_USER_AGENT)
//          --effort low|medium|high  --budget <usd>  --max-run-cost <usd>  --ledger <file>  --out <dir>
//          --only <id,id,...>  --max-searches <n>   (arm A's web searches per request, 1-50; default 12)
// --budget is a hard cap on everything spent through --ledger (default bench/results/ledger.json), across re-runs:
// the spend is written after every request, so a crash and a re-run continue from what was already spent.
// The API key comes from the environment (ANTHROPIC_API_KEY or `ant auth login`); it is never read from a file here
// or printed. Raw transcripts, submissions, scores and the summary go to bench/results/<run>/ (commit them).

import Anthropic from "@anthropic-ai/sdk";
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { runOne, type Arm, type Task } from "./agent";
import { mcpConnector } from "./connector";
import { Budget, PRICES, WEB_SEARCH_PER_REQUEST } from "./pricing";
import { PROMPTS_VERSION } from "./prompts";
import { summarize, toMarkdown, type ScoredRun } from "./report";
import { scoreSubmission, type Opts as ScoreOpts } from "./score";
import { filingFactSource } from "./filing-facts";
import { DUAL_FILERS } from "../src/config";
import type { Connector } from "./connector";

const ROOT = join(import.meta.dirname, "..", "..");
const VALUE_OPTS = ["--rescore", "--connector", "--set", "--tasks", "--arms", "--only", "--model", "--effort", "--budget", "--max-run-cost", "--max-searches", "--ledger", "--out"];

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

// Mid estimate per run (Sonnet 5.5, effort medium), measured in the 2026-11-08 pilot, to size a plan before anything
// is spent. Arm A's comps is above its pilot average ($0.55): 4 of 5 stopped on the per-run cap before submitting.
const EST: Record<Task, Record<Arm, number>> = { dcf: { A: 0.25, B: 0.1, C: 0.14 }, comps: { A: 0.85, B: 0.2, C: 0.24 } };

/**
 * The filing's own facts for a company and period label, for the scorer's second reading. Column dates come from
 * deskstack's financial_statements; the facts from SEC companyfacts (needs SEC_USER_AGENT) or the ESEF report.
 */
function filingFactsVia(connector: Connector): NonNullable<ScoreOpts["filingFacts"]> {
  const src = filingFactSource({ secUserAgent: process.env.SEC_USER_AGENT });
  type Fs = { company?: { cik?: number; lei?: string }; periods?: Array<{ label: string; type: string; start: string | null; end: string }> };
  const statements = new Map<string, Promise<Fs | null>>();
  return async (company, period) => {
    if (!statements.has(company)) {
      statements.set(
        company,
        connector
          .call("financial_statements", { ticker: company })
          .then((r) => (r.isError ? null : (JSON.parse(r.text) as Fs)))
          .catch(() => null),
      );
    }
    const fs = await statements.get(company)!;
    const col = fs?.periods?.find((p) => p.label === period && p.type === "annual");
    if (!fs || !col) return null;
    const c = { start: col.start ?? null, end: col.end };
    if (fs.company?.lei) {
      // A dual filer's other-basis figures (ASML's US GAAP 20-F) are other lines, not wrong numbers.
      const dual = DUAL_FILERS[fs.company.lei];
      const [eu, us] = await Promise.all([src.esef(fs.company.lei, c), dual ? src.sec(dual.cik, c) : Promise.resolve(null)]);
      return eu || us ? [...(eu ?? []), ...(us ?? [])] : null;
    }
    if (fs.company?.cik) return src.sec(fs.company.cik, c);
    return null;
  };
}

/** Scores the submissions of an earlier run again (no API calls, nothing spent) into <dir>/rescored/. */
async function rescore(dir: string, url: string) {
  const all = JSON.parse(readFileSync(join(ROOT, "bench", "companies.json"), "utf8")).companies as Array<{ id: string; name: string }>;
  const meta = JSON.parse(readFileSync(join(dir, "plan.json"), "utf8")) as { arms: Arm[] } & Record<string, unknown>;
  const out = join(dir, "rescored");
  mkdirSync(join(out, "runs"), { recursive: true });
  if (!process.env.SEC_USER_AGENT) console.log("SEC_USER_AGENT is not set: SEC filings won't be searched for other lines.");
  const connector = await mcpConnector(url);
  const filingFacts = filingFactsVia(connector);
  const scored: ScoredRun[] = [];
  try {
    for (const f of readdirSync(join(dir, "runs")).filter((x) => x.endsWith(".json")).sort()) {
      const d = JSON.parse(readFileSync(join(dir, "runs", f), "utf8"));
      const company = all.find((c) => c.id === d.company);
      if (!company) throw new Error(`${f}: ${d.company} is not in bench/companies.json`);
      const score = await scoreSubmission(connector, d.run.submission ?? null, company, join(out, "work", f.replace(/\.json$/, ""), "final"), { filingFacts });
      writeFileSync(join(out, "runs", f), JSON.stringify({ company: d.company, task: d.task, arm: d.arm, score }, null, 1) + "\n");
      const { transcript: _t, ...run } = d.run;
      scored.push({ company: d.company, task: d.task, arm: d.arm, run, score });
      console.log(`${f}: ${score.mismatch} wrong, ${score.other_line ?? 0} other line, ${score.definition ?? 0} other definition, of ${score.filed} filed`);
    }
    const s = summarize(scored, meta.arms);
    const m = { ...meta, rescored: new Date().toISOString(), rescore_connector: url };
    writeFileSync(join(out, "summary.json"), JSON.stringify({ meta: m, ...s }, null, 1) + "\n");
    writeFileSync(join(out, "summary.md"), toMarkdown(s, m) + "\n");
    console.log(`rescored ${scored.length} runs: ${join(out, "summary.md")}`);
  } finally {
    await connector.close();
  }
}

async function main() {
  const { opts, flags } = parse(process.argv.slice(2));
  const url = opts["--connector"];
  if (opts["--rescore"]) {
    if (!url) throw new Error("--connector URL is required to rescore");
    return rescore(opts["--rescore"], url);
  }
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
  const only = opts["--only"] ? new Set(opts["--only"].split(",").map((s) => s.trim()).filter(Boolean)) : null;
  const companies = all.filter((c) => (only ? only.has(c.id) : set === "full" || c.pilot));
  if (only && companies.length !== only.size) throw new Error(`--only: unknown id(s) ${[...only].filter((id) => !all.some((c) => c.id === id)).join(", ")}`);
  const maxSearches = Number(opts["--max-searches"] ?? 12);
  if (!Number.isInteger(maxSearches) || maxSearches < 1 || maxSearches > 50) throw new Error("--max-searches must be an integer from 1 to 50");
  if (!companies.length) throw new Error(`no company matches${only ? ` --only ${[...only].join(",")}` : ""}`);
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
  console.log(`mid estimate $${plan.reduce((s, x) => s + EST[x.task][x.arm], 0).toFixed(2)}; hard cap $${cap.toFixed(2)} on the ledger (${ledgerPath}, $${already.toFixed(2)} already spent); per-run cap $${maxRunCost.toFixed(2)}`);
  if (!flags.has("--i-approve-spend")) {
    console.log("Dry run: nothing was sent. Add --i-approve-spend to run (spends API credits, only with the owner's OK).");
    return;
  }
  const started = new Date().toISOString();
  const out = opts["--out"] ?? join(ROOT, "bench", "results", started.replace(/[:.]/g, "-"));
  mkdirSync(join(out, "runs"), { recursive: true });
  const meta = { started, model, effort, max_searches: maxSearches, set, tasks, arms, budget: cap, spent_before: already, prompts_version: PROMPTS_VERSION, connector: url, prices: p, companies: companies.map((c) => c.id) };
  writeFileSync(join(out, "plan.json"), JSON.stringify(meta, null, 1) + "\n");

  // maxRetries 0: the loop retries only 429/529 itself (not billed) and counts a timed-out request as billed.
  const client = new Anthropic({ maxRetries: 0, timeout: 600_000 });
  const connector = await mcpConnector(url);
  const filingFacts = filingFactsVia(connector);
  const budget = new Budget(cap, ledger);
  const scored: ScoredRun[] = [];
  try {
    for (const { company, task, arm } of plan) {
      const name = `${company.id}-${task}-${arm}`;
      const workdir = join(out, "work", name);
      const r = await runOne({ client, connector, budget, model, effort, company, task, arm, workdir, maxRunCost, webSearchMaxUses: maxSearches });
      const file = join(out, "runs", `${name}.json`);
      writeFileSync(file, JSON.stringify({ company: company.id, task, arm, run: r }, null, 1) + "\n"); // the cost is on disk before scoring
      let score;
      try {
        score = await scoreSubmission(connector, r.submission, company, join(workdir, "final"), { filingFacts });
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
