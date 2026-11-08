// Aggregates scored runs into the benchmark table (per arm), paired: a company-task counts only when every arm ran.

import type { Arm, RunResult, Task } from "./agent";
import type { Score } from "./score";

export interface ScoredRun {
  company: string;
  task: Task;
  arm: Arm;
  run: Omit<RunResult, "transcript">;
  score: Score;
}

export interface ArmSummary {
  arm: Arm;
  runs: number;
  submitted: number;
  valid: number;
  filed: number;
  checked: number; // match + mismatch
  mismatch: number;
  not_verifiable: number;
  causes: Record<string, number>;
  errored: number;
  wrong_pct: number | null; // mismatch / checked
  typed: number;
  unsourced: number;
  unsourced_pct: number | null;
  checker_blockers_per_model: number | null;
  checker_majors_per_model: number | null;
  avg_cost: number;
  avg_tokens: number;
  avg_seconds: number;
  total_cost: number;
}

const ratio = (a: number, b: number) => (b ? a / b : null);

export function summarize(runs: ScoredRun[], arms: Arm[]): { paired: number; arms: ArmSummary[]; total_cost: number } {
  const key = (r: ScoredRun) => `${r.company}|${r.task}`;
  const complete = new Set(
    // A company-task counts only when every arm finished (not stopped by the budget, not crashed).
    [...new Set(runs.map(key))].filter((k) => arms.every((a) => runs.some((r) => key(r) === k && r.arm === a && r.run.status !== "budget" && r.run.status !== "error"))),
  );
  const out: ArmSummary[] = [];
  for (const arm of arms) {
    const rs = runs.filter((r) => r.arm === arm && complete.has(key(r)));
    const s = (f: (r: ScoredRun) => number) => rs.reduce((t, r) => t + f(r), 0);
    const valid = rs.filter((r) => r.score.valid);
    const checked = s((r) => r.score.match + r.score.mismatch);
    out.push({
      arm,
      runs: rs.length,
      submitted: rs.filter((r) => r.run.submission).length,
      valid: valid.length,
      filed: s((r) => r.score.filed),
      checked,
      mismatch: s((r) => r.score.mismatch),
      not_verifiable: s((r) => r.score.not_found + r.score.ambiguous + r.score.unverifiable),
      causes: rs.reduce((acc, r) => {
        for (const [k, v] of Object.entries(r.score.causes ?? {})) acc[k] = (acc[k] ?? 0) + v;
        return acc;
      }, {} as Record<string, number>),
      errored: runs.filter((r) => r.arm === arm && r.run.status === "error").length,
      wrong_pct: ratio(s((r) => r.score.mismatch), checked),
      typed: s((r) => r.score.typed),
      unsourced: s((r) => r.score.unsourced),
      unsourced_pct: ratio(s((r) => r.score.unsourced), s((r) => r.score.typed)),
      checker_blockers_per_model: ratio(valid.reduce((t, r) => t + (r.score.checker?.blocker ?? 0), 0), valid.length),
      checker_majors_per_model: ratio(valid.reduce((t, r) => t + (r.score.checker?.major ?? 0), 0), valid.length),
      avg_cost: ratio(s((r) => r.run.cost), rs.length) ?? 0,
      avg_tokens: ratio(s((r) => r.run.usage.input_tokens + r.run.usage.output_tokens + (r.run.usage.cache_read_input_tokens ?? 0) + (r.run.usage.cache_creation_input_tokens ?? 0)), rs.length) ?? 0,
      avg_seconds: ratio(s((r) => r.run.seconds), rs.length) ?? 0,
      total_cost: s((r) => r.run.cost),
    });
  }
  return { paired: complete.size, arms: out, total_cost: runs.reduce((t, r) => t + r.run.cost, 0) };
}

const pct = (x: number | null) => (x === null ? "n/a" : `${(x * 100).toFixed(1)}%`);
const n2 = (x: number | null) => (x === null ? "n/a" : x.toFixed(2));

export function toMarkdown(s: ReturnType<typeof summarize>, meta: Record<string, unknown>): string {
  const label: Record<Arm, string> = { A: "A: web search only", B: "B: deskstack data", C: "C: deskstack + associate + VP review + fix" };
  const lines = [
    `# deskstack-bench results`,
    "",
    `Model ${meta.model}, effort ${meta.effort}, prompts v${meta.prompts_version}, set ${meta.set} (${s.paired} company-task pairs where every arm ran), run ${meta.started}.`,
    `Total API cost: $${s.total_cost.toFixed(2)}.`,
    "",
    "| Arm | Models (valid) | Filed figures checked | Wrong vs filing | Why wrong | Not verifiable | Typed numbers unsourced | Checker blockers / model | Avg cost | Avg tokens | Avg time | Runs errored |",
    "|---|---|---|---|---|---|---|---|---|---|---|---|",
  ];
  for (const a of s.arms) {
    const why = Object.entries(a.causes).sort((x, y) => y[1] - x[1]).map(([k, v]) => `${k} ${v}`).join(", ") || "-";
    lines.push(`| ${label[a.arm]} | ${a.submitted} (${a.valid}) | ${a.checked} | ${pct(a.wrong_pct)} (${a.mismatch}) | ${why} | ${a.not_verifiable} | ${pct(a.unsourced_pct)} (${a.unsourced}/${a.typed}) | ${n2(a.checker_blockers_per_model)} | $${a.avg_cost.toFixed(2)} | ${Math.round(a.avg_tokens).toLocaleString("en-US")} | ${a.avg_seconds.toFixed(0)} s | ${a.errored} |`);
  }
  lines.push(
    "",
    "How to read it:",
    "- Wrong vs filing = filed figures (history lines, net debt, shares; comps revenue, EBITDA, net income, net debt) that verify_value found different from the filing, over those it could check.",
    "- Not verifiable = the filing doesn't report the line for that period, the period is ambiguous, or the company couldn't be resolved (e.g. a peer outside coverage). Reported, not counted as wrong.",
    "- Scoring uses deskstack's verify_value as the oracle; arms B and C read the same data, so their tie-out is partly by construction. The comparison that matters is A against B and C. The nightly differential test (evals/differential) checks verify_value itself against the filings with independent parsers.",
    "- Arm C sees the associate's tie-out before fixing, by design (it is B plus the review layer).",
    "- EBITDA and net debt are checked against deskstack's definitions (operating income + D&A; total debt excluding leases - cash - short-term investments), which every arm is given in the prompt. Why wrong splits mismatches by the hint verify_value gave (scale, sign, currency, period, line item, other).",
    "- Pairs exclude company-tasks where any arm crashed or hit the budget; crashed runs are counted per arm.",
  );
  return lines.join("\n");
}
