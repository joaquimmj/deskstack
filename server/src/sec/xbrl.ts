// Portions adapted from open-finance-mcp (c) 2026 Nathanael Johnson, MIT License.
// https://github.com/nathanaelhub/open-finance-mcp @ 8bcf3af0 (src/open_finance_mcp/xbrl.py).
// See THIRD_PARTY_NOTICES.md.
//
// Standardize SEC XBRL "company facts" into citable annual + LTM financials.
//
// Everything here is pure: it takes the parsed JSON from
// data.sec.gov/api/xbrl/companyfacts/CIK##########.json and returns plain
// objects, so it runs the same in the Worker, in the snapshot build, and in tests.
//
// Two facts about the data drive the design:
// - Companies tag the same line item differently and change tags over time
//   (Caterpillar's NetIncomeLoss stops in 2010 and continues as
//   NetIncomeLossAvailableToCommonStockholdersBasic). Each metric has a priority
//   list of concepts, resolved per period: the first concept with a value for
//   that period wins, and the concept actually used is reported.
// - A 10-K carries prior years as comparatives and later filings can restate
//   them. For each period we take the value from the most recently filed
//   report, and cite that filing.
//
// Foreign private issuers that report under IFRS (20-F/40-F) are read from
// ifrs-full with their own concept map, in their reporting currency. A filer
// with both taxonomies (Sony) is read from whichever has the latest fiscal year.

import { CAPEX_FROM_OTHER_PRODUCTIVE_ASSETS, OPERATING_INCOME_FROM_COSTS } from "../config";

export const DURATION_CONCEPTS: Record<string, string[]> = {
  revenue: [
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "RevenuesNetOfInterestExpense",
  ],
  gross_profit: ["GrossProfit"],
  operating_income: ["OperatingIncomeLoss"],
  pretax_income: [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
  ],
  net_income: ["NetIncomeLoss", "NetIncomeLossAvailableToCommonStockholdersBasic", "ProfitLoss"],
  interest_expense: ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
  d_and_a: [
    "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
    "DepreciationAndAmortization",
    "DepreciationAmortizationAndOther",
    "Depreciation",
  ],
  // Added to d_and_a when that is depreciation alone (filers that tag the two separately: KDP, Merck, Microsoft).
  amortization_intangibles: ["AmortizationOfIntangibleAssets"],
  // Operating income for filers in OPERATING_INCOME_FROM_COSTS (revenue - costs and expenses).
  costs_and_expenses: ["CostsAndExpenses"],
  operating_cash_flow: ["NetCashProvidedByUsedInOperatingActivities"],
  capex: ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
  // Capex only for filers in CAPEX_FROM_OTHER_PRODUCTIVE_ASSETS (Verizon); elsewhere it is a minor line.
  capex_other_productive: ["PaymentsToAcquireOtherProductiveAssets"],
  diluted_shares: ["WeightedAverageNumberOfDilutedSharesOutstanding"],
  diluted_eps: ["EarningsPerShareDiluted"],
};

export const INSTANT_CONCEPTS: Record<string, string[]> = {
  cash: ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents"],
  short_term_investments: [
    "MarketableSecuritiesCurrent",
    "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    "ShortTermInvestments",
    // Coca-Cola and others tag their short-term investments with this one (KO since FY2021).
    "OtherShortTermInvestments",
  ],
  total_assets: ["Assets"],
  total_equity: ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
  // Debt components; combined by totalDebt below.
  ltd_noncurrent: [
    "LongTermDebtNoncurrent",
    "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
  ],
  ltd_total: ["LongTermDebt", "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities"],
  debt_current: ["DebtCurrent"],
  ltd_current: ["LongTermDebtCurrent", "LongTermDebtAndCapitalLeaseObligationsCurrent"],
  commercial_paper: ["CommercialPaper"],
  short_term_borrowings: ["ShortTermBorrowings"],
  // Maturity-schedule figure; stands in for the current portion only when no current-debt line is tagged
  // (Caterpillar tags its balance-sheet line with a company extension, which companyfacts leaves out).
  ltd_due_12m: ["LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths"],
};

/** Synthetic key under which esef/extract.ts keeps an issuer's own capex concept (the cell shows the real one). */
export const EXT_CAPEX_KEY = "PurchaseOfPropertyPlantAndEquipmentAndIntangibleAssetsExtension";

