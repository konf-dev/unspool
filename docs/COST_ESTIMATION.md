# Unspool Cost Estimation & Scaling Projections

## Usage Assumptions Per User Tier

| Metric | Per active user/day |
|--------|-------------------|
| Chat messages | 10 (avg 150 input tokens + 100 output tokens each) |
| Tool calls per chat | 1.5 avg (query_graph + occasional mutate_graph) |
| Cold path extractions | 5 (each chat with actionable content → ~500 input + 200 output tokens) |
| Embedding calls | 15 (context assembly ~5, cold path dedup ~10, each ~50 tokens) |
| Proactive messages | 1 (~200 input + 100 output tokens) |
| Background jobs | 3 (hourly maintenance, nightly batch, synthesis) |

---

## Per-User Token Consumption (Monthly, 30 days)

| Pipeline | Input tokens/mo | Output tokens/mo |
|----------|----------------|-----------------|
| Hot path chat (10 msgs × 30d) | 450K | 300K |
| Tool calls (15/day × 30d) | 225K | 150K |
| Cold path extraction (5/day × 30d) | 750K | 300K |
| Proactive (1/day × 30d) | 180K | 90K |
| Background jobs | 100K | 50K |
| **Chat subtotal** | **1.7M** | **890K** |
| Embeddings (15/day × 30d × 50 tok) | 22.5K | — |

---

## Cost at Scale — Gemini 2.5 Flash

### Token costs (paid tier, per 1M tokens)

| | Standard | With context caching (90% off input) |
|---|---------|-------------------------------------|
| Input | $0.30 | $0.03 |
| Output | $2.50 | $2.50 |
| Embedding (gemini-embedding-001) | $0.15 | N/A |

### LLM cost per user per month

| Users | Input tokens | Output tokens | Embedding tokens | Monthly LLM cost | With caching |
|-------|-------------|---------------|-----------------|------------------|-------------|
| 1 | 1.7M | 890K | 22.5K | $2.74 | $0.28 input + $2.23 output = **$2.51** |
| 5 | 8.5M | 4.5M | 112K | **$13.77** | **$12.52** |
| 25 | 42.5M | 22.3M | 562K | **$68.50** | **$62.33** |
| 100 | 170M | 89M | 2.25M | **$273.84** | **$249.14** |
| 500 | 850M | 445M | 11.25M | **$1,369** | **$1,246** |

*Context caching saves ~10% overall because output tokens (the bulk of cost) aren't cached.*

---

## Full Infrastructure Cost at Each Scale

### 5 Users (MVP / Free + Hobby tiers)

| Service | Tier | Monthly Cost | Notes |
|---------|------|-------------|-------|
| **Gemini API** | Free → Tier 1 | $0 – $14 | Free tier works at 5 users if <10 RPM ok; Tier 1 needs billing |
| **Supabase** | Free | $0 | 500 MB DB, 50K auth MAU — plenty |
| **Railway** | Hobby | $5 | $5 credit included, single container ~$3-4/mo actual |
| **Vercel** | Hobby (free) | $0 | Static PWA, well under limits |
| **Upstash Redis** | Free | $0 | <500K commands/mo at 5 users |
| **Upstash QStash** | Free | $0 | <1K messages/day |
| **Langfuse** | Hobby (free) | $0 | ~5K observations/mo (well under 50K) |
| **Domain** | — | $1.50 | unspool.life annual / 12 |
| **Stripe** | — | $0 | No payments yet |
| **Total** | | **$6.50 – $20.50/mo** | |

### 25 Users (Early traction)

| Service | Tier | Monthly Cost | Notes |
|---------|------|-------------|-------|
| **Gemini API** | Tier 1 | $62 – $69 | With/without caching |
| **Supabase** | Free | $0 | Still under limits |
| **Railway** | Hobby | $5 | May need ~0.5 vCPU, 512MB — within $5 credit |
| **Vercel** | Hobby (free) | $0 | |
| **Upstash Redis** | Free | $0 | ~2M commands/mo — may hit free limit, ~$4 overage |
| **Upstash QStash** | Free | $0 | ~2K messages/day — within 1K free? May need PAYG ~$1 |
| **Langfuse** | Free → Core | $0 – $29 | ~25K obs/mo — free tier ok, Core for comfort |
| **Domain** | — | $1.50 | |
| **Stripe** | — | ~$7 | If 25 users × $5/mo sub = $125 revenue, 2.9%+$0.30 × 25 |
| **Total** | | **$69 – $112/mo** | |
| **Revenue** (if $5/mo sub) | | **$125/mo** | Marginally profitable |

