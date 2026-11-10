// The README benchmark chart: read from the hand-read tables in ANALYSIS.md, and the committed SVG is current.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { loadPanels, parseResultTable, renderChart } from "../bench/chart";

const ROOT = join(import.meta.dirname, "..", "..");

describe("benchmark chart", () => {
  it("reads both result table layouts by column header", () => {
    const dcf = parseResultTable(
      "# x\n\n## Result\n\n| Arm | Models finished | Filed figures | Wrong, read by hand | Avg cost | Avg time |\n" +
        "|---|---|---|---|---|---|\n| A: web search only | 50 of 50 | 573 | **20 (3.5%)** | $0.23 | 58 s |\n" +
        "| B: deskstack data | 49 of 50 | 593 | **0** | $0.07 | 18 s |\n\nMore text.\n",
    );
    expect(dcf).toEqual([
      { arm: "A", label: "web search only", filed: 573, wrong: 20, avgCost: 0.23 },
      { arm: "B", label: "deskstack data", filed: 593, wrong: 0, avgCost: 0.07 },
    ]);
    const comps = parseResultTable(
      "## Result\n\n| Arm | Models finished | Filed figures | Wrong for the period asked, read by hand | Placeholders left as 0 | Avg cost | Avg time |\n" +
        "|---|---|---|---|---|---|---|\n| B: deskstack data | 50 of 50 | 1,021 | **0** | 0 | $0.17 | 36 s |\n",
    );
    expect(comps).toEqual([{ arm: "B", label: "deskstack data", filed: 1021, wrong: 0, avgCost: 0.17 }]);
  });

  it("matches the figures the README quotes", () => {
    const [dcf, comps] = loadPanels(ROOT);
    expect(dcf!.arms.map((a) => [a.arm, a.wrong, a.filed])).toEqual([["A", 20, 573], ["B", 0, 593], ["C", 0, 606]]);
    expect(comps!.arms.map((a) => [a.arm, a.wrong, a.filed])).toEqual([["A", 16, 445], ["B", 0, 1021], ["C", 0, 1010]]);
  });

  it("bench/benchmark.svg is current (regenerate: cd server && npx tsx bench/chart.ts)", () => {
    const committed = readFileSync(join(ROOT, "bench", "benchmark.svg"), "utf8");
    expect(committed).toBe(renderChart(loadPanels(ROOT)));
  });
});