export const IFRS_DURATION_CONCEPTS: Record<string, string[]> = {
  revenue: ["Revenue", "RevenueFromContractsWithCustomers", "RevenueFromSaleOfGoods"],
  gross_profit: ["GrossProfit"],
  operating_income: ["ProfitLossFromOperatingActivities"],
  pretax_income: ["ProfitLossBeforeTax"],
  net_income: ["ProfitLossAttributableToOwnersOfParent", "ProfitLoss"],
  // EPS's own numerator (after coupons on hybrid / AT1 instruments): used to derive an untagged share count.
  net_income_ordinary: ["ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntity"],
  interest_expense: ["InterestExpense", "FinanceCosts"],
  // Impairment-inclusive D&A concepts come last, for filers that tag nothing else (TotalEnergies, AB InBev, Ahold,
  // Iberdrola); adjustRow notes it on the cell, since EBITDA then includes impairment.
  d_and_a: [
    "DepreciationAndAmortisationExpense",
    "AdjustmentsForDepreciationAndAmortisationExpense",
    "AdjustmentsForDepreciationAndAmortisationExpenseAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
    "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
  ],
  operating_cash_flow: ["CashFlowsFromUsedInOperatingActivities"],
  capex: [
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    "PurchaseOfPropertyPlantAndEquipment",
    // Broader (includes intangibles); the concept name is reported with the value.
    "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
    // Last: an issuer's own concept for purchases of PP&E and intangibles (TotalEnergies, Airbus, VINCI, AB InBev,
    // Stellantis), kept by esef/extract.ts under this key; the cell shows the real concept and a note.
    EXT_CAPEX_KEY,
  ],
  diluted_shares: ["AdjustedWeightedAverageShares"],
  // Basic EPS last: some filers (Inditex) tag no diluted figure; adjustRow notes it on the cell.
  // Last: EPS from continuing operations, for filers that tag no total EPS (Iberdrola); adjustRow notes it.
  diluted_eps: [
    "DilutedEarningsLossPerShare", "BasicAndDilutedEarningsLossPerShare", "BasicEarningsLossPerShare",
    "DilutedEarningsLossPerShareFromContinuingOperations", "BasicEarningsLossPerShareFromContinuingOperations",
  ],
};

export const IFRS_INSTANT_CONCEPTS: Record<string, string[]> = {
  cash: ["CashAndCashEquivalents"],
  // IFRS has no general short-term investments line. Short-term deposits are the clear case (Inditex: EUR 5.7B).
  // OtherCurrentFinancialAssets is left out on purpose: it mixes derivatives and receivables.
  short_term_investments: ["ShorttermDepositsNotClassifiedAsCashEquivalents"],
  total_assets: ["Assets"],
  total_equity: ["EquityAttributableToOwnersOfParent", "Equity"],
  // IFRS Borrowings is current + non-current; the pieces are the fallback.
  borrowings: ["Borrowings"],
  borrowings_noncurrent: ["LongtermBorrowings", "NoncurrentPortionOfNoncurrentLoansReceived"],
  borrowings_current: [
    "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings",
    "CurrentLoansReceivedAndCurrentPortionOfNoncurrentLoansReceived",
  ],
  // The two components of current borrowings, used only when the total above is not tagged.
  short_term_borrowings: ["ShorttermBorrowings"],
  current_portion_of_longterm_borrowings: ["CurrentPortionOfLongtermBorrowings"],
};

// "ESEF" / "ESEF-HY": European annual and half-year reports (src/esef/extract.ts).
export const ANNUAL_FORMS = new Set(["10-K", "10-K/A", "10-KT", "20-F", "20-F/A", "40-F", "40-F/A", "ESEF"]);
export const QUARTERLY_FORMS = new Set(["10-Q", "10-Q/A", "ESEF-HY"]); // 6-K interims carry no XBRL financials

/** The filer has no usable annual facts in either taxonomy (new registrant, fund...). */
export class NoAnnualFacts extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NoAnnualFacts";
  }
}

// ---- types -----------------------------------------------------------------

/** One row of companyfacts `units.<unit>[]`. */
export interface RawFact {
  val: number;
  start?: string;
  end: string;
  accn: string;
  filed?: string;
  form?: string;
  fy?: number | null;
  fp?: string | null;
  frame?: string;
  /** ESEF only: the issuer's own (extension) concept behind a synthetic standard key. */
  src?: string;
}

/** `facts.<taxonomy>`: concept -> { units: { unit: rows } }. */
export type Namespace = Record<string, { label?: string; units?: Record<string, RawFact[]> }>;

export interface CompanyFacts {
  cik: number | string;
  entityName?: string;
  facts: Record<string, Namespace>;
}

export interface Fact {
  concept: string;
  value: number;
  start: string | null;
  end: string;
  form: string;
  accession: string;
  filed: string;
  fy: number | null;
  src?: string;
}

export interface Cell {
  value: number;
  concept: string;
  accession?: string;
  accessions?: string[];
  formula?: string;
  note?: string;
}

export interface Derived {
  value: number;
  formula: string;
}

export interface Column {
  label: string;
  start: string | null;
  end: string;
  type: "annual" | "ltm";
  ytd?: { start: string; end: string; days: number };
  values: Record<string, Cell | null>;
  balance_sheet: Record<string, Cell | null>;
  derived: Record<string, Derived | null>;
}

export interface FilingRef {
  url: string;
  form: string | null;
  filed: string | null;
}

export interface Standardized {
  cik: number;
  entity_name: string | null;
  taxonomy: string;
  currency: string;
  notes: string[];
  periods: Column[];
  filings: Record<string, FilingRef>;
}

interface Taxonomy {
  prefix: "us-gaap" | "ifrs-full";
  duration: Record<string, string[]>;
  instant: Record<string, string[]>;
}

