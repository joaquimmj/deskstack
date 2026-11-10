// Brazil (CVM open data, ODbL): the extractor on recorded files, the record, and the tools (stars brief lot 2 bis).
// Expected values are read from the published CSVs (test/fixtures/cvm), e.g. Petrobras DRE line 3.01 for 2025:
// 497549000.0000000000 thousand reais.

import { describe, expect, it } from "vitest";
import { extractDfpYear, parseCsv, tickersFromFca } from "../src/cvm/extract";
import { buildBrRecord } from "../src/cvm/record";
import { brRecords } from "./cvm-fixture";
import { baseEnv, call, fixtureAssets } from "./mcp-harness";

const env = () => baseEnv({ ASSETS: fixtureAssets(["AAPL"]) });
const petrobras = () => brRecords().find((r) => r.cvm!.code === "009512")!;
const year = (label: string) => petrobras().financials!.periods.find((p) => p.label === label)!;

const HEAD_INDEX = "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC";
const HEAD_ST = "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA";

describe("CVM extraction", () => {
  it("reads line 3.01 in thousands of reais and turns it into units", () => {
    expect(year("FY2025").values.revenue!.value).toBe(497_549_000_000);
    expect(year("FY2025").values.revenue!.concept).toBe("ifrs-full:Revenue");
    expect(year("FY2025").values.operating_income!.value).toBe(145_628_000_000); // 3.05
    expect(year("FY2025").values.net_income!.value).toBe(110_129_000_000); // 3.11.01, owners of the parent
  });

  it("takes a comparative year from the latest filing (restatements count)", () => {
    // FY2024 appears in the 2024 DFP (ÚLTIMO) and the 2025 DFP (PENÚLTIMO): the later filing wins.
    expect(year("FY2024").values.revenue!.value).toBe(490_829_000_000);
    expect(year("FY2024").values.revenue!.accession).toBe("CVM-DFP-155122");
  });

  it("keeps only the latest version of a resubmitted filing, and skips an unknown scale", () => {
    const files = new Map([
      [`dfp_cia_aberta_2025.csv`, [HEAD_INDEX,
        "1;2025-12-31;1;X SA;000001;DFP;100;2026-03-01;http://x/100",
        "1;2025-12-31;2;X SA;000001;DFP;101;2026-04-01;http://x/101"].join("\n")],
      [`dfp_cia_aberta_DRE_con_2025.csv`, [HEAD_ST,
        "1;2025-12-31;1;X SA;000001;DF;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.01;Receita de Venda de Bens e/ou Serviços;100;S",
        "1;2025-12-31;2;X SA;000001;DF;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.01;Receita de Venda de Bens e/ou Serviços;120;S",
        "1;2025-12-31;2;X SA;000001;DF;REAL;BILHAO;ÚLTIMO;2025-01-01;2025-12-31;3.05;Resultado;9;S"].join("\n")],
    ]);
    const y = extractDfpYear(files, new Set(["000001"]), 2025);
    expect(y.filings.map((f) => f.id)).toEqual(["CVM-DFP-101"]);
    expect(y.facts).toEqual([expect.objectContaining({ concept: "Revenue", value: 120_000, filing: "CVM-DFP-101" })]);
  });

  it("flags a bank, whose line 3.01 is not sales", () => {
    const files = new Map([
      [`dfp_cia_aberta_2025.csv`, `${HEAD_INDEX}\n1;2025-12-31;1;BANCO;000002;DFP;7;2026-02-01;http://x/7`],
      [`dfp_cia_aberta_DRE_con_2025.csv`, `${HEAD_ST}\n1;2025-12-31;1;BANCO;000002;DF;REAL;MIL;ÚLTIMO;2025-01-01;2025-12-31;3.01;Receitas de Intermediação Financeira;5;S`],
    ]);
    const y = extractDfpYear(files, new Set(["000002"]), 2025);
    expect(buildBrRecord({ cd_cvm: "000002", name: "BANCO" }, [y], { cnpj: "1", tickers: [] }).financial).toBe(true);
    expect(petrobras().financial).toBe(false);
  });

  it("leaves capex, D&A and EPS null: they are not fixed lines in CVM's chart", () => {
    const fy = year("FY2025");
    expect(fy.values.capex).toBeNull();
    expect(fy.values.d_and_a).toBeNull();
    expect(fy.values.diluted_eps).toBeNull();
    expect(fy.derived.ebitda).toBeNull();
  });

  it("net debt says it did not deduct the current financial investments (Aplicações Financeiras)", () => {
    expect(year("FY2025").derived.net_debt!.note).toMatch(/^does not deduct other current financial assets/);
  });

  it("tickers come from the FCA forms: still trading on B3, ordinary shares first, nothing invented", () => {
    expect(petrobras().cvm!.tickers).toEqual(["PETR3", "PETR4"]);
    const fca = parseCsv("CNPJ_Companhia;Versao;Valor_Mobiliario;Codigo_Negociacao;Mercado;Data_Fim_Negociacao\n" +
      "1;1;Ações Ordinárias;4030;Bolsa;\n2;1;Ações Ordinárias;BRFS3;Bolsa;2025-09-22\n3;1;Ações Preferenciais;ABCD4;Bolsa;\n3;1;Ações Ordinárias;ABCD3;Bolsa;");
    const text = ["CNPJ_Companhia;Versao;Valor_Mobiliario;Codigo_Negociacao;Mercado;Data_Fim_Negociacao", ...fca.map((r) => Object.values(r).join(";"))].join("\n");
    const t = tickersFromFca(text);
    expect(t.get("1")).toBeUndefined(); // a CVM code in the ticker field
    expect(t.get("2")).toBeUndefined(); // trading ended
    expect(t.get("3")).toEqual(["ABCD3", "ABCD4"]);
  });
});

