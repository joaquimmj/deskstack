// Scores deskstack's tool answers against evals/golden.json (known answers from the filed data).
// Used by test/golden.test.ts (recorded fixtures, every CI run) and scripts/golden.ts (the live connector, nightly).

export interface GoldenQuestion {
  id: string;
  question: string;
  tags: string[];
  call: { tool: string; args: Record<string, unknown> };
  read:
    | { kind: "fs"; period: string; group: string; key: string; end?: string; accession?: string }
    | { kind: "path"; path: string }
    | { kind: "has_ltm" }
    | { kind: "period_end"; period: string }
    /** True when the cell's note starts with `starts`: a fallback must say what it is. */
    | { kind: "fs_note"; period: string; group: string; key: string; starts: string; end?: undefined; accession?: undefined };
  expected: number | string | boolean | null;
  /** True when the answer only holds on the recorded fixtures (e.g. "has an LTM period" until the next 10-Q). */
  fixture_only?: boolean;
  unit: string | null;
  source: Record<string, unknown>;
}

export interface GoldenResult {
  id: string;
  pass: boolean;
  expected: GoldenQuestion["expected"];
  got: unknown;
  error?: string;
  tags: string[];
}

export type Caller = (tool: string, args: Record<string, unknown>) => Promise<{ isError: boolean; text: string; json: any }>;

function at(obj: any, path: string): unknown {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

/** The answer in a tool output. Throws when the output doesn't have the shape the question expects, so a renamed
 * field or a missing group is a miss, never a silent "null". */
export function read(q: GoldenQuestion, out: any, strictCitations = true): unknown {
  const r = q.read;
  if (r.kind === "path") {
    const v = at(out, r.path);
    if (v === undefined) throw new Error(`no field ${r.path}`);
    return v;
  }
  if (!Array.isArray(out?.periods)) throw new Error("no periods in the output");
  if (r.kind === "has_ltm") return out.periods.some((p: any) => p.type === "ltm");
  const p = out.periods.find((x: any) => x.label === r.period);
  if (!p) throw new Error(`no period ${r.period} (have ${out.periods.map((x: any) => x.label).join(", ")})`);
  if (r.kind === "period_end") return p.end;
  if (r.end && p.end !== r.end) throw new Error(`${r.period} ends ${p.end}, not ${r.end}`);
  const group = p[r.group];
  if (group == null || typeof group !== "object") throw new Error(`no ${r.group} in ${r.period}`);
  if (!(r.key in group)) throw new Error(`no ${r.key} in ${r.group}`);
  const cell = group[r.key];
  if (r.kind === "fs_note") return typeof cell?.note === "string" && cell.note.startsWith(r.starts);
  if (cell == null) return null;
  // On recorded fixtures the answer must cite the filing that reports it (the latest annual filing for that period).
  // Live, a later annual filing can report the same period again (next year's 10-K): citing it is right, as long as
  // the value is the same, which the caller checks.
  if (strictCitations && r.accession && cell.accession && cell.accession !== r.accession && !(cell.accessions ?? []).includes(r.accession)) {
    throw new Error(`${r.key} cites ${cell.accession}, not ${r.accession}`);
  }
  return cell.value;
}

/** Exact as filed: absolute amounts to the unit, per-share figures to the cent, rates to 1e-6. */
export function same(expected: GoldenQuestion["expected"], got: unknown, unit: string | null): boolean {
  if (expected === null) return got === null || got === undefined;
  if (typeof expected !== "number") return got === expected;
  if (typeof got !== "number" || !Number.isFinite(got)) return false;
  const tol = unit && /\/shares$/.test(unit) ? 0.005 : Math.abs(expected) < 1000 ? 1e-6 : 0.5;
  return Math.abs(got - expected) <= tol;
}

/** The shared server's per-minute limit (src/guard.ts rateMessage): the call is fine, it just came too fast. */
const RATE_LIMITED = /requests in a minute from your network/;

/** Retries: once after 1 s for a transient network error; up to three times after 61 s when the shared server's
 * per-minute limit answered (a full live run makes a few hundred calls; review 2026-11-11). */
async function withRetry(fn: () => ReturnType<Caller>): ReturnType<Caller> {
  let limited = 0;
  for (let attempt = 0; ; attempt++) {
    let r: Awaited<ReturnType<Caller>> | null = null;
    try {
      r = await fn();
      if (!r.isError) return r;
    } catch {
      /* retried below */
    }
    const rate = !!r && RATE_LIMITED.test(r.text);
    if (rate ? ++limited > 3 : attempt >= 1) return r ?? fn();
    await new Promise((res) => setTimeout(res, rate ? 61_000 : 1_000));
  }
}

export async function runGolden(questions: GoldenQuestion[], call: Caller, opts: { live?: boolean } = {}): Promise<GoldenResult[]> {
  const cache = new Map<string, Promise<{ isError: boolean; text: string; json: any }>>();
  const results: GoldenResult[] = [];
  for (const q of questions) {
    if (opts.live && q.fixture_only) continue;
    const key = JSON.stringify(q.call);
    if (!cache.has(key)) cache.set(key, withRetry(() => call(q.call.tool, q.call.args)));
    const base = { id: q.id, expected: q.expected, tags: q.tags };
    try {
      const r = await cache.get(key)!;
      if (r.isError) {
        results.push({ ...base, pass: false, got: null, error: r.text.slice(0, 300) });
        continue;
      }
      const got = read(q, r.json, !opts.live);
      results.push({ ...base, pass: same(q.expected, got, q.unit), got });
    } catch (e) {
      results.push({ ...base, pass: false, got: null, error: String((e as Error).message ?? e) });
    }
  }
  return results;
}

export function score(results: GoldenResult[]) {
  const passed = results.filter((r) => r.pass).length;
  const byTag: Record<string, { pass: number; total: number }> = {};
  for (const r of results) for (const t of r.tags) {
    byTag[t] ??= { pass: 0, total: 0 };
    byTag[t].total++;
    if (r.pass) byTag[t].pass++;
  }
  return { passed, total: results.length, accuracy: results.length ? passed / results.length : 0, byTag };
}

/** shields.io endpoint badge: https://img.shields.io/endpoint?url=<raw url of this JSON> */
export function badge(s: ReturnType<typeof score>) {
  const pct = Math.floor(s.accuracy * 1000) / 10;
  return { schemaVersion: 1, label: "golden set", message: `${pct}% (${s.passed}/${s.total})`, color: pct >= 95 ? "brightgreen" : pct >= 90 ? "yellow" : "red" };
}
