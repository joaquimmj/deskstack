// Scores one submitted model, automatically and against the filings (brief §8.2):
//   - every filed figure (history lines, net debt, diluted shares; comps revenue / EBITDA / net income / net debt)
//     goes through the connector's verify_value: match, mismatch (with its likely cause), not found, ambiguous, or
//     unverifiable when the company can't be resolved with confidence;
//   - every typed number is checked for a usable source;
//   - the workbook built from the spec goes through the deterministic checker.
// Market caps and assumptions aren't filed figures: they count toward sourcing only.
//
// A mismatch is not always a wrong number (pilot of 2026-11-08, ANALYSIS.md):
//   - EBITDA and net debt are computed, and definitions vary: a mismatch there is "definition", not wrong;
//   - a reported line that equals another line of the same filing (or two of them added) is "other_line": the
//     model picked a different line (revenue excluding excise taxes, capex including leased equipment).
// Only what's left counts as wrong.

import type { Connector } from "./connector";
import { findInFiling, tolerance, type Fact } from "./filing-facts";
import { buildWorkbook, checkWorkbook } from "./pytools";

export interface Item {
  company: string; // the asked company's frozen id, or the resolved id of a peer
  name?: string;
  written?: string; // the ticker as the model wrote it
  metric: string;
  period: string;
  value: number;
  scale: string;
  currency?: string;
  ref: string;
}

export type ScoredItem = Item & { status: string; cause?: string; hints?: string[]; filed_value?: number | null; resolved?: string | null; other_line?: string };

export interface Score {
  valid: boolean;
  error?: string;
  filed: number;
  match: number;
  mismatch: number;
  /** Equal to another line of the same filing, or two lines added: a different line, not a wrong number. */
  other_line?: number;
  /** EBITDA or net debt different from deskstack's definition: definitions vary, so not counted as wrong. */
  definition?: number;
  not_found: number;
  ambiguous: number;
  unverifiable: number;
  causes: Record<string, number>; // mismatches by likely cause: scale, sign, period, line item, currency, other
  typed: number;
  unsourced: number;
  checker?: { blocker: number; major: number; minor: number };
  items: ScoredItem[];
  unsourced_refs: string[];
  errors: string[];
}

// A source that names nothing: empty, a placeholder, or an admission that it wasn't found.
const WEAK = /^\s*$|^\s*(n\/?a|na|none|unknown|-+|\?+)\s*$|\b(tbd|todo|xxx+|guess(ed)?|placeholder|not found|not available|unavailable|from (my )?(memory|knowledge)|i think|i believe|approximately|roughly|ballpark)\b|\?\s*$/i;
const LINES: Record<string, string> = { revenue: "revenue", operating_income: "operating_income", d_and_a: "d_and_a", capex: "capex" };
const STOP = new Set(["the", "inc", "corp", "corporation", "company", "co", "sa", "se", "nv", "plc", "ag", "ab", "oyj", "spa", "group", "holding", "holdings", "ltd", "limited", "and", "de", "of"]);

type Spec = Record<string, any>;

/** Period as verify_value takes it: FY2025, LTM, latest or YYYY-MM-DD. A bare year becomes FY2025, like the builder. */
export function normPeriod(p: unknown): string | null {
  const t = String(p ?? "").trim();
  if (!t) return null;
  if (/^\d{4}$/.test(t)) return `FY${t}`;
  const m = t.match(/\b(FY ?\d{4}|FY ?\d{2}|LTM|TTM|\d{4}-\d{2}-\d{2})\b/i);
  if (!m) return null;
  const x = m[1]!.toUpperCase().replace(" ", "");
  if (x === "TTM") return "LTM";
  if (/^FY\d{2}$/.test(x)) return `FY20${x.slice(2)}`;
  return /^\d{4}-/.test(x) ? m[1]! : x;
}

