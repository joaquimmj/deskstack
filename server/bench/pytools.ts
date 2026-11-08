// The deterministic Python side: build the submitted spec into a workbook and run the checker, with the vendored
// copy that ships in the plugin (no installs needed).

import { execFileSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const ROOT = join(import.meta.dirname, "..", "..");
const LAUNCHER = join(ROOT, "plugins", "deskstack", "skills", "vp-review", "scripts", "deskstack.py");
const PY = process.env.PYTHON ?? "python3";

function run(args: string[]): { code: number; out: string; err: string } {
  try {
    const out = execFileSync(PY, ["-I", LAUNCHER, ...args], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"], timeout: 120_000 });
    return { code: 0, out, err: "" };
  } catch (e) {
    const x = e as { status?: number; stdout?: string; stderr?: string };
    return { code: x.status ?? 1, out: x.stdout ?? "", err: x.stderr ?? String(e) };
  }
}

/** Build the spec into dir/model.xlsx. Returns the path, or the builder's error (shown to the model to fix). */
export function buildWorkbook(spec: unknown, dir: string): { ok: true; path: string } | { ok: false; error: string } {
  mkdirSync(dir, { recursive: true });
  const specPath = join(dir, "spec.json");
  writeFileSync(specPath, JSON.stringify(spec, null, 1));
  const out = join(dir, "model.xlsx");
  const r = run(["build", specPath, out]);
  if (r.code !== 0) return { ok: false, error: (r.err || r.out).trim().replace(/^Spec error: /, "") };
  return { ok: true, path: out };
}

export interface CheckReport {
  counts: Record<string, number>;
  findings: Array<{ rule: string; severity: string; ref: string; message: string }>;
}

export function checkWorkbook(path: string): CheckReport {
  const r = run(["check", path, "--json"]);
  if (!r.out.trim()) throw new Error(`checker failed: ${r.err}`);
  return JSON.parse(r.out) as CheckReport;
}

export function checkMarkdown(path: string): string {
  return run(["check", path]).out;
}

export function ensureDir(p: string) {
  mkdirSync(dirname(p), { recursive: true });
}
