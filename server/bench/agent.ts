// One benchmark run: one company, one task, one arm. A manual agentic loop: before each request the worst case it
// could cost is checked against the budget and the per-run cap, so the cap is never crossed.
//   A: web_search only.   B: the deskstack connector's tools (and its MCP instructions, as real clients get).
//   C: B, then one review round (the associate's tie-out with verify_value and the VP's checker findings) and a fix.

import Anthropic from "@anthropic-ai/sdk";
import type { Connector } from "./connector";
import { addUsage, cost, requestBound, type Budget, type Usage, ZERO } from "./pricing";
import { ARM_NOTE, SUBMIT_TOOL, SYSTEM, taskPrompt } from "./prompts";
import { buildWorkbook, checkWorkbook } from "./pytools";
import { itemsOf, verify } from "./score";

export type Arm = "A" | "B" | "C";
export type Task = "dcf" | "comps";

/** The slice of the SDK client the loop uses, so tests can script the model. Construct the real one with
 * maxRetries: 0 — this loop retries only what isn't billed (429, 529) and counts everything else. */
export interface MessagesClient {
  messages: { create(params: Anthropic.MessageCreateParamsNonStreaming): Promise<Anthropic.Message> };
}

export interface RunOptions {
  client: MessagesClient;
  connector: Connector;
  budget: Budget;
  model: string;
  effort: "low" | "medium" | "high";
  company: { id: string; name: string };
  task: Task;
  arm: Arm;
  workdir: string;
  maxRequests?: number;
  maxRunCost?: number;
  webSearchMaxUses?: number;
  maxTokens?: number;
  sleep?: (ms: number) => Promise<void>;
}

export interface RunResult {
  status: "submitted" | "no_submission" | "budget" | "run_cap" | "error";
  error?: string;
  submission: Record<string, unknown> | null;
  first_submission: Record<string, unknown> | null; // arm C: before the review
  submit_attempts: number;
  requests: number;
  usage: Usage;
  cost: number;
  seconds: number;
  tool_calls: Record<string, number>;
  review?: string;
  transcript: unknown[];
}

const MAX_TOOL_TEXT = 30_000;
const CHARS_PER_TOKEN = 3; // conservative (real text is ~3.5-4): over-estimates the request bound

function toolsFor(arm: Arm, connectorTools: Anthropic.Tool[], maxUses: number): Anthropic.Messages.ToolUnion[] {
  const submit = SUBMIT_TOOL as unknown as Anthropic.Tool;
  if (arm === "A") return [{ type: "web_search_20260209", name: "web_search", max_uses: maxUses }, submit];
  return [...connectorTools, submit];
}

export async function connectorTools(c: Connector): Promise<Anthropic.Tool[]> {
  // Sorted, so the tool list (part of the cached prefix) is identical on every request.
  return (await c.listTools())
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((t) => ({ name: t.name, description: t.description ?? "", input_schema: t.inputSchema as Anthropic.Tool.InputSchema }));
}

function clip(text: string): string {
  return text.length > MAX_TOOL_TEXT ? `${text.slice(0, MAX_TOOL_TEXT)}\n[truncated: ${text.length - MAX_TOOL_TEXT} more characters]` : text;
}

/** For the committed transcript: drop the encrypted page payloads web search returns (keep URL and title). */
function forLog(content: unknown): unknown {
  return JSON.parse(JSON.stringify(content, (k, v) => (k === "encrypted_content" || k === "encrypted_index" ? "[omitted]" : v)));
}

