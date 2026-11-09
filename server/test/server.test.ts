// End-to-end tool calls through a real MCP client and the Worker's fetch
// handler, with SEC mocked by fixtures. Portions adapted from open-finance-mcp
// (c) 2026 Nathanael Johnson, MIT License (tests/test_server.py @ 8bcf3af0).

import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DUAL_FILERS, PREDECESSORS } from "../src/config";
import { resetCounter } from "../src/guard";
import worker from "../src/index";
import { resetMemos } from "../src/repo";
import { TTE } from "./esef-fixture";
import { secFetch } from "./helpers";
import { baseEnv, call, connect, ctx, fixtureAssets } from "./mcp-harness";

let calls: string[] = [];

beforeEach(() => {
  calls = [];
  resetMemos();
  resetCounter();
  vi.stubGlobal("fetch", secFetch(calls));
  // Rate and FX fixtures are as of 2026-11-08; freeze the calendar there (timers stay real).
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-08T12:00:00Z") });
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("tools (live SEC path)", () => {
  it("lists read-only tools, for modern and legacy clients", async () => {
    for (const mode of ["auto", "legacy"] as const) {
      const client = await connect(baseEnv(), mode);
      const { tools } = await client.listTools();
      expect(new Set(tools.map((t) => t.name))).toEqual(new Set(["company_lookup", "financial_statements", "key_metrics", "verify_value", "risk_free_rate", "fx_rate", "valuation_inputs", "data_status"]));
      expect(tools.every((t) => t.annotations?.readOnlyHint)).toBe(true);
      await client.close();
    }
  });

  it("lookup matches ticker, then name", async () => {
    const r = await call(baseEnv(), "company_lookup", { query: "exxon" });
    expect(r.isError).toBe(false);
    expect(r.json.results[0].ticker).toBe("XOM");
    expect(r.json.results[0].source).toBe("SEC company tickers list");
  });

  it("lookup finds registrants without a ticker via EDGAR search", async () => {
    const r = await call(baseEnv(), "company_lookup", { query: "exxon mobil" });
    const hit = r.json.results.find((x: { cik: number }) => x.cik === 34088);
    expect(hit).toMatchObject({ cik: 34088, name: "EXXON MOBIL CORP", ticker: null, source: "EDGAR company search" });
  });

  it("financials carry citations and no warnings for a clean filer", async () => {
    const r = await call(baseEnv(), "financial_statements", { ticker: "aapl", years: 2 });
    expect(r.isError).toBe(false);
    const out = r.json;
    expect(out.company).toMatchObject({ ticker: "AAPL", cik: 320193, reporting_standard: "US-GAAP", currency: "USD", financial_company: false });
    expect(out.warnings).toEqual([expect.stringContaining("Built live")]);
    const rev = out.periods[0].income_statement.revenue;
    const src = out.sources.find((s: { accession_or_id: string }) => s.accession_or_id === rev.accession);
    expect(src.url.startsWith("https://www.sec.gov/Archives/")).toBe(true);
    expect(src).toMatchObject({ name: "SEC EDGAR", form: expect.any(String), as_of: expect.any(String) });
    // Every cited accession in every cell is in sources.
    const cited = new Set(out.sources.map((s: { accession_or_id: string }) => s.accession_or_id));
    for (const p of out.periods) {
      for (const g of [p.income_statement, p.cash_flow, p.balance_sheet]) {
        for (const c of Object.values(g) as Array<{ accession?: string; accessions?: string[] } | null>) {
          if (c) for (const a of c.accessions ?? [c.accession!]) expect(cited.has(a)).toBe(true);
        }
      }
    }
    expect(out.units).toMatch(/absolute/);
    expect(out.shares_outstanding.concept).toBe("dei:EntityCommonStockSharesOutstanding");
    expect(out.disclaimer).toMatch(/Not affiliated with or endorsed by Anthropic/);
  });

  it("flags a bank", async () => {
    const r = await call(baseEnv(), "financial_statements", { ticker: "JPM", years: 1 });
    expect(r.json.company.financial_company).toBe(true);
    expect(r.json.warnings.some((w: string) => w.includes("not meaningful"))).toBe(true);
  });

  it("flags a lagging XBRL API", async () => {
    const r = await call(baseEnv(), "financial_statements", { ticker: "KO", years: 1 });
    expect(r.json.warnings.some((w: string) => w.includes("does not include yet"))).toBe(true);
  });

  it("new registrant explains itself and points to the predecessor CIK", async () => {
    const r = await call(baseEnv(), "financial_statements", { ticker: "XOM" });
    expect(r.isError).toBe(true);
    expect(r.text).toMatch(/predecessor/);
    expect(r.text).toContain("CIK0000034088");
    expect(r.text).not.toContain("IFRS");
  });

  it("a known reorganization falls back to the predecessor's filings, and says so", async () => {
    // The XOM fixture is the new holding registrant (no 10-K). Point the table at a fixture we have (KO).
    const real = PREDECESSORS[2115436]!;
    PREDECESSORS[2115436] = { cik: 21344, why: "test reorganization" };
    try {
      const r = await call(baseEnv(), "financial_statements", { ticker: "XOM", years: 1 });
      expect(r.isError).toBe(false);
      expect(r.json.predecessor_note).toMatch(/has no 10-K yet: test reorganization/);
      expect(r.json.predecessor_note).toContain("CIK 21344");
      expect(r.json.company.cik).toBe(21344);
      const v = await call(baseEnv(), "verify_value", { company: "XOM", items: [{ metric: "revenue", period: "FY2023", value: 1 }] });
      expect(v.json.predecessor_note).toContain("CIK 21344");
    } finally {
      PREDECESSORS[2115436] = real;
    }
  });

  it("unknown ticker points to company_lookup", async () => {
    const r = await call(baseEnv(), "financial_statements", { ticker: "ZZZZ" });
    expect(r.isError).toBe(true);
    expect(r.text).toContain("company_lookup");
  });

  it("CIK resolves registrants", async () => {
    for (const t of ["CIK0000320193", "320193"]) {
      const r = await call(baseEnv(), "financial_statements", { ticker: t, years: 1 });
      expect(r.json.company.cik).toBe(320193);
      expect(r.json.company.ticker).toBe("AAPL");
    }
  });

  it("IFRS financials come back in reporting currency", async () => {
    const r = await call(baseEnv(), "financial_statements", { ticker: "SAP", years: 1 });
    expect([r.json.company.reporting_standard, r.json.company.currency]).toEqual(["IFRS", "EUR"]);
  });

  it("missing SEC contact is a readable error", async () => {
    const r = await call(baseEnv({ SEC_USER_AGENT: "" }), "financial_statements", { ticker: "AAPL" });
    expect(r.isError).toBe(true);
    expect(r.text).toContain("SEC_USER_AGENT");
  });
});

describe("M2 tools", () => {
  it("key_metrics returns computed ratios with formulas and sources", async () => {
    const r = await call(baseEnv({ ASSETS: fixtureAssets(["AAPL"]) }), "key_metrics", { ticker: "AAPL", years: 2 });
    expect(r.isError).toBe(false);
    expect(r.json.computed).toBe(true);
    const fy = r.json.periods.find((p: { type: string }) => p.type === "annual");
    expect(fy.metrics.gross_margin.formula).toBe("gross_profit / revenue");
    expect(fy.metrics.gross_margin.value).toBeGreaterThan(0.3);
    expect(r.json.sources.length).toBeGreaterThan(0);
    expect(calls).toEqual([]);
  });

  it("risk_free_rate answers for US and EUR with a cited source", async () => {
    const us = await call(baseEnv(), "risk_free_rate", { region: "US", tenor: "10Y" });
    expect([us.json.rate_pct, us.json.rate_decimal, us.json.date]).toEqual([4.86, 0.0486, "2026-11-06"]);
    expect(us.json.sources[0].name).toMatch(/Treasury/);
    const eur = await call(baseEnv(), "risk_free_rate", { region: "EUR" });
    expect(eur.json.tenor).toBe("10Y");
    expect(eur.json.sources[0].license_note).toMatch(/ECB statistics/);
  });
});

describe("verify_value", () => {
  it("ties out a batch from a model, with hints and sources, from the snapshot", async () => {
    const r = await call(baseEnv({ ASSETS: fixtureAssets(["AAPL"]) }), "verify_value", {
      company: "AAPL",
      items: [
        { metric: "revenue", period: "FY2024", value: 391.035, scale: "billions", ref: "Inputs!C5" },
        { metric: "revenue", period: "FY2024", value: 391035, scale: "thousands", ref: "Inputs!C6" },
      ],
    });
    expect(r.isError).toBe(false);
    expect(r.json.counts).toMatchObject({ total: 2, match: 1, mismatch: 1 });
    expect(r.json.results[1].hints[0]).toMatch(/in millions/);
    expect(r.json.sources[0].url).toMatch(/^https:\/\/www\.sec\.gov\/Archives\//);
    expect(calls).toEqual([]);
  });

  it("works for EU issuers by LEI", async () => {
    const r = await call(baseEnv({ ASSETS: fixtureAssets(["AAPL"]) }), "verify_value", {
      company: TTE.lei,
      items: [{ metric: "net income", period: "FY2024", value: 15758, scale: "millions" }],
    });
    expect(r.json.results[0].status).toBe("match");
    expect(r.json.sources[0].form).toBe("ESEF annual report");
  });
});

describe("European issuers (ESEF)", () => {
  it("a dual filer's responses say a 20-F on another basis exists, and how to get it (ASML style)", async () => {
    const env = baseEnv({ ASSETS: fixtureAssets(["AAPL"]) });
    DUAL_FILERS[TTE.lei] = { cik: 4321, ticker: "TTEX", standard: "US GAAP" };
    try {
      const fs = await call(env, "financial_statements", { ticker: TTE.lei, years: 1 });
      expect(fs.json.basis_note).toMatch(/also files a 20-F with the SEC in US GAAP \(CIK 4321, ticker TTEX\)/);
      const km = await call(env, "key_metrics", { ticker: TTE.lei, years: 1 });
      expect(km.json.warnings[0]).toMatch(/^other_basis: /);
      const v = await call(env, "verify_value", { company: TTE.lei, items: [{ metric: "net income", period: "FY2024", value: 15758, scale: "millions" }] });
      expect(v.json.basis_note).toContain("'TTEX'");
    } finally {
      delete DUAL_FILERS[TTE.lei];
    }
    const plain = await call(env, "financial_statements", { ticker: TTE.lei, years: 1 });
    expect(plain.json.basis_note).toBeUndefined();
  });

  it("company_lookup finds an EU issuer by name and returns its LEI", async () => {
    const r = await call(baseEnv({ ASSETS: fixtureAssets(["AAPL"]) }), "company_lookup", { query: "totalenergies" });
    expect(r.json.results[0]).toMatchObject({ lei: TTE.lei, region: "EU", reporting_standard: "IFRS", currency: "USD" });
  });

  it("financial_statements and key_metrics accept the LEI, with ESEF citations and no SEC calls", async () => {
    const env = baseEnv({ ASSETS: fixtureAssets(["AAPL"]) });
    const fs = await call(env, "financial_statements", { ticker: TTE.lei, years: 2 });
    expect(fs.isError).toBe(false);
    expect(fs.json.company).toMatchObject({ lei: TTE.lei, region: "EU", country: "FR", currency: "USD" });
    expect(fs.json.periods.at(-1).income_statement.revenue.value).toBe(201_196_000_000);
    expect(fs.json.sources[0]).toMatchObject({ form: "ESEF annual report", url: expect.stringContaining("https://filings.xbrl.org/") });
    expect(fs.json.data_as_of).toBe("2026-11-08T04:00:00Z");
    const km = await call(env, "key_metrics", { ticker: TTE.lei, years: 2 });
    expect(km.json.periods.at(-1).metrics.net_margin.formula).toBe("net_income / revenue");
    expect(km.json.sources[0].license_note).toMatch(/filings\.xbrl\.org/);
    expect(calls.filter((u) => u.includes("sec.gov"))).toEqual([]);
  });

  it("an LEI outside the coverage gets an explanation, not a guess", async () => {
    const r = await call(baseEnv({ ASSETS: fixtureAssets(["AAPL"]) }), "financial_statements", { ticker: "529900ZZZZZZZZZZZZ42" });
    expect(r.isError).toBe(true);
    expect(r.text).toMatch(/not in the European coverage/);
  });
});

describe("valuation and FX tools", () => {
  it("fx_rate converts through ECB reference rates", async () => {
    const r = await call(baseEnv(), "fx_rate", { from: "EUR", to: "USD" });
    expect(r.json.rate).toBe(1.1165);
    expect(r.json.summary).toMatch(/^1 EUR = 1\.11650 USD/);
  });

  it("valuation_inputs returns country ERP and industry betas with attribution", async () => {
    const env = baseEnv({ ASSETS: fixtureAssets(["AAPL"]) });
    const r = await call(env, "valuation_inputs", { country: "France", industry: "Software", region: "Europe" });
    expect(r.isError).toBe(false);
    expect(r.json.country[0].equity_risk_premium).toBe(0.0501);
    expect(r.json.industry[0].industry).toBe("Software (System & Application)");
    expect(r.json.attribution).toMatch(/Damodaran/);
    const list = await call(env, "valuation_inputs", {});
    expect(list.json.industries).toContain("Advertising");
  });

  it("a transient asset failure is not remembered as 'not deployed'", async () => {
    let n = 0;
    const good = fixtureAssets(["AAPL"]);
    const flaky = {
      fetch: async (input: Request | string) => {
        const path = new URL(typeof input === "string" ? input : input.url).pathname;
        if (path === "/v1/damodaran.json" && n++ === 0) return new Response("boom", { status: 503 });
        return good.fetch(input);
      },
    };
    const env = baseEnv({ ASSETS: flaky });
    const first = await call(env, "valuation_inputs", { country: "France" });
    expect(first.isError).toBe(true);
    expect(first.text).toMatch(/Upstream data source failed/);
    const second = await call(env, "valuation_inputs", { country: "France" });
    expect(second.isError).toBe(false);
    expect(second.json.country[0].country).toBe("France");
  });

  it("valuation_inputs explains itself when the datasets are not deployed", async () => {
    const r = await call(baseEnv(), "valuation_inputs", { country: "France" });
    expect(r.isError).toBe(true);
    expect(r.text).toMatch(/not loaded/);
  });
});

describe("snapshot path", () => {
  it("serves from static assets with zero SEC calls, same numbers as live", async () => {
    const live = await call(baseEnv(), "financial_statements", { ticker: "AAPL", years: 3 });
    calls = [];
    resetMemos();
    vi.stubGlobal("fetch", secFetch(calls));
    const snap = await call(baseEnv({ ASSETS: fixtureAssets(["AAPL"]) }), "financial_statements", { ticker: "AAPL", years: 3 });
    expect(calls).toEqual([]);
    expect(snap.json.periods).toEqual(live.json.periods);
    expect(snap.json.sources).toEqual(live.json.sources);
    expect(snap.json.warnings).toEqual([]);
    expect(snap.json.data_as_of).toBe("2026-11-08T03:00:00Z");
  });

  it("falls back to live SEC for a company not in the snapshot", async () => {
    const r = await call(baseEnv({ ASSETS: fixtureAssets(["AAPL"]) }), "financial_statements", { ticker: "MSFT", years: 1 });
    expect(r.json.company.ticker).toBe("MSFT");
    expect(calls.some((u) => u.includes("companyfacts"))).toBe(true);
  });

  it("data_status reports the snapshot", async () => {
    const r = await call(baseEnv({ ASSETS: fixtureAssets(["AAPL"]) }), "data_status");
    expect(r.json.snapshot.built_at).toBe("2026-11-08T03:00:00Z");
    expect(r.json.self_host).toContain("SELF_HOSTING");
  });
});

describe("guardrails", () => {
  it("per-IP limit answers tools/call with a readable tool error", async () => {
    const env = baseEnv({ ASSETS: fixtureAssets(["AAPL"]), PER_IP_PER_MINUTE: "3" });
    const client = await connect(env, "auto", { "CF-Connecting-IP": "203.0.113.9" });
    let last;
    for (let i = 0; i < 5; i++) last = await client.callTool({ name: "data_status", arguments: {} });
    await client.close();
    expect(last!.isError).toBe(true);
    expect((last!.content as Array<{ text: string }>)[0]!.text).toMatch(/Too many requests/);
  });

  it("per-IP limit also holds in each isolate when the Cloudflare limiter lets a burst through (security audit, 2026-11-09)", async () => {
    // Live: Cloudflare's rate-limit binding is approximate per location; 512 of 515 calls in 70 s were served.
    const permissive = { limit: async () => ({ success: true }) };
    const env = baseEnv({ ASSETS: fixtureAssets(["AAPL"]), PER_IP_PER_MINUTE: "3", IP_LIMITER: permissive } as never);
    const client = await connect(env, "auto", { "CF-Connecting-IP": "203.0.113.10" });
    let last;
    for (let i = 0; i < 5; i++) last = await client.callTool({ name: "data_status", arguments: {} });
    await client.close();
    expect(last!.isError).toBe(true);
    expect((last!.content as Array<{ text: string }>)[0]!.text).toMatch(/Too many requests/);
  });

  it("daily cap answers with the self-host message", async () => {
    let total = 0;
    const db = {
      prepare: () => ({
        bind: (_d: string, n: number) => ({
          first: async () => {
            total += n;
            return { n: total + 1_000 }; // other isolates already used most of the cap
          },
        }),
      }),
    } as unknown as D1Database;
    const env = baseEnv({ ASSETS: fixtureAssets(["AAPL"]), USAGE: db, DAILY_CAP: "1000", PER_IP_PER_MINUTE: "1000" });
    const waits: Promise<unknown>[] = [];
    const ctx2 = { waitUntil: (p: Promise<unknown>) => waits.push(p) } as unknown as ExecutionContext;
    const transport = new StreamableHTTPClientTransport(new URL("https://ft.test/mcp"), {
      fetch: (url, init) => worker.fetch(new Request(url, init), env, ctx2),
    });
    const client = new Client({ name: "t", version: "1" }, { versionNegotiation: { mode: "auto" } });
    await client.connect(transport);
    await Promise.all(waits);
    const r = await client.callTool({ name: "data_status", arguments: {} });
    await client.close();
    expect(r.isError).toBe(true);
    expect((r.content as Array<{ text: string }>)[0]!.text).toMatch(/free daily capacity/);
  });

  it("rejects a foreign browser Origin", async () => {
    const res = await worker.fetch(
      new Request("https://ft.test/mcp", {
        method: "POST",
        headers: { Origin: "https://evil.example", "Content-Type": "application/json" },
        body: "{}",
      }),
      baseEnv(),
      ctx,
    );
    expect(res.status).toBe(403);
  });

  it("does not serve the Damodaran dataset as a public download", async () => {
    // In production Cloudflare serves assets BEFORE the Worker, so the guard is the config:
    // the path must be routed to the Worker (run_worker_first), which answers 404.
    const cfg = readFileSync(join(import.meta.dirname, "..", "wrangler.jsonc"), "utf8");
    const runFirst = /"run_worker_first"\s*:\s*(\[[^\]]*\])/.exec(cfg);
    expect(runFirst && JSON.parse(runFirst[1]!)).toContain("/v1/damodaran.json");
    const res = await worker.fetch(new Request("https://ft.test/v1/damodaran.json"), baseEnv({ ASSETS: fixtureAssets(["AAPL"]) }), ctx);
    expect(res.status).toBe(404);
  });

  it("serves a small landing JSON at /", async () => {
    const res = await worker.fetch(new Request("https://ft.test/"), baseEnv(), ctx);
    const j = (await res.json()) as { mcp_endpoint: string };
    expect(j.mcp_endpoint).toBe("https://ft.test/mcp");
  });
});
