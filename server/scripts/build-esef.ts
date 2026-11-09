// Build snapshot/v1/eu/ from ESEF reports on filings.xbrl.org (XBRL International).
//
// Usage: tsx scripts/build-esef.ts [--only LEI,LEI] [--out snapshot] [--cache .esef-cache]
// Issuers: data/eu-issuers.json. Each report's xBRL-JSON is up to ~25 MB, so the
// extracted facts are cached per filing id (filings never change) and only new
// filings are downloaded. Requests are paced: the API rate-limits bursts.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { PRODUCT_NAME, REPO_URL, SNAPSHOT_SCHEMA } from "../src/config";
import { extractFiling, type EsefFilingMeta, type ExtractedFiling } from "../src/esef/extract";
import { buildEuRecord, FILINGS_XBRL_ORG, type EuIssuer } from "../src/esef/record";

const arg = (n: string) => {
  const i = process.argv.indexOf(`--${n}`);
  return i >= 0 ? process.argv[i + 1] : undefined;
};
const OUT = resolve(arg("out") ?? "snapshot");
const CACHE = resolve(arg("cache") ?? ".esef-cache");
const ONLY = arg("only")?.split(",");
const UA = `${PRODUCT_NAME} snapshot build (+${REPO_URL})`;
const PACE_MS = 2_000;
const MAX_ANNUAL = 6;

let last = 0;
async function paced<T>(run: () => Promise<T>): Promise<T> {
  const wait = last + PACE_MS - Date.now();
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  last = Date.now();
  return run();
}

// A dropped connection mid-download can make Node's fetch (undici) throw an internal assertion outside the request's
// promise, which would end the whole build (deploy run 2026-11-09, after Michelin). Only that error is absorbed: the
// request it belonged to then times out below and is retried. Anything else still stops the build.
process.on("uncaughtException", (e: Error & { code?: string }) => {
  if (e.code === "ERR_ASSERTION" && /undici/.test(e.stack ?? "")) {
    console.warn("network: a connection dropped mid-download (undici assertion); that request is retried");
    return;
  }
  throw e;
});

const TIMEOUT_MS = 120_000;
const NETWORK_TRIES = 4;

/** GET with pacing, 429 back-off, a timeout, and retries on network errors. The body is read here, so a connection
 *  that drops mid-body is retried too; callers get a complete Response. */
async function get(url: string, accept = "application/vnd.api+json"): Promise<Response> {
  let failures = 0;
  for (let attempt = 0; attempt < 8 + NETWORK_TRIES; attempt++) {
    try {
      const res = await paced(() => fetch(url, { headers: { Accept: accept, "User-Agent": UA }, signal: AbortSignal.timeout(TIMEOUT_MS) }));
      if (res.status === 429) {
        await new Promise((r) => setTimeout(r, 30_000));
        continue;
      }
      const body = await res.arrayBuffer();
      return new Response(body, { status: res.status, statusText: res.statusText, headers: res.headers });
    } catch (e) {
      if (++failures >= NETWORK_TRIES) throw new Error(`${url}: ${(e as Error).message} after ${failures} tries`);
      await new Promise((r) => setTimeout(r, 5_000 * failures));
    }
  }
  throw new Error(`${url}: still rate-limited`);
}

interface ApiFiling {
  attributes: {
    fxo_id: string;
    period_end: string;
    country: string;
    processed: string;
    published?: string | null;
    json_url?: string | null;
    viewer_url?: string | null;
    report_url?: string | null;
    package_url?: string | null;
  };
}

async function filingsFor(issuer: EuIssuer): Promise<ApiFiling[]> {
  const res = await get(`${FILINGS_XBRL_ORG}/api/entities/${issuer.lei}/filings?page[size]=100`);
  if (!res.ok) throw new Error(`filings for ${issuer.lei}: HTTP ${res.status}`);
  const all = ((await res.json()) as { data: ApiFiling[] }).data.filter((f) => f.attributes.json_url);
  // The same report is often filed in several language/jurisdiction copies (e.g. FR and GB):
  // keep one per period, preferring the issuer's home jurisdiction.
  const byPeriod = new Map<string, ApiFiling>();
  for (const f of all.sort((a, b) => a.attributes.fxo_id.localeCompare(b.attributes.fxo_id))) {
    const cur = byPeriod.get(f.attributes.period_end);
    if (!cur || (f.attributes.country === issuer.country && cur.attributes.country !== issuer.country)) {
      byPeriod.set(f.attributes.period_end, f);
    }
  }
  return [...byPeriod.values()].sort((a, b) => (a.attributes.period_end < b.attributes.period_end ? 1 : -1)).slice(0, MAX_ANNUAL * 2);
}

