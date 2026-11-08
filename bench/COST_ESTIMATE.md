# deskstack-bench: API cost estimate

Status: **nothing spent yet.** 2026-11-08: the owner approved the pilot (step 1 below: Sonnet 5.5, hard cap $20). The main
run (step 2) needs its own approval once the pilot has measured the real cost. Budget available: $100 of Claude API credits.

## What one full run is

- 50 companies (≈35 US, 15 EU) × 2 tasks (quick DCF, comps table) = 100 company-tasks.
- 3 arms per company-task:
  - **A** Claude + web search only;
  - **B** Claude + deskstack data tools;
  - **C** B, then `/associate` and `/vp-review` in fresh contexts, then a fix pass.
- 300 agentic runs in all. Scoring (`verify_value`, the checker, edgartools/Arelle oracles) runs locally or on our
  free Worker: **$0 of API spend**.

## Prices used

List prices from the Claude API reference, cached 2026-10-06. Re-check them on the live pricing page before any
run.

| Model | Input | Output | 5-min cache write | Cache read |
|---|---|---|---|---|
| Sonnet 5.5 | $2 | $10 | $2.50 | $0.20 |
| Opus 5.5 | $4 | $20 | $5 | $0.20 |
| Haiku 5.5 | $0.10 | $0.50 | $0.125 | ≈ $0.01 |

All prices are per million tokens. Web search costs $10 per 1,000 searches. Thinking tokens bill as output.

## Token model

Each run is an agentic loop with prompt caching: every turn writes its new context to the cache once, then reads
the cached prefix on every later turn.

| Scenario | Arm A (web) | Arm B (deskstack) | Arm C reviewers + fix (on top of B) |
|---|---|---|---|
| low | 8 turns, +6k ctx/turn, 8k out, 5 searches | 8 turns, +3k/turn, 8k out | 10 turns, +3k/turn, 10k out |
| mid | 12 turns, +8k/turn, 15k out, 8 searches | 12 turns, +4k/turn, 15k out | 16 turns, +4k/turn, 20k out |
| high | 20 turns, +10k/turn, 30k out, 15 searches | 20 turns, +5k/turn, 30k out | 24 turns, +5k/turn, 40k out |

Arm A grows its context fastest because search results are bulky. Arm B's tool results are compact JSON.

## Cost

| Model | Scenario | Per company-task (A+B+C) | Pilot (10 company-tasks) | Full run (100) |
|---|---|---|---|---|
| Sonnet 5.5 | low | $0.93 | $9 | $93 |
| Sonnet 5.5 | **mid** | **$1.85** | **$19** | **$185** |
| Sonnet 5.5 | high | $4.04 | $40 | $404 |
| Opus 5.5 | mid | $3.23 | $32 | $323 |
| Haiku 5.5 | mid | $0.17 | $2 | $17 |

**At the mid estimate, a full 300-run benchmark on Sonnet 5.5 costs about twice the budget. Opus 5.5 is out of
reach.** Haiku 5.5 fits easily, but "a small model makes mistakes" is a weak headline.

## Recommended plan (fits $100)

1. **Pilot, hard cap $20.**
   - Scope: 5 companies (3 US, 2 EU) × 2 tasks × 3 arms on Sonnet 5.5, 30 runs, expected $9–19.
   - The runner reads `usage` after every request and stops at the cap.
   - The pilot measures the real cost per run and shakes out the runner and scoring before the main run spends
     anything.
2. **Main run, sized to what is left (≈ $80)**, using the measured cost per company-task (call it `m`):
   - if `m` ≤ $0.80: the full 50 × 2 × 3;
   - if `m` ≤ $1.60: 50 companies × DCF only × 3 arms;
   - otherwise: 25 companies × 2 tasks × 3 arms.

   The pilot's 5 companies count toward the 50. The company list is frozen before the pilot.
3. **Cost levers in the runner:**
   - a cap of 30 requests and $1.50 per run;
   - a deterministic review in arm C (verify_value and the checker, no reviewer model), cheaper than the reviewer runs
     assumed above;
   - effort `medium` on Sonnet 5.5;
   - a frozen system prompt and tool list so the cache prefix never breaks;
   - no retries of a whole run; a failed run is reported as failed.

The Batch API's 50% discount doesn't fit multi-turn tool loops well (every turn would wait for a batch), so the
plan leaves it out.

## Who does what

- The owner sets the API key in their own shell (`ANTHROPIC_API_KEY`). It is never pasted in chat or committed.
- Every run's raw output, token usage and dollar cost lands in `bench/results/` (brief §8.2: reproducible, honest
  reporting).
