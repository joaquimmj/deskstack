// deskstack-bench offline: a scripted model and the real Worker (fixtures) behind the connector. Nothing is sent to
// the API. Checks the loop, the budget cap, the arm C review round, cost accounting and scoring.

import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { runOne, type MessagesClient } from "../bench/agent";
import type { Connector } from "../bench/connector";
import { Budget, cost } from "../bench/pricing";
import { summarize, toMarkdown, type ScoredRun } from "../bench/report";
import { findInFiling, esefFactsFor, secFactsFor, tolerance } from "../bench/filing-facts";
import { resolvePeer, sameName, scoreSubmission, secondReading } from "../bench/score";
import { resetCounter } from "../src/guard";
import { resetMemos } from "../src/repo";
import { secFetch } from "./helpers";
import { baseEnv, call, connect, fixtureAssets } from "./mcp-harness";

const ROOT = join(import.meta.dirname, "..", "..");
const DCF = { kind: "dcf", ...JSON.parse(readFileSync(join(ROOT, "checker", "tests", "specs", "aapl_dcf.json"), "utf8")) };
const COMPS = { kind: "comps", ...JSON.parse(readFileSync(join(ROOT, "checker", "tests", "specs", "peers_comps.json"), "utf8")) };
const AAPL = { id: "AAPL", name: "Apple Inc." };

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

function connector(): Connector {
  const env = baseEnv({ ASSETS: fixtureAssets(["AAPL"]), DAILY_CAP: "100000", PER_IP_PER_MINUTE: "100000" });
  return {
    async instructions() {
      const c = await connect(env);
      const i = c.getInstructions?.() ?? "";
      await c.close();
      return i;
    },
    async listTools() {
      const c = await connect(env);
      const { tools } = await c.listTools();
      await c.close();
      return tools.map((t) => ({ name: t.name, description: t.description, inputSchema: t.inputSchema as Record<string, unknown> }));
    },
    async call(name, args) {
      const r = await call(env, name, args);
      return { isError: r.isError, text: r.text };
    },
    async close() {},
  };
}

type Step = { tool?: string; input?: unknown; text?: string; stop?: string };
/** A scripted model: each request returns the next step; records what it was sent. */
function fakeClient(steps: Step[]) {
  const sent: any[] = [];
  let i = 0;
  const client: MessagesClient = {
    messages: {
      async create(params) {
        sent.push(structuredClone(params));
        const s = steps[Math.min(i++, steps.length - 1)]!;
        const content: any[] = [{ type: "thinking", thinking: "", signature: "sig" }];
        if (s.text) content.push({ type: "text", text: s.text });
        if (s.tool) content.push({ type: "tool_use", id: `tu_${i}`, name: s.tool, input: s.input ?? {} });
        return {
          id: `msg_${i}`, type: "message", role: "assistant", model: params.model, content,
          stop_reason: s.stop ?? (s.tool ? "tool_use" : "end_turn"), stop_sequence: null,
          usage: { input_tokens: 1000, output_tokens: 500, cache_creation_input_tokens: 2000, cache_read_input_tokens: 10000, server_tool_use: { web_search_requests: s.tool ? 0 : 1 } },
        } as any;
      },
    },
  };
  return { client, sent };
}

const opts = (o: Partial<Parameters<typeof runOne>[0]> & { client: MessagesClient }) => ({
  connector: connector(), budget: new Budget(20), model: "claude-sonnet-5-5", effort: "medium" as const, company: AAPL, task: "dcf" as const,
  arm: "B" as const, workdir: mkdtempSync(join(tmpdir(), "bench-")), ...o,
});

