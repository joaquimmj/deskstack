// Brazilian listed companies' annual statements (DFP) from CVM's open data, as IFRS facts the standardizer reads.
//
// CVM publishes one ZIP a year of semicolon-separated CSVs (Latin-1) under the ODbL (docs/DATA_SOURCES.md §13).
// Every company files the same fixed chart of accounts ("contas fixas"), so a line is read by its code, never guessed
// from its label: 3.01 is revenue for every non-financial company. Lines CVM leaves free-form (capex, D&A, EPS per
// share class) are not mapped and stay null.

import type { CompanyFacts, RawFact } from "../sec/xbrl";

/** Form name the standardizer treats as annual (sec/xbrl.ts ANNUAL_FORMS). */
export const CVM_ANNUAL_FORM = "DFP";

export type CvmStatement = "DRE" | "BPA" | "BPP" | "DFC_MI" | "DFC_MD";

/** Fixed CVM account -> IFRS concept. Consolidated statements only (files `_con_`). */
export const CVM_ACCOUNTS: Array<{ st: CvmStatement; code: string; concept: string; instant: boolean }> = [
  { st: "DRE", code: "3.01", concept: "Revenue", instant: false }, // Receita de Venda de Bens e/ou Serviços
  { st: "DRE", code: "3.03", concept: "GrossProfit", instant: false }, // Resultado Bruto
  // Resultado Antes do Resultado Financeiro e dos Tributos: profit before financial result and taxes (EBIT).
  { st: "DRE", code: "3.05", concept: "ProfitLossFromOperatingActivities", instant: false },
  { st: "DRE", code: "3.07", concept: "ProfitLossBeforeTax", instant: false }, // Resultado Antes dos Tributos sobre o Lucro
  { st: "DRE", code: "3.11", concept: "ProfitLoss", instant: false }, // Lucro/Prejuízo Consolidado do Período
  { st: "DRE", code: "3.11.01", concept: "ProfitLossAttributableToOwnersOfParent", instant: false }, // Atribuído a Sócios da Empresa Controladora
  { st: "DRE", code: "3.11.02", concept: "ProfitLossAttributableToNoncontrollingInterests", instant: false },
  { st: "BPA", code: "1", concept: "Assets", instant: true }, // Ativo Total
  { st: "BPA", code: "1.01.01", concept: "CashAndCashEquivalents", instant: true }, // Caixa e Equivalentes de Caixa
  // Aplicações Financeiras: current financial investments, of mixed kinds. Read as other current financial assets,
  // so net debt says it did not deduct them (as for TotalEnergies), rather than guessing which part is cash-like.
  { st: "BPA", code: "1.01.02", concept: "OtherCurrentFinancialAssets", instant: true },
  { st: "BPP", code: "2.01.04", concept: "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", instant: true }, // Empréstimos e Financiamentos (circulante)
  { st: "BPP", code: "2.02.01", concept: "LongtermBorrowings", instant: true }, // Empréstimos e Financiamentos (não circulante)
  // Patrimônio Líquido Consolidado: includes minorities. CVM has no fixed line for the owners' share alone, and a
  // computed one would not be a filed figure, so total equity here is consolidated (the notes say so).
  { st: "BPP", code: "2.03", concept: "Equity", instant: true },
  { st: "DFC_MI", code: "6.01", concept: "CashFlowsFromUsedInOperatingActivities", instant: false }, // Caixa Líquido Atividades Operacionais
  { st: "DFC_MD", code: "6.01", concept: "CashFlowsFromUsedInOperatingActivities", instant: false },
];

/** What a non-financial company's line 3.01 is called. Banks and insurers reuse the code for other lines. */
export const SALES_LABEL = /^Receita de Venda de Bens e\/ou Servi/;

const SCALE: Record<string, number> = { UNIDADE: 1, MIL: 1_000 };
const CURRENCY: Record<string, string> = { REAL: "BRL" };

export interface CvmFiling {
  /** Stable citation id: CVM's document number. */
  id: string;
  cd_cvm: string;
  cnpj: string;
  name: string;
  /** Balance-sheet date the filing reports (DT_REFER). */
  refer: string;
  version: number;
  /** When CVM received it (DT_RECEB): orders restatements. */
  received: string;
  url: string;
}

export interface CvmFact {
  concept: string;
  start?: string;
  end: string;
  value: number;
  currency: string;
  filing: string; // CvmFiling.id
  label: string;
}

export interface CvmYear {
  filings: CvmFiling[];
  facts: CvmFact[];
  /** cd_cvm -> label of its line 3.01, to tell non-financial companies from banks and insurers. */
  revenueLabel: Record<string, string>;
}

/** Semicolon CSV with a header row. CVM's files have no quoted fields. */
export function parseCsv(text: string): Array<Record<string, string>> {
  const lines = text.split(/\r?\n/).filter((l) => l.length);
  const head = (lines.shift() ?? "").replace(/^﻿/, "").split(";");
  return lines.map((l) => {
    const cells = l.split(";");
    return Object.fromEntries(head.map((h, i) => [h, cells[i] ?? ""]));
  });
}

/**
 * One year's DFP files (already decoded from Latin-1), for the companies asked: the latest version of each
 * company's filing, and its fixed-account lines for the current year and the comparative year it restates.
 * `files` maps a file name (as in the ZIP) to its text.
 */
