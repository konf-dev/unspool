# Unspool Architecture Dashboard

Interactive visualization of Unspool's system architecture — pipelines, database access, config dependencies, impact analysis.

## Install

```bash
pip install -r viz/requirements.txt
```

## Run

```bash
streamlit run viz/app.py
```

Opens at http://localhost:8501

## Views

- **Message Flow** — Hot path from user message through pipeline execution to response
- **Pipelines** — Per-pipeline step sequences with context, prompts, tools, DB access
- **Background Jobs** — Cron-scheduled and event-triggered jobs with DB access
- **Database** — Schema browser + access map showing who reads/writes each table
- **Proactive Messages** — Priority-ordered trigger chain
- **Config Dependencies** — How config files connect to pipelines, tools, and jobs
- **Impact Matrix** — Searchable table: "if I change X, what breaks?"

## How it works

Reads all YAML configs and SQL migrations from `backend/`, builds a dependency graph, and renders interactive Mermaid diagrams with zoom/pan controls. Click any referenced file to view its content inline.
