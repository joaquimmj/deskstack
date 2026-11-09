// ESEF (European Single Electronic Format) annual reports, as xBRL-JSON (the
// OIM JSON form filings.xbrl.org publishes for each filing), reduced to the
// rows the IFRS standardizer reads. The same standardize() then applies the
// same rules as for SEC filers: per-period concept priority, restatements from
// the latest filing, debt without double counting, null never zero.
//
// Pure functions: used by the snapshot build (scripts/build-esef.ts) and tests.

import { shiftDays } from "../dates";
import { EXT_CAPEX_KEY, IFRS_DURATION_CONCEPTS, type CompanyFacts, type Namespace, type RawFact } from "../sec/xbrl";

/** One undimensioned numeric ifrs-full fact, compact for the build cache. */
export interface EsefRow {
  /** ifrs-full local name, e.g. "Revenue" (or a synthetic key for a kept extension concept, see x) */
  c: string;
  /** the issuer's own concept behind a synthetic key, e.g. "tot:PurchaseOfPropertyPlantAndEquipmentAndIntangibleAssets" */
  x?: string;
  /** "EUR", "USD", "EUR/shares", "shares" */
  u: string;
  /** start date (durations only) */
  s: string | null;
  /** end date (inclusive) */
  e: string;
  v: number;
}

export type ReportKind = "annual" | "half-year" | "unknown";

export interface ExtractedFiling {
  fxo_id: string;
  kind: ReportKind;
  /** End of the reporting period, from the facts (not the repository metadata). */
  report_end: string | null;
  rows: EsefRow[];
  /** Numeric facts that use a company-specific (extension) concept; all are dropped except extension capex. */
  extension_facts: number;
}

interface OimFact {
  value?: unknown;
  dimensions?: Record<string, string>;
}

export const CORE_DIMENSIONS = new Set(["concept", "entity", "period", "unit", "language"]);

/** OIM dates: "2026-01-01T00:00:00" is the instant at the start of Jan 1, i.e. the end of Dec 31. */
export function oimEnd(s: string): string {
  const [d, t] = s.split("T");
  return t && /^00:00:00/.test(t) ? shiftDays(d!, -1) : d!;
}

export function oimStart(s: string): string {
  return s.split("T")[0]!;
}

/** "iso4217:EUR" -> "EUR", "iso4217:EUR/xbrli:shares" -> "EUR/shares", "xbrli:shares" -> "shares". */
export function oimUnit(u: string | undefined): string | null {
  if (!u) return null;
  const parts = u.split("/").map((p) => {
    const [ns, local] = p.includes(":") ? p.split(":") : ["", p];
    if (ns === "iso4217") return local!;
    if (local === "shares") return "shares";
    return null;
  });
  return parts.includes(null) ? null : parts.join("/");
}

const days = (s: string, e: string) => Math.round((Date.parse(`${e}T00:00:00Z`) - Date.parse(`${s}T00:00:00Z`)) / 86_400_000) + 1;

// "PurchaseOfPropertyPlantAndEquipmentAndIntangibleAssets", "PurchasesOfIntangibleAssetsPropertyPlantAndEquipment...",
// "InvestmentsInPropertyPlantAndEquipmentAndIntangibleAssets": PP&E and intangibles, both named, bought or invested in.
// Look-alikes are excluded: unpaid or accrued amounts, leases, associates, acquisitions of businesses, disposals.
// Investment property stays in, as in the standard IFRS concept (Airbus tags PP&E, intangibles and investment property).
const EXT_CAPEX = /^(purchases?of|investmentsin|acquisitionsof)(?=.*propertyplantandequipment)(?=.*intangible)(?!.*(proceeds|sale|disposal|subsidiar|financial|notyet|unpaid|accrued|payable|lease|rightofuse|associate|jointventure|business|grant))/i;
// A well-formed QName: the issuer's concept is published as-is, so nothing else gets through.
const QNAME = /^[A-Za-z_][\w.-]{0,63}:[A-Za-z_][\w.-]{0,200}$/;

