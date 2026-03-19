# Eval Framework — How It Works

## Overview

The eval framework tests Unspool end-to-end against the **live Railway deployment**. No mocks, no simulations — it sends real messages as a real user and checks what actually happened.

There are two layers of evals:

| Layer | What it tests | How |
|-------|--------------|-----|
| **Layer 1** (response quality) | Does the response *sound right*? | LLM-as-judge on response text |
| **Layer 2** (product behavior) | Does the agent *do the right thing*? | Tool call assertions + LLM judge |

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Phase 1: Send Messages                              │
│                                                      │
│  pytest fixture (session-scoped)                     │
│    ├─ DELETE /admin/eval-cleanup (clear old data)    │
│    ├─ POST /api/chat × 25 scenarios (sequential)    │
│    │    auth: Bearer eval:{EVAL_API_KEY}             │
│    │    → parse SSE stream → response + tool names   │
│    │    → capture X-Trace-Id header                  │
│    └─ store: {scenario_id → EvalResult}              │
├──────────────────────────────────────────────────────┤
│  Wait 45 seconds (Langfuse ingestion)                │
├──────────────────────────────────────────────────────┤
│  Phase 2: Fetch Langfuse Traces                      │
│                                                      │
│  For each EvalResult:                                │
│    ├─ GET /api/public/traces?sessionId={trace_id}    │
│    ├─ GET /api/public/observations/{obs_id}          │
│    │    → find agent.run → extract tool_calls_made   │
│    └─ mutate EvalResult: add tool_calls + args       │
├──────────────────────────────────────────────────────┤
│  Phase 3: Evaluate (per-scenario pytest tests)       │
│                                                      │
│  For each scenario:                                  │
│    ├─ Deterministic tool assertions (free, instant)  │
│    │    → was the right tool called?                 │
│    │    → did args contain expected values?           │
│    ├─ Ollama LLM judge (local, no API cost)          │
│    │    → response_must / response_must_not criteria │
│    ├─ Save JSON report to tests/eval/results/        │
│    └─ POST scores to Langfuse trace                  │
└──────────────────────────────────────────────────────┘
```

## Why Two Phases?

Langfuse ingests traces asynchronously — the trace data isn't available the instant the API responds. Instead of polling per-scenario (slow, flaky), we:

1. Fire all 25 messages first (takes ~2-3 minutes)
2. Wait 45 seconds for Langfuse to catch up
3. Batch-fetch all traces in one pass

This is faster and more reliable than per-message polling.

## What Gets Tested

### Tool Assertions (deterministic)

Each scenario can define `tool_assertions` — checks on what tools the agent called and with what arguments. These are checked from two sources:

- **SSE stream**: `tool_status` events tell us which tools ran (name only, no args)
- **Langfuse traces**: The `agent.run` observation stores full `tool_calls_made` including args and results

Example assertion:
```json
{
  "tool": "schedule_action",
  "args_contain": {"rrule": "FREQ=DAILY"},
  "args_present": ["action_type"]
}
```

This checks:
- `schedule_action` was called (by name — checked via SSE + Langfuse)
- The `rrule` arg contains "FREQ=DAILY" (substring, case-insensitive — Langfuse only)
- The `action_type` arg exists (Langfuse only)

If Langfuse data isn't available (ingestion delay), tool presence is still verified via SSE.

### Response Quality (LLM judge)

Each scenario defines `response_must` and `response_must_not` criteria. These are evaluated by a local Ollama model (`qwen2.5-coder:32b` by default) acting as a strict judge.

The judge returns `{"pass": true/false, "reason": "..."}` for each criterion.

## The Eval User

The framework uses a dedicated eval user (`b8a2e17e-ff55-485f-ad6c-29055a607b33`) with special auth:

```
Authorization: Bearer eval:{EVAL_API_KEY}
```

This user:
- Bypasses rate limiting (no daily message cap)
- Gets cleaned up before each eval run (all messages, items, usage deleted)
- Has its own user profile in the database

## Langfuse Integration

### Trace Structure

Each chat message creates this Langfuse trace tree:

```
chat:{trace_id[:8]} (trace)
  └── agent.run (span) — full agent loop
        ├── agent.assemble_context (span) — DB fetches, profile load
        ├── tool.execute: schedule_action (span) — input: {args}, output: {result}
        └── tool.execute: log_entry (span) — input: {args}, output: {result}
