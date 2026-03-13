# Config Map (auto-generated — do not edit)

Generated: 2026-03-13 19:03 UTC | Git: 8c449bc

Intents config: `config/intents.yaml` (2bbcfb57edbd)
Context rules: `config/context_rules.yaml` (ed199732d456)

---

## brain_dump

_User is dumping tasks, ideas, or things to remember_

Pipeline: `config/pipelines/brain_dump.yaml` (8e7f1dec822b)

Context: profile, recent_messages | optional: entities

| Step | Type | Config | Hash |
|------|------|--------|------|
| extract | llm_call | `prompts/brain_dump_extract.md` | 419c2cbf1e86 |
| enrich | tool_call | enrich_items | — |
| save | tool_call | save_items | — |
| respond | llm_call (stream) | `prompts/brain_dump_respond.md` | e5f3c0dbdac9 |

Post-processing: process_conversation (10s)

---

## conversation

_General conversation or unclear intent_

Pipeline: `config/pipelines/conversation.yaml` (ca728c73bf6c)

Context: profile, recent_messages | optional: memories, entities

| Step | Type | Config | Hash |
|------|------|--------|------|
| extract_implicit | llm_call | `prompts/conversation_extract.md` | 44fd0f64b49d |
| save_if_any | tool_call | save_items | — |
| respond | llm_call (stream) | `prompts/conversation_respond.md` | 473a52bb22be |

---

## emotional

_User expressing feelings or venting_

Pipeline: `config/pipelines/emotional.yaml` (f937578f365e)

Context: profile, recent_messages | optional: memories

| Step | Type | Config | Hash |
|------|------|--------|------|
| detect_level | llm_call | `prompts/emotional_detect.md` | f1b68f1bad20 |
| respond | llm_call (stream) | `prompts/emotional_respond.md` | 5b16d6b52647 |

---

## meta

_User asking about the system itself_

Pipeline: `config/pipelines/meta.yaml` (7171338a6371)

Context: profile

| Step | Type | Config | Hash |
|------|------|--------|------|
| respond | llm_call (stream) | `prompts/meta_respond.md` | 6c7dd9787674 |

---

## onboarding

_First message from a new user_

Pipeline: `config/pipelines/onboarding.yaml` (7793dc50bd64)

Context: profile

| Step | Type | Config | Hash |
|------|------|--------|------|
| respond | llm_call (stream) | `prompts/onboarding_respond.md` | ea8190b82da6 |

---

## query_next

_User asking what to do next_

Pipeline: `config/pipelines/query_next.yaml` (b26ef31f1bce)

Context: profile, open_items, urgent_items, recent_messages | optional: calendar_events, memories

| Step | Type | Config | Hash |
|------|------|--------|------|
| fetch_items | tool_call | fetch_items | — |
| score_and_pick | tool_call | pick_next_item | — |
| respond | llm_call (stream) | `prompts/query_format.md` | 810b092fcb0c |

---

## query_search

_User searching for something specific they told you about_

Pipeline: `config/pipelines/query_search.yaml` (3aa769c3316d)

Context: profile, recent_messages

| Step | Type | Config | Hash |
|------|------|--------|------|
| embed_query | tool_call | generate_embedding | — |
| search | tool_call | search_hybrid | — |
| respond | llm_call (stream) | `prompts/query_search_format.md` | fe6bb563553a |

---

## query_upcoming

_User asking about upcoming deadlines or schedule_

Pipeline: `config/pipelines/query_upcoming.yaml` (124f91e6d31e)

Context: profile, urgent_items

| Step | Type | Config | Hash |
|------|------|--------|------|
| fetch_urgent | tool_call | fetch_urgent_items | — |
| respond | llm_call (stream) | `prompts/query_upcoming_format.md` | cace7ab28b3d |

---

## status_cant

_User skipping or postponing something_

Pipeline: `config/pipelines/status_cant.yaml` (ac59377069bb)

Context: profile, open_items, recent_messages

| Step | Type | Config | Hash |
|------|------|--------|------|
| match_item | tool_call | fuzzy_match_item | — |
| reschedule | tool_call | reschedule_item | — |
| respond | llm_call (stream) | `prompts/status_cant_respond.md` | b57f8288f68c |

---

## status_done

_User marking something as done_

Pipeline: `config/pipelines/status_done.yaml` (87c6d161baa4)

Context: profile, open_items, recent_messages

| Step | Type | Config | Hash |
|------|------|--------|------|
| match_item | tool_call | fuzzy_match_item | — |
| mark_done | tool_call | mark_item_done | — |
| check_momentum | tool_call | check_momentum | — |
| respond | llm_call (stream) | `prompts/status_done_respond.md` | 70099bcf230f |

---

## Unreferenced Prompts

These prompt files exist in `prompts/` but are not referenced by any pipeline:

- `prompts/classify_intent.md` (67dc30d9ae02)
- `prompts/extract_memories.md` (e02ca444a54f)
- `prompts/proactive_deadline.md` (bf92f97c87f6)
- `prompts/proactive_long_absence.md` (94a4d7f80e5e)
- `prompts/proactive_momentum.md` (723255a46657)
- `prompts/proactive_slipped.md` (f82689db55f5)
- `prompts/proactive_welcome_back.md` (26ed412e7a0b)
- `prompts/system.md` (6b61a9716880)

## Config Files

| File | Hash |
|------|------|
| `config/context_rules.yaml` | ed199732d456 |
| `config/gate.yaml` | cf263f208b24 |
| `config/intents.yaml` | 2bbcfb57edbd |
| `config/proactive.yaml` | 3ae2be6602fb |
| `config/queries.yaml` | 2750d030150b |
| `config/scoring.yaml` | 901f9dcb23c7 |
| `config/variants.yaml` | 6b8de9494654 |
| `config/pipelines/brain_dump.yaml` | 8e7f1dec822b |
| `config/pipelines/conversation.yaml` | ca728c73bf6c |
| `config/pipelines/emotional.yaml` | f937578f365e |
| `config/pipelines/meta.yaml` | 7171338a6371 |
| `config/pipelines/onboarding.yaml` | 7793dc50bd64 |
| `config/pipelines/query_next.yaml` | b26ef31f1bce |
| `config/pipelines/query_search.yaml` | 3aa769c3316d |
| `config/pipelines/query_upcoming.yaml` | 124f91e6d31e |
| `config/pipelines/status_cant.yaml` | ac59377069bb |
| `config/pipelines/status_done.yaml` | 87c6d161baa4 |

