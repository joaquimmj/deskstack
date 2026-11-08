// The plugin's demo models (checker/tests/demo_models.py): /associate's tie-out batches, run through verify_value
// against Apple's SEC fixture. Each planted data error must come back with the expected status and hint, and
// every other filed figure in the model must match.

import { describe, expect, it } from "vitest";
import { SNAPSHOT_YEARS } from "../src/config";
import { standardize } from "../src/sec/xbrl";
import { verifyItems, type VerifyItem } from "../src/verify";
import { facts, load } from "./helpers";

interface Demo {
  name: string;
  batches: { company: string; items: VerifyItem[] }[];
  expect: Record<string, { status: string; hint: string | null }>;
}

const { demos } = load<{ demos: Demo[] }>("../demo/extract.json");
const aapl = standardize(facts("AAPL"), SNAPSHOT_YEARS, true);

describe("plugin demo models: tie-out of Apple DCFs", () => {
  it("has the demos (regenerate with: python checker/tests/demo_models.py)", () => {
    expect(demos.length).toBeGreaterThanOrEqual(10);
  });

  it.each(demos.map((d) => [d.name, d] as const))("%s", (_name, demo) => {
    const results = demo.batches.flatMap((b) => {
      expect(b.company).toBe("AAPL");
      return verifyItems(aapl, b.items);
    });
    expect(results.length).toBe(14); // every filed figure in the model is extracted
    for (const r of results) {
      const want = demo.expect[r.ref!];
      if (want) {
        expect(r.status, r.ref!).toBe(want.status);
        if (want.hint) expect(r.hints.join(" "), r.ref!).toContain(want.hint);
      } else {
        expect(r.status, `${r.ref} ${r.metric} ${r.period}: ${r.hints.join(" ")}`).toBe("match");
      }
    }
  });
});