```

Each span has automatic start/end timestamps, so you can see timing for every step.

### Eval Scores on Traces

After judging, the framework posts two scores back to the Langfuse trace:
- `eval_tool_assertions` (boolean): did all tool assertions pass?
- `eval_judge_score` (numeric 0-1): what % of judge criteria passed?

These show up in the Langfuse dashboard on each trace, so you can see eval results alongside production usage.

### Trace Correlation

The app's `X-Trace-Id` response header maps to Langfuse's `sessionId` field. The runner finds traces via:

```
GET /api/public/traces?sessionId={our_trace_id}
```

Then fetches individual observations to find the `agent.run` span with tool call data.

## Running Evals

### Prerequisites

```bash
# These are on Railway — pull them with:
export EVAL_API_KEY=$(railway variables --json | python3 -c "import sys,json; print(json.load(sys.stdin)['EVAL_API_KEY'])")
export ADMIN_API_KEY=$(railway variables --json | python3 -c "import sys,json; print(json.load(sys.stdin)['ADMIN_API_KEY'])")
export LANGFUSE_HOST=$(railway variables --json | python3 -c "import sys,json; print(json.load(sys.stdin)['LANGFUSE_HOST'])")
export LANGFUSE_PUBLIC_KEY=$(railway variables --json | python3 -c "import sys,json; print(json.load(sys.stdin)['LANGFUSE_PUBLIC_KEY'])")
export LANGFUSE_SECRET_KEY=$(railway variables --json | python3 -c "import sys,json; print(json.load(sys.stdin)['LANGFUSE_SECRET_KEY'])")

# Ollama must be running with the judge model
ollama list  # should show qwen2.5-coder:32b
```

### Commands

```bash
cd backend

# Run product behavior evals (25 scenarios, ~5 min)
pytest tests/eval/test_product_behavior.py --eval -v --timeout=600

# Run with a specific tag filter
pytest tests/eval/test_product_behavior.py --eval --eval-tag=tracking -v

# Run a single scenario
pytest tests/eval/test_product_behavior.py --eval -k "track_cigarettes_daily" -v

# Check results
cat tests/eval/results/track_cigarettes_daily.json | python -m json.tool

# Generate summary report
python -m tests.eval.report
```

### Override judge model

```bash
EVAL_JUDGE_MODEL=qwen2.5:7b pytest tests/eval/test_product_behavior.py --eval -v
```

## Adding New Scenarios

Add to `backend/tests/eval/scenarios/product_behavior.json`:

```json
{
  "id": "unique_snake_case_id",
  "conversation": [
    {"role": "user", "content": "the actual message to send"}
  ],
  "tool_assertions": [
    {
      "tool": "tool_name",
      "args_contain": {"key": "substring_match"},
      "args_present": ["required_arg_key"]
    }
  ],
  "response_must": ["what the response should do"],
  "response_must_not": ["what the response should NOT do"],
  "tags": ["category", "p0"]
}
```

### tool_one_of

When multiple tools are acceptable (e.g. `save_event` OR `schedule_action` for recurring events):

```json
{
  "tool_one_of": ["save_event", "schedule_action"],
  "args_contain": {"rrule": "FREQ=MONTHLY"}
}
```

## File Map

| File | Purpose |
|------|---------|
| `tests/eval/runner.py` | HTTP client, SSE parser, Langfuse fetcher, score poster |
| `tests/eval/judge.py` | Ollama LLM-as-judge (OpenAI-compatible API) |
| `tests/eval/conftest.py` | pytest config, fixtures, CLI options |
| `tests/eval/report.py` | Aggregates results into summary |
| `tests/eval/scenarios/*.json` | Test scenario definitions |
| `tests/eval/results/*.json` | Per-scenario result files (gitignored) |
| `tests/eval/test_product_behavior.py` | Layer 2: tool assertions + judge |
| `tests/eval/test_conversation_quality.py` | Layer 1: response quality |
| `tests/eval/test_personality.py` | Layer 1: personality/voice |
| `tests/eval/test_emotional.py` | Layer 1: emotional intelligence |
| `tests/eval/test_safety.py` | Layer 1: safety boundaries |
| `src/agent/loop.py` | Langfuse instrumentation (@observe on agent + tools) |
| `src/api/chat.py` | Trace metadata (name, tags, session_id) |
