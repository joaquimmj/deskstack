// Golden set against a live deskstack connector (nightly): scores evals/golden.json and writes the accuracy badge.
//
//   npx tsx scripts/golden.ts --url https://<worker>.workers.dev/mcp [--out ../evals/results] [--badge ../site/badges/golden.json]
//
// Exits 1 below 95%. Live answers can drift from the recorded fixtures when a company restates or a new filing
// lands: each miss says what came back, so a human can decide whether the data or the golden answer moved.

import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { badge, runGolden, score, type GoldenQuestion } from "./golden-lib";

function arg(name: string, dflt?: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : dflt;
}

const url = arg("--url");
if (!url) {
  console.error("usage: tsx scripts/golden.ts --url https://<worker>.workers.dev/mcp");
  process.exit(2);
}
const root = join(import.meta.dirname, "..", "..");
const outDir = arg("--out", join(root, "evals", "results"))!;
const badgePath = arg("--badge", join(root, "site", "badges", "golden.json"))!;
const golden = JSON.parse(readFileSync(join(root, "evals", "golden.json"), "utf8")) as { questions: GoldenQuestion[] };

const client = new Client({ name: "deskstack-golden", version: "1.0.0" });
await client.connect(new StreamableHTTPClientTransport(new URL(url)));
const results = await runGolden(golden.questions, async (tool, args) => {
  const r = await client.callTool({ name: tool, arguments: args });
  const text = (r.content as Array<{ type: string; text: string }>)[0]?.text ?? "";
  return { isError: !!r.isError, text, json: r.isError ? null : JSON.parse(text) };
}, { live: true });
const skipped = golden.questions.filter((q) => q.fixture_only).map((q) => q.id);
await client.close();

const s = score(results);
const b = badge(s);
mkdirSync(outDir, { recursive: true });
mkdirSync(dirname(badgePath), { recursive: true });
writeFileSync(join(outDir, "golden-live.json"), JSON.stringify({ url, ran_at: new Date().toISOString(), ...s, results }, null, 1) + "\n");
writeFileSync(badgePath, JSON.stringify(b) + "\n");
console.log(`golden (live): ${b.message}${skipped.length ? ` (${skipped.length} fixture-only question(s) skipped: ${skipped.join(", ")})` : ""}`);
for (const r of results.filter((x) => !x.pass)) console.log(`  miss ${r.id}: expected ${JSON.stringify(r.expected)}, got ${JSON.stringify(r.got)}${r.error ? ` (${r.error})` : ""}`);
process.exit(s.accuracy >= 0.95 ? 0 : 1);