const US_GAAP: Taxonomy = { prefix: "us-gaap", duration: DURATION_CONCEPTS, instant: INSTANT_CONCEPTS };
const IFRS: Taxonomy = { prefix: "ifrs-full", duration: IFRS_DURATION_CONCEPTS, instant: IFRS_INSTANT_CONCEPTS };

interface Ctx {
  tx: Taxonomy;
  facts: Namespace;
  currency: string;
  cik?: number;
}

// ---- helpers ---------------------------------------------------------------

const DAY_MS = 86_400_000;

/** Whole days between two ISO dates (b - a). */
export function daysBetween(a: string, b: string): number {
  return Math.round((Date.parse(`${b}T00:00:00Z`) - Date.parse(`${a}T00:00:00Z`)) / DAY_MS);
}

function factDays(f: Fact): number | null {
  return f.start === null ? null : daysBetween(f.start, f.end) + 1;
}

export function filingUrl(cik: number, accession: string): string {
  return `https://www.sec.gov/Archives/edgar/data/${Math.trunc(cik)}/${accession.replaceAll("-", "")}/${accession}-index.htm`;
}

function unitFor(ctx: Ctx, metric: string): string {
  if (metric === "diluted_shares") return "shares";
  if (metric === "diluted_eps") return `${ctx.currency}/shares`;
  return ctx.currency;
}

function getFacts(ns: Namespace, concept: string, unit: string): Fact[] {
  const rows = ns[concept]?.units?.[unit] ?? [];
  const out: Fact[] = [];
  for (const r of rows) {
    if (r.val === undefined || r.val === null || !r.accn || !r.end) continue;
    out.push({
      concept,
      value: Number(r.val),
      start: r.start ?? null,
      end: r.end,
      form: r.form ?? "",
      accession: r.accn,
      filed: r.filed ?? "",
      fy: r.fy ?? null,
      ...(r.src ? { src: r.src } : {}),
    });
  }
  return out;
}

/** Python tuple comparison on (filed, accession). */
function cmpFiledAccn(a: Fact, b: Fact): number {
  if (a.filed !== b.filed) return a.filed < b.filed ? -1 : 1;
  if (a.accession !== b.accession) return a.accession < b.accession ? -1 : 1;
  return 0;
}

/** Latest filing wins; ties on the filing date go to the later accession. Mirrors Python max(). */
function latestFiled(facts: Fact[]): Fact {
  let best = facts[0]!;
  for (const f of facts.slice(1)) if (cmpFiledAccn(f, best) > 0) best = f;
  return best;
}

/** Earliest filing; mirrors Python min() (first minimal element wins ties). */
function earliestFiled(facts: Fact[]): Fact {
  let best = facts[0]!;
  for (const f of facts.slice(1)) if (cmpFiledAccn(f, best) < 0) best = f;
  return best;
}

function isAnnual(f: Fact): boolean {
  const d = factDays(f);
  return ANNUAL_FORMS.has(f.form) && d !== null && d >= 350 && d <= 380;
}

// ---- periods -----------------------------------------------------------------

interface Period {
  label: string;
  start: string;
  end: string;
}

/**
 * Fiscal-year periods, oldest first, keyed off the revenue/net-income facts.
 *
 * The fiscal-year label comes from the original 10-K for that period (the
 * earliest filing that reports it), because comparatives in later 10-Ks carry
 * the later filing's fy. Label-by-end-year would be wrong for retailers: Home
 * Depot's fiscal 2025 ends on 1 Feb 2026.
 */
function annualPeriods(ctx: Ctx): Period[] {
  const periods = new Map<string, Fact[]>(); // insertion-ordered like a Python dict
  for (const metric of ["revenue", "net_income"]) {
    for (const concept of ctx.tx.duration[metric]!) {
      for (const f of getFacts(ctx.facts, concept, ctx.currency)) {
        if (!isAnnual(f)) continue;
        const key = `${f.start}|${f.end}`;
        const list = periods.get(key);
        if (list) list.push(f);
        else periods.set(key, [f]);
      }
    }
  }
  if (periods.size === 0) throw new NoAnnualFacts("no annual revenue or net-income facts");

  const out: Period[] = [];
  const trusted: Array<{ fy: number; end: string }> = [];
  const pending: Array<{ start: string; end: string }> = [];
  for (const [key, facts] of periods) {
    const [start, end] = key.split("|") as [string, string];
    const first = earliestFiled(facts);
    // Only trust fy when the first filing is the period's own 10-K (filed within ~6 months).
    const gap = first.filed ? daysBetween(end, first.filed) : -1;
    if (first.fy && gap >= 0 && gap <= 190) {
      trusted.push({ fy: first.fy, end });
      out.push({ label: `FY${first.fy}`, start, end });
    } else pending.push({ start, end });
  }
  // A period only seen as a comparative (e.g. the oldest year in the first report) has no fy of its own. Count back
  // from the nearest period whose fy is known: for a retailer whose FY2024 ends 31 Jan 2025, the year before is FY2023
  // even though it ends in 2024. With no known fy at all, fall back to the end year.
  for (const { start, end } of pending) {
    let fy = Number(end.slice(0, 4));
    if (trusted.length) {
      const near = trusted.reduce((a, b) => (Math.abs(daysBetween(end, a.end)) <= Math.abs(daysBetween(end, b.end)) ? a : b));
      fy = near.fy - Math.round(daysBetween(end, near.end) / 365.25);
    }
    out.push({ label: `FY${fy}`, start, end });
  }
  // Stable sort by end date, like Python's list.sort.
  out.sort((a, b) => (a.end < b.end ? -1 : a.end > b.end ? 1 : 0));
  // Overlapping periods (a restated year re-cut with new dates) keep the later one.
  const dedup: Period[] = [];
  for (const p of out) {
    const last = dedup[dedup.length - 1];
    if (last && p.start <= last.end) dedup[dedup.length - 1] = p;
    else dedup.push(p);
  }
  return dedup;
}

