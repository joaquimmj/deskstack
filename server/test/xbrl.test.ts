// Parity tests for the XBRL port. Portions adapted from open-finance-mcp
// (c) 2026 Nathanael Johnson, MIT License (tests/test_xbrl.py @ 8bcf3af0).
// Same fixtures, same expected values; deliberate changes are marked "CHANGE".

import { describe, expect, it } from "vitest";
import { EXT_KEYS, ifrsTotalDebt, NoAnnualFacts, sharesOutstanding, standardize, totalDebt, type RawFact } from "../src/sec/xbrl";
import { companyfacts, fact, facts } from "./helpers";

const col = (r: ReturnType<typeof standardize>, label: string) => {
  const c = r.periods.find((p) => p.label === label);
  if (!c) throw new Error(`no column ${label}`);
  return c;
};
const rows = (cf: ReturnType<typeof facts>, concept: string, unit = "USD"): RawFact[] =>
  cf.facts["us-gaap"]![concept]!.units![unit]!;

describe("real filings", () => {
  it("Apple FY2024 matches the 10-K", () => {
    const r = standardize(facts("AAPL"), 5);
    const fy24 = col(r, "FY2024");
    expect([fy24.start, fy24.end]).toEqual(["2023-10-01", "2024-09-28"]);
    expect(fy24.values.revenue!.value).toBe(391_035_000_000);
    expect(fy24.values.revenue!.concept).toBe("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax");
    expect(fy24.values.net_income!.value).toBe(93_736_000_000);
    // Commercial paper 9.967B + term debt 10.912B current + 85.750B noncurrent.
    expect(fy24.derived.total_debt).toEqual({
      value: 106_629_000_000,
      formula: "ltd_noncurrent + ltd_current + commercial_paper",
    });
  });

  it("every cited accession has a filing URL", () => {
    const r = standardize(facts("AAPL"), 3);
    for (const p of r.periods) {
      for (const group of [p.values, p.balance_sheet]) {
        for (const c of Object.values(group)) {
          if (!c) continue;
          for (const a of c.accessions ?? [c.accession!]) expect(r.filings[a]!.url.endsWith(`${a}-index.htm`)).toBe(true);
        }
      }
    }
  });

  it("Apple LTM is FY + YTD - prior YTD", () => {
    const cf = facts("AAPL");
    const r = standardize(cf, 1);
    const ltm = r.periods.at(-1)!;
    expect(ltm.type).toBe("ltm");
    const fy = col(r, "FY2025");
    const rev = rows(cf, "RevenueFromContractWithCustomerExcludingAssessedTax");
    const ytdStart = "2025-09-28";
    const byFiled = (a: RawFact, b: RawFact) => ((a.filed ?? "") < (b.filed ?? "") ? b : a);
    const cur = rev.filter((x) => x.start === ytdStart && x.end === ltm.end).reduce(byFiled);
    const prior = rev
      .filter((x) => x.start === fy.start && x.form === "10-Q" && x.end < fy.end && x.end >= "2025-06-01")
      .reduce(byFiled);
    expect(ltm.values.revenue!.value).toBe(fy.values.revenue!.value + cur.val - prior.val);
    expect(ltm.label).toBe(`LTM to ${ltm.end}`);
    expect(ltm.ytd).toEqual({ start: ytdStart, end: ltm.end, days: 273 }); // 39 weeks
  });

  it("CHANGE: LTM diluted EPS is trailing (FY + YTD - prior YTD), not the YTD figure", () => {
    const cf = facts("AAPL");
    const r = standardize(cf, 1);
    const ltm = r.periods.at(-1)!;
    const fy = col(r, "FY2025");
    const eps = ltm.values.diluted_eps!;
    expect(eps.formula).toBe("FY + YTD - prior YTD");
    expect(eps.accessions!.length).toBeGreaterThanOrEqual(2);
    const ytdOnly = cf.facts["us-gaap"]!.EarningsPerShareDiluted!.units!["USD/shares"]!.filter(
      (x) => x.start === ltm.ytd!.start && x.end === ltm.end,
    );
    // Trailing EPS is close to the fiscal-year EPS, and far above 9-month YTD EPS.
    expect(Math.abs(eps.value - fy.values.diluted_eps!.value)).toBeLessThan(0.3 * fy.values.diluted_eps!.value);
    expect(eps.value).toBeGreaterThan(ytdOnly[0]!.val * 1.2);
  });

  it("fiscal years follow the company calendar", () => {
    const labels = standardize(facts("MSFT"), 2, false).periods.map((p) => [p.label, p.end]);
    expect(labels).toEqual([
      ["FY2025", "2025-06-30"],
      ["FY2026", "2026-06-30"],
    ]);
  });

  it("bank uses long-term debt including current; no EBITDA", () => {
    const r = standardize(facts("JPM"), 1);
    expect(r.periods[0]!.derived.total_debt!.formula.startsWith("ltd_total")).toBe(true);
    expect(r.periods[0]!.derived.ebitda).toBeNull();
  });

  it("segment-only debt is null, not zero", () => {
    const ltm = standardize(facts("CAT"), 1).periods.at(-1)!;
    expect(ltm.type).toBe("ltm");
    expect(ltm.derived.total_debt).toBeNull();
    expect(ltm.derived.net_debt).toBeNull();
  });

  it("new registrant without history raises", () => {
    expect(() => standardize(facts("XOM"))).toThrow(NoAnnualFacts);
    expect(() => standardize(facts("XOM"))).toThrow(/predecessor/);
  });

  it("shares from the cover page", () => {
    const s = sharesOutstanding(facts("AAPL"))!;
    expect(s.concept).toBe("dei:EntityCommonStockSharesOutstanding");
    expect(s.classes_summed).toBe(1);
    expect(s.value).toBeGreaterThan(1e10);
  });

  it("shares fall back to the balance sheet for per-class cover pages", () => {
    const s = sharesOutstanding(facts("GOOGL"))!;
    expect(s.concept).toBe("us-gaap:CommonStockSharesOutstanding");
    expect(s.classes_summed).toBeNull();
    expect(s.value).toBeGreaterThan(1e10);
  });

  it("IFRS filer is read in its own currency", () => {
    const r = standardize(facts("SAP"), 3);
    expect([r.taxonomy, r.currency]).toEqual(["ifrs-full", "EUR"]);
    const fy = r.periods.at(-1)!;
    expect(fy.values.revenue).toEqual({
      value: 36_800_000_000,
      concept: "ifrs-full:Revenue",
      accession: fy.values.revenue!.accession,
    });
    expect(fy.values.net_income!.concept).toBe("ifrs-full:ProfitLossAttributableToOwnersOfParent");
    expect(fy.derived.total_debt!.formula).toBe("borrowings");
    expect(r.periods.every((p) => p.type === "annual")).toBe(true); // 6-K interims carry no XBRL
    expect(r.notes.some((n) => n.includes("IFRS filer"))).toBe(true);
  });

  it("IFRS short-term deposits count as short-term investments in net debt (Inditex style)", () => {
    // Inditex FY2025 (ended 2026-01-31), EUR millions: cash 5,276, short-term deposits 5,684, borrowings 2.
    const at = (v: number) => [fact(v, null, "2026-01-31", "i-25", "2026-03-20", "ESEF", 2025)];
    const ifrs = (o: Record<string, RawFact[]>) => {
      const ns: Record<string, { units: { EUR: RawFact[] } }> = {};
      for (const [k, v] of Object.entries(o)) ns[k] = { units: { EUR: v } };
      return { cik: 0, entityName: "Inditex", facts: { "ifrs-full": ns } } as never;
    };
    const cf = ifrs({
      Revenue: [fact(39_900, "2025-02-01", "2026-01-31", "i-25", "2026-03-20", "ESEF", 2025)],
      Borrowings: at(2),
      CashAndCashEquivalents: at(5_276),
      ShorttermDepositsNotClassifiedAsCashEquivalents: at(5_684),
    });
    const p = standardize(cf, 5, false).periods[0]!;
    expect(p.balance_sheet.short_term_investments!.concept).toBe("ifrs-full:ShorttermDepositsNotClassifiedAsCashEquivalents");
    expect(p.derived.net_debt!.value).toBe(2 - 5_276 - 5_684);
  });

  it("an IFRS filer that tags only basic EPS gets it as diluted EPS, with a note (Inditex)", () => {
    // Inditex FY2025 (ended 2026-01-31): basic EPS 1.996 EUR, no diluted EPS, no share count tagged.
    const y = (v: number) => [fact(v, "2025-02-01", "2026-01-31", "i-25", "2026-03-20", "ESEF", 2025)];
    const ns: Record<string, { units: Record<string, RawFact[]> }> = {
      Revenue: { units: { EUR: y(39_900e6) } },
      ProfitLossAttributableToOwnersOfParent: { units: { EUR: y(6_220e6) } },
      BasicEarningsLossPerShare: { units: { "EUR/shares": y(1.996) } },
    };
    const p = standardize({ cik: 0, entityName: "Inditex", facts: { "ifrs-full": ns } } as never, 5, false).periods[0]!;
    expect(p.values.diluted_eps).toMatchObject({ value: 1.996, concept: "ifrs-full:BasicEarningsLossPerShare" });
    expect(p.values.diluted_eps!.note).toMatch(/basic EPS: the filer tags no diluted EPS/);
  });

  it("an IFRS filer that tags EPS only from continuing operations gets it, with a note, and no derived shares (Iberdrola)", () => {
    // Iberdrola FY2025: diluted EPS from continuing operations 0.843 EUR; no total EPS, no share count tagged.
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "ib-25", "2026-03-01", "ESEF", 2025)];
    const p = standardize({ cik: 0, entityName: "Iberdrola", facts: { "ifrs-full": {
      Revenue: { units: { EUR: y(45_000e6) } },
      ProfitLossAttributableToOwnersOfParent: { units: { EUR: y(5_600e6) } },
      BasicEarningsLossPerShareFromContinuingOperations: { units: { "EUR/shares": y(0.845) } },
      DilutedEarningsLossPerShareFromContinuingOperations: { units: { "EUR/shares": y(0.843) } },
    } } } as never, 5, false).periods[0]!.values;
    expect(p.diluted_eps).toMatchObject({ value: 0.843, concept: "ifrs-full:DilutedEarningsLossPerShareFromContinuingOperations" });
    expect(p.diluted_eps!.note).toMatch(/continuing operations/);
    // Net income includes discontinued operations, so net income / this EPS is not a share count.
    expect(p.diluted_shares).toBeNull();
  });

  it("with no share count tagged, diluted shares are derived from net income and EPS, and say so", () => {
    const y = (v: number) => [fact(v, "2025-02-01", "2026-01-31", "i-25", "2026-03-20", "ESEF", 2025)];
    const facts = (extra: Record<string, { units: Record<string, RawFact[]> }>) =>
      standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": {
        Revenue: { units: { EUR: y(30_000e6) } },
        ProfitLossAttributableToOwnersOfParent: { units: { EUR: y(6_000e6) } },
        BasicEarningsLossPerShare: { units: { "EUR/shares": y(2.0) } },
        ...extra,
      } } } as never, 5, false).periods[0]!.values;
    const derived = facts({}).diluted_shares!;
    expect(derived.value).toBe(3_000_000_000);
    expect(derived.concept).toBe(""); // computed, so verify_value shows the formula
    expect(derived.formula).toBe("net_income / basic EPS (no diluted EPS or share count tagged)");
    expect(facts({ DilutedEarningsLossPerShare: { units: { "EUR/shares": y(2.0) } } }).diluted_shares!.formula).toBe(
      "net_income / diluted_eps (no share count tagged)",
    );
    // A tagged share count always wins.
    expect(facts({ AdjustedWeightedAverageShares: { units: { shares: y(3_050e6) } } }).diluted_shares!.value).toBe(3_050e6);
  });

  it("IFRS net income says when it is consolidated profit including minorities (OMV; stars brief lot 2 bis)", () => {
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "o-25", "2026-03-20", "ESEF", 2025)];
    const run = (extra: Record<string, { units: Record<string, RawFact[]> }>) => standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": {
      Revenue: { units: { EUR: y(24_000e6) } },
      ProfitLoss: { units: { EUR: y(1_520e6) } },
      ...extra,
    } } } as never, 5, false).periods[0]!.values;
    const omv = run({ ProfitLossAttributableToNoncontrollingInterests: { units: { EUR: y(443e6) } } });
    expect(omv.net_income!.value).toBe(1_520e6); // the tagged figure, never an estimate of the owners' share
    expect(omv.net_income!.note).toMatch(/443 million attributable to non-controlling interests/);
    expect(omv).not.toHaveProperty("net_income_nci");
    // No minorities tagged (Novo Nordisk), or owners' profit tagged: nothing to say.
    expect(run({}).net_income!.note).toBeUndefined();
    expect(run({ ProfitLossAttributableToNoncontrollingInterests: { units: { EUR: y(0) } } }).net_income!.note).toBeUndefined();
    const owners = run({ ProfitLossAttributableToOwnersOfParent: { units: { EUR: y(1_077e6) } },
      ProfitLossAttributableToNoncontrollingInterests: { units: { EUR: y(443e6) } } }).net_income!;
    expect(owners.value).toBe(1_077e6);
    expect(owners.note).toBeUndefined();
  });

  it("IFRS revenue is never one component of it: sale of goods alone, next to services, is not total revenue (NOS, REN; review 2026-11-10)", () => {
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "n-25", "2026-03-20", "ESEF", 2025)];
    const std = (f: Record<string, { units: Record<string, RawFact[]> }>) => standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": {
      ProfitLoss: { units: { EUR: y(246e6) } }, ...f } } } as never, 5, false);
    // NOS: goods 170 and services 1,609, no total tagged.
    const nos = std({ RevenueFromSaleOfGoods: { units: { EUR: y(170.416e6) } }, RevenueFromRenderingOfServices: { units: { EUR: y(1_609.226e6) } } });
    expect(nos.periods[0]!.values.revenue).toBeNull();
    expect(nos.notes.join(" ")).toMatch(/FY2025.*revenue is null.*sale of goods 170 million.*rendering of services 1,609 million/);
    // A company that only sells goods (Moncler-like): sale of goods is its revenue.
    const goods = std({ RevenueFromSaleOfGoods: { units: { EUR: y(3_100e6) } } });
    expect(goods.periods[0]!.values.revenue!.value).toBe(3_100e6);
    // A tagged total always wins.
    const total = std({ Revenue: { units: { EUR: y(1_779e6) } }, RevenueFromSaleOfGoods: { units: { EUR: y(170e6) } },
      RevenueFromRenderingOfServices: { units: { EUR: y(1_609e6) } } });
    expect(total.periods[0]!.values.revenue!.value).toBe(1_779e6);
  });

  it("IFRS capex says when it is the broad line with intangibles and investment property (review 2026-11-10)", () => {
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "q-25", "2026-03-20", "ESEF", 2025)];
    const BROAD = "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets";
    const capex = (f: object) => standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": {
      Revenue: { units: { EUR: y(10_000e6) } }, ...f } } } as never, 5, false).periods[0]!.values.capex!;
    const broad = capex({ [BROAD]: { units: { EUR: y(-950e6) } } });
    expect(broad.concept).toBe(`ifrs-full:${BROAD}`);
    expect(broad.note).toMatch(/^includes purchases of intangible assets, investment property and other non-current assets/);
    const ppe = capex({ PurchaseOfPropertyPlantAndEquipment: { units: { EUR: y(-700e6) } }, [BROAD]: { units: { EUR: y(-950e6) } } });
    expect(ppe.concept).toBe("ifrs-full:PurchaseOfPropertyPlantAndEquipment");
    expect(ppe.note).toBeUndefined();
  });

  it("IFRS interest expense says when it is the broader finance costs line (IAS 1; review 2026-11-10)", () => {
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "q-25", "2026-03-20", "ESEF", 2025)];
    const ie = (f: object) => standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": {
      Revenue: { units: { EUR: y(10_000e6) } }, ...f } } } as never, 5, false).periods[0]!.values.interest_expense!;
    const fc = ie({ FinanceCosts: { units: { EUR: y(412e6) } } });
    expect(fc.value).toBe(412e6);
    expect(fc.note).toMatch(/^finance costs: the filer tags no interest expense line/);
    const both = ie({ InterestExpense: { units: { EUR: y(300e6) } }, FinanceCosts: { units: { EUR: y(412e6) } } });
    expect(both.value).toBe(300e6);
    expect(both.note).toBeUndefined();
  });

  it("IFRS total equity says when it includes minorities, the owners' share being untagged (Orkla, Corticeira; review 2026-11-10)", () => {
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "q-25", "2026-03-20", "ESEF", 2025)];
    const at = (v: number) => [fact(v, null, "2025-12-31", "q-25", "2026-03-20", "ESEF", 2025)];
    const eq = (f: Record<string, { units: Record<string, RawFact[]> }>) => standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": {
      Revenue: { units: { NOK: y(71_044e6) } }, ...f } } } as never, 5, false).periods[0]!.balance_sheet.total_equity!;
    const orkla = eq({ Equity: { units: { NOK: at(52_147e6) } }, NoncontrollingInterests: { units: { NOK: at(3_483e6) } } });
    expect(orkla.value).toBe(52_147e6); // the tagged total, never an estimate of the owners' share
    expect(orkla.note).toMatch(/includes 3,483 million of non-controlling interests/);
    expect(eq({ Equity: { units: { NOK: at(52_147e6) } } }).note).toBeUndefined();
    const owners = eq({ Equity: { units: { NOK: at(52_147e6) } }, EquityAttributableToOwnersOfParent: { units: { NOK: at(48_664e6) } },
      NoncontrollingInterests: { units: { NOK: at(3_483e6) } } });
    expect(owners.value).toBe(48_664e6);
    expect(owners.note).toBeUndefined();
  });

  it("IFRS net debt says when current financial assets are tagged only mixed with derivatives (TotalEnergies; stars brief lot 1)", () => {
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "t-25", "2026-03-20", "ESEF", 2025)];
    const at = (v: number) => [fact(v, null, "2025-12-31", "t-25", "2026-03-20", "ESEF", 2025)];
    const run = (extra: Record<string, { units: Record<string, RawFact[]> }>) => standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": {
      Revenue: { units: { USD: y(180_000e6) } },
      CashAndCashEquivalents: { units: { USD: at(26_202e6) } },
      Borrowings: { units: { USD: at(50_000e6) } },
      ...extra,
    } } } as never, 5, false).periods[0]!;
    const tte = run({ OtherCurrentFinancialAssets: { units: { USD: at(3_332e6) } } });
    expect(tte.derived.net_debt!.value).toBe(50_000e6 - 26_202e6); // not deducted: it mixes derivatives and receivables
    expect(tte.derived.net_debt!.note).toMatch(/3,332/);
    expect(tte.balance_sheet).not.toHaveProperty("other_current_financial_assets");
    // Clean short-term deposits are deducted, and then there is nothing to warn about (Inditex).
    const itx = run({ ShorttermDepositsNotClassifiedAsCashEquivalents: { units: { USD: at(5_684e6) } }, OtherCurrentFinancialAssets: { units: { USD: at(100e6) } } });
    expect(itx.derived.net_debt!.value).toBe(50_000e6 - 26_202e6 - 5_684e6);
    expect(itx.derived.net_debt!.note).toBeUndefined();
  });

  it("an IFRS filer that tags D&A only with impairment gets that figure, with a note (TotalEnergies, Ahold)", () => {
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "t-25", "2026-03-20", "ESEF", 2025)];
    const base = { Revenue: { units: { USD: y(180_000e6) } }, ProfitLossFromOperatingActivities: { units: { USD: y(20_000e6) } } };
    const cf = (extra: Record<string, { units: Record<string, RawFact[]> }>) =>
      standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": { ...base, ...extra } } } as never, 5, false).periods[0]!;
    const withImp = cf({ AdjustmentsForDepreciationAndAmortisationExpenseAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss: { units: { USD: y(13_847e6) } } });
    expect(withImp.values.d_and_a!.value).toBe(13_847e6);
    expect(withImp.values.d_and_a!.note).toMatch(/includes impairment/);
    // A D&A line without impairment always wins.
    const both = cf({
      AdjustmentsForDepreciationAndAmortisationExpenseAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss: { units: { USD: y(13_847e6) } },
      AdjustmentsForDepreciationAndAmortisationExpense: { units: { USD: y(12_000e6) } },
    });
    expect(both.values.d_and_a!.value).toBe(12_000e6);
    expect(both.values.d_and_a!.note).toBeUndefined();
  });

  it("derived shares: IFRS annual columns only, never for a loss, a tiny EPS or a US filer (review)", () => {
    const y = (v: number) => [fact(v, "2025-02-01", "2026-01-31", "i-25", "2026-03-20", "ESEF", 2025)];
    const ifrs = (ni: number, eps: number) =>
      standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": {
        Revenue: { units: { EUR: y(30_000e6) } },
        ProfitLossAttributableToOwnersOfParent: { units: { EUR: y(ni) } },
        DilutedEarningsLossPerShare: { units: { "EUR/shares": y(eps) } },
      } } } as never, 5, false).periods[0]!.values.diluted_shares;
    expect(ifrs(-600e6, -2)).toBeNull(); // loss year
    expect(ifrs(30e6, 0.12)).toBeNull(); // EPS in cents: the count would be off by percents
    const us = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "u-25", "2026-02-20", "10-K", 2025)];
    const usCf = companyfacts({ Revenues: us(1_000e6), NetIncomeLoss: us(100e6) });
    usCf.facts["us-gaap"]!.EarningsPerShareDiluted = { units: { "USD/shares": us(2.0) } };
    expect(standardize(usCf, 5, false).periods[0]!.values.diluted_shares).toBeNull();
  });

  it("EBITDA says when D&A includes impairment, and notes add up instead of replacing each other (review)", () => {
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "t-25", "2026-03-20", "ESEF", 2025)];
    const p = standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": {
      Revenue: { units: { USD: y(180_000e6) } },
      ProfitLossFromOperatingActivities: { units: { USD: y(20_000e6) } },
      AdjustmentsForDepreciationAndAmortisationExpenseAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss: { units: { USD: y(13_847e6) } },
    } } } as never, 5, false).periods[0]!;
    expect(p.derived.ebitda).toEqual({ value: 33_847e6, formula: "operating_income + d_and_a (includes impairment)" });
  });

  it("an issuer's two own D&A parts are added only from one filing, and never in the LTM column (review, PR #14)", () => {
    const own = (v: number, accn: string, filed: string, src: string, start = "2024-01-01", end = "2024-12-31", form = "ESEF") =>
      ({ ...fact(v, start, end, accn, filed, form, 2024), src });
    const ifrs = (ns: Record<string, RawFact[]>) => ({ cik: 0, entityName: "X", facts: { "ifrs-full": Object.fromEntries(
      Object.entries(ns).map(([k, v]) => [k, { units: { EUR: v } }])) } }) as never;
    // FY2024 report: 100 + 50. FY2025 report restates 2024 depreciation to 80 but doesn't tag 2024 amortization.
    const mixed = standardize(ifrs({
      Revenue: [fact(1000, "2024-01-01", "2024-12-31", "r24", "2025-03-01", "ESEF", 2024)],
      [EXT_KEYS.depreciation]: [own(100, "r24", "2025-03-01", "x:DepreciationOfPropertyPlantAndEquipment"), own(80, "r25", "2026-03-01", "x:DepreciationOfPropertyPlantAndEquipment")],
      [EXT_KEYS.amortization]: [own(50, "r24", "2025-03-01", "x:AmortisationOfIntangibleAssets")],
    }), 5, false).periods[0]!.values;
    expect(mixed.d_and_a).toBeNull(); // 130 is in neither filing
    // With a half-year report: the annual column adds the parts, the LTM column doesn't (its D&A could be defined
    // differently from the annual one).
    const fy = (k: string, v: number) => own(v, "r24", "2025-03-01", k);
    const hy = (k: string, v: number, y: number) => own(v, "h25", "2025-09-01", k, `${y}-01-01`, `${y}-06-30`, "ESEF-HY");
    const D = "x:DepreciationOfPropertyPlantAndEquipment", A = "x:AmortisationOfIntangibleAssets";
    const withHy = standardize(ifrs({
      Revenue: [fact(1000, "2024-01-01", "2024-12-31", "r24", "2025-03-01", "ESEF", 2024),
        fact(520, "2025-01-01", "2025-06-30", "h25", "2025-09-01", "ESEF-HY", 2025), fact(480, "2024-01-01", "2024-06-30", "h25", "2025-09-01", "ESEF-HY", 2025)],
      [EXT_KEYS.depreciation]: [fy(D, 100), hy(D, 55, 2025), hy(D, 45, 2024)],
      [EXT_KEYS.amortization]: [fy(A, 50), hy(A, 30, 2025), hy(A, 25, 2024)],
    }), 5, true);
    expect(withHy.periods.find((p) => p.label === "FY2024")!.values.d_and_a!.value).toBe(150);
    const ltm = withHy.periods.find((p) => /LTM/.test(p.label));
    expect(ltm, "an LTM column").toBeDefined();
    expect(ltm!.values.d_and_a).toBeNull();
  });

  it("Cisco's D&A adds intangible amortization to its property-and-equipment-only D&A tag; nobody else's does", () => {
    // Cisco FY2026 10-K: DepreciationDepletionAndAmortization 700 (property and equipment only), intangibles 916.
    const y = (v: number) => [fact(v, "2025-07-27", "2026-07-25", "c-26", "2026-09-05", "10-K", 2026)];
    const facts = { Revenues: y(56_000), DepreciationDepletionAndAmortization: y(700), AmortizationOfIntangibleAssets: y(916) };
    const csco = standardize({ ...companyfacts(facts), cik: 858877 }, 5, false).periods[0]!.values.d_and_a!;
    expect(csco.value).toBe(1616);
    expect(csco.formula).toMatch(/depreciation \+ amortization of intangible assets/);
    expect(csco.note).toMatch(/property and equipment only/);
    // Any other filer's DepreciationDepletionAndAmortization already includes amortization: kept as tagged.
    expect(standardize(companyfacts(facts), 5, false).periods[0]!.values.d_and_a!.value).toBe(700);
  });

  it("Verizon-style capex says which line it is (review)", () => {
    const y = (v: number) => [fact(v, "2024-01-01", "2024-12-31", "v-24", "2025-02-10", "10-K", 2024)];
    const vz = { ...companyfacts({ Revenues: y(1), PaymentsToAcquireOtherProductiveAssets: y(17_090) }), cik: 732712 };
    const capex = standardize(vz, 5, false).periods[0]!.values.capex!;
    expect(capex).toMatchObject({ value: 17_090, concept: "us-gaap:PaymentsToAcquireOtherProductiveAssets" });
    expect(capex.note).toMatch(/other productive assets/);
    expect(standardize(vz, 5, false).periods[0]!.values).not.toHaveProperty("capex_other_productive");
    // Any other filer: a small "other productive assets" line is not taken as capex (review, cycle 2).
    expect(standardize(companyfacts({ Revenues: y(1), PaymentsToAcquireOtherProductiveAssets: y(40) }), 5, false).periods[0]!.values.capex).toBeNull();
  });

  it("derived shares prefer net income to ordinary holders, and say how far they can be off (review, cycle 2)", () => {
    const y = (v: number) => [fact(v, "2021-01-01", "2021-12-31", "g-21", "2022-03-10", "ESEF", 2021)];
    const shares = (extra: Record<string, { units: Record<string, RawFact[]> }>) =>
      standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": {
        Revenue: { units: { EUR: y(20_000e6) } },
        ProfitLossAttributableToOwnersOfParent: { units: { EUR: y(4_000e6) } },
        DilutedEarningsLossPerShare: { units: { "EUR/shares": y(1.0) } },
        ...extra,
      } } } as never, 5, false).periods[0]!.values.diluted_shares!;
    // ING-style: EPS is computed on profit to ordinary holders, after AT1 coupons.
    const ord = shares({ ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntity: { units: { EUR: y(3_900e6) } } });
    expect(ord.value).toBe(3_900e6);
    expect(ord.formula).toMatch(/^net income to ordinary holders \/ diluted_eps/);
    expect(standardize({ cik: 0, entityName: "X", facts: { "ifrs-full": { Revenue: { units: { EUR: y(1) } }, ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntity: { units: { EUR: y(1) } } } } } as never, 5, false).periods[0]!.values).not.toHaveProperty("net_income_ordinary");
    const owners = shares({});
    expect(owners.value).toBe(4_000e6);
    expect(owners.note).toMatch(/hybrid|AT1/);
    expect(owners.note).toMatch(/±0\.5%/); // EPS 1.00 rounded to cents
  });

  it("Toyota IFRS with no standard capex concept", () => {
    const r = standardize(facts("TM"), 1);
    const fy = r.periods[0]!;
    expect([r.taxonomy, r.currency, fy.end]).toEqual(["ifrs-full", "JPY", "2025-03-31"]);
    expect(fy.values.revenue!.value).toBe(48_036_704_000_000);
    expect(fy.values.capex).toBeNull();
    expect(fy.derived.free_cash_flow).toBeNull();
    expect(fy.derived.ebitda!.value).toBe(4_795_586_000_000 + 2_251_233_000_000);
  });
});

