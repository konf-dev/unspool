# Pipeline Configuration Format

Pipelines define how the orchestrator processes a user message. Each pipeline is a YAML file in `backend/config/pipelines/`. The orchestrator engine (`backend/src/orchestrator/engine.py`) executes steps sequentially, with branching support.

---

## Pipeline Structure

```yaml
name: pipeline_name          # Must match filename (without .yaml)
description: What this does   # Human-readable

steps:
  - id: step_name             # Unique within pipeline, used for ${steps.X.output} refs
    type: llm_call            # One of: llm_call, tool_call, query, operation, branch, transform
    # ... type-specific fields

post_processing:              # Optional — background jobs to trigger after pipeline completes
  - job: process_conversation
    delay: "10s"
```

---

## Step Types

### llm_call

Calls the LLM with a rendered prompt template.

```yaml
- id: respond
  type: llm_call
  prompt: brain_dump_respond.md    # Template file in backend/prompts/
  model: null                       # null = use default LLM_MODEL from env
  stream: true                      # true = stream tokens to client (only final step usually)
  input:                            # Extra variables passed to the template
    items: "${steps.extract.output}"
  output_schema: json               # Optional — parse response as JSON
```

**Fields:**
- `prompt` (required) — Jinja2 template filename in `backend/prompts/`
- `model` — Override model for this step. `null` uses the default
- `stream` — If `true`, tokens stream to the client via SSE
- `input` — Key-value pairs resolved via variable syntax, passed to the template
- `output_schema` — If set, engine first tries `generate_structured()` (OpenAI Structured Outputs — server-side constrained decoding, guaranteed valid JSON). Falls back to text generation + `_extract_json()` parsing on failure. Schema name must match a key in `OUTPUT_SCHEMAS` in `types.py`

### tool_call

Calls a registered Python tool function.

```yaml
- id: save
  type: tool_call
  tool: save_items                   # Name from @register_tool("save_items")
  optional: false                     # If true, failures don't crash the pipeline
  input:
    user_id: "${context.user_id}"
    items: "${steps.enrich.output}"
```

**Fields:**
- `tool` (required) — Registered tool name
- `input` — Key-value pairs resolved and passed as `**kwargs` to the tool function
- `optional` — If `true`, tool exceptions are logged but don't crash the pipeline. The step result output is set to `None` and execution continues. Used for steps like `fuzzy_match_item` in `status_done`/`status_cant` where downstream prompts handle the no-match case

### query

Executes a predefined database query (defined in `config/queries.yaml`).

```yaml
- id: fetch_data
  type: query
  query: get_recent_items           # Query name from queries.yaml
  input:
    user_id: "${context.user_id}"
```

### operation

Executes a predefined operation (write/mutation).

```yaml
- id: update
  type: operation
  operation: mark_expired
  input:
    item_id: "${steps.match.output.id}"
```

### branch

Conditional jump to another step by ID.

```yaml
- id: route
  type: branch
  conditions:
    - if: "${steps.classify.output.intent}"
      equals: "brain_dump"
      goto: extract_items
    - if: "${steps.classify.output.intent}"
      equals: "emotional"
      goto: detect_emotion
    - default: generic_respond
```

### transform

Placeholder for data transformation (not yet implemented).

---

## Variable Resolution

Variables in `input` fields use `${...}` syntax:

| Pattern | Resolves to |
|---------|------------|
| `${user_message}` | The user's message text |
| `${context.user_id}` | Any attribute on the Context dataclass |
| `${context.profile}` | User profile dict |
| `${context.open_items}` | List of open items |
| `${context.recent_messages}` | Recent chat messages |
| `${context.urgent_items}` | Items with approaching deadlines |
| `${context.memories}` | User memories |
| `${context.entities}` | Known entities |
| `${context.calendar_events}` | Upcoming calendar events |
| `${context.graph_context}` | Graph-derived memory context (`<context>` block or None) |
| `${steps.X.output}` | Output of step with id `X` |
| `${steps.X.output.field}` | Sub-field of step output (if dict) |

Literal strings (not starting with `${`) pass through unchanged.

---

## Context Loading

Before pipeline execution, the engine loads context based on rules in `config/context_rules.yaml`:

```yaml
rules:
  brain_dump:
    load:                    # Required — failure raises error
      - profile
      - recent_messages
    optional:                # Failure logged but swallowed
      - entities

defaults:
  recent_messages_limit: 20
```

Available context fields and their loaders:

