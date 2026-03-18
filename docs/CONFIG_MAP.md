# Config Map (auto-generated — do not edit)

Generated: 2026-03-18 23:39 UTC | Git: 00993b8

Intents config: `config/intents.yaml` (c487f4e082c2)
Context rules: `config/context_rules.yaml` (2d3d35b83ee9)

---

## brain_dump

_User is dumping tasks, ideas, or things to remember_

Pipeline: `config/pipelines/brain_dump.yaml` (620f8eedcfa6)

Context: profile, recent_messages | optional: entities, graph_context

| Step | Type | Config | Hash |
|------|------|--------|------|
| extract | llm_call | `prompts/brain_dump_extract.md` | adb225daeecc |
| enrich | tool_call | enrich_items | — |
| save | tool_call | save_items | — |
| respond | llm_call (stream) | `prompts/brain_dump_respond.md` | ad0d6518f82d |

Post-processing: process_conversation (10s), process_graph (5s)

---

## conversation

_General conversation or unclear intent_

Pipeline: `config/pipelines/conversation.yaml` (a847a2f65b40)

Context: profile, recent_messages | optional: memories, entities, graph_context

| Step | Type | Config | Hash |
|------|------|--------|------|
| extract_implicit | llm_call | `prompts/conversation_extract.md` | 1ba21b741fb9 |
| save_if_any | tool_call | save_items | — |
| respond | llm_call (stream) | `prompts/conversation_respond.md` | 31b535ad6450 |

Post-processing: process_graph (5s)

---

## emotional

_User expressing feelings or venting_

Pipeline: `config/pipelines/emotional.yaml` (5d5764d5a784)

Context: profile, recent_messages | optional: memories, graph_context

| Step | Type | Config | Hash |
|------|------|--------|------|
| detect_level | llm_call | `prompts/emotional_detect.md` | 9e49a5672ad5 |
| respond | llm_call (stream) | `prompts/emotional_respond.md` | e28387c90959 |

Post-processing: process_graph (5s)

---

## meta

_User asking about the system itself_

Pipeline: `config/pipelines/meta.yaml` (94d96f0ddba6)

Context: profile

| Step | Type | Config | Hash |
|------|------|--------|------|
| respond | llm_call (stream) | `prompts/meta_respond.md` | 3dd8a5632072 |

---

## onboarding

_First message from a new user_

Pipeline: `config/pipelines/onboarding.yaml` (b5c93791bcd0)

Context: profile

| Step | Type | Config | Hash |
|------|------|--------|------|
| respond | llm_call (stream) | `prompts/onboarding_respond.md` | 445816d245ed |

---

## query_next

_User asking what to do next_

Pipeline: `config/pipelines/query_next.yaml` (993f0db7dd4e)

Context: profile, open_items, urgent_items, recent_messages | optional: calendar_events, memories, graph_context

| Step | Type | Config | Hash |
|------|------|--------|------|
| fetch_items | tool_call | fetch_items | — |
| score_and_pick | tool_call | pick_next_item | — |
| respond | llm_call (stream) | `prompts/query_format.md` | a76c6b019af9 |

---

## query_search

_User searching for something specific they told you about_

Pipeline: `config/pipelines/query_search.yaml` (01f901a47efa)

Context: profile, recent_messages | optional: graph_context

| Step | Type | Config | Hash |
|------|------|--------|------|
| analyze | llm_call | `prompts/analyze_query.md` | 215e52d96406 |
| fetch | tool_call | smart_fetch | — |
| respond | llm_call (stream) | `prompts/query_deep_respond.md` | 6e0a5120eff0 |

---

## query_upcoming

_User asking about upcoming deadlines or schedule_

Pipeline: `config/pipelines/query_upcoming.yaml` (d173f241675c)

Context: profile, urgent_items | optional: graph_context

| Step | Type | Config | Hash |
|------|------|--------|------|
| fetch_urgent | tool_call | fetch_urgent_items | — |
| respond | llm_call (stream) | `prompts/query_upcoming_format.md` | fcb2fa602f05 |

---

## status_cant

_User skipping or postponing something_

Pipeline: `config/pipelines/status_cant.yaml` (69b157c32b2e)

Context: profile, open_items, recent_messages | optional: graph_context

| Step | Type | Config | Hash |
|------|------|--------|------|
| match_item | tool_call | fuzzy_match_item | — |
| reschedule | tool_call | reschedule_item | — |
| respond | llm_call (stream) | `prompts/status_cant_respond.md` | 2f2fd7a01a97 |

---

## status_done

_User marking something as done_

Pipeline: `config/pipelines/status_done.yaml` (7e2640fbc4c9)

Context: profile, open_items, recent_messages | optional: graph_context

| Step | Type | Config | Hash |
|------|------|--------|------|
| match_item | tool_call | fuzzy_match_item | — |
| mark_done | tool_call | mark_item_done | — |
| check_momentum | tool_call | check_momentum | — |
| respond | llm_call (stream) | `prompts/status_done_respond.md` | 321d9147654d |

Post-processing: process_graph (5s)

---

## Unreferenced Prompts

These prompt files exist in `prompts/` but are not referenced by any pipeline:

- `prompts/classify_intent.md` (51357475ce66)
- `prompts/consolidate_memories.md` (d8c93565d87c)
- `prompts/detect_behavioral_patterns.md` (278f6bcd37a4)
- `prompts/detect_preferences.md` (764452ad50a0)
- `prompts/extract_memories.md` (e31da933834a)
- `prompts/graph_evolve.md` (e3af197a17ca)
- `prompts/graph_ingest.md` (007e9c3a7528)
- `prompts/proactive_deadline.md` (7f9a1c2ab113)
- `prompts/proactive_long_absence.md` (2181130775bf)
- `prompts/proactive_momentum.md` (723255a46657)
- `prompts/proactive_slipped.md` (d29dfbd11101)
- `prompts/proactive_welcome_back.md` (26ed412e7a0b)
- `prompts/query_search_format.md` (12788431f100)
- `prompts/system.md` (0c02e71b776e)

## Config Files

| File | Hash |
|------|------|
| `config/context_rules.yaml` | 2d3d35b83ee9 |
| `config/gate.yaml` | 04e355cf1fcc |
| `config/graph.yaml` | 2dcbcf9ca196 |
| `config/intents.yaml` | c487f4e082c2 |
| `config/jobs.yaml` | 4f88280d617e |
| `config/patterns.yaml` | d9520794840f |
| `config/proactive.yaml` | 3ae2be6602fb |
| `config/queries.yaml` | 2750d030150b |
| `config/scoring.yaml` | a39cfef9e916 |
| `config/triggers.yaml` | 070ae580ab90 |
| `config/variants.yaml` | 6b8de9494654 |
| `config/pipelines/brain_dump.yaml` | 620f8eedcfa6 |
| `config/pipelines/conversation.yaml` | a847a2f65b40 |
| `config/pipelines/emotional.yaml` | 5d5764d5a784 |
| `config/pipelines/meta.yaml` | 94d96f0ddba6 |
| `config/pipelines/onboarding.yaml` | b5c93791bcd0 |
| `config/pipelines/query_next.yaml` | 993f0db7dd4e |
| `config/pipelines/query_search.yaml` | 01f901a47efa |
| `config/pipelines/query_upcoming.yaml` | d173f241675c |
| `config/pipelines/status_cant.yaml` | 69b157c32b2e |
| `config/pipelines/status_done.yaml` | 7e2640fbc4c9 |