function pick(ctx: Ctx, metric: string, concepts: string[], match: (f: Fact) => boolean): Fact | null {
  for (const concept of concepts) {
    const hits = getFacts(ctx.facts, concept, unitFor(ctx, metric)).filter(match);
    if (hits.length) return latestFiled(hits);
  }
  return null;
}

function cell(ctx: Ctx, f: Fact | null): Cell | null {
  if (!f) return null;
  const c: Cell = { value: f.value, concept: `${ctx.tx.prefix}:${f.concept}`, accession: f.accession };
  if (f.src) {
    c.concept = f.src;
    c.note = `the issuer's own concept ${f.src}, used because no standard IFRS concept for this line is tagged`;
  }
  return c;
}

function durationValue(ctx: Ctx, metric: string, start: string, end: string, forms: Set<string>): Fact | null {
  return pick(ctx, metric, ctx.tx.duration[metric]!, (f) => f.start === start && f.end === end && forms.has(f.form));
}

function instantValue(ctx: Ctx, metric: string, end: string, forms: Set<string>): Fact | null {
  return pick(ctx, metric, ctx.tx.instant[metric]!, (f) => f.start === null && f.end === end && forms.has(f.form));
}

function sumCells(cells: Array<{ value: number } | null | undefined>): number | null {
  const vals = cells.filter((c): c is { value: number } => !!c).map((c) => c.value);
  return vals.length ? vals.reduce((a, b) => a + b, 0) : null;
}

type Inst = Record<string, { value: number } | null | undefined>;

/**
 * Combine debt components without double counting. Returns [value, formula].
 *
 * DebtCurrent already includes the current portion of long-term debt,
 * commercial paper and short-term borrowings, so those are only summed when it
 * is absent. LongTermDebt includes its current portion, so it is only used
 * (minus that portion) when no noncurrent concept exists. Operating-lease
 * liabilities are excluded by design.
 */
export function totalDebt(inst: Inst): [number | null, string] {
  let lt: number | null = null;
  let ltDesc: string | null = null;
  if (inst.ltd_noncurrent) {
    lt = inst.ltd_noncurrent.value;
    ltDesc = "ltd_noncurrent";
  } else if (inst.ltd_total) {
    lt = inst.ltd_total.value;
    ltDesc = "ltd_total";
    if (inst.ltd_current) {
      lt -= inst.ltd_current.value;
      ltDesc = "(ltd_total - ltd_current)";
    }
  }

  let cur: number | null = null;
  let curDesc: string | null = null;
  if (inst.debt_current) {
    cur = inst.debt_current.value;
    curDesc = "debt_current";
  } else {
    // Without a tagged current portion, the next-12-months maturity stands in for it, but only next to a
    // non-current line (LongTermDebt totals already include it).
    const ltdCur = inst.ltd_current ? "ltd_current" : ltDesc === "ltd_noncurrent" && inst.ltd_due_12m ? "ltd_due_12m" : null;
    const parts = [ltdCur, "commercial_paper", "short_term_borrowings"].filter((k): k is string => !!k && !!inst[k]);
    cur = parts.length ? sumCells(parts.map((k) => inst[k])) : null;
    curDesc = parts.length ? parts.join(" + ") : null;
  }

  if (lt === null && cur === null) return [null, "no debt concepts reported"];
  let formula = [ltDesc, curDesc].filter(Boolean).join(" + ");
  if (lt === null) formula += " (no long-term debt concept reported: likely incomplete)";
  return [(lt ?? 0) + (cur ?? 0), formula];
}

/**
 * IFRS Borrowings (current + non-current), else its parts. Current borrowings come
 * from their total concept, else from its two components (short-term borrowings +
 * current portion of long-term borrowings), never both. Leases excluded.
 */
export function ifrsTotalDebt(inst: Inst): [number | null, string] {
  if (inst.borrowings) return [inst.borrowings.value, "borrowings"];
  let cur: number | null = null;
  let curDesc: string | null = null;
  if (inst.borrowings_current) {
    cur = inst.borrowings_current.value;
    curDesc = "borrowings_current";
  } else {
    const parts = ["short_term_borrowings", "current_portion_of_longterm_borrowings"].filter((k) => inst[k]);
    if (parts.length) {
      cur = sumCells(parts.map((k) => inst[k]));
      curDesc = parts.length > 1 ? `(${parts.join(" + ")})` : parts[0]!;
    }
  }
  const lt = inst.borrowings_noncurrent?.value ?? null;
  if (lt === null && cur === null) return [null, "no debt concepts reported"];
  let formula = [lt !== null ? "borrowings_noncurrent" : null, curDesc].filter(Boolean).join(" + ");
  if (lt === null) formula += " (no non-current borrowings concept reported: likely incomplete)";
  return [(lt ?? 0) + (cur ?? 0), formula];
}

