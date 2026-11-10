// What a user sees when the shared server says no: what happened, when it comes back, how to self-host (stars brief lot 7).

import { describe, expect, it } from "vitest";
import { SELF_HOST_URL } from "../src/config";
import { capacityMessage, rateMessage } from "../src/guard";

describe("limit messages", () => {
  it("the daily cap says it is used up, when it resets and how long that is, and links self-hosting", () => {
    const m = capacityMessage(Date.parse("2026-11-10T16:48:30Z"));
    expect(m).toMatch(/free daily capacity is used up/);
    expect(m).toMatch(/resets at 00:00 UTC, in 7 h 12 min/);
    expect(m).toContain(SELF_HOST_URL);
  });

  it("just before midnight it says less than a minute", () => {
    expect(capacityMessage(Date.parse("2026-11-10T23:59:40Z"))).toMatch(/in less than a minute/);
  });

  it("the per-IP limit says what the limit is, when to retry, and links self-hosting", () => {
    const m = rateMessage(60);
    expect(m).toMatch(/more than 60 requests in a minute from your network/);
    expect(m).toMatch(/Retry in a minute/);
    expect(m).toContain(SELF_HOST_URL);
  });
});
