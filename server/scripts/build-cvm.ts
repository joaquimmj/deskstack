// Build snapshot/v1/br/ from CVM's open data (Brazil): annual DFP statements and B3 tickers from the FCA forms.
//
// Annual DFP statements plus this year's quarterly ITR statements (for LTM).
// Usage: tsx scripts/build-cvm.ts [--out snapshot] [--cache .cvm-cache] [--from <dir with the ZIPs>] [--only 009512,004170]
// Issuers: data/br-issuers.json. One ZIP a year (about 13 MB); a ZIP already in the cache is reused unless it is
// the current or previous year's, which CVM updates weekly with resubmissions.
//
// Licence: ODbL 1.0 (docs/DATA_SOURCES.md §13). The output is a Derivative Database, so it is published under the
// ODbL: every file says so, and dataset.json is the whole derived database, free to download.

import { createWriteStream, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import yauzl from "yauzl";
import { PRODUCT_NAME, REPO_URL, SNAPSHOT_SCHEMA, SNAPSHOT_YEARS } from "../src/config";
import { extractDfpYear, mergeTickers, tickersFromFca, type CvmYear } from "../src/cvm/extract";
import { brId, brIndexRow, buildBrRecord, CVM_NOTICE, CVM_PORTAL, ODBL_URL, type BrIssuer } from "../src/cvm/record";

const arg = (n: string) => {
  const i = process.argv.indexOf(`--${n}`);
  return i >= 0 ? process.argv[i + 1] : undefined;
};
const OUT = resolve(arg("out") ?? "snapshot");
const CACHE = resolve(arg("cache") ?? ".cvm-cache");
const FROM = arg("from") ? resolve(arg("from")!) : null;
const ONLY = arg("only")?.split(",");
const UA = `${PRODUCT_NAME} snapshot build (+${REPO_URL})`;
const BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC";
const THIS_YEAR = Number(arg("year") ?? new Date().getUTCFullYear());

const issuers: BrIssuer[] = (JSON.parse(readFileSync(join(import.meta.dirname, "..", "data", "br-issuers.json"), "utf8")) as { issuers: BrIssuer[] }).issuers
  .filter((i) => !ONLY || ONLY.includes(i.cd_cvm));
const want = new Set(issuers.map((i) => i.cd_cvm));

async function zipPath(kind: "DFP" | "ITR" | "FCA", year: number): Promise<string | null> {
  const name = `${kind.toLowerCase()}_cia_aberta_${year}.zip`;
  if (FROM) return existsSync(join(FROM, name)) ? join(FROM, name) : null;
  mkdirSync(CACHE, { recursive: true });
  const dest = join(CACHE, name);
  if (existsSync(dest) && year < THIS_YEAR - 1) return dest;
  const res = await fetch(`${BASE}/${kind}/DADOS/${name}`, { headers: { "User-Agent": UA } });
  if (res.status === 404) return null;
  if (!res.ok || !res.body) throw new Error(`${name}: HTTP ${res.status}`);
  await pipeline(Readable.fromWeb(res.body as never), createWriteStream(dest));
  return dest;
}

/** The ZIP's CSVs whose names pass `keep`, decoded from Latin-1. */
async function csvs(path: string, keep: (name: string) => boolean): Promise<Map<string, string>> {
  const out = new Map<string, string>();
  const z = await yauzl.openPromise(path, { lazyEntries: true });
  const latin1 = new TextDecoder("latin1");
  await new Promise<void>((done, fail) => {
    z.on("error", fail);
    z.on("end", () => done());
    z.on("entry", (entry: yauzl.Entry) => {
      if (!keep(entry.fileName)) return z.readEntry();
      z.openReadStream(entry, (err, stream) => {
        if (err || !stream) return fail(err);
        const chunks: Buffer[] = [];
        stream.on("data", (c: Buffer) => chunks.push(c));
        stream.on("error", fail);
        stream.on("end", () => {
          out.set(entry.fileName, latin1.decode(Buffer.concat(chunks)));
          z.readEntry();
        });
      });
    });
    z.readEntry();
  });
  return out;
}

// A year's DFP holds that year's statements and the restated year before: SNAPSHOT_YEARS + 1 ZIPs cover the window.
const years: CvmYear[] = [];
for (let y = THIS_YEAR - SNAPSHOT_YEARS; y <= THIS_YEAR; y++) {
  const p = await zipPath("DFP", y);
  if (!p) {
    console.log(`DFP ${y}: not published`);
    continue;
  }
  const files = await csvs(p, (n) => n === `dfp_cia_aberta_${y}.csv` || /_con_\d{4}\.csv$/.test(n) && /_(DRE|BPA|BPP|DFC_MI|DFC_MD)_con_/.test(n));
  const yr = extractDfpYear(files, want, y);
  years.push(yr);
  console.log(`DFP ${y}: ${yr.filings.length} filing(s), ${yr.facts.length} line(s)`);
}

// Quarterly statements (ITR), for the LTM column: this year's and last year's. Between January and the DFP's
// publication the latest fiscal year is two years back, and last year's third-quarter ITR is the one that follows it.
// (CVM files no ITR for the fourth quarter: after a DFP and before the next ITR, LTM is the fiscal year itself.)
for (const y of [THIS_YEAR - 1, THIS_YEAR]) {
  const p = await zipPath("ITR", y);
  if (!p) {
    console.log(`ITR ${y}: not published yet`);
    continue;
  }
  const files = await csvs(p, (n) => n === `itr_cia_aberta_${y}.csv` || /_(DRE|BPA|BPP|DFC_MI|DFC_MD)_con_\d{4}\.csv$/.test(n));
  const yr = extractDfpYear(files, want, y, "itr");
  years.push(yr);
  console.log(`ITR ${y}: ${yr.filings.length} filing(s), ${yr.facts.length} line(s)`);
}

// Tickers from the FCA forms of the last two years, merged: companies have until 31 May to file this year's.
let tickers = new Map<string, string[]>();
for (const y of [THIS_YEAR - 1, THIS_YEAR]) {
  const p = await zipPath("FCA", y);
  if (!p) continue;
  const f = await csvs(p, (n) => n === `fca_cia_aberta_valor_mobiliario_${y}.csv`);
  const text = f.get(`fca_cia_aberta_valor_mobiliario_${y}.csv`);
  if (!text) continue;
  const t = tickersFromFca(text);
  tickers = mergeTickers(t, tickers);
  console.log(`FCA ${y}: tickers for ${t.size} companies`);
}

mkdirSync(join(OUT, "v1", "br", "co"), { recursive: true });
const index: unknown[][] = [];
const dataset: Record<string, unknown> = {};
const coverage: Array<{ id: string; name: string; served: boolean; reason?: string }> = [];
for (const issuer of issuers) {
  const cnpj = years.flatMap((y) => y.filings).find((f) => f.cd_cvm === issuer.cd_cvm)?.cnpj ?? "";
  const rec = buildBrRecord(issuer, years, { cnpj, tickers: tickers.get(cnpj) ?? [] });
  const id = brId(issuer.cd_cvm);
  const why = !rec.financials ? rec.financials_error : rec.financial ? "a bank or insurer: line 3.01 is not sales" : null;
  coverage.push({ id, name: issuer.name, served: !why, ...(why ? { reason: why } : {}) });
  if (why) {
    console.warn(`${id} ${issuer.name}: not served (${why})`);
    continue;
  }
  writeFileSync(join(OUT, "v1", "br", "co", `${id}.json`), JSON.stringify(rec));
  dataset[id] = rec;
  index.push(brIndexRow(rec));
  const annual = rec.financials!.periods.filter((p) => p.type === "annual").length;
  console.log(`${id} ${issuer.name} ${rec.cvm!.tickers.join("/")}: ${annual} year(s)${rec.financials!.periods.some((p) => p.type === "ltm") ? " + LTM" : ""}`);
}

const license = { license: "ODbL-1.0", license_url: ODBL_URL, notice: CVM_NOTICE, source: CVM_PORTAL, derived_by: `${PRODUCT_NAME} (${REPO_URL})` };
const built = new Date().toISOString();
writeFileSync(join(OUT, "v1", "br", "companies.json"), JSON.stringify({ ...license, fields: ["id", "name", "tickers", "currency", "fiscal_year_end"], data: index }));
writeFileSync(join(OUT, "v1", "br", "manifest.json"), JSON.stringify({ schema: SNAPSHOT_SCHEMA, built_at: built, companies: index.length, ...license }));
// ODbL §4.6: the whole Derivative Database, machine-readable and free to download.
writeFileSync(join(OUT, "v1", "br", "dataset.json"), JSON.stringify({ ...license, built_at: built, companies: dataset }));
writeFileSync(join(OUT, "v1", "br", "coverage.json"), JSON.stringify({ built_at: built, issuers: coverage }));
const served = coverage.filter((c) => c.served).length;
console.log(`BR: ${served}/${issuers.length} companies served`);
if (!ONLY && served < issuers.length * 0.8) process.exit(1);