const accs = (...cells: Cell[]) => [...new Set(cells.flatMap((c) => c.accessions ?? (c.accession ? [c.accession] : [])))].sort();

/**
 * Fixes for how some filers tag a line, each stated on the cell (formula, note) so a reader sees it:
 * - D&A tagged as depreciation alone, with intangible amortization on its own line: the two are added;
 * - operating income for filers in OPERATING_INCOME_FROM_COSTS: revenue - costs and expenses;
 * - D&A tagged only together with impairment (IFRS): noted, and EBITDA's formula says so (derive);
 * - basic EPS standing in for an untagged diluted EPS (IFRS): noted; likewise EPS from continuing operations;
 * - no share count tagged (IFRS, annual columns): net income to ordinary holders (else to owners) / EPS, as a
 *   computed cell with its precision and, for the owners' figure, the hybrid-coupon caveat; only for a profit and an
 *   EPS of at least 0.50 (EPS is rounded to cents);
 * - capex for filers in CAPEX_FROM_OTHER_PRODUCTIVE_ASSETS (Verizon): their "other productive assets" line, noted;
 * - a diluted share count off by a thousand or a million (McDonald's FY2025: 716.4), rescaled only when
 *   net income / diluted EPS confirms the corrected figure within 3%.
 */
const withNote = (c: Cell, note: string): Cell => ({ ...c, note: c.note ? `${c.note}; ${note}` : note });

function adjustRow(row: Record<string, Cell | null>, ctx: Ctx, ltm = false): void {
  const dep = row.d_and_a;
  const am = row.amortization_intangibles;
  if (dep && am && dep.concept === "us-gaap:Depreciation") {
    row.d_and_a = {
      value: dep.value + am.value,
      concept: "us-gaap:Depreciation + us-gaap:AmortizationOfIntangibleAssets",
      accessions: accs(dep, am),
      formula: "depreciation + amortization of intangible assets (tagged separately)",
    };
  }
  const why = ctx.cik !== undefined ? OPERATING_INCOME_FROM_COSTS[ctx.cik] : undefined;
  const rev = row.revenue;
  const ce = row.costs_and_expenses;
  if (why && rev && ce) {
    row.operating_income = {
      value: rev.value - ce.value,
      concept: `${rev.concept} - us-gaap:CostsAndExpenses`,
      accessions: accs(rev, ce),
      formula: "revenue - costs_and_expenses",
      note: why,
    };
  }
  if (IMPAIRMENT_DA.test(row.d_and_a?.concept ?? "")) {
    row.d_and_a = withNote(row.d_and_a!, "includes impairment: the filer tags no D&A line without it, so EBITDA includes impairment too");
  }
  const basicEps = /^ifrs-full:BasicEarningsLossPerShare(FromContinuingOperations)?$/.test(row.diluted_eps?.concept ?? "");
  if (basicEps) row.diluted_eps = withNote(row.diluted_eps!, "basic EPS: the filer tags no diluted EPS");
  const continuing = /FromContinuingOperations$/.test(row.diluted_eps?.concept ?? "");
  if (continuing) row.diluted_eps = withNote(row.diluted_eps!, "EPS from continuing operations: the filer tags no total EPS");
  const ordinary = row.net_income_ordinary;
  const owners = row.net_income?.concept === "ifrs-full:ProfitLossAttributableToOwnersOfParent" ? row.net_income : null;
  const num = ordinary ?? owners;
  const eps = row.diluted_eps;
  // Not from continuing-operations EPS: net income also includes discontinued operations.
  if (!ltm && !continuing && !row.diluted_shares && num && eps && num.value > 0 && eps.value >= 0.5) {
    const band = `±${((0.005 / eps.value) * 100).toFixed(1)}%`;
    const den = basicEps ? "basic EPS (no diluted EPS or share count tagged)" : "diluted_eps (no share count tagged)";
    row.diluted_shares = {
      value: Math.round(num.value / eps.value),
      concept: "", // computed: verify_value shows the formula
      accessions: accs(num, eps),
      formula: `${ordinary ? "net income to ordinary holders" : "net_income"} / ${den}`,
      note: ordinary
        ? `approximate (${band}): EPS is rounded to cents`
        : `approximate (${band}): EPS is rounded to cents; if the issuer pays coupons on hybrid or AT1 instruments, ` +
          "the count is overstated (EPS excludes them, net income to owners includes them)",
    };
  }
  const otherCapex = ctx.cik !== undefined ? CAPEX_FROM_OTHER_PRODUCTIVE_ASSETS[ctx.cik] : undefined;
  if (!row.capex && otherCapex && row.capex_other_productive) {
    row.capex = withNote(row.capex_other_productive, otherCapex);
  }
  // Inputs to the adjustments above, not metrics of their own.
  delete row.capex_other_productive;
  delete row.net_income_ordinary;
  const sh = row.diluted_shares;
  const ni = row.net_income;
  if (sh && ni && eps && eps.value !== 0) {
    const implied = ni.value / eps.value;
    if (implied > 0 && Math.abs(sh.value / implied - 1) > 0.5) {
      for (const k of [1e3, 1e6]) {
        if (Math.abs((sh.value * k) / implied - 1) < 0.03) {
          row.diluted_shares = withNote(
            { ...sh, value: sh.value * k },
            `filed as ${sh.value}, a scale error in the filer's XBRL: net income / diluted EPS gives ${Math.round(implied).toLocaleString("en-US")}, so multiplied by ${k.toLocaleString("en-US")}`,
          );
          break;
        }
      }
    }
  }
}

