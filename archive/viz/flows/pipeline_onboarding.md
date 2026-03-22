# Pipeline: onboarding

First message from new user

```mermaid
flowchart LR
    subgraph ctx["Context Loaded"]
        direction TB
        C0["profile"]
    end
    ctx --> RESPOND
    RESPOND["🤖\nrespond\nLLM: onboarding_respond.md\n🔴 STREAM"]
    style RESPOND fill:#2d5a3d,stroke:#5dcaa5,color:#e0e0e0
    click RESPOND "backend/prompts/onboarding_respond.md"
```
