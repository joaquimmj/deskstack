// The public leaderboard (site/leaderboard/index.html), generated from the recorded runs: every analysed 50-company run
// in bench/results/ (summary.json for the model and task, ANALYSIS.md for the figures read by hand). Nothing is typed
// in by hand; a new run with its analysis adds its rows.
//
//   npx tsx bench/leaderboard.ts      # writes ../site/leaderboard/index.html
//
// A test checks the committed page is current.

import { existsSync, readdirSync, readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { parseResultTable } from "./chart";

const GH = "https://github.com/joaquimmj/deskstack";
const MODEL_NAMES: Record<string, string> = {
  "claude-sonnet-5-5": "Claude Sonnet 5.5",
  "claude-opus-5-5": "Claude Opus 5.5",
  "claude-haiku-5-5": "Claude Haiku 5.5",
};
const TASK_NAMES: Record<string, string> = { dcf: "DCF", comps: "Comps table" };

export interface BoardRow {
  run: string;
  model: string;
  task: string;
  companies: number;
  arm: string;
  label: string;
  finished: string;
  filed: number;
  wrong: number;
  avgCost: number;
  avgSeconds: number;
}

/** A column of the "## Result" table by its header, as text, one per arm row. */
function column(markdown: string, header: RegExp): string[] {
  const section = markdown.split(/^## Result\s*$/m)[1] ?? "";
  const rows = section.split("\n").map((l) => l.trim()).filter((l) => l.startsWith("|")).map((l) => l.slice(1, -1).split("|").map((c) => c.trim()));
  const i = (rows[0] ?? []).findIndex((h) => header.test(h));
  if (i < 0) throw new Error(`no column ${header}`);
  return rows.slice(2).filter((r) => /^[A-Z]:/.test(r[0] ?? "")).map((r) => r[i] ?? "");
}

export function loadBoard(root: string): BoardRow[] {
  const dir = join(root, "bench", "results");
  const rows: BoardRow[] = [];
  for (const run of readdirSync(dir).sort()) {
    const analysis = join(dir, run, "ANALYSIS.md");
    const summary = join(dir, run, "summary.json");
    if (!existsSync(analysis) || !existsSync(summary)) continue;
    const meta = (JSON.parse(readFileSync(summary, "utf8")) as { meta: { model: string; set: string; tasks: string[]; companies: string[] } }).meta;
    if (meta.set !== "full" || meta.tasks.length !== 1) continue; // the leaderboard compares full runs, one task each
    const md = readFileSync(analysis, "utf8");
    const arms = parseResultTable(md);
    const finished = column(md, /^Models finished/i);
    const secs = column(md, /^Avg time/i).map((t) => Number(t.replace(/[^\d.]/g, "")));
    arms.forEach((a, k) => rows.push({
      run, model: meta.model, task: meta.tasks[0]!, companies: meta.companies.length, arm: a.arm, label: a.label,
      finished: finished[k] ?? "", filed: a.filed, wrong: a.wrong, avgCost: a.avgCost, avgSeconds: secs[k] ?? NaN,
    }));
  }
  return rows;
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const pct = (w: number, f: number) => (f ? `${((100 * w) / f).toFixed(1)}%` : "0%");

export function renderBoard(rows: BoardRow[]): string {
  const tasks = [...new Set(rows.map((r) => r.task))];
  const models = [...new Set(rows.map((r) => r.model))];
  const tables = tasks.map((t) => {
    const body = rows.filter((r) => r.task === t).map((r) =>
      `<tr><th scope="row">${esc(MODEL_NAMES[r.model] ?? r.model)}</th><td>${esc(`${r.arm}: ${r.label}`)}</td>` +
      `<td class="r">${esc(r.finished)}</td><td class="r"><b>${r.wrong}</b> of ${r.filed.toLocaleString("en-US")} (${pct(r.wrong, r.filed)})</td>` +
      `<td class="r">$${r.avgCost.toFixed(2)}</td><td class="r">${Number.isFinite(r.avgSeconds) ? `${r.avgSeconds} s` : "-"}</td>` +
      `<td><a href="${GH}/blob/main/bench/results/${r.run}/ANALYSIS.md">analysis</a></td></tr>`).join("\n");
    const n = rows.find((r) => r.task === t)!.companies;
    return `<section class="bcard"><div class="bcard-h"><h2>${esc(TASK_NAMES[t] ?? t)}, ${n} companies</h2></div><div class="scroll"><table>
<thead><tr><th scope="col">Model</th><th scope="col">Setup</th><th scope="col" class="r">Models finished</th><th scope="col" class="r">Wrong reported figures</th><th scope="col" class="r">Cost per model</th><th scope="col" class="r">Time per model</th><th scope="col">Source</th></tr></thead>
<tbody>
${body}
</tbody></table></div></section>`;
  }).join("\n");
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>deskstack leaderboard</title>
<meta name="description" content="How many reported figures AI-built financial models get wrong, by model, with web search alone and with deskstack. Every wrong figure read by hand against the filings.">
<link rel="canonical" href="https://joaquimmj.github.io/deskstack/leaderboard/">
<link rel="stylesheet" href="../style.css">
<style>
main.board { max-width: 1100px; margin: 0 auto; padding: 48px 20px 80px; }
main.board h1 { font-size: clamp(28px, 4vw, 40px); letter-spacing: -0.02em; margin: 0 0 12px; }
main.board > p, main.board li { color: var(--ink-2); font-size: 16px; line-height: 1.6; max-width: 75ch; }
main.board section.bcard { margin: 28px 0; }
main.board .bcard-h h2 { font-size: 18px; margin: 0; }
main.board td, main.board th { font-size: 14.5px; }
main.board h2.h { font-size: 20px; margin: 40px 0 8px; }
</style>
</head>
<body>
<main class="board">
<p><a href="../">deskstack</a></p>
<h1>Leaderboard</h1>
<p>How many reported figures an AI-built model gets wrong: the same 50 companies (35 US, 15 European), one DCF and one comps table each, built by each model with web search alone, with deskstack's data, and with deskstack plus its reviewers. Every figure the scorer called wrong was then read by hand against the filing. Models so far: ${models.length}. More models soon: each run is a paid run, approved before it starts.</p>
${tables}
<h2 class="h">How the figures are checked</h2>
<ul>
<li>Each submitted figure is scored against the filing it should come from, then every one the scorer calls wrong is read by hand and classified. The analysis of each run lists every case.</li>
<li>The setups with deskstack read the data they are scored against, so their 0 is partly by construction. deskstack's data is checked separately: a golden set of questions with known answers on every push, and a nightly re-read of each answer from the filing itself with independent parsers, edgartools for SEC filings and Arelle for European reports.</li>
<li>Generated from <a href="${GH}/tree/main/bench/results">bench/results</a> by <code>server/bench/leaderboard.ts</code>. The runner, the frozen company set and the method are in <a href="${GH}/blob/main/bench/README.md">bench/</a>.</li>
</ul>
<p>Independent open-source project. Not affiliated with or endorsed by Anthropic. Not investment advice.</p>
</main>
</body>
</html>
`;
}

if (process.argv[1] && /leaderboard\.ts$/.test(process.argv[1])) {
  const root = join(import.meta.dirname, "..", "..");
  mkdirSync(join(root, "site", "leaderboard"), { recursive: true });
  const file = join(root, "site", "leaderboard", "index.html");
  writeFileSync(file, renderBoard(loadBoard(root)));
  console.log(`Wrote ${file}`);
}