### 100 Users (Product-market fit)

| Service | Tier | Monthly Cost | Notes |
|---------|------|-------------|-------|
| **Gemini API** | Tier 1 | $249 – $274 | |
| **Supabase** | Pro | $25 | 8 GB DB, 100K MAU |
| **Railway** | Pro | $20 | Need ~1 vCPU, 1 GB — $20 credit covers it |
| **Vercel** | Pro | $20 | |
| **Upstash Redis** | PAYG | $8 | ~10M commands/mo |
| **Upstash QStash** | PAYG | $3 | ~10K messages/day |
| **Langfuse** | Core | $29 | ~100K obs/mo — included |
| **Domain** | — | $1.50 | |
| **Stripe** | — | ~$22 | $500 revenue × ~4.4% |
| **Total** | | **$377 – $402/mo** | |
| **Revenue** (if $5/mo sub) | | **$500/mo** | Profitable |

### 500 Users (Growth)

| Service | Tier | Monthly Cost | Notes |
|---------|------|-------------|-------|
| **Gemini API** | Tier 2 | $1,246 – $1,369 | Volume pricing may apply |
| **Supabase** | Pro | $25 + ~$10 overage | ~2 GB DB |
| **Railway** | Pro | $20 + ~$30 compute | 2 vCPU, 2 GB RAM |
| **Vercel** | Pro | $20 | |
| **Upstash Redis** | PAYG | $30 | ~50M commands/mo |
| **Upstash QStash** | PAYG | $15 | ~50K messages/day |
| **Langfuse** | Core | $29 + ~$32 overage | ~500K obs/mo |
| **Domain** | — | $1.50 | |
| **Stripe** | — | ~$110 | $2,500 revenue × ~4.4% |
| **Total** | | **$1,538 – $1,661/mo** | |
| **Revenue** (if $5/mo sub) | | **$2,500/mo** | ~$900 margin |

---

## Cost Optimization Levers

| Lever | Savings | When to use |
|-------|---------|-------------|
| **Context caching** | ~10% on Gemini | From day 1 — cache system prompt + tools |
| **Batch API for cold path** | 50% off cold path tokens | When cold path isn't time-sensitive |
| **Smaller model for proactive** | 30-40% | Use `gemini-2.5-flash-lite` when available |
| **Embedding dedup** | Reduce embedding calls | Cache embeddings for repeated/similar queries |
| **Switch to open-source** | 70-90% off LLM | At scale, self-host Llama on GPU (Railway or dedicated) |
| **Negotiate Gemini pricing** | ~30% at scale | At Tier 2+ ($250 cumulative spend) |

---

## Break-Even Analysis

| Subscription price | Break-even users (monthly cost = revenue) |
|--------------------|------------------------------------------|
| $3/mo | ~150 users |
| $5/mo | ~80 users |
| $8/mo | ~50 users |
| $10/mo | ~40 users |

*Based on 100-user cost profile (~$400/mo infrastructure).*

---

## Quality Guardrails (Non-Negotiable)

These must NOT be compromised for cost savings:

| Metric | Minimum Standard | How we measure |
|--------|-----------------|----------------|
| Response latency (p50) | < 3 seconds | Langfuse trace timing |
| Response quality (relevance) | > 0.8 avg | Langfuse LLM-as-judge eval |
| Tone accuracy | > 0.85 avg | No cheerleading, matches user energy |
| Extraction accuracy | > 0.9 avg | Correct nodes/edges from brain dumps |
| Tool call reliability | > 95% | Correct tool selection + valid args |
| Uptime | > 99.5% | Smoke test + Railway health checks |
| Embedding recall@10 | > 0.85 | Semantic search returns relevant nodes |

If any metric drops below threshold after a cost optimization change, revert immediately.

---

## Service Tier Upgrade Triggers

| Service | Upgrade when | From → To | Cost increase |
|---------|-------------|-----------|--------------|
| Gemini | Free tier rate limits hit (>10 RPM) | Free → Tier 1 | $0 → usage-based |
| Supabase | DB > 400 MB or need no-pause | Free → Pro | $0 → $25/mo |
| Railway | Compute > $5/mo | Hobby → Pro | $5 → $20/mo |
| Vercel | Need team features or >100GB BW | Hobby → Pro | $0 → $20/mo |
| Langfuse | >40K observations/mo | Hobby → Core | $0 → $29/mo |
| Redis | >400K commands/mo | Free → PAYG | $0 → ~$2-5/mo |
| QStash | >800 messages/day | Free → PAYG | $0 → ~$1/mo |
