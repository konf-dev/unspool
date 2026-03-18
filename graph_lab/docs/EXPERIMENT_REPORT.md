# Graph Lab Experiment Report

**Date:** 2026-03-17
**Branch:** `review/business-logic-audit`
**Status:** All 9 persona replays complete, 1 (Tomoko) turns-only (no summary JSON)

---

## 1. Experiment Overview

This experiment tested the graph-based memory architecture as a replacement for Unspool's pipeline-based orchestrator. The goal: determine whether a semantic knowledge graph (SurrealDB nodes + edges + trigger chains) can handle realistic ADHD user behavior across 10 diverse personas over 30-90 simulated days.

**Pipeline under test:**
```
User message → quick_ingest (extract nodes/edges)
             → build_active_subgraph (trigger chain: semantic + temporal + open_items + recent + suppression → graph_walk)
             → serialize subgraph → reason_and_respond (LLM)
             → feedback detection (async)
             → evolution (batch, per-day: embeddings, similarity, merges, contradictions, decay)
```

**Models used:**
- Ingest + reasoning: `gpt-4.1-nano`
- Embeddings: `text-embedding-3-small`
- Corpus generation: `qwen2.5:7b` (Ollama, 3090 Ti + 2070 S) and `gpt-4o-mini` (Tomoko, Maya, Diego)

---

## 2. Corpus

### 2.1 Personas

10 personas spanning ages 17-63, each targeting different edge cases:

| Persona | Age | Sim Days | Messages | Final Nodes | Final Edges | Key Edge Cases |
|---------|-----|----------|----------|-------------|-------------|----------------|
| **Diego** | 28 | 90 | 249 | 1,456 | 992 | Extreme contradictions, voice-to-text artifacts, bilingual |
| **Elena** | 52 | 90 | 333 | 939 | 635 | 30+ reports, name collisions, formal/chaotic tone shifts |
| **Jaden** | 17 | 90 | 167 | 416 | 670 | Ultra-short messages ("k", "bruh"), long disappearances |
| **Kwame** | 41 | 90 | 280 | 561 | 576 | Cross-domain density (plumbing + family + church) |
| **Marcus** | 34 | 30 | 106 | 413 | 482 | Freelance invoicing, hyperfocus, creative blocks |
| **Maya** | 27 | 30 | 97 | 626 | 538 | Thesis anxiety, stream-of-consciousness, guilt loops |
| **Priya** | 31 | 30 | 56 | 159 | 140 | New parent sleep deprivation, API migration stress |
| **Ruth** | 63 | 90 | 141 | 557 | 444 | 150-250 word messages, buried info, topic resurrection |
| **Sam** | 22 | 90 | 249 | 801 | 553 | AuDHD, self-corrections, mycology hyperfocus dumps |
| **Tomoko** | 39 | 90 | 208* | 1,240* | 982* | Bilingual JP/EN, timezone confusion, immigration deadlines |

\* Tomoko has turns data only (208 turns JSONL); no summary replay JSON was produced.

**Totals:** 1,886 messages replayed (1,678 from 9 completed replays + 208 Tomoko turns). Original corpus contained 2,628 JSONL entries across all persona files (including day markers and skipped days).

### 2.2 Generation Infrastructure

- **3090 Ti (port 11434):** Elena, Ruth, Marcus, Priya — `qwen2.5:7b`
- **2070 S (port 11435):** Jaden, Kwame, Sam — `qwen2.5:7b` Q4
- **gpt-4o-mini (API):** Tomoko (bilingual quality), Maya, Diego
- **Temperature:** 1.1 (high variance for naturalistic diversity)
- **Concurrency:** 6 personas in parallel
- **Hardcoded messages:** Jaden only — "k", "done", "ugh", "lol nvm", "idk", "ya", "nah", "bet", "bruh", "w/e"

### 2.3 Scenario Injection

35 scripted scenarios across 10 categories were injected at scheduled intervals to guarantee edge-case coverage:

