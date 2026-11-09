// The shared service's cost guards are bindings, so the code alone can't enforce them: without IP_LIMITER the
// per-IP limit falls back to a per-isolate window, and without USAGE the daily cap is never checked
// (security audit 2026-11-09). This test fails if either binding leaves wrangler.jsonc.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const strip = (s: string) => s.replace(/^\s*\/\/.*$/gm, "").replace(/,(\s*[}\]])/g, "$1");
const config = JSON.parse(strip(readFileSync(join(import.meta.dirname, "..", "wrangler.jsonc"), "utf8")));

describe("wrangler.jsonc cost guards", () => {
  it("binds the per-IP rate limiter", () => {
    const rl = (config.ratelimits ?? []).find((r: { name: string }) => r.name === "IP_LIMITER");
    expect(rl).toBeDefined();
    expect(rl.simple.limit).toBeGreaterThan(0);
    expect([10, 60]).toContain(rl.simple.period);
  });

  it("binds the shared per-IP counter (a SQLite Durable Object, the only kind on Workers Free)", () => {
    const b = (config.durable_objects?.bindings ?? []).find((d: { name: string }) => d.name === "IP_COUNTER");
    expect(b?.class_name).toBe("IpCounter");
    const created = (config.migrations ?? []).flatMap((m: { new_sqlite_classes?: string[] }) => m.new_sqlite_classes ?? []);
    expect(created).toContain("IpCounter");
  });

  it("binds the D1 daily counter and sets a cap below the free plan's 100k requests/day", () => {
    const db = (config.d1_databases ?? []).find((d: { binding: string }) => d.binding === "USAGE");
    expect(db?.database_id).toMatch(/^[0-9a-f-]{36}$/);
    expect(Number(config.vars.DAILY_CAP)).toBeLessThan(100_000);
  });
});
