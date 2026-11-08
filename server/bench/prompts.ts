// Frozen prompts for deskstack-bench. Changing any text here changes the benchmark: bump PROMPTS_VERSION and say so
// in bench/results/<run>/plan.json. The same system prompt and output contract go to every arm; only the tools differ.

export const PROMPTS_VERSION = "2";

export const SYSTEM = `You are a financial analyst building a first-draft model for a human reviewer.
Rules:
- Every number you type must come from a source you can name: a filing (with its accession or report), a data
  provider's tool result, or a stated assumption with its rationale. Put that source next to the number.
- Never invent a figure. If you can't find one, say so in its source ("not found") rather than guessing.
- State the currency and the scale (units, thousands, millions or billions) and use one scale throughout.
- Use the company's own fiscal-year labels (e.g. FY2025) for the last three filed fiscal years.
- Conventions: capex and D&A are positive numbers. EBITDA = operating income + D&A. Net debt = total debt (excluding
  lease liabilities) - cash - short-term investments. Diluted shares = weighted average diluted shares for the year.
- Each company's figures are in its own reporting currency (a 3-letter code).
When the model is ready, call submit_model once with the full model. If submit_model returns errors, fix them and
call it again.`;

export const ARM_NOTE: Record<"A" | "B" | "C", string> = {
  A: "Tools: web_search (public web pages). No other data source is available.",
  B: "Tools: the deskstack data tools (SEC and EU ESEF filings, rates, Damodaran inputs). Use them for every filed figure.",
  C: "Tools: the deskstack data tools (SEC and EU ESEF filings, rates, Damodaran inputs). Use them for every filed figure. After you submit, independent reviewers will check the model and you will get one chance to fix it.",
};

export function taskPrompt(task: "dcf" | "comps", name: string, id: string): string {
  if (task === "dcf") {
    return `Build a quick unlevered DCF for ${name} (identifier: ${id}).
- History: revenue, operating income (EBIT), D&A and capex for the last three filed fiscal years.
- Five projected years with your assumptions: revenue growth per year, EBIT margin, tax rate, D&A and capex as % of
  revenue, WACC and terminal growth, each with its rationale as the source.
- Bridge: net debt and diluted shares at the last fiscal year end (shares in the same scale as the money figures).
Submit it with submit_model, kind "dcf".`;
  }
  return `Build a trading comparables table for ${name} (identifier: ${id}) with 4 to 6 listed peers.
- For the target and each peer: revenue, EBITDA, net income and net debt for the last filed fiscal year (or LTM if
  you state it), each in that company's reporting currency, each with its source and period.
- Market cap for each: use any source you can cite (market caps are not scored).
- If a figure isn't available for a peer, replace that peer rather than leaving the figure empty.
Submit it with submit_model, kind "comps".`;
}

const num = { type: ["number", "null"] } as const;
const sourced = { type: "object", properties: { value: num, source: { type: "string" }, period: { type: "string" } }, required: ["value", "source"] };
const series = { type: "object", properties: { values: { type: "array", items: num }, source: { type: "string" } }, required: ["values", "source"] };

/** The output contract: deskstack's builder spec (checker/deskstack_check/build.py). Validation errors come back to the model. */
export const SUBMIT_TOOL = {
  name: "submit_model",
  description:
    "Submit the finished model. kind 'dcf': company, ticker (or LEI), currency, scale, history {periods, lines {revenue, operating_income, d_and_a, capex}}, assumptions {projection_labels, revenue_growth, ebit_margin, tax_rate, da_pct_revenue, capex_pct_revenue, wacc, terminal_growth, mid_year}, bridge {net_debt, diluted_shares}. kind 'comps': target (ticker or LEI), currency, scale, period, peers [{name, ticker, currency, revenue, ebitda, net_income, market_cap, net_debt}]. Every number is {value, source} (history lines are {values: [one per period], source}); rates are decimals (0.09 = 9%). Returns 'accepted' or the errors to fix.",
  input_schema: {
    type: "object",
    properties: {
      kind: { type: "string", enum: ["dcf", "comps"] },
      company: { type: "string" },
      ticker: { type: "string" },
      target: { type: "string" },
      currency: { type: "string" },
      scale: { type: "string", enum: ["units", "thousands", "millions", "billions"] },
      period: { type: "string" },
      history: {
        type: "object",
        properties: {
          periods: { type: "array", items: { type: "string" } },
          lines: { type: "object", properties: { revenue: series, operating_income: series, d_and_a: series, capex: series } },
        },
      },
      assumptions: {
        type: "object",
        properties: {
          projection_labels: { type: "array", items: { type: "string" } },
          revenue_growth: series,
          ebit_margin: sourced,
          tax_rate: sourced,
          da_pct_revenue: sourced,
          capex_pct_revenue: sourced,
          wacc: sourced,
          terminal_growth: sourced,
          mid_year: { type: "boolean" },
        },
      },
      bridge: { type: "object", properties: { net_debt: sourced, diluted_shares: sourced } },
      peers: {
        type: "array",
        items: {
          type: "object",
          properties: {
            name: { type: "string" },
            ticker: { type: "string" },
            currency: { type: "string", pattern: "^[A-Z]{3}$" },
            revenue: sourced,
            ebitda: sourced,
            net_income: sourced,
            market_cap: sourced,
            net_debt: sourced,
          },
          required: ["name", "ticker", "currency", "revenue", "ebitda", "net_income", "market_cap", "net_debt"],
        },
      },
    },
    required: ["kind", "currency", "scale"],
  },
} as const;
