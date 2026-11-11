// Cost guardrails for the shared free service (brief §3):
// - per-IP rate limit (Workers Rate Limiting binding if configured, else a per-isolate window)
// - global daily request cap (D1 counter if configured) with a friendly "self-host" message
// Cloudflare Free also hard-stops at 100k requests/day (error 1027), so even with
// no D1 there is no billing risk; the cap exists to fail gracefully before that.

import { DEFAULT_DAILY_CAP, DEFAULT_PER_IP_PER_MINUTE, PRODUCT_NAME, SELF_HOST_URL, type Env } from "./config";

/** The daily cap: what happened, when it comes back (00:00 UTC, with the time left), how to self-host. */
export function capacityMessage(now = Date.now()): string {
  const next = new Date(now);
  next.setUTCHours(24, 0, 0, 0);
  const ms = next.getTime() - now;
  const mins = Math.ceil(ms / 60_000); // rounded up: never promise the reset sooner than it comes
  const left = ms < 60_000 ? "less than a minute" : `${Math.floor(mins / 60)} h ${mins % 60} min`;
  return (
    `${PRODUCT_NAME}'s free daily capacity is used up: the shared server has answered as many requests today as its free ` +
    `hosting allows. It resets at 00:00 UTC, in ${left}. To keep working now, deploy your own free copy in a few ` +
    `minutes: ${SELF_HOST_URL}`
  );
}

/** The per-IP limit: what the limit is, when to retry, how to self-host. */
export function rateMessage(perMinute: number): string {
  return (
    `${PRODUCT_NAME} received more than ${perMinute} requests in a minute from your network, the limit per address on ` +
    `the shared server. Retry in a minute. For heavy use, deploy your own free copy: ${SELF_HOST_URL}`
  );
}

// ---- per-IP window (fallback when no Rate Limiting binding) --------------------

const windows = new Map<string, { start: number; count: number }>();
let lastSweep = 0;

/** Tests: whether this isolate still holds an address. */
export function isolateTracks(ip: string): boolean {
  return windows.has(ip);
}

function isolateLimit(ip: string, perMinute: number, now: number): boolean {
  // PRIVACY.md: an address is kept for one to two minutes. Expired windows are swept at most once a minute.
  if (now - lastSweep >= 60_000) {
    for (const [k, w] of windows) if (now - w.start >= 60_000) windows.delete(k);
    lastSweep = now;
  }
  const w = windows.get(ip);
  if (!w || now - w.start >= 60_000) {
    if (windows.size > 10_000) windows.clear(); // bound memory
    windows.set(ip, { start: now, count: 1 });
    return true;
  }
  w.count += 1;
  return w.count <= perMinute;
}

/**
 * This isolate's own window, then the shared counter (exact), else Cloudflare's rate-limit binding. The binding is approximate
 * (counters are per location and eventually consistent: a live burst got 512 of 515 calls through in 70 s), so the
 * isolate window bounds a burst that one isolate serves. Neither is exact across isolates; the daily cap is the hard
 * limit.
 */
export async function allowIp(env: Env, ip: string, now = Date.now()): Promise<boolean> {
  const perMinute = Number(env.PER_IP_PER_MINUTE) || DEFAULT_PER_IP_PER_MINUTE;
  const local = isolateLimit(ip, perMinute, now);
  if (!local) return false;
  // The shared counter (src/limiter.ts) is exact across isolates and locations; when it answers, it decides.
  if (env.IP_COUNTER) {
    try {
      const stub = env.IP_COUNTER.get(env.IP_COUNTER.idFromName("global"));
      const r = await stub.fetch(`https://counter/hit?ip=${encodeURIComponent(ip)}&n=${perMinute}`);
      if (r.status === 200) return true;
      if (r.status === 429) return false;
    } catch {
      // over a free-plan limit or unavailable: fall back to Cloudflare's limiter below
    }
  }
  if (env.IP_LIMITER) {
    try {
      return (await env.IP_LIMITER.limit({ key: ip })).success;
    } catch {
      // the isolate window above already allowed it
    }
  }
  return true;
}

// ---- daily cap (batched D1 counter) ---------------------------------------------

const FLUSH_EVERY = 20; // requests
const FLUSH_MS = 30_000;

const counter = { day: "", pending: 0, total: 0, lastFlush: 0 };

export function utcDay(now = Date.now()): string {
  return new Date(now).toISOString().slice(0, 10);
}

/** Test isolation: clears the daily counter and the per-IP windows. */
export function resetCounter(): void {
  Object.assign(counter, { day: "", pending: 0, total: 0, lastFlush: 0 });
  windows.clear();
  lastSweep = 0;
}

async function flush(db: D1Database, day: string, n: number): Promise<number | null> {
  try {
    const row = await db
      .prepare(
        "INSERT INTO usage (day, n) VALUES (?1, ?2) ON CONFLICT(day) DO UPDATE SET n = n + excluded.n RETURNING n",
      )
      .bind(day, n)
      .first<{ n: number }>();
    return row?.n ?? null;
  } catch (e) {
    console.error("usage flush failed", e);
    return null;
  }
}

/**
 * Count one request; returns false once the day's total reaches the cap.
 * Writes to D1 at most once per FLUSH_EVERY requests or FLUSH_MS per isolate,
 * so the counter costs ~5% of D1's free daily writes at the cap.
 */
export async function allowDaily(env: Env, waitUntil: (p: Promise<unknown>) => void, now = Date.now()): Promise<boolean> {
  if (!env.USAGE) return true;
  const cap = Number(env.DAILY_CAP) || DEFAULT_DAILY_CAP;
  const day = utcDay(now);
  if (counter.day !== day) Object.assign(counter, { day, pending: 0, total: 0, lastFlush: 0 });
  if (counter.total + counter.pending >= cap) return false;
  counter.pending += 1;
  if (counter.pending >= FLUSH_EVERY || now - counter.lastFlush >= FLUSH_MS) {
    const n = counter.pending;
    counter.pending = 0;
    counter.lastFlush = now;
    const db = env.USAGE;
    waitUntil(
      flush(db, day, n).then((total) => {
        if (total !== null && counter.day === day) counter.total = Math.max(counter.total, total);
      }),
    );
  }
  return true;
}
