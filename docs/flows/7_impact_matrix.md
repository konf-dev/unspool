# Impact Matrix

Auto-generated. Shows what flows and DB tables are affected when you change a file.

| If you change... | Type | Flows affected | DB tables | Fields |
|---|---|---|---|---|
| `system.md` | prompt | All 10 pipelines (injected into every LLM call) |  |  |
| `classify_intent.md` | prompt | Intent classification (all messages) |  |  |
| `analyze_query.md` | prompt | query_search (step: analyze) |  |  |
| `brain_dump_extract.md` | prompt | brain_dump (step: extract) | entities, item_events, items, memories, memory_edges, memory_nodes, node_neighbors |  |
| `brain_dump_respond.md` | prompt | brain_dump (step: respond) | entities, item_events, items, memories, memory_edges, memory_nodes, node_neighbors |  |
| `conversation_extract.md` | prompt | conversation (step: extract_implicit) | item_events, items, memory_edges, memory_nodes, node_neighbors |  |
| `conversation_respond.md` | prompt | conversation (step: respond) | item_events, items, memory_edges, memory_nodes, node_neighbors |  |
| `emotional_detect.md` | prompt | emotional (step: detect_level) | memory_edges, memory_nodes, node_neighbors |  |
| `emotional_respond.md` | prompt | emotional (step: respond) | memory_edges, memory_nodes, node_neighbors |  |
| `meta_respond.md` | prompt | meta (step: respond) |  |  |
| `onboarding_respond.md` | prompt | onboarding (step: respond) |  |  |
| `query_deep_respond.md` | prompt | query_search (step: respond) |  |  |
| `query_format.md` | prompt | query_next (step: respond) |  |  |
| `query_upcoming_format.md` | prompt | query_upcoming (step: respond) |  |  |
| `status_cant_respond.md` | prompt | status_cant (step: respond) | item_events, items |  |
| `status_done_respond.md` | prompt | status_done (step: respond) | item_events, items, memory_edges, memory_nodes, node_neighbors |  |
| `proactive_deadline.md` | prompt (proactive) | Proactive trigger: deadline_imminent |  |  |
| `proactive_long_absence.md` | prompt (proactive) | Proactive trigger: long_absence |  |  |
| `proactive_slipped.md` | prompt (proactive) | Proactive trigger: something_slipped |  |  |
| `proactive_momentum.md` | prompt (proactive) | Proactive trigger: momentum |  |  |
| `proactive_welcome_back.md` | prompt (proactive) | Proactive trigger: welcome_back |  |  |
| `detect_behavioral_patterns.md` | prompt (patterns) | detect_patterns job (behavioral_patterns) | user_profiles | patterns |
| `detect_preferences.md` | prompt (patterns) | detect_patterns job (preference_inference) | user_profiles | patterns |
| `consolidate_memories.md` | prompt (patterns) | detect_patterns job (memory_consolidation) | user_profiles | patterns |
| `scoring.yaml (decay)` | config | decay_urgency job |  | items.urgency_score, items.status |
| `scoring.yaml (momentum)` | config | status_done via check_momentum |  |  |
| `scoring.yaml (pick_next)` | config | query_next via pick_next_item |  | items.last_surfaced_at |
| `scoring.yaml (reschedule)` | config | status_cant via reschedule_item |  | items.urgency_score, items.nudge_after |
| `scoring.yaml (matching)` | config | status_cant via fuzzy_match_item, status_done via fuzzy_match_item |  |  |
| `scoring.yaml (notifications)` | config | check_deadlines job |  | user_profiles.notification_sent_today |
| `context_rules.yaml` | config | All intents (context assembly) |  |  |
| `gate.yaml` | config | Rate limiting in /api/chat |  |  |
| `proactive.yaml` | config | Proactive message triggers |  |  |
| `patterns.yaml` | config | detect_patterns job |  |  |
| `intents.yaml` | config | Intent to pipeline routing |  |  |
| `jobs.yaml` | config | Background job schedules + dispatch |  |  |
| `variants.yaml` | config | A/B test variant selection |  |  |
| `pipelines/brain_dump.yaml` | pipeline | brain_dump pipeline | entities, item_events, items, memories, memory_edges, memory_nodes, node_neighbors |  |
| `pipelines/conversation.yaml` | pipeline | conversation pipeline | item_events, items, memory_edges, memory_nodes, node_neighbors |  |
| `pipelines/emotional.yaml` | pipeline | emotional pipeline | memory_edges, memory_nodes, node_neighbors |  |
| `pipelines/meta.yaml` | pipeline | meta pipeline |  |  |
| `pipelines/onboarding.yaml` | pipeline | onboarding pipeline |  |  |
| `pipelines/query_next.yaml` | pipeline | query_next pipeline |  |  |
| `pipelines/query_search.yaml` | pipeline | query_search pipeline |  |  |
| `pipelines/query_upcoming.yaml` | pipeline | query_upcoming pipeline |  |  |
| `pipelines/status_cant.yaml` | pipeline | status_cant pipeline | item_events, items |  |
| `pipelines/status_done.yaml` | pipeline | status_done pipeline | item_events, items, memory_edges, memory_nodes, node_neighbors |  |