const IMPAIRMENT_DA = /ImpairmentLossReversalOfImpairmentLoss/;

function derive(row: Record<string, Cell | null>, inst: Record<string, Cell | null>, tx: Taxonomy): Record<string, Derived | null> {
  const v = (src: Record<string, Cell | null>, k: string): number | null => src[k]?.value ?? null;
  const out: Record<string, Derived | null> = {};
  const oi = v(row, "operating_income");
  const da = v(row, "d_and_a");
  const daFormula = IMPAIRMENT_DA.test(row.d_and_a?.concept ?? "") ? "d_and_a (includes impairment)" : "d_and_a";
  out.ebitda = oi !== null && da !== null ? { value: oi + da, formula: `operating_income + ${daFormula}` } : null;
  const cfo = v(row, "operating_cash_flow");
  const capex = v(row, "capex");
  out.free_cash_flow =
    cfo !== null && capex !== null ? { value: cfo - capex, formula: "operating_cash_flow - capex" } : null;
  const [debt, formula] = (tx === IFRS ? ifrsTotalDebt : totalDebt)(inst);
  out.total_debt = debt === null ? null : { value: debt, formula };
  const cash = v(inst, "cash");
  if (debt !== null && cash !== null) {
    const sti = v(inst, "short_term_investments") ?? 0;
    out.net_debt = { value: debt - cash - sti, formula: "total_debt - cash - short_term_investments" };
  } else {
    out.net_debt = null;
  }
  return out;
}

// ---- LTM ---------------------------------------------------------------------

/**
 * (start, end) of the newest 10-Q year-to-date period after fyEnd. A YTD
 * period starts right after the fiscal year ends (within a week, for 52/53-week
 * calendars), so 3-month quarterly facts are excluded.
 */
function latestQuarterYtd(ctx: Ctx, fyEnd: string): [string, string] | null {
  let best: [string, string] | null = null;
  for (const concept of [...ctx.tx.duration.revenue!, ...ctx.tx.duration.net_income!]) {
    for (const f of getFacts(ctx.facts, concept, ctx.currency)) {
      if (!QUARTERLY_FORMS.has(f.form) || !f.start) continue;
      const gap = daysBetween(fyEnd, f.start);
      if (gap > 0 && gap <= 7 && (best === null || f.end > best[1])) best = [f.start, f.end];
    }
  }
  return best;
}

/** [FY, current YTD, prior-year YTD] facts for one concept, or null. */
function ltmParts(ctx: Ctx, metric: string, concept: string, lastFy: Period, ytd: [string, string]): [Fact, Fact, Fact] | null {
  const facts = getFacts(ctx.facts, concept, unitFor(ctx, metric));
  const length = daysBetween(ytd[0], ytd[1]);
  const one = (pred: (f: Fact) => boolean): Fact | null => {
    const hits = facts.filter(pred);
    return hits.length ? latestFiled(hits) : null;
  };
  const fy = one((f) => ANNUAL_FORMS.has(f.form) && f.start === lastFy.start && f.end === lastFy.end);
  const cur = one((f) => QUARTERLY_FORMS.has(f.form) && f.start === ytd[0] && f.end === ytd[1]);
  const prev = one(
    (f) =>
      QUARTERLY_FORMS.has(f.form) &&
      f.start === lastFy.start &&
      f.start !== null &&
      Math.abs(daysBetween(f.start, f.end) - length) <= 7,
  );
  return fy && cur && prev ? [fy, cur, prev] : null;
}

