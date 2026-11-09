// The per-IP limit must hold across isolates: Cloudflare's rate-limit binding is "approximate and apply separately in
// each Cloudflare location", and a per-isolate window sees only the requests that isolate serves. Live, 502 of 515
// calls from one address got through in 70 s (security check, 2026-11-09). One shared IpCounter fixes it.

import { afterEach, describe, expect, it } from "vitest";
import { allowIp, resetCounter } from "../src/guard";
import { IpCounter } from "../src/limiter";

const ask = (c: IpCounter, ip: string, perMinute: number, now: number) =>
  c.fetch(new Request(`https://counter/hit?ip=${encodeURIComponent(ip)}&n=${perMinute}&now=${now}`)).then((r) => r.status === 200);

/** A namespace whose single object is `obj` (what env.IP_COUNTER looks like to the Worker). */
const ns = (obj: { fetch(r: Request): Promise<Response> }) => ({
  idFromName: (name: string) => ({ name }),
  get: () => obj,
});

afterEach(() => resetCounter());

describe("IpCounter (shared per-IP window)", () => {
  it("allows n calls per address per minute, then refuses until the minute is over", async () => {
    const c = new IpCounter();
    const t = 1_000_000;
    const answers = [];
    for (let i = 0; i < 4; i++) answers.push(await ask(c, "203.0.113.1", 3, t + i));
    expect(answers).toEqual([true, true, true, false]);
    expect(await ask(c, "203.0.113.2", 3, t + 5)).toBe(true); // another address has its own window
    expect(await ask(c, "203.0.113.1", 3, t + 60_000)).toBe(true); // a new minute
  });

  it("rejects malformed requests instead of counting them", async () => {
    const c = new IpCounter();
    expect((await c.fetch(new Request("https://counter/hit?n=3&now=1"))).status).toBe(400);
    expect((await c.fetch(new Request("https://counter/hit?ip=x&n=0&now=1"))).status).toBe(400);
  });
});

describe("allowIp with the shared counter", () => {
  it("follows the shared counter even when the Cloudflare limiter would allow", async () => {
    const refuseAll = { fetch: async () => new Response("", { status: 429 }) };
    const env = { IP_COUNTER: ns(refuseAll), IP_LIMITER: { limit: async () => ({ success: true }) } } as never;
    expect(await allowIp(env, "198.51.100.7")).toBe(false);
  });

  it("falls back to the other limits when the shared counter fails (e.g. over the free plan's daily limits)", async () => {
    const broken = { fetch: async () => { throw new Error("Exceeded allowed volume of requests in Durable Objects free tier"); } };
    const env = { IP_COUNTER: ns(broken), IP_LIMITER: { limit: async () => ({ success: true }) } } as never;
    expect(await allowIp(env, "198.51.100.8")).toBe(true);
  });
});