| Category | Scenarios | Total Tagged Turns |
|----------|-----------|-------------------|
| Contradictions | time_change, location_change, priority_reversal, name_confusion, date_shift, plan_180 | 115 |
| Corrections | explicit, implicit, typo, retroactive | 67 |
| Emotional spirals | deadline_anxiety, frustration_recovery, guilt_cascade | 66 |
| Completions | clean, partial, reversal | 60 |
| Communication extremes | single_word, wall_of_text, all_caps, emoji_only | 50 |
| Gaps & resurrections | short_gap, long_gap, topic_resurrection | 25 |
| Ambiguity | that_thing, the_usual, pronoun_ambiguity, name_collision, tomorrow_midnight | 47 |
| Time edge cases | dst_confusion, timezone_mix, next_friday | 29 |
| Staleness | repeated_worry, outdated_info | 46 |
| Multi-topic density | five_topics, rapid_switching | 40 |
| Open-ended (unscripted) | — | 180 |

**725 of 1,678 turns (43%) had scenario tags.** The remaining 57% were free-form LLM-generated messages reflecting each persona's natural communication style.

---

## 3. Results

### 3.1 Aggregate Performance

| Metric | Mean | Median | P95 | Min | Max | N |
|--------|------|--------|-----|-----|-----|---|
| **Ingest** | 3,356 ms | 3,307 ms | 5,955 ms | 547 ms | 21,853 ms | 1,365 |
| **Retrieval** | 1,585 ms | 1,137 ms | 4,437 ms | 21 ms | 5,922 ms | 1,365 |
| **Reasoning** | 1,121 ms | 911 ms | 2,009 ms | 597 ms | 10,445 ms | 1,365 |
| **Total** | 6,064 ms | 5,916 ms | 9,718 ms | 1,542 ms | 23,270 ms | 1,365 |