// These tests run the Python checker (review and scoring), several seconds each on a loaded machine: past the
// 5 s default (review 2026-11-10: arm B, arm C and "mismatches carry their cause" timed out under load).
describe("deskstack-bench (offline)", { timeout: 60_000 }, () => {
  it("prices a request from its usage", () => {
    // 1000 in × $2 + 500 out × $10 + 2000 write × $2.5 + 10000 read × $0.2, per million; + 1 search × $0.01
    expect(cost("claude-sonnet-5-5", { input_tokens: 1000, output_tokens: 500, cache_creation_input_tokens: 2000, cache_read_input_tokens: 10000, server_tool_use: { web_search_requests: 1 } })).toBeCloseTo(0.002 + 0.005 + 0.005 + 0.002 + 0.01, 9);
    expect(() => cost("gpt-x", { input_tokens: 1, output_tokens: 1 })).toThrow(/No price/);
  });

  it("arm B: tool calls go to the connector, the accepted model is scored against the filings", async () => {
    const { client, sent } = fakeClient([{ tool: "financial_statements", input: { ticker: "AAPL", years: 3 } }, { tool: "submit_model", input: DCF }]);
    const o = opts({ client });
    const r = await runOne(o);
    expect(r.status).toBe("submitted");
    expect(r.tool_calls).toEqual({ financial_statements: 1, submit_model: 1 });
    expect(sent[0].tools.map((t: any) => t.name)).toContain("verify_value");
    expect(sent[0].tools.map((t: any) => t.name)).not.toContain("web_search");
    expect(sent[0].cache_control).toEqual({ type: "ephemeral" });
    expect(sent[0].output_config).toEqual({ effort: "medium" });
    // The connector's answer went back to the model as a tool result.
    expect(JSON.stringify(sent[1].messages.at(-1))).toContain("tool_result");
    expect(r.cost).toBeCloseTo(2 * 0.014, 9);
    const s = await scoreSubmission(o.connector, r.submission, AAPL, join(o.workdir, "final"));
    expect(s).toMatchObject({ valid: true, filed: 14, match: 14, mismatch: 0, unsourced: 0 });
    expect(s.checker).toEqual({ blocker: 0, major: 0, minor: 0 });
  });

  it("arm A: only web_search and submit_model; a turn without a tool call is nudged", async () => {
    const { client, sent } = fakeClient([{ text: "Searching done." }, { tool: "submit_model", input: DCF }]);
    const r = await runOne(opts({ client, arm: "A" }));
    expect(r.status).toBe("submitted");
    expect(sent[0].tools.map((t: any) => t.name)).toEqual(["web_search", "submit_model"]);
    expect(sent[0].tools[0]).toMatchObject({ type: "web_search_20260209", max_uses: 12 });
    expect(JSON.stringify(sent[1].messages.at(-1))).toContain("Call submit_model now");
    expect(r.usage.server_tool_use?.web_search_requests).toBe(1);
  });

  it("a rejected submission comes back with the builder's error, then a fixed one is accepted", async () => {
    const bad = structuredClone(DCF);
    bad.assumptions.wacc.value = 9; // percent typed as a whole number
    const { client, sent } = fakeClient([{ tool: "submit_model", input: bad }, { tool: "submit_model", input: DCF }]);
    const r = await runOne(opts({ client }));
    expect(r.status).toBe("submitted");
    expect(r.submit_attempts).toBe(2);
    expect(JSON.stringify(sent[1].messages.at(-1))).toMatch(/Not accepted: .*Rates are decimals/);
  });

  it("arm C: the review shows the tie-out mismatch, the fix is resubmitted and scores clean", async () => {
    const planted = structuredClone(DCF);
    planted.history.lines.revenue.values[2] = 416161000; // thousands typed into a model in millions
    const { client, sent } = fakeClient([{ tool: "submit_model", input: planted }, { tool: "submit_model", input: DCF }]);
    const o = opts({ client, arm: "C" });
    const r = await runOne(o);
    expect(r.status).toBe("submitted");
    expect(r.review).toMatch(/13 of 14 filed figures match/);
    expect(r.review).toMatch(/history\.revenue\[FY2025\].*mismatch.*Scale/);
    expect(JSON.stringify(sent[1].messages.at(-1))).toContain("Independent review of your model");
    const first = await scoreSubmission(o.connector, r.first_submission, AAPL, join(o.workdir, "first"));
    const final = await scoreSubmission(o.connector, r.submission, AAPL, join(o.workdir, "final"));
    expect([first.mismatch, final.mismatch]).toEqual([1, 0]);
  });

  it("stops before a request that could cross the budget, and caps a runaway run", async () => {
    const { client, sent } = fakeClient([{ tool: "financial_statements", input: { ticker: "AAPL" } }]);
    const r = await runOne(opts({ client, budget: new Budget(0.1) })); // one request could cost ~$0.17 (16K output tokens)
    expect(r.status).toBe("budget");
    expect(sent.length).toBe(0);
    const loop = fakeClient([{ tool: "company_lookup", input: { query: "apple" } }]);
    const r2 = await runOne(opts({ client: loop.client, maxRequests: 3 }));
    expect(r2.status).toBe("run_cap");
    expect(loop.sent.length).toBe(3);
  });

  it("scores comps: the target ties out, a peer outside coverage is not verifiable, market caps aren't scored", async () => {
    const s = await scoreSubmission(connector(), COMPS, AAPL, mkdtempSync(join(tmpdir(), "bench-")));
    const aapl = s.items.filter((x) => x.company === "AAPL");
    expect(aapl.map((x) => x.status)).toEqual(["match", "match", "match", "match"]);
    expect(s.items.filter((x) => x.company !== "AAPL").every((x) => x.status === "unverifiable")).toBe(true);
    expect(s.items.some((x) => x.metric === "market_cap")).toBe(false);
    expect(s.typed).toBe(20);
  });

  it("the budget is a hard cap: many cheap requests then an expensive one never cross it", async () => {
    const budget = new Budget(1.0);
    const { client } = fakeClient([{ tool: "company_lookup", input: { query: "apple" } }]);
    const stub: Connector = { instructions: async () => "", listTools: async () => [], call: async () => ({ isError: false, text: "{}" }), close: async () => {} };
    const r = await runOne(opts({ client, budget, connector: stub, maxRequests: 200, maxRunCost: 100 }));
    expect(r.status).toBe("budget");
    expect(budget.spent).toBeLessThanOrEqual(1.0);
  });

  it("the ledger carries spend across processes", async () => {
    let stored = 0;
    const ledger = { read: () => stored, write: (t: number) => { stored = t; } };
    const { client } = fakeClient([{ tool: "submit_model", input: DCF }]);
    await runOne(opts({ client, budget: new Budget(20, ledger) }));
    expect(stored).toBeCloseTo(0.014, 9);
    expect(new Budget(20, ledger).spent).toBeCloseTo(0.014, 9); // a re-run starts from what was spent
  });

  it("a submit_model cut off by max_tokens is never run; a wrong kind is rejected", async () => {
    const partial = { ...COMPS, peers: COMPS.peers.slice(0, 2) };
    const { client, sent } = fakeClient([{ tool: "submit_model", input: partial, stop: "max_tokens" }, { tool: "submit_model", input: COMPS }, { tool: "submit_model", input: DCF }]);
    const r = await runOne(opts({ client, task: "dcf" }));
    expect(JSON.stringify(sent[1].messages.at(-1))).toContain("cut off by the length limit");
    expect(JSON.stringify(sent[2].messages.at(-1))).toContain('needs kind \\"dcf\\"');
    expect(r.status).toBe("submitted");
    expect((r.submission as { kind: string }).kind).toBe("dcf");
  });

  it("a connector exception is a tool error for the model, not the end of the run", async () => {
    const c = connector();
    const broken: Connector = { ...c, call: async (n, a) => (n === "financial_statements" ? Promise.reject(new Error("socket hang up")) : c.call(n, a)) };
    const { client, sent } = fakeClient([{ tool: "financial_statements", input: { ticker: "AAPL" } }, { tool: "submit_model", input: DCF }]);
    const r = await runOne(opts({ client, connector: broken }));
    expect(r.status).toBe("submitted");
    expect(JSON.stringify(sent[1].messages.at(-1))).toContain("Tool error: socket hang up");
  });

  it("arm B and C get the server's MCP instructions in the system prompt; arm A doesn't", async () => {
    const b = fakeClient([{ tool: "submit_model", input: DCF }]);
    await runOne(opts({ client: b.client }));
    expect(b.sent[0].system).toContain("Instructions from the deskstack data server");
    const a = fakeClient([{ tool: "submit_model", input: DCF }]);
    await runOne(opts({ client: a.client, arm: "A" }));
    expect(a.sent[0].system).not.toContain("deskstack data server");
  });

  it("the transcript records what was sent back to the model, not only its replies", async () => {
    const { client } = fakeClient([{ tool: "financial_statements", input: { ticker: "AAPL", years: 3 } }, { tool: "submit_model", input: DCF }]);
    const r = await runOne(opts({ client }));
    const roles = (r.transcript as Array<{ role: string }>).map((t) => t.role);
    expect(roles).toEqual(["user", "assistant", "user", "assistant"]);
  });

  it("peers: a ticker that collides with another company, or a numeric local code, is never scored against it", async () => {
    const spec = structuredClone(COMPS);
    spec.peers = [COMPS.peers[0], { ...COMPS.peers[1], name: "LVMH Moet Hennessy", ticker: "MC" }, { ...COMPS.peers[2], name: "Toyota Industries", ticker: "6201.T" }];
    const s = await scoreSubmission(connector(), spec, AAPL, mkdtempSync(join(tmpdir(), "bench-")));
    const peers = s.items.filter((x) => x.company !== "AAPL");
    expect(peers.every((x) => x.status === "unverifiable")).toBe(true);
    expect(s.mismatch).toBe(0);
  });

  it("the target is found by name when the model writes a local ticker", async () => {
    const spec = structuredClone(COMPS);
    spec.target = "AAPL.O";
    spec.peers[0] = { ...spec.peers[0], ticker: "AAPL.O", name: "Apple Inc." };
    const s = await scoreSubmission(connector(), spec, AAPL, mkdtempSync(join(tmpdir(), "bench-")));
    expect(s.items.filter((x) => x.company === "AAPL").map((x) => x.status)).toEqual(["match", "match", "match", "match"]);
  });

  it("a peer whose name only starts like the target's is not the target (comps run: CCEP scored as KO)", async () => {
    expect(sameName("Coca-Cola Europacific Partners plc", "COCA COLA CO")).toBe(false);
    expect(sameName("LVMH", "LVMH MOET HENNESSY LOUIS VUITTON")).toBe(true);
    expect(sameName("Apple", "Apple Inc.")).toBe(true);
    expect(sameName("Industria de Diseño Textil (Inditex) [target]", "Industria de Diseno Textil")).toBe(true); // asides are dropped
    expect(sameName("Coca-Cola Co - target", "COCA COLA CO")).toBe(true);
    expect(sameName("Apple Inc. (target)", "Apple Inc.")).toBe(true);
    const spec = structuredClone(COMPS);
    spec.peers = [COMPS.peers[0], { ...COMPS.peers[1], name: "Apple Hospitality REIT", ticker: "APLE" }];
    const s = await scoreSubmission(connector(), spec, AAPL, mkdtempSync(join(tmpdir(), "bench-")));
    expect(s.items.filter((x) => x.ref.startsWith("peers[APLE]")).every((x) => x.company !== "AAPL")).toBe(true);
  });

  it("a peer resolves to the hit with its ticker or its exact name, not a longer name that contains it (comps run: KO scored as Coca-Cola Consolidated)", async () => {
    const hits = [
      { name: "Coca-Cola Consolidated, Inc.", ticker: "COKE", cik: 317540 },
      { name: "COCA COLA CO", ticker: "KO", cik: 21344 },
    ];
    const fake = (results: unknown[]): Connector => ({
      instructions: async () => "", listTools: async () => [], close: async () => {},
      call: async () => ({ isError: false, text: JSON.stringify({ results }) }),
    } as unknown as Connector);
    expect(await resolvePeer(fake(hits), "Coca-Cola Co", "KO", new Map(), {})).toBe("KO");
    expect(await resolvePeer(fake(hits), "Coca-Cola Co", "", new Map(), {})).toBe("KO"); // exact name, no ticker
    // Only longer names that contain it, more than one: ambiguous, not resolved.
    expect(await resolvePeer(fake([hits[0], { name: "Coca-Cola Europacific Partners", ticker: "CCEP" }]), "Coca-Cola", "", new Map(), {})).toBeNull();
    // A single longer name is still found ("LVMH" is LVMH Moet Hennessy Louis Vuitton).
    expect(await resolvePeer(fake([{ name: "LVMH MOET HENNESSY LOUIS VUITTON", ticker: "MC.PA" }]), "LVMH", "", new Map(), {})).toBe("MC.PA");
  });

  it("items are normalised like the builder, and one bad item doesn't sink the batch", async () => {
    const spec = structuredClone(DCF);
    spec.history.periods = ["2023", "2024", "2025"];
    spec.bridge.net_debt.period = "FY2025 (as of 2025-09-27, from the balance sheet)";
    spec.currency = "USD m";
    const s = await scoreSubmission(connector(), spec, AAPL, mkdtempSync(join(tmpdir(), "bench-")));
    expect(s.match).toBe(14);
    expect(s.items.find((x) => x.ref === "bridge.net_debt")!.period).toBe("FY2025");
  });

  it("mismatches carry their cause", async () => {
    const spec = structuredClone(DCF);
    spec.history.lines.capex.values = spec.history.lines.capex.values.map((v: number) => -v);
    spec.history.lines.revenue.values[2] = 416161000;
    const s = await scoreSubmission(connector(), spec, AAPL, mkdtempSync(join(tmpdir(), "bench-")));
    expect(s.causes).toEqual({ sign: 3, scale: 1 });
  });

  it("weak sources are caught, short real ones aren't", async () => {
    const { itemsOf } = await import("../bench/score");
    const spec = structuredClone(DCF);
    spec.history.lines.revenue.source = "10-K";
    spec.history.lines.capex.source = "Not available";
    spec.assumptions.wacc.source = "Approximately, from my knowledge";
    const s = await scoreSubmission(connector(), spec, AAPL, mkdtempSync(join(tmpdir(), "bench-")));
    expect(s.unsourced_refs.sort()).toEqual(["assumptions.wacc", "history.capex[FY2023]", "history.capex[FY2024]", "history.capex[FY2025]"]);
    expect(itemsOf(spec, AAPL).typed.length).toBe(25);
  });

  it("the report compares arms on paired company-tasks only", async () => {
    const mk = (arm: "A" | "B" | "C", mismatch: number, company = "AAPL"): ScoredRun => ({
      company, task: "dcf", arm,
      run: { status: "submitted", submission: {}, first_submission: {}, submit_attempts: 1, requests: 3, usage: { input_tokens: 10, output_tokens: 5 }, cost: 0.5, seconds: 10, tool_calls: {} },
      score: { valid: true, filed: 14, match: 14 - mismatch, mismatch, not_found: 0, ambiguous: 0, unverifiable: 0, causes: { scale: mismatch }, errors: [], typed: 25, unsourced: arm === "A" ? 5 : 0, checker: { blocker: 0, major: 1, minor: 0 }, items: [], unsourced_refs: [] },
    });
    const crashed = { ...mk("B", 0, "CAT"), run: { ...mk("B", 0, "CAT").run, status: "error" as const } };
    const runs = [mk("A", 4), mk("B", 0), mk("C", 0), mk("A", 7, "KO"), mk("A", 1, "CAT"), crashed, mk("C", 0, "CAT")]; // KO: only A; CAT: B crashed
    const s = summarize(runs, ["A", "B", "C"]);
    expect(s.paired).toBe(1);
    expect(s.arms[1]!.errored).toBe(1);
    expect(s.arms.map((a) => [a.arm, a.mismatch, a.checked])).toEqual([["A", 4, 14], ["B", 0, 14], ["C", 0, 14]]);
    expect(s.arms[0]!.wrong_pct).toBeCloseTo(4 / 14);
    expect(toMarkdown(s, { model: "m", effort: "medium", prompts_version: "1", set: "pilot", started: "t" })).toMatch(/\| A: web search only \| 1 \(1\) \| 14 \| 28\.6% \(4\)/);
  });
});