async function review(o: RunOptions, spec: Record<string, unknown>): Promise<string> {
  const { items } = itemsOf(spec, o.company);
  const v = await verify(o.connector, items);
  const bad = v.filter((x) => x.status !== "match");
  const lines = [
    `Associate (tie-out with verify_value): ${v.length - bad.length} of ${v.length} filed figures match the filings.`,
    ...bad.map((x) => `- ${x.ref} (${x.metric} ${x.period}) = ${x.value}: ${x.status}${x.hints?.length ? `. ${x.hints.join(" ")}` : ""}`),
  ];
  const wb = buildWorkbook(spec, `${o.workdir}/review`);
  if (wb.ok) {
    const c = checkWorkbook(wb.path);
    const serious = c.findings.filter((f) => f.severity === "blocker" || f.severity === "major");
    lines.push("", `VP review (deterministic checker): ${c.counts.blocker ?? 0} blocker, ${c.counts.major ?? 0} major.`);
    for (const f of serious) lines.push(`- ${f.rule} ${f.ref}: ${f.message}`);
  }
  lines.push("", "Fix what is wrong (check each figure against its filing), then call submit_model again with the full corrected model.");
  return lines.join("\n");
}

function chars(x: unknown): number {
  return typeof x === "string" ? x.length : JSON.stringify(x).length;
}

