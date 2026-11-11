// server.json for the official MCP Registry (format read 2026-11-10 from modelcontextprotocol/registry docs:
// quickstart.mdx, remote-servers.mdx, server.schema.json 2025-12-11). Publishing is a manual, public step.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { VERSION } from "../src/config";

const s = JSON.parse(readFileSync(join(import.meta.dirname, "..", "..", "server.json"), "utf8"));

describe("MCP Registry server.json", () => {
  it("follows the 2025-12-11 schema's rules for a remote-only server", () => {
    expect(s.$schema).toBe("https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json");
    expect(s.name).toMatch(/^io\.github\.joaquimmj\/[a-zA-Z0-9._-]+$/); // GitHub auth namespace
    expect(s.description.length).toBeGreaterThan(0);
    expect(s.description.length).toBeLessThanOrEqual(100); // hard validation limit
    expect(s.title.length).toBeLessThanOrEqual(100);
    expect(s.packages).toBeUndefined();
    expect(s.remotes).toEqual([{ type: "streamable-http", url: "https://deskstack.deskstack-server.workers.dev/mcp" }]);
    expect(s.repository).toMatchObject({ url: "https://github.com/joaquimmj/deskstack", source: "github" });
  });

  it("carries the server's version", () => {
    expect(s.version).toBe(VERSION);
  });
});
