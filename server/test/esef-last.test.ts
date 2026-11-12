// A network failure on one issuer must not drop it from the snapshot (2026-11-12: Kongsberg's index call failed
// four times and it went off the live connector). The build keeps its record from the last good snapshot.
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { lastGood } from "../scripts/esef-last";

describe("last good ESEF record", () => {
  const dir = mkdtempSync(join(tmpdir(), "esef-last-"));
  mkdirSync(join(dir, "co"));
  writeFileSync(join(dir, "companies.json"), JSON.stringify({ data: [["LEI1", "Kongsberg", "NO", "NOK", "1231"], ["LEI2", "No file", "NO", "NOK", "1231"]] }));
  writeFileSync(join(dir, "co", "LEI1.json"), JSON.stringify({ lei: "LEI1", financials: { currency: "NOK" } }));

  it("returns the record and its index row", () => {
    const k = lastGood(dir, "LEI1")!;
    expect(k.row).toEqual(["LEI1", "Kongsberg", "NO", "NOK", "1231"]);
    expect(JSON.parse(k.record).financials.currency).toBe("NOK");
    expect(k.hasFinancials).toBe(true);
  });

  it("returns null without both a row and a record, or without a last snapshot", () => {
    expect(lastGood(dir, "LEI2")).toBeNull();
    expect(lastGood(dir, "LEI3")).toBeNull();
    expect(lastGood(join(dir, "missing"), "LEI1")).toBeNull();
  });
});