| Field | Loader | Source |
|-------|--------|--------|
| profile | `fetch_profile` | `user_profiles` table |
| recent_messages | `fetch_messages` | `messages` table (last N) |
| open_items | `fetch_items` | `items` table where status=open |
| urgent_items | `fetch_urgent_items` | Items with deadline < 48h |
| entities | `fetch_entities` | `entities` table |
| memories | `fetch_memories` | `memories` table (recent or semantic) |
| calendar_events | `fetch_calendar_events` | `calendar_events` table (upcoming) |
| graph_context | `fetch_graph_context` | Graph memory (triggers → subgraph → serialized text) |

---

## Prompt Templates

Templates live in `backend/prompts/` as Markdown files with YAML frontmatter:

```markdown
---
name: classify_intent
version: "1.1"
input_vars: [user_message, recent_messages]
---
Classify the user's message into exactly one intent.
...
{{ user_message }}
```

- Frontmatter is stripped before rendering
- Body is rendered with Jinja2 (`{{ variable }}`, `{% for %}`, `{% if %}`)
- All context fields + step outputs + explicit `input` values are available as template variables

---

## Post-Processing

Pipelines can trigger background jobs after completion:

```yaml
post_processing:
  - job: process_conversation    # Maps to QStash job endpoint
    delay: "10s"                 # Delay before execution
```

---

## A/B Testing (Variants)

Defined in `config/variants.yaml`. When a pipeline has variants, the engine randomly assigns users and can override the model:

```yaml
brain_dump:
  control:
    weight: 0.5
    overrides: {}
  concise:
    weight: 0.5
    overrides:
      model: claude-haiku-4-5-20251001
```

Assignments are persisted in the `experiment_assignments` table.

---

## Existing Pipelines

| Pipeline | Steps | Description |
|----------|-------|-------------|
| `brain_dump` | extract → enrich → save → respond | Extract items from brain dump, score, save, respond |
| `query_next` | fetch_items → score_and_pick → respond | Pick best next item, respond with one thing |
| `query_search` | analyze → smart_fetch → respond | LLM-analyzed query → targeted multi-source fetch |
| `query_upcoming` | fetch_upcoming → respond | Show upcoming deadlines |
| `status_done` | match_item → mark_done → check_momentum → respond | Mark done, celebrate streak |
| `status_cant` | match_item → reschedule → respond | Reschedule or deprioritize |
| `emotional` | detect_level → respond | Detect emotional state, respond empathetically |
| `onboarding` | respond | Welcome new user |
| `meta` | respond | Explain what Unspool can do |
| `conversation` | extract_implicit → save_if_any → respond | General chat, extract any implicit items |

---

## Proactive Messages

Proactive messages (displayed when user opens the app) are config-driven via `config/proactive.yaml`:

```yaml
triggers:
  deadline_imminent:
    enabled: true
    condition: urgent_items       # Condition type to evaluate
    params:
      hours: 24                   # Passed to the condition evaluator
    prompt: proactive_deadline.md # Jinja2 template in prompts/
    priority: 1                   # Lower = evaluated first
```

Triggers are evaluated in priority order on initial message load. Only the first matching trigger fires per session. Each trigger renders its response through the LLM using a prompt template (not hardcoded strings).

Available condition types: `urgent_items`, `days_absent`, `recent_completions`, `slipped_items`.

---

## Scoring & Thresholds

Tool thresholds and notification parameters live in `config/scoring.yaml`. This includes urgency decay, momentum detection, item picking boosts, reschedule delays, fuzzy matching thresholds, and push notification settings. Energy estimation and initial urgency scoring are handled by the LLM in prompt templates, not by config-driven heuristics. See `docs/TOOLS.md` for the full section reference.

Additional config files: `config/jobs.yaml` (cron schedules, dispatch mapping) and `config/patterns.yaml` (pattern detection analysis definitions).

---

## Intent Classification

All messages go through LLM-based intent classification using `prompts/classify_intent.md`. There are no hardcoded regex patterns — this avoids misclassification on ambiguous inputs like "buy" (could be brain_dump or conversation depending on context).

Intents are defined in `config/intents.yaml`:

```yaml
intents:
  brain_dump:
    description: User is dumping tasks, ideas, or things to remember
    pipeline: brain_dump
  # ...

fallback_intent: conversation
classification_model: gpt-4.1-nano  # Fast model for intent classification
```

---

## Adding a New Pipeline

1. Create `backend/config/pipelines/your_pipeline.yaml`
2. Add the intent to `backend/config/intents.yaml` with `pipeline: your_pipeline`
3. Add context rules to `backend/config/context_rules.yaml`
4. Add any new prompt templates to `backend/prompts/`
5. Update `backend/prompts/classify_intent.md` to include the new intent
6. If the pipeline needs new tools, add thresholds to `config/scoring.yaml`
7. Run `pytest tests/test_config_loader.py` to verify it loads
