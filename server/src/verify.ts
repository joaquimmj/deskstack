// verify_value: tie out numbers from a model or memo to the filed figures.
//
// For each claimed value (line item, period, value, unit) we look up the
// standardized cell (the same rules as financial_statements), compare within
// a tolerance, and when it doesn't match we look for the usual causes: a scale
// error (thousands vs millions), a flipped sign, the wrong currency, a figure
// from another period, or a different line item. Pure: no I/O.

import type { Cell, Column, Derived, Standardized } from "./sec/xbrl";

export type Status = "match" | "mismatch" | "not_found" | "ambiguous";
export type Scale = "units" | "thousands" | "millions" | "billions";

export interface VerifyItem {
  /** Line item: a standardized key (revenue, net_income, ...) or a common name ("sales", "EBIT", "capex"). */
  metric: string;
  /** "FY2024", "2024", "LTM", "latest", or a period end date "2024-09-28". */
  period: string;
  value: number;
  /** Scale the value is expressed in (default units). */
  scale?: Scale;
  /** ISO currency of the value, if stated. */
  currency?: string;
  /**
   * Relative tolerance. Default: the rounding the number is written with (half a unit of its last
   * significant digit), so 391 (billions) accepts 391.035 B but 390.135 B does not.
   */
  tolerance?: number;
  /** Free label echoed back (e.g. the cell reference "Inputs!C7"). */
  ref?: string;
}

export interface VerifyResult {
  ref: string | null;
  metric: string;
  resolved_metric: string | null;
  period: string;
  resolved_period: string | null;
  status: Status;
  claimed: number;
  /** The claimed value converted to units (scale applied). */
  claimed_units: number;
  filed: number | null;
  difference: number | null;
  relative_difference: number | null;
  concept: string | null;
  computed: boolean;
  /** The filed figure's own caveat (a segment total, a figure including impairment, basic EPS...), when it has one. */
  note?: string;
  accessions: string[];
  /** How far off the claimed value may be and still match, in units, and why. */
  allowance: { units: number; basis: string };
  hints: string[];
}

const SCALE: Record<Scale, number> = { units: 1, thousands: 1e3, millions: 1e6, billions: 1e9 };

/** Common names for the standardized line items. */
const ALIASES: Record<string, string> = {
  revenue: "revenue",
  revenues: "revenue",
  sales: "revenue",
  "net sales": "revenue",
  "total revenue": "revenue",
  turnover: "revenue",
  "chiffre d'affaires": "revenue",
  "gross profit": "gross_profit",
  "gross margin": "gross_profit",
  "operating income": "operating_income",
  "operating profit": "operating_income",
  ebit: "operating_income",
  "pretax income": "pretax_income",
  "income before taxes": "pretax_income",
  "profit before tax": "pretax_income",
  ebt: "pretax_income",
  "net income": "net_income",
  "net profit": "net_income",
  earnings: "net_income",
  "interest expense": "interest_expense",
  "d&a": "d_and_a",
  "depreciation and amortization": "d_and_a",
  "depreciation & amortization": "d_and_a",
  "operating cash flow": "operating_cash_flow",
  "cash from operations": "operating_cash_flow",
  cfo: "operating_cash_flow",
  capex: "capex",
  "capital expenditures": "capex",
  "capital expenditure": "capex",
  "diluted shares": "diluted_shares",
  "weighted average diluted shares": "diluted_shares",
  eps: "diluted_eps",
  "diluted eps": "diluted_eps",
  cash: "cash",
  "cash and cash equivalents": "cash",
  "short term investments": "short_term_investments",
  "total assets": "total_assets",
  assets: "total_assets",
  equity: "total_equity",
  "total equity": "total_equity",
  "shareholders equity": "total_equity",
  "stockholders equity": "total_equity",
  ebitda: "ebitda",
  fcf: "free_cash_flow",
  "free cash flow": "free_cash_flow",
  debt: "total_debt",
  "total debt": "total_debt",
  "gross debt": "total_debt",
  "net debt": "net_debt",
};

export function resolveMetric(m: string): string | null {
  const k = m.trim().toLowerCase().replace(/[_]+/g, " ").replace(/\s+/g, " ");
  return ALIASES[k] ?? ALIASES[k.replace(/ /g, "_")] ?? (k.replace(/ /g, "_") in KNOWN ? k.replace(/ /g, "_") : null);
}

const KNOWN: Record<string, true> = Object.fromEntries(
  [
    "revenue", "gross_profit", "operating_income", "pretax_income", "net_income", "interest_expense", "d_and_a",
    "operating_cash_flow", "capex", "diluted_shares", "diluted_eps", "cash", "short_term_investments", "total_assets",
    "total_equity", "ebitda", "free_cash_flow", "total_debt", "net_debt",
  ].map((k) => [k, true]),
);

