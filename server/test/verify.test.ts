// verify_value on real filings with planted errors (brief M2: catches planted errors in 20 fixture cases).

import { describe, expect, it } from "vitest";
import { SNAPSHOT_YEARS } from "../src/config";
import { standardize } from "../src/sec/xbrl";
import { resolveMetric, resolvePeriod, summarize, verifyItems, type VerifyItem } from "../src/verify";
import { tteRecord } from "./esef-fixture";
import { facts } from "./helpers";

const aapl = standardize(facts("AAPL"), SNAPSHOT_YEARS, true);
const jpm = standardize(facts("JPM"), SNAPSHOT_YEARS, true);
const tte = tteRecord().financials!;
const one = (std = aapl, item: VerifyItem) => verifyItems(std, [item])[0]!;
const fy24 = aapl.periods.find((p) => p.label === "FY2024")!;
const REV24 = fy24.values.revenue!.value; // 391,035,000,000
const NI24 = fy24.values.net_income!.value;

describe("verify_value: correct numbers match", () => {
  it.each([
    ["revenue in billions, rounded", { metric: "revenue", period: "FY2024", value: 391.035, scale: "billions" as const }],
    ["revenue in millions, by alias", { metric: "Net sales", period: "FY2024", value: 391035, scale: "millions" as const }],
    ["revenue in units, by period end", { metric: "sales", period: "2024-09-28", value: REV24 }],
    ["net income, 2-digit year", { metric: "net income", period: "FY24", value: NI24 / 1e6, scale: "millions" as const }],
    ["total debt (computed)", { metric: "total debt", period: "FY2024", value: 106_629, scale: "millions" as const }],
  ])("%s", (_name, item) => {
    const r = one(aapl, item);
    expect(r.status).toBe("match");
    expect(r.accessions.length + (r.computed ? 1 : 0)).toBeGreaterThan(0);
  });

  it("computed lines say so and show their formula", () => {
    const r = one(aapl, { metric: "total debt", period: "FY2024", value: 106_629, scale: "millions" });
    expect(r.computed).toBe(true);
    expect(r.hints.join(" ")).toMatch(/ltd_noncurrent \+ ltd_current \+ commercial_paper/);
  });

  it("EPS within rounding to 2 decimals", () => {
    const eps = fy24.values.diluted_eps!.value;
    expect(one(aapl, { metric: "EPS", period: "FY2024", value: Math.round(eps * 100) / 100 }).status).toBe("match");
  });
});

describe("verify_value: planted errors are caught, with the right hint", () => {
  it("scale: millions written as thousands", () => {
    const r = one(aapl, { metric: "revenue", period: "FY2024", value: 391035, scale: "thousands" });
    expect(r.status).toBe("mismatch");
    expect(r.hints.join(" ")).toMatch(/Scale: the value matches if it is in millions/);
  });

  it("scale: no unit given for a figure in billions", () => {
    const r = one(aapl, { metric: "revenue", period: "FY2024", value: 391.035 });
    expect(r.status).toBe("mismatch");
    expect(r.hints.join(" ")).toMatch(/in billions/);
  });

  it("sign: capex entered as a negative number", () => {
    const capex = fy24.values.capex!.value;
    const r = one(aapl, { metric: "capex", period: "FY2024", value: -capex });
    expect(r.status).toBe("mismatch");
    expect(r.hints.join(" ")).toMatch(/^.*Sign: the value has the opposite sign/);
  });

  it("period: last year's revenue used for this year", () => {
    const fy23 = aapl.periods.find((p) => p.label === "FY2023")!;
    const r = one(aapl, { metric: "revenue", period: "FY2024", value: fy23.values.revenue!.value });
    expect(r.status).toBe("mismatch");
    expect(r.hints.join(" ")).toMatch(/Period: the value matches revenue for FY2023/);
  });

  it("line item: gross profit typed into the revenue row", () => {
    const r = one(aapl, { metric: "revenue", period: "FY2024", value: fy24.values.gross_profit!.value });
    expect(r.status).toBe("mismatch");
    expect(r.hints.join(" ")).toMatch(/Line item: the value matches gross_profit/);
  });

  it("line item: operating income used as net income", () => {
    const r = one(aapl, { metric: "net income", period: "FY2024", value: fy24.values.operating_income!.value });
    expect(r.hints.join(" ")).toMatch(/matches operating_income/);
  });

  it("a typo (transposed digits) is a plain mismatch with the difference", () => {
    const r = one(aapl, { metric: "revenue", period: "FY2024", value: 390.135, scale: "billions" });
    expect(r.status).toBe("mismatch");
    expect(r.difference).toBeCloseTo(390.135e9 - REV24, -3);
    expect(r.hints).toEqual([]);
  });

  it("rounding-aware: 391 and 391.04 (billions) are fair roundings of 391.035; 391.05 is not", () => {
    expect(one(aapl, { metric: "revenue", period: "FY2024", value: 391, scale: "billions" }).status).toBe("match");
    expect(one(aapl, { metric: "revenue", period: "FY2024", value: 391000, scale: "millions" }).status).toBe("match");
    expect(one(aapl, { metric: "revenue", period: "FY2024", value: 391.04, scale: "billions" }).status).toBe("match");
    expect(one(aapl, { metric: "revenue", period: "FY2024", value: 391.05, scale: "billions" }).status).toBe("mismatch");
  });

  it("an off-by-1% number fails the default tolerance but passes a looser one", () => {
    const v = (REV24 * 1.01) / 1e9;
    expect(one(aapl, { metric: "revenue", period: "FY2024", value: v, scale: "billions" }).status).toBe("mismatch");
    expect(one(aapl, { metric: "revenue", period: "FY2024", value: v, scale: "billions", tolerance: 0.02 }).status).toBe("match");
  });

  it("currency: euros claimed for a USD reporter", () => {
    const r = one(aapl, { metric: "revenue", period: "FY2024", value: 391.035, scale: "billions", currency: "EUR" });
    expect(r.status).toBe("mismatch");
    expect(r.hints.join(" ")).toMatch(/Currency/);
  });

  it("not reported: a bank has no operating income, so nothing to match (null, never 0)", () => {
    const r = one(jpm, { metric: "EBITDA", period: "latest", value: 50, scale: "billions" });
    expect(r.status).toBe("not_found");
    expect(r.hints.join(" ")).toMatch(/not reported/);
  });

  it("unknown line item and unknown period explain what is available", () => {
    expect(one(aapl, { metric: "vibes", period: "FY2024", value: 1 }).hints[0]).toMatch(/Unknown line item/);
    expect(one(aapl, { metric: "revenue", period: "FY1999", value: 1 }).hints[0]).toMatch(/No period/);
  });

  it("IFRS issuer (TotalEnergies, USD): a figure in EUR is flagged; the right one matches", () => {
    expect(one(tte, { metric: "revenue", period: "FY2025", value: 201.196, scale: "billions" }).status).toBe("match");
    expect(one(tte, { metric: "revenue", period: "FY2025", value: 201.196, scale: "billions", currency: "EUR" }).status).toBe("mismatch");
  });

  it("IFRS: company-specific capex is not reported, so it can't be 'verified' by a guess", () => {
    expect(one(tte, { metric: "capex", period: "FY2025", value: 16.953, scale: "billions" }).status).toBe("not_found");
  });
});