describe("CVM quarterly statements (ITR): LTM", () => {
  const rec = (code: string) => brRecords().find((r) => r.cvm!.code === code)!;
  const ltm = (code: string) => rec(code).financials!.periods.find((p) => p.type === "ltm")!;

  it("builds the LTM as FY + YTD - prior YTD from the latest ITR (expected values worked from the CSVs)", () => {
    expect(ltm("009512")).toMatchObject({ label: "LTM to 2026-06-30", end: "2026-06-30" });
    expect(ltm("009512").values.revenue).toMatchObject({ value: 548_493_000_000, formula: "FY + YTD - prior YTD" });
    expect(ltm("005410")).toMatchObject({ label: "LTM to 2026-09-30" }); // WEG has filed its third quarter
    expect(ltm("005410").values.revenue!.value).toBe(40_719_467_000);
  });

  it("reads only the latest version of a resubmitted ITR (Vale's second quarter has three)", () => {
    const ids = Object.keys(rec("004170").filings);
    expect(ids).toContain("CVM-ITR-159978");
    expect(ids).not.toContain("CVM-ITR-159847");
    expect(ids).not.toContain("CVM-ITR-159855");
  });

  it("verify_value ties an LTM figure, and calls one a quarter late stale", async () => {
    const r = await call(env(), "verify_value", {
      company: "WEGE3",
      items: [
        { metric: "revenue", period: "LTM", value: 40_719.467, scale: "millions" },
        { metric: "revenue", period: "LTM", value: 40_130.18, scale: "millions" }, // the twelve months to June
      ],
    });
    expect(r.json.results.map((x: { status: string }) => x.status)).toEqual(["match", "mismatch"]);
    expect(r.json.results[1].hints[0]).toMatch(/^Stale: .*2026-06-30.*2026-09-30/);
    expect(r.json.sources.some((x: { form: string }) => x.form === "ITR")).toBe(true);
  });
});

describe("CVM through the tools", () => {
  it("company_lookup finds a Brazilian company by B3 ticker, id or name", async () => {
    for (const q of ["PETR4", "CVM9512", "petrobras"]) {
      const r = await call(env(), "company_lookup", { query: q });
      expect(r.json.results[0]).toMatchObject({ id: "CVM9512", region: "BR", tickers: ["PETR3", "PETR4"], currency: "BRL" });
    }
  });

  it("financial_statements cites each DFP and carries the ODbL attribution", async () => {
    const r = await call(env(), "financial_statements", { ticker: "WEGE3", years: 2 });
    expect(r.isError).toBe(false);
    expect(r.json.company).toMatchObject({ id: "CVM5410", region: "BR", reporting_standard: "IFRS (CVM DFP)" });
    expect(r.json.attribution).toMatch(/CVM Open Data Portal.*Open Database License/);
    expect(r.json.sources[0]).toMatchObject({ form: "DFP" });
    expect(r.json.sources[0].license_note).toMatch(/ODbL/);
    expect(r.json.notes.join(" ")).toMatch(/fixed chart of accounts/);
  });

  it("verify_value ties a Brazilian figure to its filing and catches a scale error", async () => {
    const fy = year("FY2025");
    const r = await call(env(), "verify_value", {
      company: "PETR4",
      items: [
        { metric: "revenue", period: "FY2025", value: 497_549, scale: "millions" },
        { metric: "net income", period: "FY2025", value: 110_129_000, scale: "millions" },
      ],
    });
    expect(r.json.results.map((x: { status: string }) => x.status)).toEqual(["match", "mismatch"]);
    expect(r.json.results[1].hints.join(" ")).toMatch(/Scale/);
    expect(r.json.sources[0].accession_or_id).toBe(fy.values.revenue!.accession);
  });

  it("data_status counts the Brazilian coverage and links the ODbL dataset", async () => {
    const r = await call(env(), "data_status");
    expect(r.json.coverage.brazil_cvm).toMatch(/^5 large non-financial Brazilian listed companies/);
    expect(r.json.coverage.brazil_cvm).toMatch(/dataset\.json/);
  });
});
