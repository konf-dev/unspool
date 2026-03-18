# Eval Framework

Black-box evaluation suite that tests the production API at `api.unspool.life`. Two layers: **promptfoo** for LLM response quality (169 cases + 50 redteam) and **pytest** for DB side-effects and contract verification (~26 cases).

---

## Architecture

```
eval/
├── promptfooconfig.yaml     # Main config — provider, defaults, test file refs
├── redteam.yaml             # Security/adversarial test generation
├── package.json             # npm scripts for running suites
├── cases/                   # 8 YAML files, one per category
│   ├── intent.yaml          # 35 cases
│   ├── extraction.yaml      # 15 cases
│   ├── personality.yaml     # 20 cases
│   ├── emotional.yaml       # 10 cases
│   ├── functional.yaml      # 29 cases
│   ├── edge_cases.yaml      # 20 cases
│   ├── multi_turn.yaml      # 15 cases
│   └── regression.yaml      # 25 cases
├── pytest/                  # DB verification + contract tests
│   ├── conftest.py          # Fixtures: client, admin, api_url
│   ├── client.py            # EvalClient (chat via eval auth)
│   ├── admin.py             # AdminClient (inspect DB state)
│   ├── test_extraction_db.py
│   ├── test_performance.py
│   ├── test_contract.py
│   └── test_langfuse.py
└── results/                 # Local output (gitignored)
```

All tests hit the real API. The eval auth bypass (`Bearer eval:<EVAL_API_KEY>`) skips Supabase JWT validation but routes through the full pipeline.

---

## Quick Start

```bash
cd eval

# Install promptfoo
npm install

# Set env vars (add to .env or export)
export EVAL_API_KEY=...          # Eval auth bypass key (set in Railway)
export ADMIN_API_KEY=...         # Admin API access (DB inspection, cleanup)
export OPENAI_API_KEY=...       # Used by promptfoo's llm-rubric judge
export LANGFUSE_PUBLIC_KEY=...  # Optional: trace verification tests
export LANGFUSE_SECRET_KEY=...

# Run all promptfoo tests
npm run eval

# View results in browser
npm run eval:view

# Run pytest suite
cd pytest && pytest -x --timeout=60
```

---

## Test Categories

### Promptfoo (169 cases)

| Category | Count | What it tests |
|----------|-------|---------------|
| `intent` | 35 | Correct intent classification across all 10 intents |
| `extraction` | 15 | Task details extracted (deadlines, energy, urgency) |
| `personality` | 20 | Tone, length, emoji usage match user preferences |
| `emotional` | 10 | Empathetic responses to frustration, overwhelm, anxiety |
| `functional` | 29 | Core flows: brain dump, pick next, mark done, queries |
| `edge_cases` | 20 | Empty input, huge messages, unicode, ambiguous phrasing |
| `multi_turn` | 15 | Conversation continuity across multiple messages |
| `regression` | 25 | Previously-broken behaviors pinned with test cases |

### Pytest (~26 cases)

| File | What it tests |
|------|---------------|
| `test_extraction_db.py` | Items created in DB with correct fields after brain dump |
| `test_performance.py` | Response latency under thresholds |
| `test_contract.py` | SSE format, HTTP status codes, error shapes |
| `test_langfuse.py` | Traces emitted with expected spans |

### Red Team (50 generated cases)

Promptfoo's redteam plugin generates adversarial inputs: prompt injection, jailbreaks, PII extraction, identity hijacking, multilingual attacks, leetspeak bypass.

---

## Running Specific Suites

```bash
# By category (npm scripts)
npm run eval:intent
npm run eval:personality
npm run eval:functional
npm run eval:regression

# By filter pattern (ad hoc)
npx promptfoo eval --filter-pattern 'intent_brain_dump_*'
npx promptfoo eval --filter-pattern 'edge_*'

# Red team
npm run eval:redteam

# Pytest — single file
cd pytest && pytest test_contract.py -v
```

---

## Adding Test Cases

### Promptfoo (response quality)

Add to the appropriate `cases/*.yaml` file:

```yaml
- description: "intent_brain_dump_with_context"
  vars:
    message: "remind me to water the plants every Sunday"
  assert:
    - type: llm-rubric
      value: "Response confirms capturing a recurring task without asking unnecessary questions."
    - type: not-contains
      value: "went wrong"
```

Naming convention: `<category>_<subcategory>_<detail>`. The `description` field is used for `--filter-pattern` matching.

Available assert types: `llm-rubric` (LLM judges response), `contains`, `not-contains`, `javascript` (custom JS expression), `similar` (embedding similarity), `latency`.

### Pytest (DB verification)

Add to the appropriate `pytest/test_*.py` file. Use the `client` and `admin` fixtures:

```python
async def test_deadline_extracted(client, admin):
    await admin.cleanup()
    await client.send_message("submit the proposal by March 20th")
    items = await admin.get_items(EVAL_USER_ID)
    assert items[0]["deadline_at"] is not None
    assert items[0]["deadline_type"] == "hard"
```

---

## CI/CD

Two triggers in GitHub Actions:

1. **Manual:** `workflow_dispatch` — run any time from Actions tab
2. **PR label:** Adding `run-eval` label to a PR triggers the full suite

The workflow installs promptfoo, sets secrets from GitHub environment, runs both layers, and posts a summary comment on the PR.

---

## Environment Variables

| Variable | Required | Used by |
|----------|----------|---------|
| `EVAL_API_KEY` | Yes | Auth bypass for eval requests |
| `ADMIN_API_KEY` | Yes | DB inspection, cleanup endpoint |
| `OPENAI_API_KEY` | Yes | Promptfoo's `llm-rubric` judge model |
| `LANGFUSE_PUBLIC_KEY` | For trace tests | `test_langfuse.py` verification |
| `LANGFUSE_SECRET_KEY` | For trace tests | `test_langfuse.py` verification |
| `API_URL` | No (default: `https://api.unspool.life`) | Override target API |

---

## Cleanup

Eval runs create items, messages, and traces under the eval user. Clean up after runs:

```bash
# Via npm script
npm run cleanup

# Direct
curl -X DELETE -H "X-Admin-Key: $ADMIN_API_KEY" \
  https://api.unspool.life/admin/eval-cleanup
```

This removes all data associated with the eval user (`b8a2e17e-ff55-485f-ad6c-29055a607b33`). Run it after eval sessions to avoid polluting production data.