describe("verify_value: periods and batches", () => {
  it("LTM, latest and 52/53-week period ends resolve", () => {
    expect(resolvePeriod(aapl, "LTM")).toHaveLength(1);
    expect(resolvePeriod(aapl, "latest")[0]!.label).toBe(aapl.periods.filter((p) => p.type === "annual").at(-1)!.label);
    // Apple's FY2024 ended 2024-09-28; "2024-09-30" (a calendar month end) is within a week.
    expect(resolvePeriod(aapl, "2024-09-30")[0]!.label).toBe("FY2024");
  });

  it("a bare year that can mean two fiscal years is ambiguous, never guessed", () => {
    const std = structuredClone(aapl);
    // Make FY2025 end in calendar 2024 is impossible; instead model a retailer: FY2024 ends 2025-02-01, FY2023 ends 2024-02-03.
    std.periods = [
      { ...std.periods[0]!, label: "FY2023", start: "2023-01-29", end: "2024-02-03", type: "annual" },
      { ...std.periods[1]!, label: "FY2024", start: "2024-02-04", end: "2025-02-01", type: "annual" },
    ];
    const r = one(std, { metric: "revenue", period: "2024", value: 1 });
    expect(r.status).toBe("ambiguous");
    expect(r.hints[0]).toMatch(/FY2024 .* or FY2023/);
    expect(resolvePeriod(std, "FY2024")).toHaveLength(1);
  });

  it("a batch reports every item and the counts", () => {
    const results = verifyItems(aapl, [
      { metric: "revenue", period: "FY2024", value: 391.035, scale: "billions", ref: "Inputs!C5" },
      { metric: "revenue", period: "FY2024", value: 391035, scale: "thousands", ref: "Inputs!C6" },
      { metric: "capex", period: "LTM", value: 1, ref: "Inputs!C7" },
      { metric: "vibes", period: "FY2024", value: 1, ref: "Inputs!C8" },
    ]);
    expect(results.map((r) => r.ref)).toEqual(["Inputs!C5", "Inputs!C6", "Inputs!C7", "Inputs!C8"]);
    expect(summarize(results)).toEqual({ total: 4, match: 1, mismatch: 2, not_found: 1, ambiguous: 0 });
  });

  it("aliases cover the common names", () => {
    expect(["sales", "EBIT", "D&A", "CFO", "FCF", "net debt", "Chiffre d'affaires"].map(resolveMetric)).toEqual([
      "revenue",
      "operating_income",
      "d_and_a",
      "operating_cash_flow",
      "free_cash_flow",
      "net_debt",
      "revenue",
    ]);
  });
});
