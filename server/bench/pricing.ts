// List prices (USD per million tokens) used to track spend while the benchmark runs.
// Source: Claude API reference (cached 2026-10-06). Re-check https://platform.claude.com/docs/en/about-claude/pricing
// before a paid run; the runner prints the prices it uses.

export interface Price {
  input: number;
  output: number;
  cacheWrite5m: number;
  cacheRead: number;
}

export const PRICES: Record<string, Price> = {
  "claude-sonnet-5-5": { input: 2, output: 10, cacheWrite5m: 2.5, cacheRead: 0.2 },
  "claude-opus-5-5": { input: 4, output: 20, cacheWrite5m: 5, cacheRead: 0.2 },
  "claude-haiku-5-5": { input: 0.1, output: 0.5, cacheWrite5m: 0.125, cacheRead: 0.01 },
};
export const WEB_SEARCH_PER_REQUEST = 0.01; // $10 per 1,000 searches

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  cache_creation_input_tokens?: number | null;
  cache_read_input_tokens?: number | null;
  server_tool_use?: { web_search_requests?: number | null } | null;
}

export function cost(model: string, u: Usage): number {
  const p = PRICES[model];
  if (!p) throw new Error(`No price for ${model}: add it to bench/pricing.ts before running`);
  return (
    (u.input_tokens * p.input +
      u.output_tokens * p.output +
      (u.cache_creation_input_tokens ?? 0) * p.cacheWrite5m +
      (u.cache_read_input_tokens ?? 0) * p.cacheRead) /
      1e6 +
    (u.server_tool_use?.web_search_requests ?? 0) * WEB_SEARCH_PER_REQUEST
  );
}

export function addUsage(a: Usage, b: Usage): Usage {
  return {
    input_tokens: a.input_tokens + b.input_tokens,
    output_tokens: a.output_tokens + b.output_tokens,
    cache_creation_input_tokens: (a.cache_creation_input_tokens ?? 0) + (b.cache_creation_input_tokens ?? 0),
    cache_read_input_tokens: (a.cache_read_input_tokens ?? 0) + (b.cache_read_input_tokens ?? 0),
    server_tool_use: { web_search_requests: (a.server_tool_use?.web_search_requests ?? 0) + (b.server_tool_use?.web_search_requests ?? 0) },
  };
}

export const ZERO: Usage = { input_tokens: 0, output_tokens: 0 };

/** The most one request can cost: every input token billed as a cache write (nothing cached), the full max_tokens
 * of output, and every allowed web search. Used to refuse a request that could cross the cap. */
export function requestBound(model: string, inputTokens: number, maxTokens: number, maxSearches: number): number {
  const p = PRICES[model];
  if (!p) throw new Error(`No price for ${model}`);
  return (inputTokens * Math.max(p.input, p.cacheWrite5m) + maxTokens * p.output) / 1e6 + maxSearches * WEB_SEARCH_PER_REQUEST;
}

/** Spending cap shared by every run, persisted after each request so a crash and a re-run can't start again from $0. */
export class Budget {
  spent: number;
  constructor(
    readonly cap: number,
    private readonly ledger?: { read(): number; write(total: number): void },
  ) {
    this.spent = ledger ? ledger.read() : 0;
  }
  /** True when a request costing up to `bound` could cross the cap. */
  wouldExceed(bound: number): boolean {
    return this.spent + bound > this.cap;
  }
  charge(c: number) {
    this.spent += c;
    this.ledger?.write(this.spent);
  }
}
