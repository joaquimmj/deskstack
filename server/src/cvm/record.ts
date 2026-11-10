// One Brazilian listed company's precomputed record (built by scripts/build-cvm.ts, served under /v1/br/). Same shape
// as a European issuer's record, so the statement tools, key_metrics and verify_value read it unchanged.

import { SNAPSHOT_SCHEMA, SNAPSHOT_YEARS } from "../config";
import type { EuFilingRef, EuRecord } from "../esef/record";
import { NoAnnualFacts, standardize, type Standardized } from "../sec/xbrl";
import { SALES_LABEL, toCompanyFacts, type CvmYear } from "./extract";

export const CVM_PORTAL = "https://dados.cvm.gov.br/";
export const ODBL_URL = "https://opendatacommons.org/licenses/odbl/1-0/";
/** ODbL §4.3 notice, plus the citation CVM's terms ask for. */
export const CVM_NOTICE =
  "Contains information from the CVM Open Data Portal (https://dados.cvm.gov.br/), made available under the Open " +
  "Database License (ODbL, https://opendatacommons.org/licenses/odbl/1-0/).";

/** deskstack's id for a Brazilian company: "CVM" + its CVM code, e.g. CVM9512 for Petrobras. */
export const BR_ID_RE = /^CVM\d{1,6}$/;
export function brId(cdCvm: string): string {
  return `CVM${Number(cdCvm)}`;
}

/** The index row for a company: id, name, tickers, currency, and the fiscal year end of its last annual column
 * (the LTM column comes after the annual ones, and ends on a quarter). */
export function brIndexRow(rec: EuRecord): [string, string, string[], string | null, string | null] {
  const lastAnnual = rec.financials?.periods.filter((p) => p.type === "annual").at(-1);
  return [rec.lei, rec.name, rec.cvm?.tickers ?? [], rec.financials?.currency ?? null, lastAnnual?.end.slice(5).replace("-", "") ?? null];
}

export interface BrIssuer {
  cd_cvm: string;
  name: string;
}

export function buildBrRecord(issuer: BrIssuer, years: CvmYear[], cvm: { cnpj: string; tickers: string[] }): EuRecord {
  const mine = years.flatMap((y) => y.filings).filter((f) => f.cd_cvm === issuer.cd_cvm);
  const byId = new Map(mine.map((f) => [f.id, f]));
  const label = years.map((y) => y.revenueLabel[issuer.cd_cvm]).filter(Boolean).at(-1) ?? "";
  // Banks and insurers reuse line 3.01 for other items: flagged, so EBITDA and EV metrics stay off.
  const financial = !!label && !SALES_LABEL.test(label);
  let financials: Standardized | null = null;
  let error: string | null = null;
  try {
    financials = standardize(toCompanyFacts(issuer.name, years, issuer.cd_cvm), SNAPSHOT_YEARS, true, {
      source: "cvm",
      filingUrl: (a) => byId.get(a)?.url ?? CVM_PORTAL,
    });
  } catch (e) {
    if (!(e instanceof NoAnnualFacts)) throw e;
    error = "no consolidated annual statements (DFP) in CVM's open data";
  }
  const filings: Record<string, EuFilingRef> = {};
  for (const f of mine) {
    filings[f.id] = {
      fxo_id: f.id,
      processed: f.received,
      published: f.received,
      country: "BR",
      viewer_url: null,
      report_url: f.url,
      package_url: null,
      kind: f.form === "ITR" ? "half-year" : "annual",
      report_end: f.refer,
    };
  }
  return {
    schema: SNAPSHOT_SCHEMA,
    kind: "cvm",
    lei: brId(issuer.cd_cvm),
    name: issuer.name,
    country: "BR",
    financial,
    financials,
    financials_error: error,
    filings,
    built_at: "",
    origin: "snapshot",
    cvm: { code: issuer.cd_cvm, cnpj: cvm.cnpj, tickers: cvm.tickers },
  };
}