/** Undimensioned numeric ifrs-full facts of one filing (plus kept extension capex), deduplicated, and the report kind. */
export function extractFiling(doc: { facts?: Record<string, OimFact> }, fxoId: string): ExtractedFiling {
  const seen = new Set<string>();
  const rows: EsefRow[] = [];
  const extCapex = new Map<string, Map<string, EsefRow>>();
  let extension = 0;
  for (const f of Object.values(doc.facts ?? {})) {
    const dims = f.dimensions ?? {};
    if (Object.keys(dims).some((k) => !CORE_DIMENSIONS.has(k))) continue; // a breakdown (segment, component...)
    const concept = dims.concept ?? "";
    const raw = typeof f.value === "string" ? f.value : null;
    if (raw === null || raw.trim() === "" || !Number.isFinite(Number(raw))) continue;
    let c: string;
    let x: string | undefined;
    if (concept.startsWith("ifrs-full:")) {
      c = concept.slice("ifrs-full:".length);
    } else {
      extension++;
      // Issuers that tag capex only with their own concept (purchases of PP&E and intangible assets).
      if (!QNAME.test(concept) || !EXT_CAPEX.test(concept.split(":").pop() ?? "")) continue;
      c = EXT_CAPEX_KEY;
      x = concept;
    }
    const unit = oimUnit(dims.unit);
    const period = dims.period;
    if (!unit || !period) continue;
    const [a, b] = period.split("/");
    const row: EsefRow = b
      ? { c, u: unit, s: oimStart(a!), e: oimEnd(b), v: Number(raw) }
      : { c, u: unit, s: null, e: oimEnd(a!), v: Number(raw) };
    if (x) {
      // A purchase is an outflow: stored positive like the standard capex concepts, whatever the issuer's sign.
      row.x = x;
      row.v = Math.abs(row.v);
      const k = `${row.u}|${row.s}|${row.e}`;
      if (!extCapex.has(k)) extCapex.set(k, new Map());
      extCapex.get(k)!.set(x, row);
      continue;
    }
    const key = `${row.c}|${row.u}|${row.s}|${row.e}`;
    if (seen.has(key)) continue; // the same fact tagged in several places of the report
    seen.add(key);
    rows.push(row);
  }
  // One issuer concept per period is a capex line; two different ones are ambiguous, so neither is used.
  for (const byConcept of extCapex.values()) if (byConcept.size === 1) rows.push(...byConcept.values());

  // Classify by the facts: the longest revenue/profit period that ends at the report's last date.
  const flow = new Set([...IFRS_DURATION_CONCEPTS.revenue!, ...IFRS_DURATION_CONCEPTS.net_income!, "ProfitLoss"]);
  const flows = rows.filter((r) => r.s && flow.has(r.c));
  const reportEnd = flows.reduce<string | null>((m, r) => (m === null || r.e > m ? r.e : m), null);
  const span = flows.filter((r) => r.e === reportEnd).reduce((m, r) => Math.max(m, days(r.s!, r.e)), 0);
  const kind: ReportKind = span >= 350 && span <= 380 ? "annual" : span >= 170 && span <= 200 ? "half-year" : "unknown";
  return { fxo_id: fxoId, kind, report_end: reportEnd, rows, extension_facts: extension };
}

/** Repository metadata kept per filing for citations. */
export interface EsefFilingMeta {
  fxo_id: string;
  /** When the repository processed it (our "filed" date for restatement ordering). */
  processed: string;
  published: string | null;
  country: string;
  viewer_url: string | null;
  report_url: string | null;
  package_url: string | null;
}

/** Forms the standardizer understands: ESEF annual reports are annual, half-year reports are interim. */
export const ESEF_ANNUAL_FORM = "ESEF";
export const ESEF_INTERIM_FORM = "ESEF-HY";

/**
 * Fiscal-year label for a period ending on `end`. A year that ends in January or
 * February is named for the year it mostly covers (Inditex's fiscal 2025 ends on
 * 2026-01-31, Ahold Delhaize's fiscal 2022 on 2023-01-01), like US retailers.
 */
export function fiscalYear(end: string): number {
  const y = Number(end.slice(0, 4));
  return Number(end.slice(5, 7)) <= 2 ? y - 1 : y;
}

/** Merge extracted filings into the companyfacts shape, so standardize() can read them. */
export function toCompanyFacts(name: string, filings: Array<{ meta: EsefFilingMeta; data: ExtractedFiling }>): CompanyFacts {
  const ns: Namespace = {};
  for (const { meta, data } of filings) {
    if (data.kind === "unknown") continue;
    const form = data.kind === "annual" ? ESEF_ANNUAL_FORM : ESEF_INTERIM_FORM;
    for (const r of data.rows) {
      const units = (ns[r.c] ??= { units: {} }).units!;
      // "filed" orders restatements: use the issuer's publication date, falling back to processing.
      const filed = (meta.published ?? meta.processed).slice(0, 10);
      const row: RawFact = { val: r.v, end: r.e, accn: meta.fxo_id, filed, form, fy: fiscalYear(r.e) };
      if (r.s) row.start = r.s;
      if (r.x) row.src = r.x;
      (units[r.u] ??= []).push(row);
    }
  }
  return { cik: 0, entityName: name, facts: { "ifrs-full": ns } };
}