function ltmColumn(ctx: Ctx, lastFy: Period): Column | null {
  const ytd = latestQuarterYtd(ctx, lastFy.end);
  if (!ytd) return null;

  const row: Record<string, Cell | null> = {};
  for (const m of Object.keys(ctx.tx.duration)) {
    if (m === "diluted_shares") {
      // A weighted-average share count is not additive: report the latest YTD figure as-is.
      const f = durationValue(ctx, m, ytd[0], ytd[1], QUARTERLY_FORMS);
      const c = cell(ctx, f);
      row[m] = c ? { ...c, note: "weighted average for the year-to-date period, not trailing twelve months" } : null;
      continue;
    }
    row[m] = null;
    // FY + YTD - prior YTD is only valid when one concept covers all three.
    for (const concept of ctx.tx.duration[m]!) {
      const parts = ltmParts(ctx, m, concept, lastFy, ytd);
      if (!parts) continue;
      const [fy, cur, prev] = parts;
      // An issuer's own concept must be the same one in all three parts (review: mixed concepts gave nonsense).
      if (fy.src !== cur.src || fy.src !== prev.src) continue;
      row[m] = {
        value: fy.value + cur.value - prev.value,
        concept: fy.src ?? `${ctx.tx.prefix}:${concept}`,
        ...(fy.src ? { note: `the issuer's own concept ${fy.src}, used because no standard IFRS concept for this line is tagged` } : {}),
        formula: "FY + YTD - prior YTD",
        accessions: [...new Set([fy.accession, cur.accession, prev.accession])].sort(),
        // Change vs open-finance-mcp: it reported diluted EPS as the YTD figure
        // (e.g. 9 months) under an LTM label. Trailing EPS is the sum of the last
        // four quarters, i.e. FY + YTD - prior YTD, which is what we compute.
        ...(m === "diluted_eps"
          ? { note: "sum of the last four quarters' EPS; per-share amounts are approximately additive" }
          : {}),
      };
      break;
    }
  }
  const inst: Record<string, Cell | null> = {};
  for (const m of Object.keys(ctx.tx.instant)) inst[m] = cell(ctx, instantValue(ctx, m, ytd[1], QUARTERLY_FORMS));
  return {
    // Exact span, not "6M": 52/53-week filers (PepsiCo) have 12- and 16-week quarters.
    label: `LTM to ${ytd[1]}`,
    start: null,
    end: ytd[1],
    type: "ltm",
    ytd: { start: ytd[0], end: ytd[1], days: daysBetween(ytd[0], ytd[1]) + 1 },
    values: row,
    balance_sheet: (adjustRow(row, ctx, true), inst),
    derived: derive(row, inst, ctx.tx),
  };
}

// ---- taxonomy choice + entry point ---------------------------------------------

/** The currency most annual revenue/net-income facts are reported in. */
export function reportingCurrency(ns: Namespace): string | null {
  const counts = new Map<string, number>();
  for (const concept of [
    "Revenues",
    "Revenue",
    "NetIncomeLoss",
    "ProfitLoss",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
  ]) {
    for (const [unit, rows] of Object.entries(ns[concept]?.units ?? {})) {
      if (unit.includes("/") || unit === "shares") continue;
      const n = rows.filter((r) => r.form !== undefined && ANNUAL_FORMS.has(r.form)).length;
      counts.set(unit, (counts.get(unit) ?? 0) + n);
    }
  }
  let best: string | null = null;
  let bestN = 0;
  for (const [unit, n] of counts) {
    if (best === null || n > bestN) {
      best = unit;
      bestN = n;
    }
  }
  return best !== null && bestN > 0 ? best : null;
}

function choose(cf: CompanyFacts): [Ctx, Period[]] {
  let best: [Ctx, Period[]] | null = null;
  for (const tx of [US_GAAP, IFRS]) {
    const ns = cf.facts?.[tx.prefix];
    const currency = ns ? reportingCurrency(ns) : null;
    if (!ns || !currency) continue;
    const ctx: Ctx = { tx, facts: ns, currency };
    let periods: Period[];
    try {
      periods = annualPeriods(ctx);
    } catch (e) {
      if (e instanceof NoAnnualFacts) continue;
      throw e;
    }
    if (best === null || periods[periods.length - 1]!.end > best[1][best[1].length - 1]!.end) best = [ctx, periods];
  }
  if (!best) {
    throw new NoAnnualFacts(
      "no 10-K or 20-F history: possibly a newly formed registrant whose history sits under a predecessor CIK",
    );
  }
  return best;
}

/** Index of accession -> form/filed, from every fact in the chosen taxonomy (for citations). */
function filingIndex(ns: Namespace): Map<string, { form: string | null; filed: string | null }> {
  const idx = new Map<string, { form: string | null; filed: string | null }>();
  for (const concept of Object.values(ns)) {
    for (const rows of Object.values(concept.units ?? {})) {
      for (const r of rows) if (r.accn && !idx.has(r.accn)) idx.set(r.accn, { form: r.form ?? null, filed: r.filed ?? null });
    }
  }
  return idx;
}

export interface StandardizeOptions {
  /** Where the facts come from: SEC companyfacts (default) or ESEF reports. Changes notes and citation URLs. */
  source?: "sec" | "esef";
  /** Citation URL for an accession / filing id (default: the SEC EDGAR filing index). */
  filingUrl?: (accession: string) => string;
}