async function extracted(f: ApiFiling): Promise<ExtractedFiling> {
  // v4: extraction keeps issuers' own concepts for capex, EBIT and D&A (EXTENSIONS in src/esef/extract.ts); bump on extraction changes.
  if (!/^[A-Za-z0-9._-]+$/.test(f.attributes.fxo_id) || f.attributes.fxo_id.includes("..")) {
    throw new Error(`unexpected filing id ${JSON.stringify(f.attributes.fxo_id).slice(0, 80)}`);
  }
  const path = join(CACHE, `${f.attributes.fxo_id}.v4.json`);
  if (existsSync(path)) return JSON.parse(readFileSync(path, "utf8")) as ExtractedFiling;
  if (!/^\/(?!\/)/.test(f.attributes.json_url ?? "")) throw new Error(`${f.attributes.fxo_id}: unexpected json_url`);
  const res = await get(`${FILINGS_XBRL_ORG}${f.attributes.json_url}`, "application/json");
  if (!res.ok) throw new Error(`${f.attributes.fxo_id}: HTTP ${res.status}`);
  const data = extractFiling((await res.json()) as never, f.attributes.fxo_id);
  writeFileSync(path, JSON.stringify(data));
  return data;
}

const issuers = (JSON.parse(readFileSync(resolve("data/eu-issuers.json"), "utf8")) as { issuers: EuIssuer[] }).issuers.filter(
  (i) => !ONLY || ONLY.includes(i.lei),
);
mkdirSync(CACHE, { recursive: true });
mkdirSync(join(OUT, "v1", "eu", "co"), { recursive: true });

const index: unknown[][] = [];
let ok = 0;
for (const issuer of issuers) {
  try {
    const list = await filingsFor(issuer);
    const done: Array<{ meta: EsefFilingMeta; data: ExtractedFiling }> = [];
    const kinds = new Set<string>();
    for (const f of list) {
      const data = await extracted(f);
      // Mislabeled repository metadata (a period_end in the future) is harmless: the facts' own dates are used.
      const key = `${data.kind}|${data.report_end}`;
      if (data.kind === "unknown" || kinds.has(key)) continue;
      kinds.add(key);
      const a = f.attributes;
      done.push({
        meta: {
          fxo_id: a.fxo_id,
          processed: a.processed,
          published: a.published ?? null,
          country: a.country,
          viewer_url: a.viewer_url ?? null,
          report_url: a.report_url ?? null,
          package_url: a.package_url ?? null,
        },
        data,
      });
      if (done.filter((d) => d.data.kind === "annual").length >= MAX_ANNUAL) break;
    }
    const rec = buildEuRecord(issuer, done);
    writeFileSync(join(OUT, "v1", "eu", "co", `${issuer.lei}.json`), JSON.stringify(rec));
    const last = rec.financials?.periods.filter((p) => p.type === "annual").at(-1);
    index.push([issuer.lei, issuer.name, issuer.country, rec.financials?.currency ?? null, last?.end.slice(5).replace("-", "") ?? null]);
    if (rec.financials) ok++;
    console.log(`${issuer.lei} ${issuer.name}: ${done.length} report(s), ${rec.financials ? `${rec.financials.periods.length} period(s) ${rec.financials.currency}` : rec.financials_error}`);
  } catch (e) {
    console.warn(`${issuer.lei} ${issuer.name}: FAILED ${(e as Error).message}`);
  }
}

writeFileSync(join(OUT, "v1", "eu", "companies.json"), JSON.stringify({ fields: ["lei", "name", "country", "currency", "fiscal_year_end"], data: index }));
writeFileSync(
  join(OUT, "v1", "eu", "manifest.json"),
  JSON.stringify({ schema: SNAPSHOT_SCHEMA, built_at: new Date().toISOString(), issuers: index.length, with_financials: ok, source: "filings.xbrl.org (XBRL International) ESEF reports" }),
);
console.log(`EU: ${ok}/${issuers.length} issuers with financials`);
// Fail the step (the workflow then keeps the last good copy) if most issuers broke.
if (!ONLY && ok < issuers.length * 0.8) process.exit(1);
