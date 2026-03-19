# MCP Evaluation for Unspool (March 2026)

## Decision: Do not adopt MCP

## What is MCP?
Model Context Protocol — an open standard by Anthropic for connecting LLMs to external tools. Now supported by OpenAI, Google, Microsoft. 22k+ GitHub stars on the Python SDK. Dominant in developer tools (Claude Desktop, Cursor, VS Code).

## Why not for Unspool?

1. **Wrong problem.** MCP connects *external* tools to AI apps you don't control. Unspool IS the AI app. Our tools are internal.
2. **Performance penalty.** MCP requires separate processes (stdio/HTTP). Our tools are direct async function calls — zero overhead.
3. **No ecosystem benefit.** 10k+ MCP servers exist, none match our domain-specific tools (pick_next, fuzzy_match_item, enrich_items, graph retrieval).
4. **State management friction.** Our tools mutate AgentState (should_ingest, saved_items flags). MCP tools are stateless RPC.
5. **Consumer products don't use MCP.** Zero documented adoption by consumer chat products. MCP is a developer-tool protocol.

## What about pre-built tool libraries?

| Option | Stars | Verdict |
|--------|-------|---------|
| Mem0 (memory) | 50k | Vector-only, no graph. Our custom graph is better aligned. |
| Letta/MemGPT | 22k | Heavy framework dependency. Overkill. |
| LangChain tools | 103k | Framework-coupled. Their own CEO says tool adoption is limited. |
| Composio | N/A | Good for calendar OAuth if we add write. Not needed now. |
| Tavily (web search) | N/A | Consider later if web search needed. $0.01/search. |

## Our current approach is correct
- 11 tools in tools.py with JSON schemas + async handlers + dispatch dict
- Direct function calls = zero overhead, max debuggability
- Exactly what Anthropic recommends in "Building Effective Agents"
- Well within LLM tool selection capability (<20 tools)

## When to revisit
- Exposing tools to external AI apps (letting Claude Desktop access Unspool data)
- Tool count grows past 30-40 (need dynamic filtering)
- Adding third-party integrations with existing MCP servers
- Multi-agent architecture where agents share tool access