type AnyCell = (Cell & { formula?: string }) | (Derived & { concept?: undefined; accession?: undefined; accessions?: undefined });

function cellOf(col: Column, metric: string): AnyCell | null {
  return (col.values[metric] ?? col.balance_sheet[metric] ?? col.derived[metric] ?? null) as AnyCell | null;
}

/** Columns a period string can mean. Several = ambiguous (e.g. "2024" for a retailer whose FY2024 ends in 2025). */
export function resolvePeriod(std: Standardized, p: string): Column[] {
  const s = p.trim().toUpperCase();
  const cols = std.periods;
  const annual = cols.filter((c) => c.type === "annual");
  if (s === "LTM" || s === "TTM") return cols.filter((c) => c.type === "ltm");
  if (s === "LATEST" || s === "LAST" || s === "LFY") return annual.slice(-1);
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
    // A period end: an exact match, else a 52/53-week year ending within a week of it.
    const exact = cols.filter((c) => c.end === s);
    if (exact.length) return exact;
    const t = Date.parse(`${s}T00:00:00Z`);
    return annual.filter((c) => Math.abs(Date.parse(`${c.end}T00:00:00Z`) - t) <= 7 * 86_400_000);
  }
  const fy = /^(?:FY|F)?\s*'?(\d{2}|\d{4})$/.exec(s);
  if (fy) {
    const y = fy[1]!.length === 2 ? 2000 + Number(fy[1]) : Number(fy[1]);
    const byLabel = annual.filter((c) => c.label === `FY${y}`);
    // A bare year can also mean "the fiscal year that ended in that calendar year".
    const byEnd = /^\d{4}$/.test(s) ? annual.filter((c) => c.end.startsWith(`${y}-`) && c.label !== `FY${y}`) : [];
    return [...byLabel, ...byEnd];
  }
  return [];
}

/**
 * Half a unit of the last significant digit of `v`: 391.035 -> 0.0005, 391 -> 0.5, 391000 -> 500.
 * Trailing zeros of an integer are read as rounding (391,000 million is "rounded to the billion").
 */
export function roundingStep(v: number): number {
  const a = Math.abs(v);
  if (!Number.isFinite(a) || a === 0) return 0.5;
  const str = a.toPrecision(15).replace(/0+$/, "").replace(/\.$/, "");
  const dot = str.indexOf(".");
  if (dot >= 0) return 0.5 * 10 ** -(str.length - dot - 1);
  const z = /0*$/.exec(String(Math.round(a)))![0].length;
  return 0.5 * 10 ** z;
}

function allowanceFor(it: VerifyItem, scale: Scale, filed: number): { units: number; basis: string } {
  if (it.tolerance !== undefined) {
    return { units: it.tolerance * Math.abs(filed), basis: `relative tolerance ${it.tolerance}` };
  }
  const step = roundingStep(it.value) * SCALE[scale];
  // Never tighter than one part in a million (float noise), never looser than 1% (a rounding claim that wide is not a tie-out).
  const units = Math.min(Math.max(step, 1e-6 * Math.abs(filed)), 0.01 * Math.abs(filed) || step);
  return { units, basis: `rounding of the value as written (±${fmt(units)})` };
}

function within(claimed: number, filed: number, allowance: number): boolean {
  if (filed === 0) return Math.abs(claimed) <= allowance;
  return Math.abs(claimed - filed) <= allowance + 1e-9 * Math.abs(filed);
}

const fmt = (v: number) => (Math.abs(v) >= 1e6 ? v.toExponential(4) : String(Math.round(v * 1e4) / 1e4));

