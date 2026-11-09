// One shared per-IP window for the whole service (a Durable Object, bound as IP_COUNTER in wrangler.jsonc).
//
// Why: Cloudflare's rate-limit binding is "approximate and apply separately in each Cloudflare location", and a
// per-isolate window only sees the requests its isolate serves; live, 502 of 515 calls from one address got through
// in 70 s (security check, 2026-11-09). A single object sees every call, so its count is exact.
//
// Cost on Workers Free (docs read 2026-11-09): one object request per MCP request (the daily cap keeps that under
// 100,000/day), and one object running all day is about 10,800 of the 13,000 GB-s/day. Over a free limit the call
// errors, and guard.ts falls back to the other two limits. Counts live in memory: losing them on eviction only
// resets the current minute. Only the Worker can reach this object; it has no public route.

const MAX_TRACKED = 100_000;

export class IpCounter {
  private windows = new Map<string, { start: number; count: number }>();

  // Durable Objects are constructed with (state, env); neither is needed for an in-memory window.
  constructor(_state?: unknown, _env?: unknown) {}

  async fetch(request: Request): Promise<Response> {
    const q = new URL(request.url).searchParams;
    const ip = q.get("ip") ?? "";
    const perMinute = Number(q.get("n"));
    const now = q.has("now") ? Number(q.get("now")) : Date.now();
    if (!ip || ip.length > 64 || !Number.isInteger(perMinute) || perMinute < 1 || !Number.isFinite(now)) {
      return new Response("bad request", { status: 400 });
    }
    if (this.windows.size > MAX_TRACKED) {
      for (const [k, w] of this.windows) if (now - w.start >= 60_000) this.windows.delete(k);
      if (this.windows.size > MAX_TRACKED) this.windows.clear(); // bound memory under a flood of addresses
    }
    const w = this.windows.get(ip);
    if (!w || now - w.start >= 60_000) {
      this.windows.set(ip, { start: now, count: 1 });
      return new Response("ok");
    }
    w.count += 1;
    return w.count <= perMinute ? new Response("ok") : new Response("too many", { status: 429 });
  }
}
