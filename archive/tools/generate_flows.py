#!/usr/bin/env python3
"""Auto-generate flow diagrams from Unspool's YAML configs.

Reads all config files (intents, pipelines, context_rules, scoring, proactive,
jobs, patterns, gate) and generates Mermaid diagrams + an HTML viewer.

Usage:
    python tools/generate_flows.py              # Generate all
    python tools/generate_flows.py --check      # CI: fail if output differs
    python tools/generate_flows.py --only pipelines  # Just one diagram type
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
CONFIG = BACKEND / "config"
PIPELINES_DIR = CONFIG / "pipelines"
PROMPTS_DIR = BACKEND / "prompts"
MIGRATIONS_DIR = BACKEND / "supabase" / "migrations"
OUT_DIR = ROOT / "docs" / "flows"

# ---------------------------------------------------------------------------
# Structural knowledge: tool/job → DB access
# ---------------------------------------------------------------------------

TOOL_DB_ACCESS: dict[str, dict[str, list[str]]] = {
    "save_items": {"reads": [], "writes": ["items", "item_events"]},
    "mark_item_done": {"reads": ["items"], "writes": ["items", "item_events"]},
    "reschedule_item": {"reads": ["items"], "writes": ["items", "item_events"]},
    "enrich_items": {"reads": [], "writes": []},
    "pick_next_item": {"reads": ["items"], "writes": []},
    "fuzzy_match_item": {"reads": ["items"], "writes": []},
    "check_momentum": {"reads": ["item_events"], "writes": []},
    "smart_fetch": {
        "reads": ["items", "memories", "messages", "calendar_events"],
        "writes": [],
    },
    "fetch_profile": {"reads": ["user_profiles"], "writes": []},
    "fetch_messages": {"reads": ["messages"], "writes": []},
    "fetch_items": {"reads": ["items"], "writes": []},
    "fetch_urgent_items": {"reads": ["items"], "writes": []},
    "fetch_memories": {"reads": ["memories"], "writes": []},
    "fetch_entities": {"reads": ["entities"], "writes": []},
    "fetch_calendar_events": {"reads": ["calendar_events"], "writes": []},
    "search_semantic": {"reads": ["items"], "writes": []},
    "search_hybrid": {"reads": ["items"], "writes": []},
    "search_text": {"reads": ["items"], "writes": []},
    "generate_embedding": {"reads": [], "writes": []},
    "fetch_graph_context": {
        "reads": ["memory_nodes", "memory_edges", "node_neighbors"],
        "writes": ["memory_nodes"],
    },
}

JOB_DB_ACCESS: dict[str, dict[str, list[str]]] = {
    "process_conversation": {
        "reads": ["items", "messages"],
        "writes": ["items", "item_events", "entities", "memories"],
    },
    "decay_urgency": {"reads": ["items"], "writes": ["items"]},
    "check_deadlines": {
        "reads": ["items", "user_profiles", "push_subscriptions"],
        "writes": ["user_profiles"],
    },
    "sync_calendar": {
        "reads": ["user_profiles", "oauth_tokens"],
        "writes": ["calendar_events"],
    },
    "detect_patterns": {
        "reads": ["user_profiles", "item_events", "messages", "memories"],
        "writes": ["user_profiles"],
    },
    "reset_notifications": {"reads": [], "writes": ["user_profiles"]},
    "process_graph": {
        "reads": ["messages", "memory_nodes", "memory_edges", "node_neighbors"],
        "writes": ["memory_nodes", "memory_edges", "node_neighbors"],
    },
}

SCORING_CONSUMERS: dict[str, dict[str, list[str]]] = {
    "decay": {
        "tools": [],
        "jobs": ["decay_urgency"],
        "fields": ["items.urgency_score", "items.status"],
    },
    "momentum": {"tools": ["check_momentum"], "jobs": [], "fields": []},
    "pick_next": {
        "tools": ["pick_next_item"],
        "jobs": [],
        "fields": ["items.last_surfaced_at"],
    },
    "reschedule": {
        "tools": ["reschedule_item"],
        "jobs": [],
        "fields": ["items.urgency_score", "items.nudge_after"],
    },
    "matching": {"tools": ["fuzzy_match_item"], "jobs": [], "fields": []},
    "notifications": {
        "tools": [],
        "jobs": ["check_deadlines"],
        "fields": ["user_profiles.notification_sent_today"],
    },
}

CONTEXT_LOADER_TABLES: dict[str, str] = {
    "profile": "user_profiles",
    "recent_messages": "messages",
    "open_items": "items",
    "urgent_items": "items",
    "memories": "memories",
    "entities": "entities",
    "calendar_events": "calendar_events",
    "graph_context": "memory_nodes",
}

# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_all_configs() -> dict:
    configs: dict = {}
    configs["intents"] = load_yaml(CONFIG / "intents.yaml")
    configs["context_rules"] = load_yaml(CONFIG / "context_rules.yaml")
    configs["scoring"] = load_yaml(CONFIG / "scoring.yaml")
    configs["proactive"] = load_yaml(CONFIG / "proactive.yaml")
    configs["jobs"] = load_yaml(CONFIG / "jobs.yaml")
    configs["patterns"] = load_yaml(CONFIG / "patterns.yaml")
    configs["gate"] = load_yaml(CONFIG / "gate.yaml")
    configs["variants"] = load_yaml(CONFIG / "variants.yaml")
    configs["graph"] = load_yaml(CONFIG / "graph.yaml")
    configs["triggers"] = load_yaml(CONFIG / "triggers.yaml")

    configs["pipelines"] = {}
    for p in sorted(PIPELINES_DIR.glob("*.yaml")):
        configs["pipelines"][p.stem] = load_yaml(p)

    return configs


def parse_table_schemas() -> dict[str, list[dict[str, str]]]:
    """Extract table name → column list from migration SQL."""
    tables: dict[str, list[dict[str, str]]] = {}
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    full_sql = "\n".join(f.read_text() for f in sql_files)

    # CREATE TABLE
    for m in re.finditer(
        r"CREATE TABLE (\w+)\s*\((.*?)\);", full_sql, re.DOTALL | re.IGNORECASE
    ):
        tname = m.group(1)
        body = m.group(2)
        cols = []
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line or line.startswith("--"):
                continue
            # Skip constraints
            if re.match(
                r"^(PRIMARY|UNIQUE|CHECK|FOREIGN|CONSTRAINT|CREATE)", line, re.I
            ):
                continue
            parts = line.split()
            if len(parts) >= 2 and parts[0].upper() not in (
                "PRIMARY",
                "UNIQUE",
                "CHECK",
                "FOREIGN",
                "CONSTRAINT",
            ):
                col_name = parts[0]
                col_type = parts[1]
                cols.append({"name": col_name, "type": col_type})
        if cols:
            tables[tname] = cols

    # ALTER TABLE ADD COLUMN
    for m in re.finditer(
        r"ALTER TABLE (\w+)\s+ADD COLUMN\s+(?:IF NOT EXISTS\s+)?(\w+)\s+(\w+)",
        full_sql,
        re.IGNORECASE,
    ):
        tname, col_name, col_type = m.group(1), m.group(2), m.group(3)
        if tname in tables:
            if not any(c["name"] == col_name for c in tables[tname]):
                tables[tname] = [*tables[tname], {"name": col_name, "type": col_type}]

    # ALTER TABLE RENAME COLUMN
    for m in re.finditer(
        r"ALTER TABLE (\w+)\s+RENAME COLUMN\s+(\w+)\s+TO\s+(\w+)",
        full_sql,
        re.IGNORECASE,
    ):
        tname, old, new = m.group(1), m.group(2), m.group(3)
        if tname in tables:
            for c in tables[tname]:
                if c["name"] == old:
                    c["name"] = new

    return tables


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------


def build_dependency_graph(
    configs: dict,
) -> dict:
    """Build forward dependency graph: config → pipeline → tool/prompt → DB."""
    graph: dict = {
        "intent_to_pipeline": {},
        "pipeline_steps": {},
        "pipeline_context": {},
        "pipeline_post_processing": {},
        "prompt_to_pipelines": {},
        "tool_to_pipelines": {},
    }

    # intents → pipelines
    for intent, info in configs["intents"].get("intents", {}).items():
        graph["intent_to_pipeline"][intent] = info.get("pipeline", intent)

    # pipelines → steps, context, post-processing
    rules = configs["context_rules"].get("rules", {})
    for pname, pdata in configs["pipelines"].items():
        steps = pdata.get("steps", [])
        graph["pipeline_steps"][pname] = steps

        # Context from context_rules
        intent_rule = rules.get(pname, {})
        graph["pipeline_context"][pname] = {
            "required": intent_rule.get("load", []),
            "optional": intent_rule.get("optional", []),
        }

        # Post-processing
        pp = pdata.get("post_processing", [])
        graph["pipeline_post_processing"][pname] = pp

        # Reverse maps
        for step in steps:
            prompt = step.get("prompt")
            if prompt:
                graph["prompt_to_pipelines"].setdefault(prompt, []).append(pname)
            tool = step.get("tool")
            if tool:
                graph["tool_to_pipelines"].setdefault(tool, []).append(pname)

    return graph


def build_impact_matrix(configs: dict, graph: dict) -> list[dict[str, str]]:
    """Invert the dependency graph to produce an impact matrix."""
    rows: list[dict[str, str]] = []

    # system.md affects everything
    rows.append(
        {
            "file": "system.md",
            "type": "prompt",
            "flows": "All 10 pipelines (injected into every LLM call)",
            "tables": "",
            "fields": "",
        }
    )

    # classify_intent.md
    rows.append(
        {
            "file": "classify_intent.md",
            "type": "prompt",
            "flows": "Intent classification (all messages)",
            "tables": "",
            "fields": "",
        }
    )

    # Per-prompt impact
    for prompt, pipelines in sorted(graph["prompt_to_pipelines"].items()):
        if prompt in ("system.md", "classify_intent.md"):
            continue
        # Find which steps in which pipelines use this prompt
        step_details = []
        all_tables: set[str] = set()
        for pname in pipelines:
            for step in graph["pipeline_steps"].get(pname, []):
                if step.get("prompt") == prompt:
                    step_details.append(f"{pname} (step: {step['id']})")
                    # If this step feeds into a tool step, trace DB impact
        # Check if pipeline has tool steps that write
        for pname in pipelines:
            for step in graph["pipeline_steps"].get(pname, []):
                tool = step.get("tool")
                if tool and tool in TOOL_DB_ACCESS:
                    all_tables.update(TOOL_DB_ACCESS[tool].get("writes", []))
            for pp in graph["pipeline_post_processing"].get(pname, []):
                job = pp.get("job", "")
                if job in JOB_DB_ACCESS:
                    all_tables.update(JOB_DB_ACCESS[job].get("writes", []))

        rows.append(
            {
                "file": prompt,
                "type": "prompt",
                "flows": ", ".join(step_details),
                "tables": ", ".join(sorted(all_tables)) if all_tables else "",
                "fields": "",
            }
        )

    # Proactive prompts
    for trigger_name, trigger in configs["proactive"].get("triggers", {}).items():
        prompt = trigger.get("prompt", "")
        if prompt:
            rows.append(
                {
                    "file": prompt,
                    "type": "prompt (proactive)",
                    "flows": f"Proactive trigger: {trigger_name}",
                    "tables": "",
                    "fields": "",
                }
            )

    # Pattern analysis prompts
    for analysis_name, analysis in configs["patterns"].get("analyses", {}).items():
        prompt = analysis.get("prompt")
        if prompt:
            rows.append(
                {
                    "file": prompt,
                    "type": "prompt (patterns)",
                    "flows": f"detect_patterns job ({analysis_name})",
                    "tables": "user_profiles",
                    "fields": "patterns",
                }
            )

    # Scoring sections
    for section, consumers in SCORING_CONSUMERS.items():
        affected = []
        for tool in consumers["tools"]:
            pips = graph["tool_to_pipelines"].get(tool, [])
            affected.extend(f"{p} via {tool}" for p in pips)
        for job in consumers["jobs"]:
            affected.append(f"{job} job")
        rows.append(
            {
                "file": f"scoring.yaml ({section})",
                "type": "config",
                "flows": ", ".join(affected) if affected else "",
                "tables": "",
                "fields": ", ".join(consumers["fields"]),
            }
        )

    # Other configs
    for cfg_name, desc in [
        ("context_rules.yaml", "All intents (context assembly)"),
        ("gate.yaml", "Rate limiting in /api/chat"),
        ("proactive.yaml", "Proactive message triggers"),
        ("patterns.yaml", "detect_patterns job"),
        ("intents.yaml", "Intent to pipeline routing"),
        ("jobs.yaml", "Background job schedules + dispatch"),
        ("variants.yaml", "A/B test variant selection"),
    ]:
        rows.append(
            {
                "file": cfg_name,
                "type": "config",
                "flows": desc,
                "tables": "",
                "fields": "",
            }
        )

    # Pipeline files
    for pname in sorted(configs["pipelines"]):
        tables: set[str] = set()
        for step in graph["pipeline_steps"].get(pname, []):
            tool = step.get("tool")
            if tool and tool in TOOL_DB_ACCESS:
                tables.update(TOOL_DB_ACCESS[tool].get("writes", []))
        for pp in graph["pipeline_post_processing"].get(pname, []):
            job = pp.get("job", "")
            if job in JOB_DB_ACCESS:
                tables.update(JOB_DB_ACCESS[job].get("writes", []))
        rows.append(
            {
                "file": f"pipelines/{pname}.yaml",
                "type": "pipeline",
                "flows": f"{pname} pipeline",
                "tables": ", ".join(sorted(tables)),
                "fields": "",
            }
        )

    return rows


# ---------------------------------------------------------------------------
# Mermaid generators
# ---------------------------------------------------------------------------

STYLE_LLM = "fill:#2d5a3d,stroke:#5dcaa5,color:#e0e0e0"
STYLE_TOOL = "fill:#2d3d5a,stroke:#5588cc,color:#e0e0e0"
STYLE_ASYNC = "fill:#5a3d2d,stroke:#cc8855,color:#e0e0e0"
STYLE_ERROR = "fill:#5a2d2d,stroke:#cc5555,color:#e0e0e0"
STYLE_ROUTE = "fill:#3d3d5a,stroke:#8888cc,color:#e0e0e0"
STYLE_GRAY = "fill:#3a3a3a,stroke:#888888,color:#e0e0e0"


def _sanitize_id(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", s)


def gen_message_flow(configs: dict, graph: dict) -> str:
    lines = ["flowchart TD"]
    lines.append(
        '    MSG["User sends message"] --> GATE{"Rate limit check\\n(Redis, fail-open)"}'
    )
    lines.append('    GATE -->|blocked| R429["429: limit reached"]')
    lines.append(
        '    GATE -->|allowed| SAVE_USER["Save user message\\n→ messages table"]'
    )
    lines.append('    SAVE_USER --> TIMEOUT["60s timeout wrapper"]')
    lines.append('    TIMEOUT --> CLASSIFY["classify_intent\\n🤖 classify_intent.md"]')
    lines.append('    CLASSIFY --> CTX["Assemble context\\n(context_rules.yaml)"]')
    lines.append("    CTX --> ROUTE{Intent Router}")

    # Intent → pipeline routing
    intents = configs["intents"].get("intents", {})
    pipeline_nodes = set()
    for intent, info in intents.items():
        pname = info.get("pipeline", intent)
        node_id = f"P_{_sanitize_id(pname).upper()}"
        pipeline_nodes.add((node_id, pname))
        lines.append(f'    ROUTE -->|{intent}| {node_id}["{pname} pipeline"]')

    for node_id, _ in sorted(pipeline_nodes):
        lines.append(f"    {node_id} --> STREAM")

    lines.append(
        '    STREAM["Stream response via SSE"] --> SAVE_AI["Save assistant response\\n→ messages table"]'
    )
    lines.append('    SAVE_AI --> POST{"Post-processing?"}')

    # Which pipelines have post-processing
    pp_pipelines = [p for p, pp in graph["pipeline_post_processing"].items() if pp]
    if pp_pipelines:
        lines.append(
            f'    POST -->|{", ".join(pp_pipelines)}| QSTASH["QStash dispatch\\n10s delay"]'
        )
    lines.append('    POST -->|other pipelines| DONE["Done"]')
    lines.append(
        '    QSTASH --> PROC["process_conversation\\n→ embeddings, entities, memories"]'
    )

    # Error paths
    lines.append(
        "    TIMEOUT -->|TimeoutError| ERR_TIMEOUT[\"'sorry, that took too long'\\n→ metadata.error=true\"]"
    )
    lines.append(
        "    TIMEOUT -->|Exception| ERR_CRASH[\"'sorry, something went wrong'\\n→ metadata.error=true\"]"
    )

    # Styles
    lines.append(f"    style CLASSIFY {STYLE_LLM}")
    lines.append(f"    style ROUTE {STYLE_ROUTE}")
    lines.append(f"    style QSTASH {STYLE_ASYNC}")
    lines.append(f"    style PROC {STYLE_ASYNC}")
    lines.append(f"    style ERR_TIMEOUT {STYLE_ERROR}")
    lines.append(f"    style ERR_CRASH {STYLE_ERROR}")
    lines.append(f"    style R429 {STYLE_ERROR}")

    # Click links
    lines.append('    click CLASSIFY "backend/prompts/classify_intent.md"')
    lines.append('    click CTX "backend/config/context_rules.yaml"')
    lines.append('    click ROUTE "backend/config/intents.yaml"')
    lines.append('    click QSTASH "backend/config/jobs.yaml"')
    for node_id, pname in sorted(pipeline_nodes):
        lines.append(f'    click {node_id} "backend/config/pipelines/{pname}.yaml"')

    return "\n".join(lines)


def gen_pipeline_detail(pname: str, pdata: dict, context: dict) -> str:
    steps = pdata.get("steps", [])
    post_processing = pdata.get("post_processing", [])

    lines = ["flowchart LR"]

    # Context subgraph
    required = context.get("required", [])
    optional = context.get("optional", [])
    if required or optional:
        lines.append('    subgraph ctx["Context Loaded"]')
        lines.append("        direction TB")
        for i, field in enumerate(required):
            lines.append(f'        C{i}["{field}"]')
        for i, field in enumerate(optional, start=len(required)):
            lines.append(f'        C{i}["{field} (opt)"]')
        lines.append("    end")
        if steps:
            first_id = _sanitize_id(steps[0]["id"]).upper()
            lines.append(f"    ctx --> {first_id}")

    # Steps
    styles = []
    clicks = []
    for idx, step in enumerate(steps):
        sid = _sanitize_id(step["id"]).upper()
        stype = step.get("type", "")
        prompt = step.get("prompt", "")
        tool = step.get("tool", "")
        stream = step.get("stream", False)
        schema = step.get("output_schema", "")

        # Build label
        label_parts = [step["id"]]
        if stype == "llm_call":
            label_parts.insert(0, "🤖")
            if prompt:
                label_parts.append(f"LLM: {prompt}")
            if schema:
                label_parts.append(f"→ {schema}")
            if stream:
                label_parts.append("🔴 STREAM")
            styles.append(f"    style {sid} {STYLE_LLM}")
            if prompt:
                clicks.append(f'    click {sid} "backend/prompts/{prompt}"')
        elif stype == "tool_call":
            label_parts.insert(0, "🔧")
            if tool:
                label_parts.append(f"tool: {tool}")
                # Show DB writes
                db_writes = TOOL_DB_ACCESS.get(tool, {}).get("writes", [])
                if db_writes:
                    label_parts.append(f"→ {', '.join(db_writes)}")
            styles.append(f"    style {sid} {STYLE_TOOL}")
            if tool:
                clicks.append(f'    click {sid} "backend/src/tools/"')
        elif stype == "branch":
            styles.append(f"    style {sid} {STYLE_ROUTE}")

        label = "\\n".join(label_parts)
        lines.append(f'    {sid}["{label}"]')

        # Edge to next step with variable flow label
        if idx < len(steps) - 1:
            next_sid = _sanitize_id(steps[idx + 1]["id"]).upper()
            # Extract output variable name from next step's input
            next_inputs = steps[idx + 1].get("input", {}) or {}
            edge_label = ""
            for var_name, var_ref in next_inputs.items():
                if isinstance(var_ref, str) and f"steps.{step['id']}" in var_ref:
                    edge_label = var_name
                    break
            if edge_label:
                lines.append(f"    {sid} -->|{edge_label}| {next_sid}")
            else:
                lines.append(f"    {sid} --> {next_sid}")

    # Post-processing
    if post_processing:
        last_sid = _sanitize_id(steps[-1]["id"]).upper() if steps else "ctx"
        for pp in post_processing:
            pp_id = f"PP_{_sanitize_id(pp.get('job', 'unknown')).upper()}"
            delay = pp.get("delay", "")
            job_name = pp.get("job", "")
            db_writes = JOB_DB_ACCESS.get(job_name, {}).get("writes", [])
            label = f"📬 post: {job_name}"
            if delay:
                label += f"\\n{delay} delay"
            if db_writes:
                label += f"\\n→ {', '.join(db_writes)}"
            lines.append(f'    {last_sid} --> {pp_id}["{label}"]')
            styles.append(f"    style {pp_id} {STYLE_ASYNC}")
            clicks.append(f'    click {pp_id} "backend/config/jobs.yaml"')

    lines.extend(styles)
    lines.extend(clicks)
    return "\n".join(lines)


def gen_background_jobs(configs: dict) -> str:
    lines = ["flowchart TD"]
    cron_jobs = configs["jobs"].get("cron_jobs", {})

    # Cron triggers
    lines.append('    subgraph cron["Cron Triggers (QStash)"]')
    for i, (job_name, job_data) in enumerate(cron_jobs.items()):
        schedule = job_data.get("schedule", "")
        lines.append(f'        T{i}["⏰ {job_name}\\n{schedule}"]')
    lines.append("    end")

    # Event trigger
    lines.append('    subgraph event["Event Triggers"]')
    lines.append('        TE["📬 10s after chat\\n(brain_dump, conversation)"]')
    lines.append("    end")

    # Job nodes with reads/writes
    for i, (job_name, _) in enumerate(cron_jobs.items()):
        job_id = _sanitize_id(job_name).upper()
        access = JOB_DB_ACCESS.get(job_name.replace("-", "_"), {})
        reads = access.get("reads", [])
        writes = access.get("writes", [])

        label_parts = [job_name.replace("-", "_")]
        if reads:
            label_parts.append(f"READ: {', '.join(reads)}")
        if writes:
            label_parts.append(f"WRITE: {', '.join(writes)}")

        label = "\\n".join(label_parts)
        lines.append(f'    T{i} --> {job_id}["{label}"]')
        lines.append(f"    style {job_id} {STYLE_TOOL}")
        lines.append(
            f'    click {job_id} "backend/src/jobs/{job_name.replace("-", "_")}.py"'
        )

    # process_conversation (event-triggered)
    pc_access = JOB_DB_ACCESS["process_conversation"]
    pc_label = "process_conversation\\n"
    pc_label += f"READ: {', '.join(pc_access['reads'])}\\n"
    pc_label += f"WRITE: {', '.join(pc_access['writes'])}"
    lines.append(f'    TE --> PROC_CONV["{pc_label}"]')
    lines.append(f"    style PROC_CONV {STYLE_ASYNC}")
    lines.append('    click PROC_CONV "backend/src/jobs/process_conversation.py"')

    return "\n".join(lines)


def gen_db_access_map(
    tables: dict[str, list[dict[str, str]]],
    graph: dict,
    configs: dict,
) -> str:
    """Generate a database access diagram showing tables and their accessors."""
    lines = ["flowchart LR"]

    # Core tables (most accessed)
    core_tables = [
        "items",
        "messages",
        "user_profiles",
        "item_events",
        "memories",
        "entities",
    ]
    secondary_tables = [
        "calendar_events",
        "subscriptions",
        "push_subscriptions",
        "oauth_tokens",
        "llm_usage",
        "experiment_assignments",
        "recurrences",
    ]

    # Build accessor sets per table
    table_readers: dict[str, set[str]] = {
        t: set() for t in [*core_tables, *secondary_tables]
    }
    table_writers: dict[str, set[str]] = {
        t: set() for t in [*core_tables, *secondary_tables]
    }

    # From tools (via pipelines)
    for tool, access in TOOL_DB_ACCESS.items():
        source = f"{tool}"
        for t in access.get("reads", []):
            if t in table_readers:
                table_readers[t].add(source)
        for t in access.get("writes", []):
            if t in table_writers:
                table_writers[t].add(source)

    # From jobs
    for job, access in JOB_DB_ACCESS.items():
        source = f"{job} job"
        for t in access.get("reads", []):
            if t in table_readers:
                table_readers[t].add(source)
        for t in access.get("writes", []):
            if t in table_writers:
                table_writers[t].add(source)

    # API-level access
    table_readers["messages"].add("chat API")
    table_writers["messages"].add("chat API")
    table_readers.setdefault("subscriptions", set()).add("gate check")
    table_writers.setdefault("push_subscriptions", set()).add("subscribe API")
    table_writers.setdefault("oauth_tokens", set()).add("auth API")
    table_writers.setdefault("llm_usage", set()).add("engine (per LLM call)")
    table_readers.setdefault("llm_usage", set()).add("admin API")

    lines.append('    subgraph postgres["PostgreSQL (Supabase)"]')

    for tname in [*core_tables, *secondary_tables]:
        tid = _sanitize_id(tname).upper()
        cols = tables.get(tname, [])
        col_names = [c["name"] for c in cols[:8]]  # Show first 8 columns
        if len(cols) > 8:
            col_names.append(f"... +{len(cols) - 8} more")
        col_str = ", ".join(col_names)
        lines.append(f'        {tid}["{tname}\\n({col_str})"]')

    lines.append("    end")

    # Redis
    lines.append('    subgraph redis["Redis (Upstash)"]')
    lines.append('        REDIS_RATE["rate:user:date\\n(24h TTL)"]')
    lines.append('        REDIS_SESSION["session:user:key\\n(1h TTL)"]')
    lines.append('        REDIS_CACHE["cache:key\\n(30d TTL, variants)"]')
    lines.append("    end")

    # Writer edges
    for tname in [*core_tables, *secondary_tables]:
        tid = _sanitize_id(tname).upper()
        for writer in sorted(table_writers.get(tname, set())):
            wid = f"W_{_sanitize_id(writer).upper()}"
            lines.append(f'    {wid}["{writer}"] -->|writes| {tid}')
            lines.append(f"    style {wid} {STYLE_ASYNC}")

    # Reader edges (only for core tables to avoid clutter)
    for tname in core_tables:
        tid = _sanitize_id(tname).upper()
        for reader in sorted(table_readers.get(tname, set())):
            rid = f"R_{_sanitize_id(tname)}_{_sanitize_id(reader).upper()}"
            lines.append(f'    {tid} -->|reads| {rid}["{reader}"]')
            lines.append(f"    style {rid} {STYLE_TOOL}")

    return "\n".join(lines)


def gen_proactive_flow(configs: dict) -> str:
    triggers = configs["proactive"].get("triggers", {})
    sorted_triggers = sorted(triggers.items(), key=lambda x: x[1].get("priority", 99))

    lines = ["flowchart TD"]
    lines.append(
        '    OPEN["User opens app\\nGET /api/messages"] --> EVAL["Evaluate proactive triggers\\n(proactive.yaml, priority order)"]'
    )

    prev_no = "EVAL"
    for i, (tname, tdata) in enumerate(sorted_triggers):
        tid = f"T{i}"
        aid = f"A{i}"
        priority = tdata.get("priority", i + 1)
        condition = tdata.get("condition", "")
        prompt = tdata.get("prompt", "")
        description = tdata.get("description", tname)
        params = tdata.get("params", {})

        param_str = ", ".join(f"{k}: {v}" for k, v in params.items())

        lines.append(
            f'    {prev_no} --> {tid}{{"P{priority}: {tname}?\\n{condition}\\n({param_str})"}}'
        )
        lines.append(f'    {tid} -->|yes| {aid}["🤖 LLM: {prompt}\\n{description}"]')
        lines.append(f"    style {aid} {STYLE_LLM}")
        lines.append(f'    click {aid} "backend/prompts/{prompt}"')
        lines.append(f"    {aid} --> SAVE")
        prev_no = f"{tid}"
        lines.append(f"    {tid} -->|no| NEXT{i}[ ]")
        lines.append(f"    style NEXT{i} {STYLE_GRAY}")
        prev_no = f"NEXT{i}"

    lines.append(f'    {prev_no} --> NONE["No proactive message"]')
    lines.append('    SAVE["Save as assistant message\\nmetadata.type = proactive"]')
    lines.append('    click EVAL "backend/config/proactive.yaml"')

    return "\n".join(lines)


def gen_config_deps(configs: dict, graph: dict) -> str:
    lines = ["flowchart TD"]

    # Config nodes
    config_files = [
        ("INTENTS", "intents.yaml"),
        ("CONTEXT", "context_rules.yaml"),
        ("SCORING", "scoring.yaml"),
        ("GATE", "gate.yaml"),
        ("JOBS", "jobs.yaml"),
        ("PROACTIVE", "proactive.yaml"),
        ("PATTERNS", "patterns.yaml"),
        ("VARIANTS", "variants.yaml"),
    ]

    lines.append('    subgraph configs["Config Files"]')
    for cid, cname in config_files:
        lines.append(f'        {cid}["{cname}"]')
        lines.append(f"        style {cid} {STYLE_ROUTE}")
        lines.append(f'        click {cid} "backend/config/{cname}"')
    lines.append("    end")

    # Pipeline nodes
    lines.append('    subgraph pipelines["Pipelines"]')
    for pname in sorted(configs["pipelines"]):
        pid = f"P_{_sanitize_id(pname).upper()}"
        lines.append(f'        {pid}["{pname}"]')
        lines.append(f'        click {pid} "backend/config/pipelines/{pname}.yaml"')
    lines.append("    end")

    # Tool nodes
    tools_used = set()
    for pname, steps in graph["pipeline_steps"].items():
        for step in steps:
            if step.get("tool"):
                tools_used.add(step["tool"])
    lines.append('    subgraph tools["Tools"]')
    for tool in sorted(tools_used):
        tid = f"TOOL_{_sanitize_id(tool).upper()}"
        lines.append(f'        {tid}["{tool}"]')
    lines.append("    end")

    # Job nodes
    lines.append('    subgraph jobs["Background Jobs"]')
    for job in JOB_DB_ACCESS:
        jid = f"JOB_{_sanitize_id(job).upper()}"
        lines.append(f'        {jid}["{job}"]')
    lines.append("    end")

    # Edges: intents → pipelines
    for pname in configs["pipelines"]:
        pid = f"P_{_sanitize_id(pname).upper()}"
        lines.append(f"    INTENTS -->|routes| {pid}")
    lines.append("    CONTEXT -->|loads data| pipelines")

    # Edges: pipelines → tools
    for tool in sorted(graph["tool_to_pipelines"]):
        tid = f"TOOL_{_sanitize_id(tool).upper()}"
        for pname in sorted(set(graph["tool_to_pipelines"][tool])):
            pid = f"P_{_sanitize_id(pname).upper()}"
            lines.append(f"    {pid} --> {tid}")

    # Edges: scoring → tools/jobs
    for section, consumers in SCORING_CONSUMERS.items():
        for tool in consumers["tools"]:
            tid = f"TOOL_{_sanitize_id(tool).upper()}"
            lines.append(f"    SCORING -->|{section}| {tid}")
        for job in consumers["jobs"]:
            jid = f"JOB_{_sanitize_id(job).upper()}"
            lines.append(f"    SCORING -->|{section}| {jid}")

    # Edges: jobs config → jobs
    for job in JOB_DB_ACCESS:
        jid = f"JOB_{_sanitize_id(job).upper()}"
        lines.append(f"    JOBS --> {jid}")

    lines.append("    PATTERNS --> JOB_DETECT_PATTERNS")
    lines.append("    PROACTIVE -->|triggers| pipelines")
    lines.append("    VARIANTS -->|selects variant| pipelines")
    lines.append('    GATE -->|rate limit| GATE_CHECK["rate_limit_check"]')

    return "\n".join(lines)


def gen_impact_matrix_md(matrix: list[dict[str, str]]) -> str:
    lines = [
        "# Impact Matrix",
        "",
        "Auto-generated. Shows what flows and DB tables are affected when you change a file.",
        "",
        "| If you change... | Type | Flows affected | DB tables | Fields |",
        "|---|---|---|---|---|",
    ]
    for row in matrix:
        lines.append(
            f"| `{row['file']}` | {row['type']} | {row['flows']} | {row['tables']} | {row['fields']} |"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output renderers
# ---------------------------------------------------------------------------


def wrap_mermaid_md(title: str, description: str, mermaid: str) -> str:
    return f"# {title}\n\n{description}\n\n```mermaid\n{mermaid}\n```\n"


def write_markdown_files(
    configs: dict,
    graph: dict,
    tables: dict,
    matrix: list[dict[str, str]],
) -> list[Path]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # 1. Message flow
    p = OUT_DIR / "1_message_flow.md"
    p.write_text(
        wrap_mermaid_md(
            "Message Flow — Hot Path",
            "Every user message follows this path. Click nodes to open source files.",
            gen_message_flow(configs, graph),
        )
    )
    written.append(p)

    # 2. Pipeline details
    for pname, pdata in sorted(configs["pipelines"].items()):
        ctx = graph["pipeline_context"].get(pname, {})
        p = OUT_DIR / f"2_pipeline_{pname}.md"
        desc = pdata.get("description", "")
        p.write_text(
            wrap_mermaid_md(
                f"Pipeline: {pname}",
                f"{desc}\n\nGreen = LLM call, Blue = tool call, Orange = async post-processing.",
                gen_pipeline_detail(pname, pdata, ctx),
            )
        )
        written.append(p)

    # 3. Background jobs
    p = OUT_DIR / "3_background_jobs.md"
    p.write_text(
        wrap_mermaid_md(
            "Background Jobs — Cold Path",
            "All jobs triggered by QStash cron or event dispatch.",
            gen_background_jobs(configs),
        )
    )
    written.append(p)

    # 4. Database access
    p = OUT_DIR / "4_database_access.md"
    p.write_text(
        wrap_mermaid_md(
            "Database Access Map",
            "Shows all tables, their columns, and which tools/jobs read/write them.",
            gen_db_access_map(tables, graph, configs),
        )
    )
    written.append(p)

    # 5. Proactive flow
    p = OUT_DIR / "5_proactive_flow.md"
    p.write_text(
        wrap_mermaid_md(
            "Proactive Messages — Presence-Triggered",
            "Evaluated in priority order when user opens the app. First match fires.",
            gen_proactive_flow(configs),
        )
    )
    written.append(p)

    # 6. Config deps
    p = OUT_DIR / "6_config_dependencies.md"
    p.write_text(
        wrap_mermaid_md(
            "Config Dependencies",
            "Shows which config files affect which pipelines, tools, and jobs.",
            gen_config_deps(configs, graph),
        )
    )
    written.append(p)

    # 7. Impact matrix
    p = OUT_DIR / "7_impact_matrix.md"
    p.write_text(gen_impact_matrix_md(matrix))
    written.append(p)

    return written


def write_html_viewer(
    configs: dict,
    graph: dict,
    tables: dict,
    matrix: list[dict[str, str]],
) -> Path:
    """Generate a single self-contained HTML file with all diagrams."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    diagrams: list[dict[str, str]] = []

    # 1. Message flow
    diagrams.append(
        {
            "id": "message-flow",
            "title": "Message Flow",
            "mermaid": gen_message_flow(configs, graph),
        }
    )

    # 2. Pipelines
    for pname in sorted(configs["pipelines"]):
        pdata = configs["pipelines"][pname]
        ctx = graph["pipeline_context"].get(pname, {})
        diagrams.append(
            {
                "id": f"pipeline-{pname}",
                "title": f"Pipeline: {pname}",
                "mermaid": gen_pipeline_detail(pname, pdata, ctx),
            }
        )

    # 3. Background jobs
    diagrams.append(
        {
            "id": "background-jobs",
            "title": "Background Jobs",
            "mermaid": gen_background_jobs(configs),
        }
    )

    # 4. DB access
    diagrams.append(
        {
            "id": "database",
            "title": "Database Access",
            "mermaid": gen_db_access_map(tables, graph, configs),
        }
    )

    # 5. Proactive
    diagrams.append(
        {
            "id": "proactive",
            "title": "Proactive Messages",
            "mermaid": gen_proactive_flow(configs),
        }
    )

    # 6. Config deps
    diagrams.append(
        {
            "id": "config-deps",
            "title": "Config Dependencies",
            "mermaid": gen_config_deps(configs, graph),
        }
    )

    # Build tab buttons and content
    tab_buttons = []
    tab_contents = []
    for i, d in enumerate(diagrams):
        active = " active" if i == 0 else ""
        tab_buttons.append(
            f'<button class="tab-btn{active}" data-tab="{d["id"]}">{d["title"]}</button>'
        )
        display = "block" if i == 0 else "none"
        tab_contents.append(
            f'<div class="tab-content" id="{d["id"]}" style="display:{display}">'
            f'<pre class="mermaid">\n{d["mermaid"]}\n</pre></div>'
        )

    # Impact matrix tab
    tab_buttons.append(
        '<button class="tab-btn" data-tab="impact-matrix">Impact Matrix</button>'
    )
    impact_rows = ""
    for row in matrix:
        impact_rows += (
            f"<tr><td><code>{row['file']}</code></td><td>{row['type']}</td>"
            f"<td>{row['flows']}</td><td>{row['tables']}</td><td>{row['fields']}</td></tr>\n"
        )
    tab_contents.append(
        f"""<div class="tab-content" id="impact-matrix" style="display:none">
<input type="text" id="matrix-search" placeholder="Filter by file name..." />
<table id="matrix-table">
<thead><tr><th>If you change...</th><th>Type</th><th>Flows affected</th><th>DB tables</th><th>Fields</th></tr></thead>
<tbody>{impact_rows}</tbody>
</table></div>"""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Unspool — System Flow Visualization</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #0D0D0F; color: #e0e0e0;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    padding: 20px;
  }}
  h1 {{ font-size: 1.4rem; margin-bottom: 16px; color: #5dcaa5; }}
  .tab-bar {{
    display: flex; flex-wrap: wrap; gap: 4px;
    margin-bottom: 20px; border-bottom: 1px solid #333;
    padding-bottom: 8px;
  }}
  .tab-btn {{
    background: #1a1a1f; color: #aaa; border: 1px solid #333;
    padding: 8px 16px; cursor: pointer; border-radius: 6px 6px 0 0;
    font-size: 0.85rem; transition: all 0.2s;
  }}
  .tab-btn:hover {{ background: #252530; color: #e0e0e0; }}
  .tab-btn.active {{ background: #2d5a3d; color: #fff; border-color: #5dcaa5; }}
  .tab-content {{ min-height: 400px; }}
  .mermaid {{ background: transparent !important; }}
  /* Impact matrix */
  #matrix-search {{
    width: 100%; max-width: 400px; padding: 8px 12px;
    background: #1a1a1f; color: #e0e0e0; border: 1px solid #333;
    border-radius: 6px; margin-bottom: 12px; font-size: 0.9rem;
  }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.85rem; }}
  th {{ background: #1a1a1f; color: #5dcaa5; text-align: left; padding: 10px; border-bottom: 2px solid #333; }}
  td {{ padding: 8px 10px; border-bottom: 1px solid #222; }}
  tr:hover {{ background: #1a1a1f; }}
  code {{ color: #cc8855; font-size: 0.85rem; }}
  .footer {{ margin-top: 40px; color: #555; font-size: 0.8rem; text-align: center; }}
</style>
</head>
<body>
<h1>unspool — system flow visualization</h1>
<div class="tab-bar">
{"".join(tab_buttons)}
</div>
{"".join(tab_contents)}
<div class="footer">
Auto-generated from config files. Run <code>python tools/generate_flows.py</code> to regenerate.
</div>

<script type="module">
import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
mermaid.initialize({{
  startOnLoad: true,
  theme: 'dark',
  securityLevel: 'loose',
  flowchart: {{ htmlLabels: true, curve: 'basis' }},
  themeVariables: {{
    primaryColor: '#2d5a3d',
    primaryTextColor: '#e0e0e0',
    primaryBorderColor: '#5dcaa5',
    lineColor: '#555',
    secondaryColor: '#2d3d5a',
    tertiaryColor: '#1a1a1f',
    background: '#0D0D0F',
    mainBkg: '#1a1a1f',
    nodeBorder: '#555',
    clusterBkg: '#111115',
    clusterBorder: '#333',
    titleColor: '#e0e0e0',
    edgeLabelBackground: '#0D0D0F',
  }}
}});

// Tab switching
document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
    btn.classList.add('active');
    const tab = document.getElementById(btn.dataset.tab);
    tab.style.display = 'block';
    // Re-render mermaid for newly visible tabs
    const pre = tab.querySelector('.mermaid');
    if (pre && !pre.dataset.processed) {{
      pre.dataset.processed = 'true';
      mermaid.run({{ nodes: [pre] }});
    }}
  }});
}});

// Impact matrix filter
const search = document.getElementById('matrix-search');
if (search) {{
  search.addEventListener('input', () => {{
    const q = search.value.toLowerCase();
    document.querySelectorAll('#matrix-table tbody tr').forEach(row => {{
      row.style.display = row.textContent.toLowerCase().includes(q) ? '' : 'none';
    }});
  }});
}}
</script>
</body>
</html>"""

    out_path = OUT_DIR / "index.html"
    out_path.write_text(html)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def compute_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def main() -> None:
    global OUT_DIR  # noqa: PLW0603

    parser = argparse.ArgumentParser(description="Generate Unspool flow diagrams")
    parser.add_argument(
        "--check", action="store_true", help="Fail if output differs from committed"
    )
    parser.add_argument(
        "--only",
        choices=[
            "message-flow",
            "pipelines",
            "jobs",
            "database",
            "proactive",
            "config-deps",
            "impact",
        ],
        help="Generate only one diagram type",
    )
    args = parser.parse_args()

    configs = load_all_configs()
    tables = parse_table_schemas()
    graph = build_dependency_graph(configs)
    matrix = build_impact_matrix(configs, graph)

    if args.check:
        import tempfile

        # Capture hashes of committed files
        old_hashes: dict[str, str] = {}
        if OUT_DIR.exists():
            for f in OUT_DIR.iterdir():
                if f.suffix == ".md":
                    old_hashes[f.name] = compute_hash(f)

        # Generate to temp dir and compare
        saved_out = OUT_DIR
        with tempfile.TemporaryDirectory() as tmpdir:
            OUT_DIR = Path(tmpdir)

            written = write_markdown_files(configs, graph, tables, matrix)

            new_hashes = {f.name: compute_hash(f) for f in written}
        OUT_DIR = saved_out

        if old_hashes != new_hashes:
            changed = [k for k in new_hashes if old_hashes.get(k) != new_hashes[k]]
            print(f"Flow diagrams are stale. Changed: {', '.join(changed)}")
            print("Run: python tools/generate_flows.py")
            sys.exit(1)
        else:
            print("Flow diagrams are up to date.")
            sys.exit(0)

    written = write_markdown_files(configs, graph, tables, matrix)

    print(f"Generated {len(written)} files in {OUT_DIR}/")
    for f in written:
        print(f"  {f.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