describe("second reading of mismatches (pilot 2026-11-08)", { timeout: 60_000 }, () => {
  it("tolerance is half a unit of the last digit written, at the submitted scale", () => {
    expect(tolerance(218_945, 1e6)).toBe(0.5e6);
    expect(tolerance(2_447.754, 1e6)).toBeCloseTo(500, 6);
    expect(tolerance(15_004.697, 1e6)).toBeCloseTo(500, 6);
  });

  it("finds one line, or two added together, and nothing looser", () => {
    const facts = [
      { concept: "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", value: 2_821e6 },
      { concept: "us-gaap:PaymentsToAcquireEquipmentOnLease", value: 1_465e6 },
      { concept: "us-gaap:Revenues", value: 67_589e6 },
    ];
    expect(findInFiling(2_821e6, 0.5e6, facts)).toBe("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment");
    expect(findInFiling(4_286e6, 0.5e6, facts)).toBe("us-gaap:PaymentsToAcquireEquipmentOnLease + us-gaap:PaymentsToAcquirePropertyPlantAndEquipment");
    expect(findInFiling(-4_286e6, 0.5e6, facts)).not.toBeNull(); // sign conventions differ (capex as an outflow)
    expect(findInFiling(4_287e6, 0.5e6, facts)).toBeNull();
  });

  it("with a metric, only lines of its family count: no chance sums of unrelated lines (main run, 2026-11-09)", () => {
    const facts = [
      { concept: "ifrs-full:IncreaseDecreaseThroughChangesInOwnershipInterestsInSubsidiariesThatDoNotResultInLossOfControl", value: 100e6 },
      { concept: "ifrs-full:DeferredTaxAssets", value: 222e6 },
      { concept: "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities", value: 300e6 },
      { concept: "ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities", value: 22e6 },
      { concept: "us-gaap:WeightedAverageNumberOfSharesOutstandingBasic", value: 850e6 },
      { concept: "us-gaap:CompensationAndBenefitsTrust", value: 4e6 },
    ];
    expect(findInFiling(322e6, 0.5e6, facts)).not.toBeNull(); // the old rule: some pair always fits
    expect(findInFiling(322e6, 0.5e6, facts, "capex")).toBe(
      "ifrs-full:PurchaseOfIntangibleAssetsClassifiedAsInvestingActivities + ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    );
    expect(findInFiling(322e6, 0.5e6, facts.slice(0, 3), "capex")).toBeNull();
    expect(findInFiling(850e6, 0.5e6, facts, "diluted_shares")).toBe("us-gaap:WeightedAverageNumberOfSharesOutstandingBasic");
    expect(findInFiling(854e6, 0.5e6, facts, "diluted_shares")).toBeNull(); // shares: single lines only
    expect(findInFiling(300e6, 0.5e6, facts, "no_such_metric")).toBeNull();
  });

  it("SEC facts: annual filings only, the column's period, every namespace but dei", () => {
    const cf = {
      facts: {
        dei: { EntityCommonStockSharesOutstanding: { units: { shares: [{ val: 1, end: "2025-12-31", form: "10-K" }] } } },
        "us-gaap": {
          PaymentsToAcquireEquipmentOnLease: {
            units: {
              USD: [
                { val: 1_465e6, start: "2025-01-01", end: "2025-12-31", form: "10-K" },
                { val: 900e6, start: "2025-07-01", end: "2025-12-31", form: "10-K" }, // a half-year inside the 10-K
                { val: 1_000e6, start: "2025-01-01", end: "2025-12-31", form: "8-K" },
              ],
            },
          },
          LongTermDebtNoncurrent: { units: { USD: [{ val: 30_696e6, end: "2025-12-31", form: "10-K" }] } },
          EarningsPerShareDiluted: { units: { "USD/shares": [{ val: 18.8, start: "2025-01-01", end: "2025-12-31", form: "10-K" }] } },
        },
      },
    };
    expect(secFactsFor(cf, { start: "2025-01-01", end: "2025-12-31" })).toEqual([
      { concept: "us-gaap:PaymentsToAcquireEquipmentOnLease", value: 1_465e6 },
      { concept: "us-gaap:LongTermDebtNoncurrent", value: 30_696e6 },
    ]);
  });

  it("ESEF facts: statement lines only (no members), extension concepts included, OIM end dates", () => {
    const report = {
      facts: {
        a: { value: "182344000000", dimensions: { concept: "tot:RevenuesFromSales", entity: "x", unit: "iso4217:USD", period: "2025-01-01T00:00:00/2026-01-01T00:00:00" } },
        b: { value: "201196000000", dimensions: { concept: "ifrs-full:Revenue", entity: "x", unit: "iso4217:USD", period: "2025-01-01T00:00:00/2026-01-01T00:00:00" } },
        c: { value: "50000000000", dimensions: { concept: "ifrs-full:Revenue", entity: "x", unit: "iso4217:USD", period: "2025-01-01T00:00:00/2026-01-01T00:00:00", "ifrs-full:SegmentsAxis": "tot:Refining" } },
        d: { value: "26202000000", dimensions: { concept: "ifrs-full:CashAndCashEquivalents", entity: "x", unit: "iso4217:USD", period: "2026-01-01T00:00:00" } },
        e: { value: "1", dimensions: { concept: "ifrs-full:Revenue", entity: "x", unit: "iso4217:USD", period: "2024-01-01T00:00:00/2025-01-01T00:00:00" } },
      },
    };
    const facts = esefFactsFor(report, { start: "2025-01-01", end: "2025-12-31" });
    expect(facts.map((f) => f.concept)).toEqual(["tot:RevenuesFromSales", "ifrs-full:Revenue", "ifrs-full:CashAndCashEquivalents"]);
    expect(findInFiling(182_344e6, 0.5e6, facts)).toBe("tot:RevenuesFromSales");
  });

  it("a figure verify_value computed (e.g. derived shares) is 'definition', not wrong (review, cycle 2)", async () => {
    const out = await secondReading([{ company: "ITX", metric: "diluted_shares", period: "FY2025", value: 3_120, scale: "millions", ref: "bridge.diluted_shares", status: "mismatch", cause: "other", hints: [], computed: true }]);
    expect(out[0]!.status).toBe("definition");
  });

  it("computed figures become 'definition', reported lines found in the filing 'other_line', the rest stays wrong", async () => {
    const base = { company: "CAT", period: "FY2025", scale: "millions", status: "mismatch", cause: "other", hints: [] };
    const items = [
      { ...base, metric: "net_debt", value: 33_344, ref: "bridge.net_debt" },
      { ...base, metric: "capex", value: 4_286, ref: "history.capex[FY2025]" },
      { ...base, metric: "capex", value: 9_999, ref: "history.capex[FY2024]" },
      { ...base, metric: "revenue", value: 1, ref: "history.revenue[FY2025]", status: "match" },
    ];
    const filingFacts = async () => [
      { concept: "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", value: 2_821e6 },
      { concept: "us-gaap:PaymentsToAcquireEquipmentOnLease", value: 1_465e6 },
    ];
    const out = await secondReading(items, { filingFacts });
    expect(out.map((x) => x.status)).toEqual(["definition", "other_line", "mismatch", "match"]);
    expect(out[0]!.cause).toBeUndefined();
    expect(out[1]!.other_line).toContain("PaymentsToAcquireEquipmentOnLease");
    expect(out[2]!.cause).toBe("other");
    // Without filing facts, a reported-line mismatch stays wrong.
    expect((await secondReading([items[1]!]))[0]!.status).toBe("mismatch");
  });
});
