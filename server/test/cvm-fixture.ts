// Brazilian records built from the recorded CVM files (DFP 2023-2025, ITR 2026) (test/fixtures/cvm), through the real extractor and builder.

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { extractDfpYear, tickersFromFca } from "../src/cvm/extract";
import { brId, buildBrRecord } from "../src/cvm/record";
import type { EuRecord } from "../src/esef/record";

const DIR = join(import.meta.dirname, "fixtures", "cvm");
export const BR_FIXTURE_ISSUERS = [
  { cd_cvm: "009512", name: "PETROLEO BRASILEIRO S.A. PETROBRAS" },
  { cd_cvm: "004170", name: "VALE S.A." },
  { cd_cvm: "005410", name: "WEG S.A." },
  { cd_cvm: "023264", name: "AMBEV S.A." },
  { cd_cvm: "020087", name: "EMBRAER S.A." },
];

let memo: EuRecord[] | null = null;
export function brRecords(): EuRecord[] {
  if (memo) return memo;
  const files = new Map(readdirSync(DIR).filter((f) => f.endsWith(".csv")).map((f) => [f, readFileSync(join(DIR, f), "utf8")]));
  const want = new Set(BR_FIXTURE_ISSUERS.map((i) => i.cd_cvm));
  const years = [...[2023, 2024, 2025].map((y) => extractDfpYear(files, want, y)), extractDfpYear(files, want, 2026, "itr")];
  const tickers = tickersFromFca(files.get("fca_cia_aberta_valor_mobiliario_2026.csv")!);
  memo = BR_FIXTURE_ISSUERS.map((i) => {
    const cnpj = years.flatMap((y) => y.filings).find((f) => f.cd_cvm === i.cd_cvm)!.cnpj;
    const rec = buildBrRecord(i, years, { cnpj, tickers: tickers.get(cnpj) ?? [] });
    rec.built_at = "2026-11-10T04:00:00Z";
    return rec;
  });
  return memo;
}

/** The /v1/br/ asset files, as the snapshot build writes them. */
export function brAssets(): Map<string, unknown> {
  const files = new Map<string, unknown>();
  const recs = brRecords();
  files.set("/v1/br/companies.json", {
    fields: ["id", "name", "tickers", "currency", "fiscal_year_end"],
    data: recs.map((r) => [brId(r.cvm!.code), r.name, r.cvm!.tickers, r.financials!.currency, "1231"]),
  });
  files.set("/v1/br/manifest.json", { built_at: "2026-11-10T04:00:00Z" });
  for (const r of recs) files.set(`/v1/br/co/${r.lei}.json`, r);
  return files;
}
