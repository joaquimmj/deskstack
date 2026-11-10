// The golden set (evals/golden.json) against recorded fixtures, through the real MCP tools.
// Brief M7: accuracy ≥ 95% — on the live connector. On recorded fixtures the answers can't drift, so every question
// must pass unless it is listed in KNOWN_MISSES with the reason. Every miss is printed with what came back.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { buildEuRecord } from "../src/esef/record";
import { resetCounter } from "../src/guard";
import { resetMemos } from "../src/repo";
import { badge, runGolden, score, type GoldenQuestion } from "../scripts/golden-lib";
import { ITX, TTE, esefFixture, meta, tteRecord } from "./esef-fixture";
import { secFetch } from "./helpers";
import { baseEnv, call, fixtureAssets } from "./mcp-harness";

const golden = JSON.parse(readFileSync(join(import.meta.dirname, "..", "..", "evals", "golden.json"), "utf8")) as { questions: GoldenQuestion[] };
const KNOWN_MISSES: Record<string, string> = {};
const SEC = ["AAPL", "MSFT", "GOOGL", "KO", "CAT", "JPM", "SAP", "TM", "UL"];

// Stars brief lot 2 bis: one issuer per further country, from recorded reports (test/fixtures/esef/issuers.json).
type FixtureIssuer = { lei: string; name: string; country: string; currency: string; fye: string; filings: { id: string; published: string }[] };
const MORE_EU = (JSON.parse(readFileSync(join(import.meta.dirname, "fixtures", "esef", "issuers.json"), "utf8")) as { issuers: FixtureIssuer[] }).issuers;
const moreEu = () => MORE_EU.map((i) => ({
  lei: i.lei, name: i.name, country: i.country, currency: i.currency, fye: i.fye,
  record: buildEuRecord({ lei: i.lei, name: i.name, country: i.country }, i.filings.map((f) => ({ meta: meta(f.id, f.published), data: esefFixture(f.id) }))),
}));

const itxRecord = () =>
  buildEuRecord(ITX, [
    { meta: meta("549300TTCXZOGZM2EY83-2025-01-31-ESEF-ES-0", "2025-04-30"), data: esefFixture("549300TTCXZOGZM2EY83-2025-01-31-ESEF-ES-0") },
    { meta: meta("549300TTCXZOGZM2EY83-2026-01-31-ESEF-ES-0", "2026-04-29"), data: esefFixture("549300TTCXZOGZM2EY83-2026-01-31-ESEF-ES-0") },
  ]);

beforeEach(() => {
  resetMemos();
  resetCounter();
  vi.stubGlobal("fetch", secFetch([]));
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-08T12:00:00Z") });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("golden set (recorded fixtures)", () => {
  it("has at least 60 questions with unique ids", () => {
    const ids = golden.questions.map((q) => q.id);
    expect(ids.length).toBeGreaterThanOrEqual(60);
    expect(new Set(ids).size).toBe(ids.length);
  });

  const env = () => baseEnv({
      ASSETS: fixtureAssets(SEC, [
        { lei: TTE.lei, name: TTE.name, country: "FR", currency: "USD", fye: "1231", record: tteRecord() },
        { lei: ITX.lei, name: ITX.name, country: "ES", currency: "EUR", fye: "0131", record: itxRecord() },
        ...moreEu(),
      ]),
      DAILY_CAP: "100000",
      PER_IP_PER_MINUTE: "100000",
    });

  it("answers every question exactly as filed (known misses listed with a reason)", { timeout: 60_000 }, async () => {
    const e = env();
    const results = await runGolden(golden.questions, (tool, args) => call(e, tool, args));
    const s = score(results);
    const misses = results.filter((r) => !r.pass).map((r) => `${r.id}: expected ${JSON.stringify(r.expected)}, got ${JSON.stringify(r.got)}${r.error ? ` (${r.error})` : ""}`);
    console.log(`golden: ${badge(s).message}${misses.length ? "\n  " + misses.join("\n  ") : ""}`);
    const unexpected = results.filter((r) => !r.pass && !(r.id in KNOWN_MISSES));
    expect(unexpected.map((r) => r.id), misses.join("\n")).toEqual([]);
    expect(s.accuracy).toBeGreaterThanOrEqual(0.95);
  });

  it("is not vacuous: a wrong expected value, a wrong period or a wrong null each count as a miss", async () => {
    const e = env();
    const pick = (id: string) => structuredClone(golden.questions.find((q) => q.id === id)!);
    const off = pick("aapl-fy2025-revenue");
    off.expected = (off.expected as number) + 1_000_000; // off by one million dollars
    const period = pick("msft-fy2026-net-income");
    (period.read as { period: string }).period = "FY2019";
    const notNull = pick("jpm-fy2025-net-income");
    notNull.expected = null;
    const eps = pick("aapl-fy2025-diluted-eps");
    eps.expected = (eps.expected as number) + 0.01; // one cent
    const results = await runGolden([off, period, notNull, eps], (tool, args) => call(e, tool, args));
    expect(results.map((r) => r.pass)).toEqual([false, false, false, false]);
    expect(results[1]!.error).toMatch(/no period FY2019/);
  });

  it("a renamed field, a missing group or a wrong citation is a miss, not a null", async () => {
    const { read } = await import("../scripts/golden-lib");
    const q = structuredClone(golden.questions.find((x) => x.id === "jpm-no-capex")!);
    const period = (extra: object) => ({ periods: [{ label: "FY2025", end: "2025-12-31", ...extra }] });
    expect(() => read(q, period({ cash_flow: { capex_renamed: null } }))).toThrow(/no capex/);
    expect(() => read(q, period({}))).toThrow(/no cash_flow/);
    expect(read(q, period({ cash_flow: { capex: null } }))).toBeNull();
    const ltm = golden.questions.find((x) => x.id === "sap-no-ltm")!;
    expect(() => read(ltm, { error: "boom" })).toThrow(/no periods/);
    const rev = structuredClone(golden.questions.find((x) => x.id === "aapl-fy2025-revenue")!);
    const cell = { value: rev.expected, accession: "0000320193-99-999999" };
    expect(() => read(rev, { periods: [{ label: "FY2025", end: "2025-09-27", income_statement: { revenue: cell } }] })).toThrow(/cites/);
    expect(() => read(rev, { periods: [{ label: "FY2025", end: "2025-09-28", income_statement: { revenue: cell } }] })).toThrow(/ends/);
  });
});
