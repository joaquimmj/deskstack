// Records the tool calls behind examples/ from the live connector, so the examples are built from what the real tools
// returned, and the tests can rebuild them offline.
//
//   npx tsx scripts/examples.ts data     # the calls in examples/plan.json -> examples/<case>/calls/<id>.json
//   npx tsx scripts/examples.ts verify   # verify_value on examples/<case>/batches.json -> examples/<case>/calls/verify.json
//
// examples/refresh.sh runs the whole loop. Each recorded file keeps the request, the response and the date.

import { mkdirSync, readFileSync, writeFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { mcpConnector } from "../bench/connector";

const ROOT = join(import.meta.dirname, "..", "..");
const EX = join(ROOT, "examples");
const plan = JSON.parse(readFileSync(join(EX, "plan.json"), "utf8")) as {
  connector: string;
  cases: Record<string, Array<{ id: string; tool: string; args: Record<string, unknown> }>>;
};
const mode = process.argv[2];
if (mode !== "data" && mode !== "verify") {
  console.error("usage: tsx scripts/examples.ts data|verify");
  process.exit(2);
}

const today = new Date().toISOString().slice(0, 10);
const c = await mcpConnector(plan.connector);
try {
  for (const [name, calls] of Object.entries(plan.cases)) {
    const dir = join(EX, name, "calls");
    mkdirSync(dir, { recursive: true });
    if (mode === "data") {
      for (const call of calls) {
        const r = await c.call(call.tool, call.args);
        if (r.isError) throw new Error(`${name}/${call.id}: ${call.tool} failed: ${r.text}`);
        const rec = { tool: call.tool, args: call.args, connector: plan.connector, recorded_at: today, response: JSON.parse(r.text) };
        writeFileSync(join(dir, `${call.id}.json`), JSON.stringify(rec, null, 1) + "\n");
        console.log(`${name}/${call.id}`);
      }
    } else {
      const bf = join(EX, name, "batches.json");
      if (!existsSync(bf)) throw new Error(`${bf} is missing: run python3 examples/build.py first`);
      const batches = JSON.parse(readFileSync(bf, "utf8")) as Array<{ company: string; items: unknown[] }>;
      const out = [];
      for (const b of batches) {
        const r = await c.call("verify_value", b as unknown as Record<string, unknown>);
        if (r.isError) throw new Error(`${name}: verify_value failed for ${b.company}: ${r.text}`);
        out.push({ request: b, response: JSON.parse(r.text) });
      }
      const rec = { tool: "verify_value", connector: plan.connector, recorded_at: today, batches: out };
      writeFileSync(join(dir, "verify.json"), JSON.stringify(rec, null, 1) + "\n");
      console.log(`${name}/verify (${batches.length} batches)`);
    }
  }
} finally {
  await c.close();
}