describe("rules on synthetic facts", () => {
  it("concept priority is resolved per period (Caterpillar-style)", () => {
    const cf = companyfacts({
      Revenues: [
        fact(100, "2009-01-01", "2009-12-31", "a-09", "2010-02-20", "10-K", 2009),
        fact(110, "2010-01-01", "2010-12-31", "a-10", "2011-02-20", "10-K", 2010),
        fact(120, "2011-01-01", "2011-12-31", "a-11", "2012-02-20", "10-K", 2011),
      ],
      NetIncomeLoss: [
        fact(9, "2009-01-01", "2009-12-31", "a-09", "2010-02-20", "10-K", 2009),
        fact(10, "2010-01-01", "2010-12-31", "a-10", "2011-02-20", "10-K", 2010),
      ],
      ProfitLoss: [
        fact(11, "2010-01-01", "2010-12-31", "a-11", "2012-02-20", "10-K", 2011),
        fact(12, "2011-01-01", "2011-12-31", "a-11", "2012-02-20", "10-K", 2011),
      ],
    });
    const ni = standardize(cf, 5, false).periods.map((p) => [p.values.net_income!.concept, p.values.net_income!.value]);
    expect(ni).toEqual([
      ["us-gaap:NetIncomeLoss", 9],
      ["us-gaap:NetIncomeLoss", 10],
      ["us-gaap:ProfitLoss", 12],
    ]);
  });

  it("OtherShortTermInvestments counts as short-term investments in net debt (Coca-Cola style)", () => {
    // KO FY2025: debt 45.436B, cash 10.270B, OtherShortTermInvestments 3.602B (found by the benchmark pilot).
    const cf = companyfacts({
      Revenues: [fact(47_000, "2025-01-01", "2025-12-31", "k-25", "2026-02-20", "10-K", 2025)],
      LongTermDebtNoncurrent: [fact(40_000, null, "2025-12-31", "k-25", "2026-02-20", "10-K", 2025)],
      DebtCurrent: [fact(5_436, null, "2025-12-31", "k-25", "2026-02-20", "10-K", 2025)],
      CashAndCashEquivalentsAtCarryingValue: [fact(10_270, null, "2025-12-31", "k-25", "2026-02-20", "10-K", 2025)],
      OtherShortTermInvestments: [fact(3_602, null, "2025-12-31", "k-25", "2026-02-20", "10-K", 2025)],
    });
    const p = standardize(cf, 5, false).periods[0]!;
    expect(p.balance_sheet.short_term_investments!.concept).toBe("us-gaap:OtherShortTermInvestments");
    expect(p.derived.net_debt!.value).toBe(45_436 - 10_270 - 3_602);
  });

  it("next-12-months maturity stands in for an untagged current portion (Caterpillar style)", () => {
    // CAT FY2025: short-term borrowings 5.514B + LT debt due within one year 7.120B (company extension on the
    // balance sheet; only the maturity schedule is in us-gaap) + LT debt due after one year 30.696B = 43.330B.
    const td = (inst: Record<string, number>) =>
      totalDebt(Object.fromEntries(Object.entries(inst).map(([k, v]) => [k, { value: v }])) as never);
    expect(td({ ltd_noncurrent: 30_696, short_term_borrowings: 5_514, ltd_due_12m: 7_120 })).toEqual([
      43_330,
      "ltd_noncurrent + ltd_due_12m + short_term_borrowings",
    ]);
    // A tagged current portion wins; the maturity figure is never added on top.
    expect(td({ ltd_noncurrent: 30_696, ltd_current: 7_000, ltd_due_12m: 7_120 })[0]).toBe(37_696);
    // LongTermDebt already includes its current portion: no maturity figure added.
    expect(td({ ltd_total: 37_816, ltd_due_12m: 7_120 })).toEqual([37_816, "ltd_total"]);
    // DebtCurrent already covers the current portion.
    expect(td({ ltd_noncurrent: 30_696, debt_current: 12_634, ltd_due_12m: 7_120 })[0]).toBe(43_330);
  });

  it("D&A tagged as depreciation alone gets intangible amortization added (Keurig Dr Pepper, Merck, Microsoft)", () => {
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "d-25", "2026-02-20", "10-K", 2025)];
    const base = { Revenues: y(16_603), OperatingIncomeLoss: y(3_575), AmortizationOfIntangibleAssets: y(138) };
    const split = standardize(companyfacts({ ...base, Depreciation: y(455) }), 5, false).periods[0]!;
    expect(split.values.d_and_a).toMatchObject({
      value: 455 + 138,
      concept: "us-gaap:Depreciation + us-gaap:AmortizationOfIntangibleAssets",
      formula: "depreciation + amortization of intangible assets (tagged separately)",
    });
    expect(split.derived.ebitda).toEqual({ value: 3_575 + 455 + 138, formula: "operating_income + d_and_a" });
    // A combined D&A concept already includes amortization: nothing added.
    const both = standardize(companyfacts({ ...base, DepreciationDepletionAndAmortization: y(593) }), 5, false).periods[0]!;
    expect(both.values.d_and_a!.value).toBe(593);
    expect(both.derived.ebitda).toEqual({ value: 3_575 + 593, formula: "operating_income + d_and_a" });
  });

  it("listed filers get operating income as revenue - costs and expenses (Disney tags its segment total)", () => {
    const y = (v: number) => [fact(v, "2022-10-02", "2023-09-30", "w-23", "2023-11-21", "10-K", 2023)];
    const facts = { Revenues: y(88_898), CostsAndExpenses: y(79_906), OperatingIncomeLoss: y(12_863), NetIncomeLoss: y(2_354) };
    const disney = { ...companyfacts(facts), cik: 1744489 };
    const oi = standardize(disney, 5, false).periods[0]!.values.operating_income!;
    expect(oi).toMatchObject({ value: 8_992, formula: "revenue - costs_and_expenses", concept: "us-gaap:Revenues - us-gaap:CostsAndExpenses" });
    expect(oi.note).toMatch(/segment operating income/);
    // Any other filer keeps its tagged operating income.
    expect(standardize(companyfacts(facts), 5, false).periods[0]!.values.operating_income!.value).toBe(12_863);
  });

  it("a share count off by a million is rescaled only when net income / EPS confirms it (McDonald's)", () => {
    const y = (v: number) => [fact(v, "2025-01-01", "2025-12-31", "m-25", "2026-02-20", "10-K", 2025)];
    const mcd = (shares: number, eps: number) => {
      const cf = companyfacts({ Revenues: y(26_885e6), NetIncomeLoss: y(8_560e6) });
      cf.facts["us-gaap"]!.EarningsPerShareDiluted = { units: { "USD/shares": y(eps) } };
      cf.facts["us-gaap"]!.WeightedAverageNumberOfDilutedSharesOutstanding = { units: { shares: y(shares) } };
      return standardize(cf, 5, false).periods[0]!.values.diluted_shares!;
    };
    const fixed = mcd(716.4, 11.95);
    expect(fixed.value).toBeCloseTo(716_400_000, 0);
    expect(fixed.note).toMatch(/filed as 716.4, a scale error/);
    expect(mcd(716_400_000, 11.95).value).toBe(716_400_000); // already right: untouched
    expect(mcd(716.4, 3.1).value).toBe(716.4); // EPS doesn't confirm: left as filed
  });

  it("capex falls back to PaymentsToAcquireOtherProductiveAssets when nothing else is tagged (Verizon)", () => {
    const y = (v: number) => [fact(v, "2024-01-01", "2024-12-31", "v-24", "2025-02-10", "10-K", 2024)];
    const vz = standardize({ ...companyfacts({ Revenues: y(134_788), PaymentsToAcquireOtherProductiveAssets: y(17_090) }), cik: 732712 }, 5, false);
    expect(vz.periods[0]!.values.capex).toMatchObject({ value: 17_090, concept: "us-gaap:PaymentsToAcquireOtherProductiveAssets" });
    // PP&E purchases win when tagged.
    const both = standardize({ ...companyfacts({ Revenues: y(1), PaymentsToAcquirePropertyPlantAndEquipment: y(100), PaymentsToAcquireOtherProductiveAssets: y(7) }), cik: 732712 }, 5, false);
    expect(both.periods[0]!.values.capex!.value).toBe(100);
  });

  it("restated value comes from the latest filing; label from the original", () => {
    const cf = companyfacts({
      Revenues: [
        fact(100, "2024-02-05", "2025-02-02", "orig", "2025-03-15", "10-K", 2024),
        fact(97, "2024-02-05", "2025-02-02", "restated", "2026-03-14", "10-K", 2025),
      ],
    });
    const p = standardize(cf, 5, false).periods[0]!;
    expect(p.label).toBe("FY2024"); // a retailer year ending Feb 2025 is fiscal 2024
    expect([p.values.revenue!.value, p.values.revenue!.accession]).toEqual([97, "restated"]);
  });

  it("LTM needs one concept across FY and both YTDs", () => {
    const cf = companyfacts({
      Revenues: [
        fact(400, "2025-01-01", "2025-12-31", "k", "2026-02-10", "10-K", 2025),
        fact(90, "2025-01-01", "2025-03-31", "q-prior", "2025-05-01", "10-Q"),
      ],
      SalesRevenueNet: [fact(110, "2026-01-01", "2026-03-31", "q", "2026-05-01", "10-Q")],
    });
    let ltm = standardize(cf).periods.at(-1)!;
    expect(ltm.type).toBe("ltm");
    expect(ltm.values.revenue).toBeNull();

    cf.facts["us-gaap"]!.Revenues!.units!.USD!.push(fact(110, "2026-01-01", "2026-03-31", "q", "2026-05-01", "10-Q"));
    ltm = standardize(cf).periods.at(-1)!;
    expect(ltm.values.revenue!.value).toBe(400 + 110 - 90);
  });

  it.each([
    [{ debt_current: 30, ltd_current: 10, commercial_paper: 20, ltd_noncurrent: 100 }, 130, "ltd_noncurrent + debt_current"],
    [{ ltd_total: 110, ltd_current: 10 }, 110, "(ltd_total - ltd_current) + ltd_current"],
    [{ short_term_borrowings: 5 }, 5, "short_term_borrowings (no long-term debt concept reported: likely incomplete)"],
    [{}, null, "no debt concepts reported"],
  ])("total debt never double counts %#", (inst, value, formula) => {
    const cells = Object.fromEntries(Object.entries(inst).map(([k, v]) => [k, { value: v }]));
    expect(totalDebt(cells)).toEqual([value, formula]);
  });

  it("multi-class cover page is summed", () => {
    const dei = {
      EntityCommonStockSharesOutstanding: {
        units: {
          shares: [
            { val: 300, end: "2026-07-20", accn: "x", filed: "2026-07-25", form: "10-Q" },
            { val: 50, end: "2026-07-20", accn: "x", filed: "2026-07-25", form: "10-Q" },
            { val: 340, end: "2026-04-20", accn: "w", filed: "2026-04-25", form: "10-Q" },
          ],
        },
      },
    };
    const s = sharesOutstanding(companyfacts({}, dei))!;
    expect([s.value, s.classes_summed, s.accession]).toEqual([350, 2, "x"]);
  });

  it("newest taxonomy wins for a filer with both (Sony-style)", () => {
    const cf = companyfacts({
      Revenues: [fact(100, "2019-04-01", "2020-03-31", "old", "2020-06-20", "20-F", 2020)],
    });
    cf.facts["ifrs-full"] = {
      Revenue: { units: { JPY: [fact(9000, "2024-04-01", "2025-03-31", "new", "2025-06-20", "20-F", 2025)] } },
    };
    let r = standardize(cf, 5, false);
    expect([r.taxonomy, r.currency]).toEqual(["ifrs-full", "JPY"]);
    expect(r.periods.at(-1)!.values.revenue!.value).toBe(9000);

    cf.facts["us-gaap"]!.Revenues!.units!.USD!.push(
      fact(120, "2025-04-01", "2026-03-31", "newer", "2026-06-20", "20-F", 2026),
    );
    r = standardize(cf, 5, false);
    expect(r.taxonomy).toBe("us-gaap");
  });

  it.each([
    [{ borrowings: 30, borrowings_noncurrent: 20, borrowings_current: 10 }, 30, "borrowings"],
    [{ borrowings_noncurrent: 20, borrowings_current: 10 }, 30, "borrowings_noncurrent + borrowings_current"],
    [{ borrowings_current: 10 }, 10, "borrowings_current (no non-current borrowings concept reported: likely incomplete)"],
    // Current debt tagged as its two components (no total): summed, never added on top of a total.
    [{ borrowings_noncurrent: 20, short_term_borrowings: 3, current_portion_of_longterm_borrowings: 4 }, 27, "borrowings_noncurrent + (short_term_borrowings + current_portion_of_longterm_borrowings)"],
    [{ borrowings_noncurrent: 20, borrowings_current: 7, short_term_borrowings: 3 }, 27, "borrowings_noncurrent + borrowings_current"],
    [{}, null, "no debt concepts reported"],
  ])("IFRS debt never double counts %#", (inst, value, formula) => {
    const cells = Object.fromEntries(Object.entries(inst).map(([k, v]) => [k, { value: v }]));
    expect(ifrsTotalDebt(cells)).toEqual([value, formula]);
  });
});
