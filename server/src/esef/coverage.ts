// Per-country coverage of the European snapshot, written by scripts/build-esef.ts as v1/eu/coverage.json
// and printed in the build log: issuers served, and those rejected with the reason.

export interface CoverageEntry {
  lei: string;
  name: string;
  country: string;
  served: boolean;
  reason?: string;
}

export interface CoverageReport {
  served: number;
  rejected: number;
  by_country: Record<string, { served: number; rejected: Array<{ lei: string; name: string; reason: string }> }>;
  /** Markdown table: country, served, rejected. */
  table: string;
}

export function coverageReport(entries: CoverageEntry[]): CoverageReport {
  const by: CoverageReport["by_country"] = {};
  for (const e of entries) {
    const c = (by[e.country] ??= { served: 0, rejected: [] });
    if (e.served) c.served++;
    else c.rejected.push({ lei: e.lei, name: e.name, reason: e.reason ?? "unknown" });
  }
  const countries = Object.keys(by).sort();
  const table = ["| Country | Served | Rejected |", "|---|---|---|", ...countries.map((k) => `| ${k} | ${by[k]!.served} | ${by[k]!.rejected.length} |`)].join("\n");
  const served = entries.filter((e) => e.served).length;
  return { served, rejected: entries.length - served, by_country: Object.fromEntries(countries.map((k) => [k, by[k]!])), table };
}