export function verifyItems(std: Standardized, items: VerifyItem[]): VerifyResult[] {
  return items.map((it) => {
    const scale = it.scale ?? "units";
    const claimedUnits = it.value * SCALE[scale];
    const metric = resolveMetric(it.metric);
    const base: VerifyResult = {
      ref: it.ref ?? null,
      metric: it.metric,
      resolved_metric: metric,
      period: it.period,
      resolved_period: null,
      status: "not_found",
      claimed: it.value,
      claimed_units: claimedUnits,
      filed: null,
      difference: null,
      relative_difference: null,
      concept: null,
      computed: false,
      accessions: [],
      allowance: { units: 0, basis: "" },
      hints: [],
    };
    if (!metric) {
      base.hints.push(
        `Unknown line item ${JSON.stringify(it.metric)}. Use one of: ${Object.keys(KNOWN).join(", ")} (or a common name like "sales", "EBIT", "capex").`,
      );
      return base;
    }
    const cols = resolvePeriod(std, it.period);
    if (!cols.length) {
      const have = std.periods.map((c) => c.label).join(", ");
      base.hints.push(`No period ${JSON.stringify(it.period)}. Available: ${have}.`);
      return base;
    }
    if (cols.length > 1) {
      base.status = "ambiguous";
      base.hints.push(
        `${JSON.stringify(it.period)} can mean ${cols.map((c) => `${c.label} (ended ${c.end})`).join(" or ")}; ` +
          "pass the fiscal-year label or the period end date.",
      );
      return base;
    }
    const col = cols[0]!;
    base.resolved_period = `${col.label} (ended ${col.end})`;
    const cell = cellOf(col, metric);
    if (!cell) {
      base.hints.push(`${metric} is not reported for ${col.label} (null in the filing data). Do not use a figure from memory.`);
      return base;
    }
    const filed = cell.value;
    base.filed = filed;
    base.difference = claimedUnits - filed;
    base.relative_difference = filed !== 0 ? (claimedUnits - filed) / Math.abs(filed) : null;
    base.concept = "concept" in cell && cell.concept ? cell.concept : null;
    base.computed = !base.concept;
    base.accessions = "accessions" in cell && cell.accessions ? cell.accessions : "accession" in cell && cell.accession ? [cell.accession] : [];
    if (base.computed && "formula" in cell) base.hints.push(`Computed value: ${cell.formula}.`);
    if ("note" in cell && cell.note) {
      base.note = cell.note;
      base.hints.push(`About this figure: ${cell.note}.`);
    }

    const allow = allowanceFor(it, scale, filed);
    base.allowance = allow;
    const tolFor = (f: number) => allowanceFor(it, scale, f).units;
    if (it.currency && it.currency.toUpperCase() !== std.currency) {
      base.status = "mismatch";
      base.hints.push(`Currency: the value is stated in ${it.currency.toUpperCase()} but the company reports in ${std.currency}; convert with fx_rate first.`);
      return base;
    }
    if (within(claimedUnits, filed, allow.units)) {
      base.status = "match";
      return base;
    }
    base.status = "mismatch";
    // Why might it be off? Check the usual suspects, most specific first.
    for (const [name, f] of Object.entries(SCALE) as Array<[Scale, number]>) {
      if (name !== scale && within(it.value * f, filed, roundingStep(it.value) * f + 1e-6 * Math.abs(filed))) {
        base.hints.push(`Scale: the value matches if it is in ${name}, not ${scale} (filed ${fmt(filed)} = ${fmt(filed / f)} ${name}).`);
      }
    }
    const typo = transposition(it.value, filed / SCALE[scale]);
    if (typo) base.hints.push(typo);
    if (within(-claimedUnits, filed, allow.units)) base.hints.push("Sign: the value has the opposite sign of the filed figure (capex and D&A are reported as positive outflows).");
    for (const other of std.periods) {
      if (other === col) continue;
      const oc = cellOf(other, metric);
      if (oc && within(claimedUnits, oc.value, tolFor(oc.value))) base.hints.push(`Period: the value matches ${metric} for ${other.label} (ended ${other.end}), not ${col.label}.`);
    }
    for (const k of Object.keys(KNOWN)) {
      if (k === metric) continue;
      const oc = cellOf(col, k);
      if (oc && oc.value !== 0 && within(claimedUnits, oc.value, tolFor(oc.value))) base.hints.push(`Line item: the value matches ${k} for ${col.label}, not ${metric}.`);
    }
    return base;
  });
}

/**
 * "391,053" written for a filed 391,035: two adjacent digits swapped, the classic keying error (the difference is a
 * multiple of 9). Compared at the written value's own precision.
 */
export function transposition(written: number, filedInScale: number): string | null {
  const dec = Math.min((String(Math.abs(written)).split(".")[1] ?? "").length, 6);
  const show = (v: number) => v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
  const a = Math.abs(written).toFixed(dec).replace(".", "");
  const b = Math.abs(filedInScale).toFixed(dec).replace(".", "");
  if (a.length !== b.length || Math.sign(written) !== Math.sign(filedInScale)) return null;
  if (a.replace(/^0+/, "").length < 3) return null; // with two digits a "swap" is too often a coincidence
  const diff = [...a].flatMap((ch, i) => (ch !== b[i] ? [i] : []));
  if (diff.length !== 2 || diff[1] !== diff[0]! + 1 || a[diff[0]!] !== b[diff[1]!] || a[diff[1]!] !== b[diff[0]!]) return null;
  return `Typo: two adjacent digits look swapped (filed ${show(filedInScale)}, written ${show(written)}).`;
}

export function summarize(results: VerifyResult[]) {
  const by = (s: Status) => results.filter((r) => r.status === s).length;
  return { total: results.length, match: by("match"), mismatch: by("mismatch"), not_found: by("not_found"), ambiguous: by("ambiguous") };
}