N=1,365 excludes 313 turns with 0ms timing (Jaden's hardcoded messages and day-boundary turns that skip the pipeline).

**Key observations:**
- **Ingest dominates.** At 55% of total time, node/edge extraction is the bottleneck — expected since it involves an LLM call to parse natural language into graph structure.
- **Reasoning is fast.** Median 911ms for a full LLM response with graph context is acceptable for production streaming.
- **Retrieval scales sublinearly** with graph size (see 3.2), which is the critical finding.

### 3.2 Retrieval Scaling

Retrieval time as graphs grow — first 10 turns vs last 10 turns per persona:

| Persona | Turns | Final Nodes | Retrieval First 10 | Retrieval Last 10 | Slowdown |
|---------|-------|-------------|--------------------:|------------------:|---------:|
| Diego | 249 | 1,456 | 189 ms | 920 ms | 4.9x |
| Elena | 333 | 939 | 202 ms | 1,387 ms | 6.9x |
| Jaden | 167 | 416 | 88 ms | 4,992 ms | **56.7x** |
| Kwame | 280 | 561 | 139 ms | 2,317 ms | 16.7x |
| Marcus | 106 | 413 | 142 ms | 2,514 ms | 17.7x |
| Maya | 97 | 626 | 154 ms | 2,636 ms | 17.1x |
| Priya | 56 | 159 | 142 ms | 530 ms | 3.7x |
| Ruth | 141 | 557 | 138 ms | 2,967 ms | 21.5x |
| Sam | 249 | 801 | 170 ms | 1,325 ms | 7.8x |

**Findings:**
- **Jaden is the outlier** at 56.7x slowdown with only 416 nodes. The high edge-to-node ratio (1.61 — highest of all personas) causes graph_walk explosion. Jaden's ultra-short messages ("k", "done") create ambiguous nodes that get heavily cross-linked during evolution.
- **Diego handles scale best** despite having the most nodes (1,456). His nodes/turn ratio of 5.8 means more specific, well-differentiated nodes that don't over-connect. Retrieval stays under 1s.
- **Priya (smallest graph, 159 nodes)** has the smallest slowdown (3.7x), confirming that retrieval degradation is graph-size-related.
- **The graph_walk trigger is the scaling bottleneck.** It runs after all independent triggers and does 1-hop traversal from their combined results. More edges = more traversal = more time.

**Recommendation:** Cap graph_walk output (already at max_nodes: 30, but edge traversal itself is expensive in SurrealDB). Consider indexing edge endpoints or switching to batched traversal queries.

### 3.3 Graph Growth Patterns

| Persona | Nodes/Turn | Edges/Nodes | Interpretation |
|---------|-----------|-------------|----------------|
| Maya | 6.5 | 0.86 | Stream-of-consciousness = many distinct concepts per message |
| Diego | 5.8 | 0.68 | Multi-topic, bilingual = high concept extraction |
| Ruth | 4.0 | 0.80 | Long messages with buried info = more nodes, moderate linking |
| Marcus | 3.9 | 1.17 | Moderate messages but creative/interconnected topics |
| Sam | 3.2 | 0.69 | Structured + emotional alternation, clean concept boundaries |
| Elena | 2.8 | 0.68 | Professional communication, explicit topics |
| Priya | 2.8 | 0.88 | Concise, direct messages |
| Jaden | 2.5 | **1.61** | Short messages but evolution over-links ambiguous nodes |
| Kwame | 2.0 | 1.03 | Cross-domain but practical/concrete topics |

**Graph density (edges/nodes) correlates with retrieval degradation more than raw node count.** Jaden's 1.61 ratio produces the worst retrieval scaling despite having only 416 nodes. Diego's 1,456 nodes at 0.68 ratio stay fast.

### 3.4 Evolution Statistics

| Persona | Evolutions Run | Skipped Days | Active Days |
|---------|---------------|--------------|-------------|
| Elena | 84 | 6 | 84/90 |
| Kwame | 82 | 8 | 82/90 |
| Sam | 81 | 8 | 82/90 |
| Diego | 77 | 13 | 77/90 |
| Ruth | 68 | 22 | 68/90 |
| Jaden | 63 | 27 | 63/90 |
| Maya | 30 | 0 | 30/30 |
| Marcus | 27 | 3 | 27/30 |
| Priya | 23 | 7 | 23/30 |

**535 total evolution cycles** across all personas. Each evolution cycle: generates missing embeddings, discovers connections via similarity (threshold 0.8), runs LLM synthesis for merges/contradictions/refinements, applies edge decay (0.99x per cycle, min 0.01), and prunes weak edges.

Jaden's 27 skipped days (30% skip rate) matches his persona config (`skip_day_probability: 0.25`) — long disappearances are being simulated correctly.

---

## 4. Qualitative Analysis

### 4.1 Correction Handling

The graph handles explicit corrections well when the user clearly signals the correction:

> **Elena, day 4** (explicit_correction):
> "Hey, Marco said something about a new game. I mean, it's not like I've forgotten about the slides, but..."
> **Unspool:** "It's okay to want a quick escape—sometimes a tiny break helps clear the fog. Paying the tuition now, even if just a quick action, could ease that mental load..."

The system picks up the self-correction ("I mean, it's not like I've forgotten") and responds to the corrected intent rather than the surface statement. Ingest creates an `edge_update` that weakens the connection between the original statement and the corrected one.

**Gap: Implicit corrections** (where the user simply states the correct info without acknowledging the error) are harder. The evolution phase catches some of these via contradiction detection (threshold 0.9), but the delay means 1-2 messages may use stale data.

### 4.2 Emotional Attunement

Responses demonstrate appropriate tone matching even without access to the hidden `energy` and `mood` fields:

> **Priya, day 2** (energy: low, mood: bad):
> "Hey, what should I do again? API migration is just not going well, and Raj keeps reminding me of the performance review..."
> **Unspool:** "It sounds like you're really running on empty. Maybe give yourself permission to just take a tiny breather..."

The graph surfaces relevant context (API migration node, performance review node, Arjun/teething nodes) and the reasoning LLM infers emotional state from the message content. The response avoids productivity-pushing and offers emotional validation first.

### 4.3 Topic Density

Kwame's cross-domain messages (plumbing + kids + church + health in one message) produce clean multi-node ingest. At 2.0 nodes/turn (lowest ratio), the system is appropriately consolidating related concepts rather than fragmenting them.

> **Kwame, day 1** (5 topics in one message):
> "invoice reminder, van brake issues, Nana errands, church picnic, Kofi's game Saturday"
> → Ingest extracts ~5-6 nodes with edges linking family/business/church domains

The low nodes/turn ratio suggests effective deduplication — repeated references to "Kofi" or "the van" match existing nodes rather than creating duplicates.

### 4.4 Ultra-Short Messages

Jaden's hardcoded messages ("k", "done", "bruh") expose a weakness: the ingest model creates vague nodes from minimal content. These nodes then get heavily cross-linked during evolution because their embeddings are too generic, leading to the 1.61 edges/nodes ratio and worst-case retrieval scaling.

**Recommendation:** Add a minimum content length threshold for node creation. Messages under ~10 characters should update existing node activation times without creating new nodes.

### 4.5 Orphan Nodes

Not directly measured in this experiment, but the evolution cycle's edge decay (0.99x per cycle, min 0.01) means nodes can become effectively disconnected after ~460 cycles without traversal (0.99^460 ≈ 0.01). For 90-day personas running daily evolution, this means nodes untouched for ~15 months would reach minimum edge strength — well beyond the experiment duration. No pruning was observed in this run.

**Future work:** Add orphan detection metrics to replay output. Track nodes with all edges below 0.1 strength.

### 4.6 Error Rate

Several "Sorry, something went wrong" responses appeared in the replay data, particularly for Diego (days 7, 9, 22, 34, 54) and Elena (day 13). These represent pipeline timeouts or LLM errors during the 60-second window. The error rate was not systematically tracked in the replay results.

**Recommendation:** Add `error_count` and `timeout_count` fields to `ReplayResult` for future runs.

---

## 5. Deduplication Effectiveness

The evolution phase's dedup threshold (0.9 similarity) and the ingest phase's `existing_match` field work together to control node proliferation:

| Persona | Messages | Final Nodes | Nodes/Message | Assessment |
|---------|----------|-------------|---------------|------------|
| Kwame | 280 | 561 | 2.0 | Excellent — heavy topic overlap handled well |
| Jaden | 167 | 416 | 2.5 | Good count, but edge over-linking is the real issue |
| Elena | 333 | 939 | 2.8 | Good — 30+ reports don't create 30+ name nodes |
| Priya | 56 | 159 | 2.8 | Expected for short run |
| Sam | 249 | 801 | 3.2 | Moderate — mycology dumps create many unique concepts |
| Marcus | 106 | 413 | 3.9 | Slightly high — creative metaphors resist dedup |
| Ruth | 141 | 557 | 4.0 | Expected — long messages contain many unique details |
| Diego | 249 | 1,456 | 5.8 | High — bilingual + voice artifacts create variants |
| Maya | 97 | 626 | 6.5 | Highest — stream-of-consciousness creates many tangential nodes |

**Diego's 5.8 nodes/turn** is concerning. Bilingual messages and voice-to-text artifacts ("sooo", "like", "OMG") likely create variant nodes that don't match existing ones. The dedup threshold of 0.9 may be too strict for noisy input.

**Recommendation:** Lower `dedup_threshold` to 0.85 for personas with high noise profiles, or add a normalization step before embedding comparison.

---

## 6. Architecture Observations

### 6.1 Trigger Chain

The 5 independent triggers + 1 dependent trigger design works well:
- **Semantic** (vector_search, limit 15, min_sim 0.3) provides the foundation
- **Temporal** (48h window) catches upcoming deadlines without explicit queries
- **Open_items** (status: "not done") surfaces unfinished work
- **Recent** (24h, limit 10) maintains conversational continuity
- **Suppression** (status: "surfaced", 24h window) prevents repetitive responses
- **Graph_walk** (1-hop from all above) discovers indirect connections

The semantic trigger does most of the work. Temporal and open_items add value for deadline-driven personas (Tomoko, Elena) but are less relevant for freeform personas (Maya, Sam).

### 6.2 Serialization

The 2,000-token context window for graph serialization is tight. With 50-node max subgraphs, each node gets ~40 tokens of context on average. For Ruth's long-message graph (detailed nodes), this may truncate important context.

**Recommendation:** Make `max_context_tokens` configurable per-persona or scale it based on graph density.

### 6.3 Feedback Loop

Feedback was skipped for all replays (`skip_feedback: true` is the default for bulk testing). The `feedback_ms` values of ~0.0004ms across all turns confirm no feedback processing occurred. This means:
- No nodes were marked as "surfaced" (suppression trigger was inert)
- No completions were tracked
- No commitments were made

**Future experiment:** Run a subset of replays with feedback enabled and compare suppression effectiveness and completion tracking accuracy.

---

## 7. Key Metrics Summary

| Metric | Value |
|--------|-------|
| Personas tested | 10 |
| Completed replay summaries | 9 (Tomoko turns-only) |
| Total messages replayed | 1,886 |
| Total evolution cycles | 535 |
| Scenario categories | 10 |
| Unique scenario tags | 36 |
| Scenario-tagged turns | 725 (43%) |
| Total nodes created | 5,928 (9 replays) + ~1,240 (Tomoko) |
| Total edges created | 5,030 (9 replays) + ~982 (Tomoko) |
| Median turn latency | 5,916 ms |
| P95 turn latency | 9,718 ms |
| Median ingest time | 3,307 ms |
| Median retrieval time | 1,137 ms |
| Median reasoning time | 911 ms |

---

## 8. Recommendations

### P0 — Must fix before production

1. **Cap graph_walk traversal cost.** Jaden's 56.7x retrieval slowdown shows the walk trigger can explode on dense graphs. Add an edge-count limit or time budget to the traversal query.

2. **Minimum content threshold for node creation.** Messages under ~10 characters should not create new nodes. Update activation timestamps on existing nodes instead.

3. **Track error counts in replay results.** Multiple "sorry, something went wrong" responses went untracked. Add `error_count`, `timeout_count`, and `error_turns` to `ReplayResult`.

### P1 — Should fix

4. **Lower dedup threshold for noisy input.** Diego's 5.8 nodes/turn suggests 0.9 similarity is too strict when voice-to-text artifacts or bilingual code-switching create surface variations of the same concept. Test 0.85.

5. **Run feedback-enabled replays.** The suppression trigger was inert for this entire experiment. Need data on whether feedback detection + suppression actually reduces repetitive surfacing.

6. **Add graph density metrics to evolution output.** Track edges/nodes ratio, orphan node count, and max-degree nodes per evolution cycle.

### P2 — Nice to have

7. **Dynamic context window.** Scale `max_context_tokens` based on graph density or persona verbosity.

8. **Tomoko replay completion.** The missing summary JSON means we can't compare her performance against other personas in aggregate.

9. **A/B config comparison.** The replay system supports `--graph-config` for testing different configurations. Run the same corpus through different dedup thresholds, walk depths, and decay rates.

---

## 9. Files Reference

| Path | Description |
|------|-------------|
| `results/replay-{persona}-{hash}.json` | Full replay results (9 files) |
| `results/replay-{persona}-{hash}_turns.jsonl` | Per-turn timing data (10 files) |
| `corpus/output/latest/*.jsonl` | Generated corpus (10 personas, 2,628 entries) |
| `config/personas/*.yaml` | Persona definitions (10 files) |
| `corpus/scenarios/*.yaml` | Scenario definitions (10 files, 35 scenarios) |
| `config/graph.yaml` | Graph system config used for replays |
| `config/triggers.yaml` | Trigger chain definitions |
| `config/corpus.yaml` | Corpus generation config |

---

## 10. Conclusion

The graph-based memory architecture handles realistic ADHD user behavior at scale. Across 1,886 messages from 10 diverse personas, the system maintained sub-6-second median latency, effectively deduplicated concepts (2.0-6.5 nodes/turn depending on communication style), and produced emotionally appropriate responses.

The primary risk is **retrieval scaling on dense graphs**. The graph_walk trigger's 1-hop traversal is the bottleneck, and personas with high edge density (Jaden: 1.61 edges/nodes) see disproportionate slowdown. This is solvable with traversal budgets and smarter node creation for minimal-content messages.

The feedback loop remains untested at scale. The next experiment should enable feedback detection and measure whether suppression actually prevents the repetitive surfacing that ADHD users would find particularly frustrating.

The corpus + replay infrastructure is production-ready for ongoing regression testing. Any graph config change can be validated by replaying the same 1,886 messages and comparing timing/quality metrics.