/** Standardized annual (+ optional LTM) financials with per-value citations. */
export function standardize(cf: CompanyFacts, years = 5, includeLtm = true, opts: StandardizeOptions = {}): Standardized {
  const cik = Math.trunc(Number(cf.cik));
  const urlFor = opts.filingUrl ?? ((a: string) => filingUrl(cik, a));
  const [ctx, allPeriods] = choose(cf);
  ctx.cik = cik;
  const periods = allPeriods.slice(-years);
  const columns: Column[] = [];

  for (const p of periods) {
    const row: Record<string, Cell | null> = {};
    for (const m of Object.keys(ctx.tx.duration)) row[m] = cell(ctx, durationValue(ctx, m, p.start, p.end, ANNUAL_FORMS));
    const inst: Record<string, Cell | null> = {};
    for (const m of Object.keys(ctx.tx.instant)) inst[m] = cell(ctx, instantValue(ctx, m, p.end, ANNUAL_FORMS));
    adjustRow(row, ctx);
    columns.push({ ...p, type: "annual", values: row, balance_sheet: inst, derived: derive(row, inst, ctx.tx) });
  }

  if (includeLtm && periods.length) {
    const ltm = ltmColumn(ctx, periods[periods.length - 1]!);
    if (ltm) columns.push(ltm);
  }

  const accessions = new Set<string>();
  for (const col of columns) {
    for (const group of [col.values, col.balance_sheet]) {
      for (const c of Object.values(group)) {
        if (!c) continue;
        for (const a of c.accessions ?? [c.accession!]) accessions.add(a);
      }
    }
  }

  const notes = [
    "Values are as most recently reported (restatements included); each cites its filing.",
    "Balance-sheet items are period-end instants. Share counts are weighted diluted; where none is tagged (some IFRS filers) the count is computed from net income and EPS, with its formula and precision.",
    "Derived metrics show their formula. EBITDA is null when operating income is not " +
      "reported (common for banks and insurers, where EBITDA is not meaningful).",
  ];
  if (opts.source === "esef") {
    notes.push(
      "ESEF report (IFRS as adopted in the EU), from the issuer's tagged consolidated statements. Lines the " +
        "issuer tagged only with its own (extension) concepts are not mapped and come back null, except capex " +
        "(an issuer's own concept for purchases of PP&E and intangibles, shown with its real name).",
    );
    if (!columns.some((c) => c.type === "ltm")) {
      notes.push("No LTM column: the issuer's half-year report is not available in ESEF format.");
    }
  } else if (ctx.tx === IFRS) {
    notes.push(
      "IFRS filer (20-F/40-F): figures follow IFRS, not US GAAP. Interim results are furnished " +
        "on 6-K without XBRL, so there is no LTM column.",
    );
  }
  const idx = filingIndex(ctx.facts);
  const filings: Record<string, FilingRef> = {};
  for (const a of [...accessions].sort()) {
    const meta = idx.get(a);
    filings[a] = { url: urlFor(a), form: meta?.form ?? null, filed: meta?.filed ?? null };
  }
  return {
    cik,
    entity_name: cf.entityName ?? null,
    taxonomy: ctx.tx.prefix,
    currency: ctx.currency,
    notes,
    periods: columns,
    filings,
  };
}

export interface SharesOutstanding {
  value: number;
  as_of: string;
  classes_summed: number | null;
  concept: string;
  accession: string;
  url: string;
  note?: string;
}

/**
 * Latest share count for market cap. Prefers the cover-page
 * dei:EntityCommonStockSharesOutstanding, summed across share classes when a
 * filing reports several. Companies that tag the cover page only per class
 * (Alphabet) have no undimensioned dei fact in the API, so fall back to the
 * balance-sheet us-gaap:CommonStockSharesOutstanding, already a total.
 */
export function sharesOutstanding(cf: CompanyFacts): SharesOutstanding | null {
  const facts = cf.facts ?? {};
  const cik = Math.trunc(Number(cf.cik));
  const periodic = new Set([...ANNUAL_FORMS, ...QUARTERLY_FORMS]);

  const dei = (facts.dei?.EntityCommonStockSharesOutstanding?.units?.shares ?? []).filter(
    (r) => r.form !== undefined && periodic.has(r.form),
  );
  if (dei.length) {
    let latest = dei[0]!;
    for (const r of dei.slice(1)) {
      const a = [r.filed ?? "", r.end];
      const b = [latest.filed ?? "", latest.end];
      if (a[0]! > b[0]! || (a[0] === b[0] && a[1]! > b[1]!)) latest = r;
    }
    const same = dei.filter((r) => r.accn === latest.accn && r.end === latest.end);
    return {
      value: same.reduce((s, r) => s + Number(r.val), 0),
      as_of: latest.end,
      classes_summed: same.length,
      concept: "dei:EntityCommonStockSharesOutstanding",
      accession: latest.accn,
      url: filingUrl(cik, latest.accn),
    };
  }

  const rows = (facts["us-gaap"]?.CommonStockSharesOutstanding?.units?.shares ?? []).filter(
    (r) => r.form !== undefined && periodic.has(r.form) && r.start === undefined,
  );
  if (!rows.length) return null;
  let latest = rows[0]!;
  for (const r of rows.slice(1)) {
    if (r.end > latest.end || (r.end === latest.end && (r.filed ?? "") > (latest.filed ?? ""))) latest = r;
  }
  return {
    value: Number(latest.val),
    as_of: latest.end,
    classes_summed: null,
    concept: "us-gaap:CommonStockSharesOutstanding",
    note: "Cover-page count not available undimensioned; balance-sheet total across all classes.",
    accession: latest.accn,
    url: filingUrl(cik, latest.accn),
  };
}
