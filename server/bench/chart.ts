// The README's benchmark chart, drawn from the recorded runs. Each run's ANALYSIS.md holds the result table read by
// hand against the filings; this reads that table and nothing else, so the chart can't drift from the analysis.
//
//   npx tsx bench/chart.ts            # writes ../bench/benchmark.svg
//
// A test checks the committed SVG is current.

import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

export interface ArmResult {
  arm: string; // "A", "B", "C"
  label: string; // "web search only", ...
  filed: number;
  wrong: number;
  avgCost: number;
}

export interface ChartPanel {
  title: string;
  source: string; // the ANALYSIS.md path, relative to the repo root
  arms: ArmResult[];
}

/** The runs the README cites. Only analysed runs: the partial runs of 9 November have no hand reading. */
export const CHART_RUNS = [
  { title: "DCF, 50 companies", dir: "bench/results/2026-11-09T09-25-07-305Z" },
  { title: "Comps, 50 companies", dir: "bench/results/2026-11-09T13-04-05-468Z" },
];

const num = (s: string): number => {
  const m = s.replace(/[*,$]/g, "").match(/-?\d+(\.\d+)?/);
  if (!m) throw new Error(`no number in "${s}"`);
  return Number(m[0]);
};

/** Reads the "## Result" table of an ANALYSIS.md. Columns are found by their header, so the two layouts both work. */
export function parseResultTable(markdown: string): ArmResult[] {
  const section = markdown.split(/^## Result\s*$/m)[1];
  if (!section) throw new Error("no '## Result' section");
  const rows = section
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l.startsWith("|"))
    .map((l) => l.slice(1, -1).split("|").map((c) => c.trim()));
  const [header, , ...body] = rows;
  if (!header) throw new Error("no result table");
  const col = (prefix: RegExp): number => {
    const i = header.findIndex((h) => prefix.test(h));
    if (i < 0) throw new Error(`no column ${prefix}`);
    return i;
  };
  const filed = col(/^Filed figures/i);
  const wrong = col(/^Wrong/i);
  const cost = col(/^Avg cost/i);
  return body
    .filter((r) => /^[A-Z]:/.test(r[0] ?? ""))
    .map((r) => {
      const [arm, ...label] = (r[0] ?? "").split(":");
      return {
        arm: arm!.trim(),
        label: label.join(":").trim(),
        filed: num(r[filed] ?? ""),
        wrong: num((r[wrong] ?? "").split("(")[0]!),
        avgCost: num(r[cost] ?? ""),
      };
    });
}

export function loadPanels(root: string): ChartPanel[] {
  return CHART_RUNS.map(({ title, dir }) => {
    const source = `${dir}/ANALYSIS.md`;
    return { title, source, arms: parseResultTable(readFileSync(join(root, source), "utf8")) };
  });
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const pct = (w: number, f: number) => (f ? `${((100 * w) / f).toFixed(1)}%` : "0%");

/** Horizontal bars: share of filed figures that were wrong, per arm, one panel per task. */
export function renderChart(panels: ChartPanel[]): string {
  const W = 900;
  const labelW = 300;
  const barMax = 260;
  const rowH = 30;
  const top = 58;
  const panelGap = 34;
  // The scale: the largest share across panels, rounded up to the next whole percent.
  const maxPct = Math.max(1, Math.ceil(Math.max(...panels.flatMap((p) => p.arms.map((a) => (100 * a.wrong) / a.filed)))));
  const out: string[] = [];
  let y = top;
  for (const p of panels) {
    out.push(`<text class="h" x="16" y="${y}">${esc(p.title)}</text>`);
    y += 14;
    for (const a of p.arms) {
      const share = (100 * a.wrong) / a.filed;
      const w = a.wrong ? Math.max(3, (share / maxPct) * barMax) : 0;
      const cy = y + rowH / 2;
      out.push(`<text class="l" x="16" y="${cy + 5}">${esc(`${a.arm}: ${a.label}`)}</text>`);
      out.push(`<rect class="track" x="${labelW}" y="${y + 6}" width="${barMax}" height="${rowH - 12}" rx="3"/>`);
      if (w) out.push(`<rect class="${a.wrong ? "bad" : "ok"}" x="${labelW}" y="${y + 6}" width="${w.toFixed(1)}" height="${rowH - 12}" rx="3"/>`);
      const text = `${a.wrong} of ${a.filed.toLocaleString("en-US")} wrong (${pct(a.wrong, a.filed)}) · $${a.avgCost.toFixed(2)} each`;
      out.push(`<text class="v${a.wrong ? " vbad" : ""}" x="${labelW + barMax + 12}" y="${cy + 5}">${esc(text)}</text>`);
      y += rowH;
    }
    y += panelGap;
  }
  const H = y - panelGap + 40;
  const note =
    "Reported figures in each AI-built model, read by hand against the filings. Claude Sonnet 5.5. " +
    "B and C read the data they are scored against.";
  return [
    `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" ` +
      `aria-label="deskstack benchmark: wrong reported figures per setup">`,
    "<style>",
    "svg{--bg:#ffffff;--fg:#1f2328;--mute:#59636e;--track:#eef0f3;--bad:#cf222e;}",
    "@media (prefers-color-scheme: dark){svg{--bg:#0d1117;--fg:#e6edf3;--mute:#9198a1;--track:#21262d;--bad:#f85149;}}",
    ".bg{fill:var(--bg)}text{font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;fill:var(--fg)}",
    ".t{font-size:16px;font-weight:600}.h{font-size:13px;font-weight:600}.l,.v{font-size:13px}",
    ".n{font-size:11px;fill:var(--mute)}.track{fill:var(--track)}.bad{fill:var(--bad)}.vbad{fill:var(--bad);font-weight:600}",
    "</style>",
    `<rect class="bg" width="${W}" height="${H}" rx="8"/>`,
    `<text class="t" x="16" y="30">Wrong reported figures, by setup</text>`,
    ...out,
    `<text class="n" x="16" y="${H - 16}">${esc(note)}</text>`,
    "</svg>",
    "",
  ].join("\n");
}

if (process.argv[1] && /chart\.ts$/.test(process.argv[1])) {
  const root = join(import.meta.dirname, "..", "..");
  const file = join(root, "bench", "benchmark.svg");
  writeFileSync(file, renderChart(loadPanels(root)));
  console.log(`Wrote ${file}`);
}
