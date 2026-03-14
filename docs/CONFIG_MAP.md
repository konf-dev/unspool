# Config Map (auto-generated — do not edit)

Generated: 2026-03-14 21:52 UTC | Git: 66887a7

Intents config: `config/intents.yaml` (2bbcfb57edbd)
Context rules: `config/context_rules.yaml` (ed199732d456)

---

## brain_dump

_User is dumping tasks, ideas, or things to remember_

Pipeline: `config/pipelines/brain_dump.yaml` (0a34fe2013ab)

Context: profile, recent_messages | optional: entities

| Step | Type | Config | Hash |
|------|------|--------|------|
| extract | llm_call | `prompts/brain_dump_extract.md` | 967cfa9f316d |
| enrich | tool_call | enrich_items | — |
| save | tool_call | save_items | — |
| respond | llm_call (stream) | `prompts/brain_dump_respond.md` | da90e80fca58 |

Post-processing: process_conversation (10s)

---

## conversation

_General conversation or unclear intent_

Pipeline: `config/pipelines/conversation.yaml` (ca728c73bf6c)

Context: profile, recent_messages | optional: memories, entities

| Step | Type | Config | Hash |
|------|------|--------|------|
| extract_implicit | llm_call | `prompts/conversation_extract.md` | 1ba21b741fb9 |
| save_if_any | tool_call | save_items | — |
| respond | llm_call (stream) | `prompts/conversation_respond.md` | 31b535ad6450 |

---

## emotional

_User expressing feelings or venting_

Pipeline: `config/pipelines/emotional.yaml` (5b44a97eecfe)

Context: profile, recent_messages | optional: memories

| Step | Type | Config | Hash |
|------|------|--------|------|
| detect_level | llm_call | `prompts/emotional_detect.md` | 9e49a5672ad5 |
| respond | llm_call (stream) | `prompts/emotional_respond.md` | 5b16d6b52647 |

---

## meta

_User asking about the system itself_

Pipeline: `config/pipelines/meta.yaml` (7171338a6371)

Context: profile

| Step | Type | Config | Hash |
|------|------|--------|------|
| respond | llm_call (stream) | `prompts/meta_respond.md` | 26d786cc6618 |

---

## onboarding

_First message from a new user_

Pipeline: `config/pipelines/onboarding.yaml` (7793dc50bd64)

Context: profile

| Step | Type | Config | Hash |
|------|------|--------|------|
| respond | llm_call (stream) | `prompts/onboarding_respond.md` | 445816d245ed |

---

## query_next

_User asking what to do next_

Pipeline: `config/pipelines/query_next.yaml` (b26ef31f1bce)

Context: profile, open_items, urgent_items, recent_messages | optional: calendar_events, memories

| Step | Type | Config | Hash |
|------|------|--------|------|
| fetch_items | tool_call | fetch_items | — |
| score_and_pick | tool_call | pick_next_item | — |
| respond | llm_call (stream) | `prompts/query_format.md` | 89bcf6cfef12 |

---

## query_search

_User searching for something specific they told you about_

Pipeline: `config/pipelines/query_search.yaml` (2db518421e5d)

Context: profile, recent_messages

| Step | Type | Config | Hash |
|------|------|--------|------|
| analyze | llm_call | `prompts/analyze_query.md` | 215e52d96406 |
| fetch | tool_call | smart_fetch | — |
| respond | llm_call (stream) | `prompts/query_deep_respond.md` | 6e0a5120eff0 |

---

## query_upcoming

_User asking about upcoming deadlines or schedule_

Pipeline: `config/pipelines/query_upcoming.yaml` (124f91e6d31e)

Context: profile, urgent_items

| Step | Type | Config | Hash |
|------|------|--------|------|
| fetch_urgent | tool_call | fetch_urgent_items | — |
| respond | llm_call (stream) | `prompts/query_upcoming_format.md` | fcb2fa602f05 |

---

## status_cant

_User skipping or postponing something_

Pipeline: `config/pipelines/status_cant.yaml` (ac59377069bb)

Context: profile, open_items, recent_messages

| Step | Type | Config | Hash |
|------|------|--------|------|
| match_item | tool_call | fuzzy_match_item | — |
| reschedule | tool_call | reschedule_item | — |
| respond | llm_call (stream) | `prompts/status_cant_respond.md` | ec658dc9f77a |

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
| respond | llm_call (stream) | `prompts/status_done_respond.md` | 321d9147654d |

---

## Unreferenced Prompts

These prompt files exist in `prompts/` but are not referenced by any pipeline:

- `prompts/classify_intent.md` (7006eeb9edb7)
- `prompts/consolidate_memories.md` (d8c93565d87c)
- `prompts/detect_behavioral_patterns.md` (278f6bcd37a4)
- `prompts/detect_preferences.md` (764452ad50a0)
- `prompts/extract_memories.md` (e31da933834a)
- `prompts/proactive_deadline.md` (827e07af5990)
- `prompts/proactive_long_absence.md` (94a4d7f80e5e)
- `prompts/proactive_momentum.md` (723255a46657)
- `prompts/proactive_slipped.md` (d29dfbd11101)
- `prompts/proactive_welcome_back.md` (26ed412e7a0b)
- `prompts/query_search_format.md` (12788431f100)
- `prompts/system.md` (958b419c8274)

## Config Files

| File | Hash |
|------|------|
| `config/context_rules.yaml` | ed199732d456 |
| `config/gate.yaml` | 9e7cd6798b38 |
| `config/intents.yaml` | 2bbcfb57edbd |
| `config/jobs.yaml` | 6a771b1867b2 |
| `config/patterns.yaml` | d9520794840f |
| `config/proactive.yaml` | 3ae2be6602fb |
| `config/queries.yaml` | 2750d030150b |
| `config/scoring.yaml` | a39cfef9e916 |
| `config/variants.yaml` | 6b8de9494654 |
| `config/pipelines/brain_dump.yaml` | 0a34fe2013ab |
| `config/pipelines/conversation.yaml` | ca728c73bf6c |
| `config/pipelines/emotional.yaml` | 5b44a97eecfe |
| `config/pipelines/meta.yaml` | 7171338a6371 |
| `config/pipelines/onboarding.yaml` | 7793dc50bd64 |
| `config/pipelines/query_next.yaml` | b26ef31f1bce |
| `config/pipelines/query_search.yaml` | 2db518421e5d |
| `config/pipelines/query_upcoming.yaml` | 124f91e6d31e |
| `config/pipelines/status_cant.yaml` | ac59377069bb |
| `config/pipelines/status_done.yaml` | 87c6d161baa4 |

