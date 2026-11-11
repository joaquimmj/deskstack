// Per-country coverage of the European snapshot: issuers served, and those rejected with the reason (stars brief lot 2 bis).

import { describe, expect, it } from "vitest";
import { coverageReport } from "../src/esef/coverage";

describe("European coverage report", () => {
  it("counts served and rejected issuers per country, with each rejection's reason", () => {
    const r = coverageReport([
      { lei: "A", name: "Alpha", country: "FR", served: true },
      { lei: "B", name: "Beta", country: "FR", served: false, reason: "no annual report on filings.xbrl.org" },
      { lei: "C", name: "Gamma", country: "NL", served: true },
    ]);
    expect(r.served).toBe(2);
    expect(r.rejected).toBe(1);
    expect(r.by_country.FR).toEqual({ served: 1, rejected: [{ lei: "B", name: "Beta", reason: "no annual report on filings.xbrl.org" }] });
    expect(r.by_country.NL).toEqual({ served: 1, rejected: [] });
    expect(r.table).toContain("| FR | 1 | 1 |");
  });
});
