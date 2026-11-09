// The second reading of a mismatch on a reported line: is the submitted value another line of the same filing,
// or two of its lines added together? A model that took "revenues excluding excise taxes" instead of "sales", or
// added equipment leased to others to capex, didn't invent a number: it picked a different line. The scorer
// reports those apart from wrong numbers (found by the 2026-11-08 pilot, see its ANALYSIS.md).
//
// Facts come from the filing itself, not from deskstack: SEC companyfacts for the 10-K (or 20-F) period, or the
// ESEF report's xBRL-JSON on filings.xbrl.org. Company extension concepts are only in the ESEF reports.

import { CORE_DIMENSIONS, oimEnd, oimStart } from "../src/esef/extract";

export interface Fact {
  concept: string;
  value: number;
}

/** The period of one statement column, as deskstack's financial_statements labels it. */
export interface Column {
  start: string | null;
  end: string;
}

/** Half a unit of the last digit written: 218,945 (millions) can stand for 218,944.5M to 218,945.5M. */
export function tolerance(value: number, scale: number): number {
  const s = String(Math.abs(value));
  const decimals = s.includes("e") ? 0 : Math.min((s.split(".")[1] ?? "").length, 6);
  return 0.5 * 10 ** -decimals * scale;
}

/** A filing line (or two added together) equal to `value` within `tol`, compared in absolute value. */
export function findInFiling(value: number, tol: number, facts: Fact[]): string | null {
  const v = Math.abs(value);
  const seen = new Map<number, string>();
  for (const f of facts) {
    const a = Math.abs(f.value);
    if (a > 0 && !seen.has(a)) seen.set(a, f.concept);
  }
  for (const [a, c] of seen) if (Math.abs(a - v) <= tol) return c;
  const s = [...seen.entries()].sort((x, y) => x[0] - y[0]);
  for (let i = 0, j = s.length - 1; i < j; ) {
    const sum = s[i]![0] + s[j]![0];
    if (Math.abs(sum - v) <= tol) return `${s[i]![1]} + ${s[j]![1]}`;
    if (sum < v) i++;
    else j--;
  }
  return null;
}

const ANNUAL = new Set(["10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"]);

interface SecFact {
  val: number;
  start?: string;
  end: string;
  form?: string;
}

/** Facts of annual filings for one column, every namespace except dei, from SEC companyfacts JSON. */
export function secFactsFor(companyfacts: { facts?: Record<string, Record<string, { units?: Record<string, SecFact[]> }>> }, col: Column): Fact[] {
  const out: Fact[] = [];
  for (const [ns, concepts] of Object.entries(companyfacts.facts ?? {})) {
    if (ns === "dei") continue;
    for (const [name, c] of Object.entries(concepts)) {
      for (const [unit, rows] of Object.entries(c.units ?? {})) {
        if (unit === "pure" || unit.includes("/")) continue;
        for (const r of rows) {
          if (!ANNUAL.has(r.form ?? "") || r.end !== col.end) continue;
          // A period line must cover the column; a balance-sheet line (no start) is taken at the column's end.
          if (!r.start || r.start === col.start) out.push({ concept: `${ns}:${name}`, value: r.val });
        }
      }
    }
  }
  return out;
}

interface OimFact {
  value?: unknown;
  dimensions?: Record<string, string>;
}

/** Facts of an ESEF report (xBRL-JSON) for one column, including company extension concepts. */
export function esefFactsFor(report: { facts?: Record<string, OimFact> }, col: Column): Fact[] {
  const out: Fact[] = [];
  for (const f of Object.values(report.facts ?? {})) {
    const d = f.dimensions ?? {};
    if (Object.keys(d).some((k) => !CORE_DIMENSIONS.has(k))) continue; // a segment or member, not a statement line
    const value = Number(f.value);
    if (!d.concept || !d.period || !Number.isFinite(value) || typeof f.value === "boolean") continue;
    const [a, b] = d.period.split("/");
    const start = b ? oimStart(a!) : null;
    const end = oimEnd(b ?? a!);
    if (end !== col.end) continue;
    if (start === null || start === col.start) out.push({ concept: d.concept, value });
  }
  return out;
}

export interface FactSourceOpts {
  /** SEC asks automated clients for a User-Agent with a contact; without one, SEC facts are skipped. */
  secUserAgent?: string;
  fetch?: typeof fetch;
}

/** Fetches and caches the filing facts the scorer needs, by SEC CIK or by LEI. */
export function filingFactSource(o: FactSourceOpts = {}) {
  const get = o.fetch ?? fetch;
  const cache = new Map<string, Promise<unknown | null>>();
  const json = (url: string, headers: Record<string, string> = {}) => {
    if (!cache.has(url)) {
      cache.set(
        url,
        get(url, { headers })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
      );
    }
    return cache.get(url)!;
  };
  return {
    async sec(cik: number, col: Column): Promise<Fact[] | null> {
      if (!o.secUserAgent) return null;
      const cf = await json(`https://data.sec.gov/api/xbrl/companyfacts/CIK${String(cik).padStart(10, "0")}.json`, { "User-Agent": o.secUserAgent });
      return cf ? secFactsFor(cf as never, col) : null;
    },
    async esef(lei: string, col: Column): Promise<Fact[] | null> {
      const list = (await json(`https://filings.xbrl.org/api/entities/${lei}/filings?page[size]=100`)) as {
        data?: Array<{ attributes: { period_end?: string; json_url?: string | null } }>;
      } | null;
      const filing = list?.data?.find((f) => f.attributes.period_end === col.end && f.attributes.json_url);
      if (!filing) return null;
      const report = await json(`https://filings.xbrl.org${filing.attributes.json_url}`);
      return report ? esefFactsFor(report as never, col) : null;
    },
  };
}