export function extractDfpYear(files: Map<string, string>, want: Set<string>, year: number): CvmYear {
  const index = files.get(`dfp_cia_aberta_${year}.csv`);
  if (!index) throw new Error(`dfp_cia_aberta_${year}.csv is missing from the DFP files`);
  // Latest version per company and reference date.
  const latest = new Map<string, CvmFiling>();
  for (const r of parseCsv(index)) {
    if (!want.has(r.CD_CVM!)) continue;
    const f: CvmFiling = {
      id: `CVM-DFP-${r.ID_DOC}`,
      cd_cvm: r.CD_CVM!,
      cnpj: r.CNPJ_CIA!,
      name: r.DENOM_CIA!,
      refer: r.DT_REFER!,
      version: Number(r.VERSAO),
      received: r.DT_RECEB!,
      url: r.LINK_DOC!,
    };
    const key = `${f.cd_cvm}|${f.refer}`;
    const prev = latest.get(key);
    if (!prev || f.version > prev.version) latest.set(key, f);
  }
  const byKey = new Map([...latest.values()].map((f) => [`${f.cd_cvm}|${f.refer}|${f.version}`, f]));
  const facts: CvmFact[] = [];
  const revenueLabel: Record<string, string> = {};
  const seen = new Set<string>();
  for (const acc of CVM_ACCOUNTS) {
    const text = files.get(`dfp_cia_aberta_${acc.st}_con_${year}.csv`);
    if (!text) continue;
    for (const r of parseCsv(text)) {
      if (r.CD_CONTA !== acc.code || !want.has(r.CD_CVM!)) continue;
      const filing = byKey.get(`${r.CD_CVM}|${r.DT_REFER}|${r.VERSAO}`);
      if (!filing) continue; // an older version
      if (acc.code === "3.01") revenueLabel[filing.cd_cvm] = r.DS_CONTA!;
      const scale = SCALE[r.ESCALA_MOEDA!];
      const currency = CURRENCY[r.MOEDA!];
      const v = Number(r.VL_CONTA);
      if (!scale || !currency || !Number.isFinite(v)) continue; // unknown scale or currency: never guessed
      const end = r.DT_FIM_EXERC!;
      const start = acc.instant ? undefined : r.DT_INI_EXERC!;
      // DFC is filed either indirect (MI) or direct (MD): the same line once is enough.
      const dedupe = `${filing.id}|${acc.concept}|${start ?? ""}|${end}`;
      if (seen.has(dedupe)) continue;
      seen.add(dedupe);
      facts.push({ concept: acc.concept, ...(start ? { start } : {}), end, value: v * scale, currency, filing: filing.id, label: r.DS_CONTA! });
    }
  }
  return { filings: [...latest.values()], facts, revenueLabel };
}

/** The companyfacts shape standardize() reads: CVM lines as IFRS concepts, each citing its DFP. */
export function toCompanyFacts(name: string, years: CvmYear[], cdCvm: string): CompanyFacts {
  const filings = new Map(years.flatMap((y) => y.filings).filter((f) => f.cd_cvm === cdCvm).map((f) => [f.id, f]));
  const ns: Record<string, { units: Record<string, RawFact[]> }> = {};
  for (const y of years) {
    for (const f of y.facts) {
      const filing = filings.get(f.filing);
      if (!filing) continue;
      const row: RawFact = { val: f.value, end: f.end, accn: f.filing, filed: filing.received, form: CVM_ANNUAL_FORM, fy: Number(filing.refer.slice(0, 4)) };
      if (f.start) row.start = f.start;
      ((ns[f.concept] ??= { units: {} }).units[f.currency] ??= []).push(row);
    }
  }
  return { cik: 0, entityName: name, facts: { "ifrs-full": ns } };
}

/**
 * B3 tickers per CNPJ from CVM's FCA registration forms (fca_cia_aberta_valor_mobiliario_YYYY.csv, also ODbL):
 * shares traded on the exchange ("Bolsa"), still trading, latest form version. Ordinary shares first.
 */
export function tickersFromFca(text: string): Map<string, string[]> {
  const latest = new Map<string, number>();
  const rows = parseCsv(text);
  for (const r of rows) latest.set(r.CNPJ_Companhia!, Math.max(latest.get(r.CNPJ_Companhia!) ?? 0, Number(r.Versao)));
  const out = new Map<string, Array<{ code: string; ordinary: boolean }>>();
  for (const r of rows) {
    if (Number(r.Versao) !== latest.get(r.CNPJ_Companhia!)) continue;
    if (r.Mercado !== "Bolsa" || r.Data_Fim_Negociacao || !/^[A-Z]{4}\d{1,2}$/.test(r.Codigo_Negociacao ?? "")) continue;
    if (!/^Ações/.test(r.Valor_Mobiliario ?? "") && !/^Units?$/i.test(r.Valor_Mobiliario ?? "")) continue;
    const list = out.get(r.CNPJ_Companhia!) ?? [];
    if (!list.some((t) => t.code === r.Codigo_Negociacao)) list.push({ code: r.Codigo_Negociacao!, ordinary: /Ordin/.test(r.Valor_Mobiliario!) });
    out.set(r.CNPJ_Companhia!, list);
  }
  return new Map([...out].map(([k, v]) => [k, v.sort((a, b) => Number(b.ordinary) - Number(a.ordinary) || a.code.localeCompare(b.code)).map((t) => t.code)]));
}
