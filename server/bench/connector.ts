// The deskstack connector as the benchmark sees it: list its tools, call one. Over MCP to a URL, or any stand-in
// with the same shape (tests use the Worker in-process).

import { Client, StreamableHTTPClientTransport } from "@modelcontextprotocol/client";

export interface ToolDef {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
}
export interface ToolResult {
  isError: boolean;
  text: string;
}
export interface Connector {
  /** The server's MCP instructions, which real MCP clients put in front of the model. */
  instructions(): Promise<string>;
  listTools(): Promise<ToolDef[]>;
  call(name: string, args: Record<string, unknown>): Promise<ToolResult>;
  close(): Promise<void>;
}

export async function mcpConnector(url: string): Promise<Connector> {
  const client = new Client({ name: "deskstack-bench", version: "1.0.0" });
  await client.connect(new StreamableHTTPClientTransport(new URL(url)));
  return {
    async instructions() {
      return client.getInstructions?.() ?? "";
    },
    async listTools() {
      const { tools } = await client.listTools();
      return tools.map((t) => ({ name: t.name, description: t.description, inputSchema: t.inputSchema as Record<string, unknown> }));
    },
    async call(name, args) {
      const r = await client.callTool({ name, arguments: args });
      const text = (r.content as Array<{ type: string; text?: string }>).map((c) => c.text ?? "").join("\n");
      return { isError: !!r.isError, text };
    },
    close: () => client.close(),
  };
}
