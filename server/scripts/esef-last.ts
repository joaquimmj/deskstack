// An issuer's record and index row from the last good EU snapshot (the workflow restores it as .esef-last), kept
// when tonight's build can't reach filings.xbrl.org for that issuer.

import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

export function lastGood(lastDir: string, lei: string): { record: string; row: unknown[]; hasFinancials: boolean } | null {
  const file = join(lastDir, "co", `${lei}.json`);
  const index = join(lastDir, "companies.json");
  if (!existsSync(file) || !existsSync(index)) return null;
  const row = (JSON.parse(readFileSync(index, "utf8")) as { data: unknown[][] }).data.find((r) => r[0] === lei);
  if (!row) return null;
  const record = readFileSync(file, "utf8");
  return { record, row, hasFinancials: !!(JSON.parse(record) as { financials?: unknown }).financials };
}
