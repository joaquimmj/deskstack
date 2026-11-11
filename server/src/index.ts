// Worker entry: an authless, stateless MCP server (Streamable HTTP) at /mcp.
// Static assets (the nightly SEC snapshot under /v1/) are served by Cloudflare
// before this code runs, so they cost no Worker CPU.

import { createMcpHandler, originValidationResponse } from "@modelcontextprotocol/server";
import { DEFAULT_PER_IP_PER_MINUTE, DISCLAIMER, PRODUCT_NAME, REPO_URL, VERSION, type Env } from "./config";
import { allowDaily, allowIp, capacityMessage, rateMessage } from "./guard";
export { IpCounter } from "./limiter"; // the Durable Object class bound as IP_COUNTER
import { Fx } from "./fx";
import { cachedFetchText, Rates } from "./rates";
import { Repo } from "./repo";
import { SecClient } from "./sec/edgar";
import { buildServer } from "./tools";

type Handler = ReturnType<typeof createMcpHandler>;
const handlers = new WeakMap<object, Map<string, Handler>>();

/** Claude's web/desktop origins plus local tools (MCP Inspector). Requests without Origin pass. */
const BASE_ORIGINS = ["claude.ai", "claude.com", "localhost", "127.0.0.1"];

function cacheOrNull(): Cache | undefined {
  try {
    return (globalThis as unknown as { caches?: { default?: Cache } }).caches?.default;
  } catch {
    return undefined;
  }
}

/**
 * The MCP handler for this env. With `refuse`, every tool call returns that
 * message as a tool error (rate limit, daily cap): the SDK still speaks the
 * protocol correctly for old and new clients, and Claude shows the message.
 */
export type Refusal = "" | "rate" | "capacity";

/**
 * The MCP handler for this env. With a refusal, every tool call returns its message as a tool error (rate limit,
 * daily cap): the SDK still speaks the protocol correctly for old and new clients, and Claude shows the message.
 * Handlers are cached per kind of refusal; the message itself is written at call time (it counts down to the reset).
 */
export function handlerFor(env: Env, refusal: Refusal = ""): Handler {
  let byKind = handlers.get(env);
  if (!byKind) handlers.set(env, (byKind = new Map()));
  let h = byKind.get(refusal);
  if (!h) {
    const cache = cacheOrNull();
    const sec = new SecClient({ userAgent: env.SEC_USER_AGENT, cache });
    const repo = new Repo(sec, env.ASSETS ?? null);
    const text = cachedFetchText((i, init) => fetch(i, init), cache);
    const rates = new Rates(text);
    const fx = new Fx(text);
    const perMinute = Number(env.PER_IP_PER_MINUTE) || DEFAULT_PER_IP_PER_MINUTE;
    const refuse = refusal === "rate" ? () => rateMessage(perMinute) : refusal === "capacity" ? () => capacityMessage() : undefined;
    h = createMcpHandler(() => buildServer({ repo, rates, fx }, refuse), { legacy: "stateless" });
    byKind.set(refusal, h);
  }
  return h;
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/" && request.method === "GET") {
      return Response.json({
        name: PRODUCT_NAME,
        version: VERSION,
        mcp_endpoint: `${url.origin}/mcp`,
        how_to_connect: "In Claude: Settings > Connectors > Add custom connector, paste the mcp_endpoint URL, no sign-in.",
        source: REPO_URL,
        disclaimer: DISCLAIMER,
      });
    }
    // Everything else (including /v1/damodaran.json, routed here by run_worker_first) is not public.
    if (url.pathname !== "/mcp") return new Response("Not found", { status: 404 });

    const extra = (env.ALLOWED_ORIGINS ?? "").split(",").map((s) => s.trim()).filter(Boolean);
    const rejected = originValidationResponse(request, [...BASE_ORIGINS, ...extra]);
    if (rejected) return rejected;

    if (request.method !== "POST") return handlerFor(env).fetch(request); // SDK answers GET/DELETE with 405

    const ip = request.headers.get("CF-Connecting-IP") ?? "unknown";
    if (!(await allowIp(env, ip))) return handlerFor(env, "rate").fetch(request);
    if (!(await allowDaily(env, (p) => ctx.waitUntil(p)))) return handlerFor(env, "capacity").fetch(request);

    return handlerFor(env).fetch(request);
  },
} satisfies ExportedHandler<Env>;
