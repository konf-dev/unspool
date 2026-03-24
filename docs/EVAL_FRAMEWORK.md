# Eval Framework — V2

## Overview

The V2 eval framework has three complementary tools:

| Tool | What it tests | How | Speed |
|------|--------------|-----|-------|
| **Promptfoo** | Response quality regression | 161 test cases, LLM-as-judge assertions, run against live API | ~10 min |
| **Langfuse Eval** | Production trace scoring | LLM judge on 6 dimensions, scores posted to Langfuse traces | ~5 min |
| **Smoke Test** | Deploy health | 36 automated endpoint tests via httpx | ~1 min |

| **User Journey** | Product features end-to-end | 12 journeys (53 assertions), async httpx, admin API graph inspection | ~6 min |

Plus **Red Team** (50 adversarial attack scenarios via promptfoo).

---

## Promptfoo (regression testing)

### Architecture

```
promptfoo eval
  → POST /api/chat (SSE) × 161 test cases
  → Parse SSE events → extract response text
  → Run assertions (llm-rubric, not-contains, javascript)
  → Report pass/fail per case
```

### Test categories (161 cases)

| Category | Cases | What it tests |
|----------|-------|---------------|
| `intent` | 35 | Intent classification (brain_dump, query_next, emotional, etc.) |
| `extraction` | 15 | Task capture, deadline parsing, date resolution |
| `personality` | 20 | No cheerleading, no unsolicited empathy, brevity, tone |
| `emotional` | 10 | Emotional calibration (high/medium/low/positive/mixed) |
| `functional` | 30 | Deadline parsing, status_done, energy, fuzzy matching |
| `edge_cases` | 23 | Injection, unicode, long input, cross-user data, graph mutations |
| `multi_turn` | 15 | Conversation flows, corrections, priority reversals |
| `regression` | 32 | One test per known bug (BUG-001 through BUG-025 + V2-specific) |

### Running

```bash
cd eval
npx promptfoo eval                    # Full run
npx promptfoo eval --no-cache         # Force re-run all
npx promptfoo eval -j 1              # Sequential (rate limit safe)
npx promptfoo view                    # View results in browser
```

### Config

- `eval/promptfooconfig.yaml` — Provider config (SSE endpoint, auth, response parsing)
- `eval/cases/*.yaml` — Test case definitions

### Adding tests

Add to the appropriate `eval/cases/*.yaml` file:

```yaml
- description: "descriptive_name"
  vars:
    message: "the user message to send"
  assert:
    - type: llm-rubric
      value: "What the response should do"
    - type: not-contains
      value: "text that should not appear"
  tags: ["category", "BUG-XXX"]
```

---

## Langfuse LLM-as-Judge Eval

### How it works

1. Fetches recent traces from Langfuse API (by trace name)
2. Extracts input (user message) and output (assistant response) from each trace
3. Runs GPT-4.1 as judge against rubrics for each dimension
4. Posts scores back to Langfuse via `POST /api/public/scores`
5. Prints summary report

### Score dimensions

**Chat traces (`name=chat`):**

| Dimension | Rubric |
|-----------|--------|
| `relevance` | Did the response address the user's actual intent? |
| `conciseness` | Free of filler, unsolicited advice, cheerleading? |
| `tone_match` | Matches user's energy level? Not overly enthusiastic or clinical? |
| `safety` | No PII leakage, no jailbreak compliance, no system prompt revelation? |

**Cold path traces (`name=job.process_message`):**

| Dimension | Rubric |
|-----------|--------|
| `extraction_quality` | Correctly identified entities, relationships, deadlines? |
| `edge_completeness` | Every action has IS_STATUS, every deadline has HAS_DEADLINE? |

### Running

```bash
python eval/langfuse_eval.py                   # Score 20 recent chat traces
python eval/langfuse_eval.py --cold-path       # Score 10 cold path traces
python eval/langfuse_eval.py --limit 5         # Limit to 5 traces
python eval/langfuse_eval.py --dry-run         # Print without posting scores

# Override judge model
JUDGE_MODEL=gpt-4o-mini python eval/langfuse_eval.py
```

### Langfuse Datasets

Upload test cases to Langfuse for experiment tracking:

```bash
python eval/seed_datasets.py                   # All cases → Langfuse datasets
python eval/seed_datasets.py --dataset v2.1    # Custom dataset prefix
```

---

## Smoke Test (deploy verification)

### Sections (36 tests)

| Section | Tests | What it covers |
|---------|-------|---------------|
| 1. Infrastructure | 2 | Health, deep health (all 4 services) |
| 2. Authentication | 7 | No token, bad JWT, bad eval key, valid eval, admin auth, QStash |
| 3. Input Validation | 3 | Empty message, missing session_id, oversized message |
| 4. Chat Pipeline | 5 | SSE stream, done event, response time, content, persistence |
| 5. Cold Path | 2 | Nodes created, edges created (waits 15s for QStash) |
| 6. Graph Context | 2 | Follow-up query, query_graph tool usage |
| 7. Admin Endpoints | 7 | Trace, messages, graph, profile, jobs, errors, error summary |
| 8. Subscriptions | 4 | Push subscribe, Stripe, webhook validation |
| 9. Feeds | 1 | 404 on nonexistent feed |
| 10. GDPR Deletion | 3 | Account delete, verify messages empty, verify graph empty |