export async function runOne(o: RunOptions): Promise<RunResult> {
  const t0 = Date.now();
  const sleep = o.sleep ?? ((ms: number) => new Promise((r) => setTimeout(r, ms)));
  const res: RunResult = { status: "no_submission", submission: null, first_submission: null, submit_attempts: 0, requests: 0, usage: ZERO, cost: 0, seconds: 0, tool_calls: {}, transcript: [] };
  const maxUses = o.webSearchMaxUses ?? 12;
  const maxTokens = o.maxTokens ?? 16000;
  const maxRequests = o.maxRequests ?? 30;
  const maxRunCost = o.maxRunCost ?? 1.5;
  let tools: Anthropic.Messages.ToolUnion[];
  let system = SYSTEM;
  try {
    tools = toolsFor(o.arm, o.arm === "A" ? [] : await connectorTools(o.connector), maxUses);
    if (o.arm !== "A") {
      const ins = await o.connector.instructions();
      if (ins) system = `${SYSTEM}\n\nInstructions from the deskstack data server:\n${ins}`;
    }
  } catch (e) {
    return finish("error", `connector unavailable: ${String((e as Error).message ?? e)}`);
  }
  const messages: Anthropic.MessageParam[] = [{ role: "user", content: `${ARM_NOTE[o.arm]}\n\n${taskPrompt(o.task, o.company.name, o.company.id)}` }];
  res.transcript.push({ role: "user", content: messages[0]!.content });
  let inputEstimate = Math.ceil((chars(system) + chars(tools) + chars(messages)) / CHARS_PER_TOKEN);
  let reviewed = o.arm !== "C";
  let nudges = 0;
  let rejections = 0;
  const searches = o.arm === "A" ? maxUses : 0;

  const pushUser = (content: Anthropic.MessageParam["content"]) => {
    messages.push({ role: "user", content });
    res.transcript.push({ role: "user", content: forLog(content) });
    inputEstimate += Math.ceil(chars(content) / CHARS_PER_TOKEN);
  };

  try {
    while (true) {
      const bound = requestBound(o.model, inputEstimate, maxTokens, searches);
      if (o.budget.wouldExceed(bound)) return finish("budget");
      if (res.requests >= maxRequests || res.cost + bound > maxRunCost) return finish("run_cap");
      let response: Anthropic.Message | undefined;
      for (let attempt = 0; ; attempt++) {
        try {
          response = await o.client.messages.create({
            model: o.model,
            max_tokens: maxTokens,
            system,
            tools,
            messages,
            cache_control: { type: "ephemeral" },
            output_config: { effort: o.effort },
          } as Anthropic.MessageCreateParamsNonStreaming);
          break;
        } catch (e) {
          const status = (e as { status?: number }).status;
          if ((status === 429 || status === 529) && attempt < 3) {
            await sleep(15_000 * (attempt + 1)); // rate limited or overloaded: not billed, wait and retry
            continue;
          }
          if (e instanceof Anthropic.APIConnectionError || status === undefined || status >= 500) {
            // A timeout or a dropped connection may still be billed: count the worst case.
            res.cost += bound;
            o.budget.charge(bound);
          }
          throw e;
        }
      }
      res.requests++;
      const c = cost(o.model, response.usage);
      res.cost += c;
      res.usage = addUsage(res.usage, response.usage);
      o.budget.charge(c);
      inputEstimate = response.usage.input_tokens + (response.usage.cache_read_input_tokens ?? 0) + (response.usage.cache_creation_input_tokens ?? 0) + response.usage.output_tokens;
      res.transcript.push({ role: "assistant", request: res.requests, stop_reason: response.stop_reason, usage: response.usage, cost: c, content: forLog(response.content) });
      messages.push({ role: "assistant", content: response.content });
      if (response.stop_reason === "pause_turn") continue;
      if (response.stop_reason === "refusal") return finish("error", "the model refused");
      const uses = response.content.filter((b): b is Anthropic.ToolUseBlock => b.type === "tool_use");
      if (response.stop_reason === "max_tokens") {
        // A cut-off tool input can parse as a valid but partial object: never run it.
        if (uses.length) pushUser(uses.map((u) => ({ type: "tool_result" as const, tool_use_id: u.id, content: "Your output was cut off by the length limit, so this call was not run. Send it again in full, with less text around it.", is_error: true })));
        else pushUser("Your reply was cut off by the length limit. Continue, and call submit_model with the complete model.");
        continue;
      }
      if (!uses.length) {
        if (nudges++ >= 2) return finish(res.submission ? "submitted" : "no_submission");
        pushUser("Call submit_model now with the complete model.");
        continue;
      }
      const results: Anthropic.ToolResultBlockParam[] = [];
      let accepted: Record<string, unknown> | null = null;
      for (const u of uses) {
        res.tool_calls[u.name] = (res.tool_calls[u.name] ?? 0) + 1;
        if (u.name === "submit_model") {
          res.submit_attempts++;
          const spec = u.input as Record<string, unknown>;
          const wrongKind = spec?.kind !== o.task ? `this task needs kind "${o.task}", not "${String(spec?.kind)}"` : null;
          const wb = wrongKind ? { ok: false as const, error: wrongKind } : buildWorkbook(spec, `${o.workdir}/attempt-${res.submit_attempts}`);
          if (wb.ok) {
            accepted = spec;
            rejections = 0;
            results.push({ type: "tool_result", tool_use_id: u.id, content: "accepted" });
          } else {
            rejections++;
            results.push({ type: "tool_result", tool_use_id: u.id, content: `Not accepted: ${wb.error}`, is_error: true });
          }
          continue;
        }
        try {
          const r = await o.connector.call(u.name, (u.input ?? {}) as Record<string, unknown>);
          results.push({ type: "tool_result", tool_use_id: u.id, content: clip(r.text), ...(r.isError ? { is_error: true } : {}) });
        } catch (e) {
          results.push({ type: "tool_result", tool_use_id: u.id, content: `Tool error: ${String((e as Error).message ?? e)}`, is_error: true });
        }
      }
      if (accepted) {
        res.submission = accepted;
        res.first_submission ??= accepted;
        if (reviewed) return finish("submitted");
        reviewed = true;
        nudges = 0; // the fix round gets its own nudges
        try {
          res.review = await review(o, accepted);
        } catch (e) {
          res.review = `review failed: ${String((e as Error).message ?? e)}`;
          return finish("submitted");
        }
        pushUser([...results, { type: "text", text: `Independent review of your model:\n\n${res.review}` }]);
        continue;
      }
      if (rejections >= 4) return finish(res.submission ? "submitted" : "no_submission", "submit_model rejected 4 times in a row");
      pushUser(results);
    }
  } catch (e) {
    return finish("error", String((e as Error).message ?? e));
  }

  function finish(status: RunResult["status"], error?: string): RunResult {
    res.status = status === "budget" || status === "run_cap" || status === "error" ? status : res.submission ? "submitted" : status;
    if (error) res.error = error;
    res.seconds = (Date.now() - t0) / 1000;
    return res;
  }
}
