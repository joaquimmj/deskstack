/** The one place the product name lives (CLAUDE.md: don't hardcode it elsewhere). */
export const PRODUCT_NAME = "deskstack";
export const VERSION = "0.5.0";
export const REPO_URL = "https://github.com/joaquimmj/deskstack";
export const SELF_HOST_URL = `${REPO_URL}/blob/main/docs/SELF_HOSTING.md`;

export const DISCLAIMER =
  "Independent open-source project. Not affiliated with or endorsed by Anthropic. " +
  "Data may be incomplete or delayed; verify against the cited filing before use. Not investment advice.";

/** Snapshot layout under the Worker's static assets (built by scripts/build-snapshot.ts). */
export const SNAPSHOT_SCHEMA = 1;
export const SNAPSHOT_PREFIX = "/v1";
/** Years kept per company in the snapshot; also the max a caller can ask for. */
export const SNAPSHOT_YEARS = 15;

/** Defaults for the cost guardrails; each can be overridden by a Worker var. */
export const DEFAULT_DAILY_CAP = 90_000; // Cloudflare Free hard-stops at 100k requests/day
export const DEFAULT_PER_IP_PER_MINUTE = 60;

export interface Env {
  /** Static assets binding (the snapshot). Absent in some tests and local runs. */
  ASSETS?: { fetch(input: Request | string): Promise<Response> };
  /** Optional D1 database for the global daily request counter. */
  USAGE?: D1Database;
  /** Optional Workers Rate Limiting binding (per IP). */
  IP_LIMITER?: { limit(opts: { key: string }): Promise<{ success: boolean }> };
  /** The shared per-IP counter (src/limiter.ts IpCounter). */
  IP_COUNTER?: { idFromName(name: string): unknown; get(id: unknown): { fetch(input: string): Promise<Response> } };
  /** Required for live SEC requests: "<name> <contact email>" per SEC fair-access policy. */
  SEC_USER_AGENT?: string;
  DAILY_CAP?: string;
  PER_IP_PER_MINUTE?: string;
  /** Comma-separated extra Origin hostnames allowed (besides Claude's and localhost). */
  ALLOWED_ORIGINS?: string;
}

/**
 * Listed registrants with no 10-K yet whose history sits under a predecessor CIK (holding-company
 * reorganizations). Checked against EDGAR: the predecessor's ticker moved to the new registrant.
 */
export const PREDECESSORS: Record<number, { cik: number; why: string }> = {
  // Exxon Mobil Corp delisted (Form 25, July 2026); XOM is now ExxonMobil Holdings Corp, first 10-Q 2026-11-02.
  2115436: { cik: 34088, why: "ExxonMobil Holdings Corp became the listed parent of Exxon Mobil Corp in July 2026" },
};

/**
 * Filers whose tagged OperatingIncomeLoss is not a GAAP operating income; theirs is revenue - CostsAndExpenses.
 * Checked against the 10-K (Disney FY2023: tagged 12,863 = total segment operating income; pretax income 4,769).
 */
export const OPERATING_INCOME_FROM_COSTS: Record<number, string> = {
  1744489: "Disney tags its total segment operating income as OperatingIncomeLoss and reports no GAAP operating income line",
};

/** EU issuers that also file a 20-F with the SEC on another accounting basis, so two sets of right figures exist. */
export const DUAL_FILERS: Record<string, { cik: number; ticker: string; standard: string }> = {
  // ASML: IFRS annual report (ESEF) and a US GAAP 20-F (2024 operating income: IFRS 9,937; US GAAP 9,023).
  "724500Y6DUVHQD6OXN27": { cik: 937966, ticker: "ASML", standard: "US GAAP" },
};

/** US filers that tag their capital expenditures only as PaymentsToAcquireOtherProductiveAssets (checked in the 10-K). */
export const CAPEX_FROM_OTHER_PRODUCTIVE_ASSETS: Record<number, string> = {
  732712: "Verizon tags its capital expenditures (including capitalized software) as other productive assets",
};

/** US filers whose D&A tag covers property and equipment only, with intangible amortization tagged on its own (checked in the 10-K). */
export const DA_EXCLUDES_INTANGIBLES: Record<number, string> = {
  858877: "Cisco tags D&A for property and equipment only; amortization of intangible assets is added",
};
