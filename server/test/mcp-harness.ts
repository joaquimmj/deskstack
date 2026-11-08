// A real MCP client talking to the Worker's fetch handler, with SEC mocked by fixtures (see helpers.secFetch).
// Shared by the tool tests and the golden set.

import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";
import type { Env } from "../src/config";
import worker from "../src/index";
import { pad } from "../src/sec/edgar";
import { buildCompanyRecord } from "../src/sec/record";
import { syntheticDamodaran } from "./damodaran-fixture";
import { TTE, tteRecord } from "./esef-fixture";
import { facts, load, submissions, tickerToCik } from "./helpers";

export const UA = "deskstack-tests test@example.com";
export const ctx = { waitUntil: (_p: Promise<unknown>) => {}, passThroughOnException: () => {} } as unknown as ExecutionContext;
export const baseEnv = (over: Partial<Env> = {}): Env => ({ SEC_USER_AGENT: UA, ...over });

export async function connect(env: Env, mode: "auto" | "legacy" = "auto", headers: Record<string, string> = {}) {
  const transport = new StreamableHTTPClientTransport(new URL("https://ft.test/mcp"), {
    fetch: (url, init) => {
      const req = new Request(url, init);
      for (const [k, v] of Object.entries(headers)) req.headers.set(k, v);
      return worker.fetch(req, env, ctx);
    },
  });
  const client = new Client({ name: "test", version: "1.0.0" }, { versionNegotiation: { mode } });
  await client.connect(transport);
  return client;
}

export async function call(env: Env, tool: string, args: Record<string, unknown> = {}) {
  const client = await connect(env);
  try {
    const r = await client.callTool({ name: tool, arguments: args });
    const text = (r.content as Array<{ type: string; text: string }>)[0]!.text;
    return { isError: !!r.isError, text, json: r.isError ? null : JSON.parse(text) };
  } finally {
    await client.close();
  }
}

export interface EuFixture {
  lei: string;
  name: string;
  country: string;
  currency: string;
  fye: string;
  record: unknown;
}

/** Static-assets stand-in built from fixtures, like the nightly snapshot. */
export function fixtureAssets(tickers: string[], eu: EuFixture[] = [{ lei: TTE.lei, name: TTE.name, country: "FR", currency: "USD", fye: "1231", record: tteRecord() }]) {
  const t2c = tickerToCik();
  const files = new Map<string, unknown>();
  const t = load<{ fields: string[]; data: unknown[][] }>("company_tickers_exchange.json");
  files.set("/v1/companies.json", t);
  files.set("/v1/damodaran.json", syntheticDamodaran());
  files.set("/v1/eu/companies.json", { fields: ["lei", "name", "country", "currency", "fiscal_year_end"], data: eu.map((e) => [e.lei, e.name, e.country, e.currency, e.fye]) });
  files.set("/v1/eu/manifest.json", { built_at: "2026-11-08T04:00:00Z" });
  for (const e of eu) files.set(`/v1/eu/co/${e.lei}.json`, e.record);
  files.set("/v1/manifest.json", { schema: 1, built_at: "2026-11-08T03:00:00Z", companies: t.data.length, records: tickers.length, source: "fixtures" });
  for (const tk of tickers) {
    const cik = t2c.get(tk)!;
    files.set(`/v1/co/${pad(cik)}.json`, buildCompanyRecord(facts(tk), submissions(tk), cik, "2026-11-08T03:00:00Z", "snapshot"));
  }
  return {
    fetch: async (input: Request | string) => {
      const path = new URL(typeof input === "string" ? input : input.url).pathname;
      return files.has(path) ? Response.json(files.get(path)) : new Response("nope", { status: 404 });
    },
  };
}