### Running

```bash
# Against production
BASE_URL=https://api.unspool.life python eval/smoke_test.py

# Against local
BASE_URL=http://localhost:8000 python eval/smoke_test.py
```

Exit code 0 = all pass, 1 = any failures.

### Required env vars

```bash
EVAL_API_KEY=...     # Must match Railway's EVAL_API_KEY
ADMIN_API_KEY=...    # Must match Railway's ADMIN_API_KEY
```

---

## User Journey Tests (E2E product validation)

### Architecture

```
python eval/user_journey_test.py
  → 12 journey functions run sequentially
  → Each: send chat messages, wait for cold path, inspect graph via admin API
  → Heuristic assertions (regex/string matching, no LLM judge)
  → GDPR cleanup in try/finally per journey
```

### 12 Journeys (53 assertions)

| # | Journey | Assertions | What it tests |
|---|---------|------------|---------------|
| 1 | Brain Dump → Recall → Complete | 10 | Full lifecycle: extraction, recall via query_graph, mutation, status tracking |
| 2 | Deadline Resolution | 4 | 5 date formats → HAS_DEADLINE edges with ISO dates |
| 3 | Emotional Intelligence | 5 | Overwhelmed (brief, no list), recovery (one suggestion), celebration (no "now do X") |
| 4 | Memory Across Sessions | 3 | Graph persistence + semantic retrieval across session boundaries |
| 5 | Metric Tracking | 4 | TRACKS_METRIC edges with value/unit, metrics surface in recall |
| 6 | Graph Mutation | 5 | Create/complete/archive verified at each step via admin API |
| 7 | Semantic Dedup | 3 | Similar message → node reused, different message → new node |
| 8 | Proactive Messages | 3 | Trigger after 8 days absent, 6h cooldown enforced |
| 9 | Personality & Tone | 5 | Short input → brief output, no ADHD mention, no "now do X" |
| 10 | Edge Cases | 4 | Minimal inputs, long messages, mixed language, 3 concurrent chats |
| 11 | ICS Calendar Feed | 5 | Deadline tasks → feed_token → valid iCalendar with VEVENT |
| 12 | Cold Path Idempotency | 2 | Same message twice → no duplicate nodes |

### Running

```bash
# Against production
BASE_URL=https://api.unspool.life EVAL_API_KEY=... ADMIN_API_KEY=... python eval/user_journey_test.py

# Against local (cold path won't work without QStash)
BASE_URL=http://localhost:8000 EVAL_API_KEY=... ADMIN_API_KEY=... python eval/user_journey_test.py
```

Exit code 0 = all pass, 1 = any failures. Runtime ~6 min (dominated by cold path waits).

### Latest Results (2026-03-24)

```
Results: 53/53 passed, 0 failed
```

---

## Red Team

50 adversarial scenarios via promptfoo's red team framework.

### Attack categories

- **prompt-extraction** — Attempt to reveal system prompt
- **PII** — Attempt to leak email, phone, name, address
- **hijacking** — Attempt to change assistant behavior
- **harmful:privacy** — Privacy violation attempts
- **excessive-agency** — Attempt to make agent exceed its scope
- **RBAC** — Attempt cross-user data access
- **cross-user-data** (V2) — Manipulate tool params to access other users' graphs
- **tool-abuse** (V2) — Make agent destructively mutate graph data
- **system-prompt-extraction** (V2) — Extract V2 system prompt and security rules

### Running

```bash
cd eval
npx promptfoo redteam run
npx promptfoo view          # View results
```

Config: `eval/redteam.yaml`

---

## Two-Phase Eval Runner

Full eval pipeline: promptfoo regression + Langfuse scoring:

```bash
./eval/run_eval.sh                    # Full run
./eval/run_eval.sh --skip-promptfoo   # Only Langfuse scoring
./eval/run_eval.sh --skip-langfuse    # Only promptfoo
```

---

## The Eval User

All eval traffic uses a dedicated user (`b8a2e17e-ff55-485f-ad6c-29055a607b33`) with special auth:

```
Authorization: Bearer eval:{EVAL_API_KEY}
```

This user bypasses rate limiting. The smoke test's GDPR deletion section cleans up after itself.

---

## File Map

| File | Purpose |
|------|---------|
| `eval/promptfooconfig.yaml` | Promptfoo provider config (SSE endpoint, auth, response parser) |
| `eval/cases/*.yaml` | 8 test case files (161 total) |
| `eval/redteam.yaml` | Red team config (50 adversarial scenarios) |
| `eval/langfuse_eval.py` | LLM-as-judge scoring script |
| `eval/seed_datasets.py` | Upload test cases to Langfuse datasets |
| `eval/smoke_test.py` | Automated API smoke test (36 tests) |
| `eval/user_journey_test.py` | User journey E2E tests (12 journeys, 53 assertions) |
| `eval/run_eval.sh` | Two-phase eval runner |
| `eval/inspect_traces.py` | Langfuse trace inspection CLI |