const words = (s: string) => new Set(s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").split(/[^a-z0-9]+/).filter((w) => w.length >= 2 && !STOP.has(w)));
export function sameName(a: string, b: string): boolean {
  const A = words(a), B = words(b);
  for (const w of A) if (B.has(w)) return true;
  return false;
}

/** Filed figures to tie out, and every typed number with its source. */
export function itemsOf(spec: Spec, asked: { id: string; name: string }): { items: Item[]; typed: Array<{ ref: string; source: string }> } {
  const items: Item[] = [];
  const typed: Array<{ ref: string; source: string }> = [];
  const scale = String(spec.scale ?? "units");
  const cur = (c: unknown) => (typeof c === "string" && /^[A-Z]{3}$/.test(c.trim()) ? c.trim() : undefined);
  const add = (ref: string, v: unknown, source: unknown) => {
    if (typeof v === "number" && Number.isFinite(v)) typed.push({ ref, source: typeof source === "string" ? source : "" });
  };
  const push = (it: Omit<Item, "period"> & { period: unknown }) => {
    items.push({ ...it, period: normPeriod(it.period) ?? String(it.period ?? "").slice(0, 40), ref: it.ref.slice(0, 60) });
  };
  if (spec.kind === "dcf") {
    const periods: string[] = spec.history?.periods ?? [];
    for (const [key, metric] of Object.entries(LINES)) {
      const line = spec.history?.lines?.[key];
      (line?.values ?? []).forEach((v: unknown, i: number) => {
        const ref = `history.${key}[${periods[i] ?? i}]`;
        add(ref, v, line?.sources?.[i] ?? line?.source);
        if (typeof v === "number" && periods[i] !== undefined) push({ company: asked.id, metric, period: periods[i], value: v, scale, currency: cur(spec.currency), ref });
      });
    }
    const last = periods.at(-1) ?? "latest";
    for (const k of ["net_debt", "diluted_shares"]) {
      const b = spec.bridge?.[k];
      add(`bridge.${k}`, b?.value, b?.source);
      if (typeof b?.value === "number") push({ company: asked.id, metric: k, period: normPeriod(b.period) ? b.period : last, value: b.value, scale, currency: k === "net_debt" ? cur(spec.currency) : undefined, ref: `bridge.${k}` });
    }
    const a = spec.assumptions ?? {};
    (a.revenue_growth?.values ?? []).forEach((v: unknown, i: number) => add(`assumptions.revenue_growth[${i}]`, v, a.revenue_growth?.sources?.[i] ?? a.revenue_growth?.source));
    for (const k of ["ebit_margin", "tax_rate", "da_pct_revenue", "capex_pct_revenue", "wacc", "terminal_growth"]) add(`assumptions.${k}`, a[k]?.value, a[k]?.source);
  } else if (spec.kind === "comps") {
    for (const p of spec.peers ?? []) {
      const tk = String(p.ticker ?? "");
      const isTarget = [String(spec.target ?? ""), asked.id].some((t) => t && tk.toUpperCase() === t.toUpperCase()) || (p.name && sameName(String(p.name), asked.name));
      for (const k of ["revenue", "ebitda", "net_income", "net_debt", "market_cap"]) {
        const c = p[k];
        const ref = `peers[${tk || p.name}].${k}`;
        add(ref, c?.value, c?.source);
        if (k !== "market_cap" && typeof c?.value === "number") {
          push({ company: isTarget ? asked.id : "", name: String(p.name ?? ""), written: tk, metric: k, period: c.period || spec.period || "latest", value: c.value, scale, currency: cur(p.currency) ?? cur(spec.currency), ref });
        }
      }
    }
  }
  return { items, typed };
}

export interface Opts {
  sleep?: (ms: number) => Promise<void>;
  /** The filing's own facts for a company id and period label (e.g. "FY2025"), or null when unavailable. */
  filingFacts?: (company: string, period: string) => Promise<Fact[] | null>;
}

/** Computed from several lines, with definitions that vary between companies and analysts. */
export const COMPUTED = new Set(["ebitda", "net_debt"]);
const SCALE: Record<string, number> = { units: 1, thousands: 1e3, millions: 1e6, billions: 1e9 };

/** Reclassifies mismatches that are a different definition or a different line of the same filing. */
export async function secondReading(items: ScoredItem[], o: Opts = {}): Promise<ScoredItem[]> {
  const out: ScoredItem[] = [];
  for (const x of items) {
    if (x.status !== "mismatch") {
      out.push(x);
      continue;
    }
    const { cause: _c, ...rest } = x;
    if (COMPUTED.has(x.metric)) {
      out.push({ ...rest, status: "definition", hints: [...(x.hints ?? []), "computed figure: differs from deskstack's definition, which varies between analysts"] });
      continue;
    }
    const scale = SCALE[x.scale] ?? null;
    const facts = scale && x.company && o.filingFacts ? await o.filingFacts(x.company, x.period).catch(() => null) : null;
    const hit = facts && scale ? findInFiling(x.value * scale, tolerance(x.value, scale), facts, x.metric) : null;
    out.push(hit ? { ...rest, status: "other_line", other_line: hit, hints: [...(x.hints ?? []), `equals ${hit} in the same filing`] } : x);
  }
  return out;
}

async function callWithRetry(c: Connector, name: string, args: Record<string, unknown>, o: Opts) {
  const sleep = o.sleep ?? ((ms: number) => new Promise((r) => setTimeout(r, ms)));
  let r = await c.call(name, args);
  for (let i = 0; i < 3 && r.isError && /too many requests|capacity|rate limit|try again/i.test(r.text); i++) {
    await sleep(20_000 * (i + 1));
    r = await c.call(name, args);
  }
  return r;
}

/** A peer's id: company_lookup by name (and ticker), accepted only when the hit's name matches the peer's name. */
async function resolvePeer(c: Connector, name: string, written: string, cache: Map<string, string | null>, o: Opts): Promise<string | null> {
  const key = `${name}|${written}`;
  if (cache.has(key)) return cache.get(key)!;
  let id: string | null = null;
  const local = written.replace(/[.:][A-Z]{1,4}$/i, "");
  const queries = [name, /^\d+$/.test(local) ? null : local].filter((q): q is string => !!q && q.length > 1);
  outer: for (const q of queries) {
    const r = await callWithRetry(c, "company_lookup", { query: q, limit: 5 }, o);
    if (r.isError) continue;
    for (const hit of (JSON.parse(r.text).results ?? []) as Array<{ name?: string; lei?: string; ticker?: string | null; cik?: number }>) {
      if (hit.name && name && sameName(hit.name, name)) {
        id = hit.lei ?? hit.ticker ?? (hit.cik ? String(hit.cik) : null);
        if (id) break outer;
      }
    }
  }
  cache.set(key, id);
  return id;
}

const CAUSES: Array<[string, RegExp]> = [["scale", /^Scale:/], ["sign", /^Sign:/], ["currency", /^Currency:/], ["period", /^Period:/], ["line item", /^Line item:/], ["typo", /^Typo:/]];

export async function verify(connector: Connector, items: Item[], o: Opts = {}, errors: string[] = []): Promise<ScoredItem[]> {
  const out: ScoredItem[] = [];
  const ids = new Map<string, string | null>();
  const groups = new Map<string, Item[]>();
  for (const it of items) {
    const id = it.company || (await resolvePeer(connector, it.name ?? "", it.written ?? "", ids, o));
    if (!id) {
      out.push({ ...it, status: "unverifiable", resolved: null, hints: ["company not resolved with a matching name by company_lookup"] });
      continue;
    }
    groups.set(id, [...(groups.get(id) ?? []), { ...it, company: id }]);
  }
  const toArg = (x: Item) => ({ metric: x.metric, period: x.period, value: x.value, scale: x.scale, ...(x.currency ? { currency: x.currency } : {}), ref: x.ref });
  const record = (x: Item, v: { status: string; hints?: string[]; filed?: number | null } | undefined) => {
    const hints = v?.hints ?? [];
    const cause = v?.status === "mismatch" ? (CAUSES.find(([, re]) => hints.some((h) => re.test(h)))?.[0] ?? "other") : undefined;
    out.push({ ...x, status: v?.status ?? "unverifiable", ...(cause ? { cause } : {}), hints, filed_value: v?.filed ?? null, resolved: x.company });
  };
  for (const [company, list] of groups) {
    for (let i = 0; i < list.length; i += 50) {
      const chunk = list.slice(i, i + 50);
      const r = await callWithRetry(connector, "verify_value", { company, items: chunk.map(toArg) }, o);
      if (!r.isError) {
        const res = JSON.parse(r.text).results as Array<{ ref: string; status: string; hints: string[]; filed: number | null }>;
        for (const x of chunk) record(x, res.find((y) => y.ref === x.ref));
        continue;
      }
      // One bad item rejects the whole call: fall back to one call per item, so only that item is unverifiable.
      errors.push(`verify_value ${company}: ${r.text.slice(0, 200)}`);
      for (const x of chunk) {
        const one = await callWithRetry(connector, "verify_value", { company, items: [toArg(x)] }, o);
        if (one.isError) out.push({ ...x, status: "unverifiable", resolved: company, hints: [one.text.slice(0, 200)] });
        else record(x, (JSON.parse(one.text).results as Array<{ status: string; hints: string[]; filed: number | null }>)[0]);
      }
    }
  }
  return out;
}

export async function scoreSubmission(connector: Connector, spec: Spec | null, asked: { id: string; name: string }, dir: string, o: Opts = {}): Promise<Score> {
  const empty: Score = { valid: false, filed: 0, match: 0, mismatch: 0, other_line: 0, definition: 0, not_found: 0, ambiguous: 0, unverifiable: 0, causes: {}, typed: 0, unsourced: 0, items: [], unsourced_refs: [], errors: [] };
  if (!spec) return { ...empty, error: "no model submitted" };
  const errors: string[] = [];
  const { items, typed } = itemsOf(spec, asked);
  const verified = await secondReading(await verify(connector, items, o, errors), o);
  const n = (s: string) => verified.filter((x) => x.status === s).length;
  const causes: Record<string, number> = {};
  for (const x of verified) if (x.cause) causes[x.cause] = (causes[x.cause] ?? 0) + 1;
  const unsourced = typed.filter((t) => WEAK.test(t.source) || t.source.trim().length < 3);
  const built = buildWorkbook(spec, dir);
  let checker: Score["checker"];
  if (built.ok) {
    try {
      const c = checkWorkbook(built.path).counts;
      checker = { blocker: c.blocker ?? 0, major: c.major ?? 0, minor: c.minor ?? 0 };
    } catch (e) {
      errors.push(`checker: ${String((e as Error).message ?? e)}`);
    }
  }
  return {
    valid: built.ok,
    ...(built.ok ? {} : { error: built.error }),
    filed: verified.length,
    match: n("match"),
    mismatch: n("mismatch"),
    other_line: n("other_line"),
    definition: n("definition"),
    not_found: n("not_found"),
    ambiguous: n("ambiguous"),
    unverifiable: n("unverifiable"),
    causes,
    typed: typed.length,
    unsourced: unsourced.length,
    checker,
    items: verified,
    unsourced_refs: unsourced.map((u) => u.ref),
    errors,
  };
}
